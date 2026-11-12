import json
import logging
import uuid

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db import IntegrityError, transaction
from django.http import HttpResponseBadRequest
from django.shortcuts import get_object_or_404, render
from django.views import View
from django.views.decorators.http import require_POST
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from .idcards import card_pdf_response
from .models import Member, SyncLog
from .permissions import CanRegisterMembers, IsCoordinatorOrExec, members_visible_to
from .serializers import MemberSerializer, MemberSyncSerializer, SyncLogSerializer
from .utils import PhotoError, clean_member_photo

log = logging.getLogger(__name__)
CFG = settings.MEMBER_SYNC


# ---------------------------------------------------------------------------
# Batch sync (field agent PWA)
# ---------------------------------------------------------------------------

class BatchSyncView(APIView):
    """
    POST multipart/form-data
        records   = JSON array of member objects (each with client UUID `id`)
        photo_<id> = compressed image Blob for that record (optional)

    Always answers 200 with a per-record result so one bad record never blocks
    the rest of the batch:
        created          -> stored
        already_synced   -> UUID already on server (a retry after a lost reply)
        flagged          -> stored, but marked as a possible duplicate for review
        rejected         -> validation failed; agent must fix and resend

    The client may delete its local copy for every status except `rejected`.
    """
    permission_classes = [CanRegisterMembers]
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request):
        try:
            records = json.loads(request.data.get("records", "[]"))
        except (TypeError, json.JSONDecodeError):
            return Response({"detail": "`records` must be a JSON array."}, status=status.HTTP_400_BAD_REQUEST)
        if not isinstance(records, list) or not records:
            return Response({"detail": "No records supplied."}, status=status.HTTP_400_BAD_REQUEST)
        if len(records) > CFG["MAX_RECORDS_PER_BATCH"]:
            return Response(
                {"detail": f"Max {CFG['MAX_RECORDS_PER_BATCH']} records per batch."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        results = [self._process(request, rec) for rec in records]

        counts = {k: 0 for k in ("created", "already_synced", "flagged", "rejected")}
        for r in results:
            counts[r["status"]] += 1
        SyncLog.objects.create(
            agent=request.user,
            records_received=len(records),
            client_info=request.headers.get("User-Agent", "")[:200],
            **counts,
        )
        return Response({"results": results, "summary": counts})

    # -- one record --------------------------------------------------------

    def _process(self, request, rec):
        raw_id = rec.get("id") if isinstance(rec, dict) else None
        try:
            member_id = uuid.UUID(str(raw_id))
        except (ValueError, TypeError):
            return {"id": raw_id, "status": "rejected", "errors": {"id": ["Missing or invalid UUID."]}}

        # Idempotency: the reply to an earlier upload may have been lost.
        existing = Member.objects.filter(pk=member_id).only("membership_number").first()
        if existing:
            return {"id": str(member_id), "status": "already_synced"}

        ser = MemberSyncSerializer(data=rec, context={"request": request})
        if not ser.is_valid():
            return {"id": str(member_id), "status": "rejected", "errors": ser.errors}
        data = ser.validated_data

        photo = None
        upload = request.FILES.get(f"photo_{member_id}")
        if upload:
            try:
                photo = clean_member_photo(
                    upload, max_bytes=CFG["MAX_PHOTO_BYTES"], size_px=CFG["PHOTO_SIZE_PX"]
                )
            except PhotoError as e:
                return {"id": str(member_id), "status": "rejected", "errors": {"photo": [str(e)]}}

        flag, dup = find_duplicate(data)
        try:
            self._create(request, data, photo, flag, dup)
        except IntegrityError:
            # Lost a race: same UUID or same NID arrived concurrently.
            if Member.objects.filter(pk=member_id).exists():
                return {"id": str(member_id), "status": "already_synced"}
            flag, dup = find_duplicate(data)
            if not dup:
                log.exception("Unexpected integrity error syncing %s", member_id)
                return {"id": str(member_id), "status": "rejected", "errors": {"non_field_errors": ["Server conflict, retry."]}}
            try:
                self._create(request, data, photo, flag, dup)
            except IntegrityError:
                log.exception("Second integrity error syncing %s", member_id)
                return {"id": str(member_id), "status": "rejected", "errors": {"non_field_errors": ["Server conflict, retry."]}}

        result = {"id": str(member_id), "status": "flagged" if flag else "created"}
        if flag:
            result["flag"] = flag
            result["message"] = Member.ReviewFlag(flag).label
        return result

    @staticmethod
    def _create(request, data, photo, flag, dup):
        with transaction.atomic():
            member = Member(
                id=data["id"],
                full_name=data["full_name"],
                nid_number=data["nid_number"],
                phone_number=data["phone_number"],
                gender=data["gender"],
                date_of_birth=data["date_of_birth"],
                electorate=data["electorate"],
                llg_ward=data["llg_ward"],
                village_or_street=data["village_or_street"],
                client_created_at=data["client_created_at"],
                registered_by=request.user,
                source=Member.Source.FIELD,
                review_flag=flag,
                duplicate_of=dup if flag in (Member.ReviewFlag.DUPLICATE_NID,
                                             Member.ReviewFlag.DUPLICATE_NAME_PHONE) else None,
            )
            member.save(force_insert=True)
            if photo:
                member.photo.save(photo.name, photo, save=True)
        return member


def find_duplicate(data):
    """
    Returns (review_flag, existing_member). Order matters:
      1. Same NID           -> hard duplicate (kept, linked, needs review)
      2. Same name + phone  -> hard duplicate
      3. Same phone only    -> soft flag; families in PNG often share one phone
    """
    live = Member.objects.filter(duplicate_of__isnull=True)
    if data["nid_number"]:
        m = live.filter(nid_number=data["nid_number"]).first()
        if m:
            return Member.ReviewFlag.DUPLICATE_NID, m
    if data["phone_number"]:
        same_phone = live.filter(phone_number=data["phone_number"])
        m = same_phone.filter(full_name__iexact=data["full_name"]).first()
        if m:
            return Member.ReviewFlag.DUPLICATE_NAME_PHONE, m
        m = same_phone.first()
        if m:
            return Member.ReviewFlag.SHARED_PHONE, m
    return Member.ReviewFlag.NONE, None


class SyncHistoryView(APIView):
    permission_classes = [CanRegisterMembers]

    def get(self, request):
        logs = SyncLog.objects.filter(agent=request.user)[:50]
        total = Member.objects.filter(registered_by=request.user).count()
        return Response({"total_registered": total, "batches": SyncLogSerializer(logs, many=True).data})


# ---------------------------------------------------------------------------
# Coordinator / executive API
# ---------------------------------------------------------------------------

class MemberViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin,
                    mixins.UpdateModelMixin, viewsets.GenericViewSet):
    serializer_class = MemberSerializer
    permission_classes = [IsCoordinatorOrExec]

    def get_queryset(self):
        qs = members_visible_to(self.request.user)
        p = self.request.query_params
        if p.get("electorate"):
            qs = qs.filter(electorate_id=p["electorate"])
        if p.get("verified") in ("0", "1"):
            qs = qs.filter(is_verified=p["verified"] == "1")
        if p.get("flagged") == "1":
            qs = qs.exclude(review_flag="")
        if p.get("q"):
            qs = qs.filter(full_name__icontains=p["q"])
        return qs

    @action(detail=True, methods=["post"])
    def verify(self, request, pk=None):
        member = self.get_object()
        try:
            number = member.verify(request.user)
        except ValueError as e:
            return Response({"detail": str(e)}, status=status.HTTP_409_CONFLICT)
        return Response({"membership_number": number})

    @action(detail=True, methods=["post"], url_path="clear-flag")
    def clear_flag(self, request, pk=None):
        """Coordinator confirms a flagged record is a different person."""
        member = self.get_object()
        member.review_flag = ""
        member.duplicate_of = None
        try:
            member.save(update_fields=["review_flag", "duplicate_of", "updated_at"])
        except IntegrityError:
            return Response(
                {"detail": "Another live member holds this NID. Correct the NID first."},
                status=status.HTTP_409_CONFLICT,
            )
        return Response({"ok": True})


# ---------------------------------------------------------------------------
# ID cards (portal, session auth)
# ---------------------------------------------------------------------------

def _require_card_rights(user):
    if not (user.is_exec or user.is_coordinator):
        raise PermissionDenied


@login_required
def single_card_pdf(request, member_id):
    _require_card_rights(request.user)
    member = get_object_or_404(members_visible_to(request.user), pk=member_id, is_verified=True)
    return card_pdf_response([member], layout="single", filename=f"{member.membership_number}.pdf")


@login_required
@require_POST
def batch_cards_pdf(request):
    """
    POST ids=<uuid>&ids=<uuid>...   or   unprinted=1[&electorate=<id>]
         per_page=8|10 (default 10)
    """
    _require_card_rights(request.user)
    qs = members_visible_to(request.user).filter(is_verified=True)
    ids = request.POST.getlist("ids")
    if ids:
        qs = qs.filter(pk__in=ids)
    elif request.POST.get("unprinted") == "1":
        qs = qs.filter(id_card_printed=False)
        if request.POST.get("electorate"):
            qs = qs.filter(electorate_id=request.POST["electorate"])
    else:
        return HttpResponseBadRequest("Pass ids or unprinted=1")

    members = list(qs.order_by("electorate__name", "full_name")[:400])
    if not members:
        return HttpResponseBadRequest("No verified members match.")
    per_page = 8 if request.POST.get("per_page") == "8" else 10
    return card_pdf_response(members, layout="batch", per_page=per_page, filename="member-cards.pdf")


# ---------------------------------------------------------------------------
# Public QR verification
# ---------------------------------------------------------------------------

class VerifyMemberView(View):
    """
    Target of the card QR code. Shows only what an official needs to confirm
    the card: never NID, phone, DOB or village.
    """

    def get(self, request, member_id):
        member = (Member.objects.select_related("electorate__province")
                  .filter(pk=member_id).first())
        valid = bool(member and member.is_verified and not member.duplicate_of_id)
        return render(request, "members/verify.html", {"member": member, "valid": valid}, status=200)
