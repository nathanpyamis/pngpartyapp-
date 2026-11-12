from datetime import date, timedelta

from django.utils import timezone
from rest_framework import serializers

from apps.geo.models import Electorate

from .models import Member, SyncLog
from .permissions import can_register_in
from .utils import normalize_name, normalize_nid, normalize_png_phone

MIN_MEMBER_AGE = 18


class MemberSyncSerializer(serializers.Serializer):
    """
    One offline record from the PWA outbox. The photo arrives separately as
    multipart file `photo_<id>` and is handled by the view.
    """
    id = serializers.UUIDField()
    full_name = serializers.CharField(max_length=150)
    nid_number = serializers.CharField(max_length=30, required=False, allow_blank=True, default="")
    phone_number = serializers.CharField(max_length=20, required=False, allow_blank=True, default="")
    gender = serializers.ChoiceField(choices=Member.Gender.choices)
    date_of_birth = serializers.DateField(required=False, allow_null=True, default=None)
    electorate = serializers.PrimaryKeyRelatedField(queryset=Electorate.objects.select_related("province"))
    llg_ward = serializers.CharField(max_length=120, required=False, allow_blank=True, default="")
    village_or_street = serializers.CharField(max_length=150, required=False, allow_blank=True, default="")
    client_created_at = serializers.DateTimeField()

    def validate_full_name(self, v):
        v = normalize_name(v)
        if len(v) < 3:
            raise serializers.ValidationError("Name too short.")
        return v

    def validate_nid_number(self, v):
        return normalize_nid(v)

    def validate_phone_number(self, v):
        v = normalize_png_phone(v)
        if v and len(v) not in (7, 8):  # landline 7 digits, mobile 8
            raise serializers.ValidationError("Not a valid PNG phone number.")
        return v

    def validate_date_of_birth(self, v):
        if v is None:
            return v
        today = date.today()
        age = today.year - v.year - ((today.month, today.day) < (v.month, v.day))
        if age < MIN_MEMBER_AGE:
            raise serializers.ValidationError(f"Members must be at least {MIN_MEMBER_AGE}.")
        if age > 120:
            raise serializers.ValidationError("Check the date of birth.")
        return v

    def validate_client_created_at(self, v):
        # Phones in the field often have wrong clocks; never accept the future.
        now = timezone.now()
        return min(v, now + timedelta(minutes=5))

    def validate_electorate(self, electorate):
        user = self.context["request"].user
        if not can_register_in(user, electorate):
            raise serializers.ValidationError("You are not assigned to this electorate.")
        return electorate


class MemberSerializer(serializers.ModelSerializer):
    """Read/edit serializer for coordinators and executives."""
    electorate_name = serializers.CharField(source="electorate.name", read_only=True)
    province_name = serializers.CharField(source="electorate.province.name", read_only=True)
    registered_by_name = serializers.CharField(source="registered_by.get_full_name", read_only=True, default="")

    class Meta:
        model = Member
        fields = [
            "id", "membership_number", "full_name", "nid_number", "phone_number", "gender",
            "date_of_birth", "photo", "electorate", "electorate_name", "province_name",
            "llg_ward", "village_or_street", "source", "registered_by_name",
            "is_verified", "verified_at", "review_flag", "duplicate_of",
            "id_card_printed", "id_card_printed_at", "client_created_at", "server_synced_at",
        ]
        read_only_fields = [
            "id", "membership_number", "source", "is_verified", "verified_at",
            "id_card_printed", "id_card_printed_at", "client_created_at", "server_synced_at",
        ]


class SyncLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = SyncLog
        fields = ["received_at", "records_received", "created", "already_synced", "flagged", "rejected"]
