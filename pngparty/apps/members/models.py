import secrets
import uuid

from django.conf import settings
from django.db import IntegrityError, models, transaction
from django.db.models import Q
from django.utils import timezone


def member_photo_path(instance, filename):
    # Name by UUID, never by client filename; one photo per member.
    now = timezone.now()
    return f"members/{now:%Y/%m}/{instance.pk}.jpg"


class Member(models.Model):
    class Gender(models.TextChoices):
        MALE = "M", "Male"
        FEMALE = "F", "Female"

    class Source(models.TextChoices):
        FIELD = "FIELD", "Field agent"
        ONLINE = "ONLINE", "Online self-registration"
        ADMIN = "ADMIN", "Entered by staff"

    class ReviewFlag(models.TextChoices):
        NONE = "", "—"
        DUPLICATE_NID = "DUP_NID", "Same NID as an existing member"
        DUPLICATE_NAME_PHONE = "DUP_NAME_PHONE", "Same name and phone as an existing member"
        SHARED_PHONE = "SHARED_PHONE", "Phone already used by another member"

    # Client-generated UUIDv4 -> the idempotency key for offline sync
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    membership_number = models.CharField(max_length=20, unique=True, null=True, blank=True)

    full_name = models.CharField(max_length=150)
    nid_number = models.CharField("NID number", max_length=30, blank=True, db_index=True)
    phone_number = models.CharField(max_length=20, blank=True, db_index=True)
    gender = models.CharField(max_length=1, choices=Gender.choices)
    date_of_birth = models.DateField(null=True, blank=True)
    photo = models.ImageField(upload_to=member_photo_path, blank=True)

    electorate = models.ForeignKey("geo.Electorate", on_delete=models.PROTECT, related_name="members")
    llg_ward = models.CharField("LLG / Ward", max_length=120, blank=True)
    village_or_street = models.CharField(max_length=150, blank=True)

    source = models.CharField(max_length=6, choices=Source.choices, default=Source.FIELD)
    registered_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="registered_members",
    )

    # Verification workflow
    is_verified = models.BooleanField(default=False, db_index=True)
    verified_at = models.DateTimeField(null=True, blank=True)
    verified_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="verified_members",
    )
    review_flag = models.CharField(max_length=16, choices=ReviewFlag.choices, blank=True, default="")
    duplicate_of = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.SET_NULL, related_name="possible_duplicates"
    )

    # ID card
    id_card_printed = models.BooleanField(default=False)
    id_card_printed_at = models.DateTimeField(null=True, blank=True)

    # Timestamps
    client_created_at = models.DateTimeField(null=True, blank=True)
    server_synced_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-server_synced_at"]
        indexes = [
            models.Index(fields=["electorate", "is_verified"]),
            models.Index(fields=["review_flag"]),
        ]
        constraints = [
            # One live record per NID. Flagged duplicates (duplicate_of set) are
            # kept for coordinator review instead of being rejected, so no field
            # agent's work is ever lost.
            models.UniqueConstraint(
                fields=["nid_number"],
                condition=~Q(nid_number="") & Q(duplicate_of__isnull=True),
                name="uniq_live_nid",
            ),
        ]

    def __str__(self):
        return f"{self.full_name} ({self.membership_number or 'unverified'})"

    @property
    def province(self):
        return self.electorate.province

    # ---- Workflow ----------------------------------------------------------

    def verify(self, user):
        """Approve the member and allot a membership number (PNGP-MOR-A1B2C3)."""
        if self.duplicate_of_id:
            raise ValueError("Resolve the duplicate flag before verifying.")
        code = self.electorate.province.code.upper()
        for _ in range(10):
            candidate = f"PNGP-{code}-{secrets.token_hex(3).upper()}"
            try:
                with transaction.atomic():
                    self.membership_number = self.membership_number or candidate
                    self.is_verified = True
                    self.verified_at = timezone.now()
                    self.verified_by = user
                    self.save(update_fields=[
                        "membership_number", "is_verified", "verified_at", "verified_by", "updated_at",
                    ])
                return self.membership_number
            except IntegrityError:
                self.membership_number = None  # collision: 16.7M space, retry
        raise RuntimeError("Could not allocate a unique membership number")

    def mark_card_printed(self):
        self.id_card_printed = True
        self.id_card_printed_at = timezone.now()
        self.save(update_fields=["id_card_printed", "id_card_printed_at", "updated_at"])


class SyncLog(models.Model):
    """One row per batch an agent uploads -> 'view their own sync history'."""
    agent = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="sync_logs")
    received_at = models.DateTimeField(auto_now_add=True)
    records_received = models.PositiveSmallIntegerField(default=0)
    created = models.PositiveSmallIntegerField(default=0)
    already_synced = models.PositiveSmallIntegerField(default=0)
    flagged = models.PositiveSmallIntegerField(default=0)
    rejected = models.PositiveSmallIntegerField(default=0)
    client_info = models.CharField(max_length=200, blank=True)

    class Meta:
        ordering = ["-received_at"]
