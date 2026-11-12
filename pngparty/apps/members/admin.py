from django.contrib import admin, messages

from .idcards import card_pdf_response
from .models import Member, SyncLog
from .permissions import members_visible_to


@admin.register(Member)
class MemberAdmin(admin.ModelAdmin):
    """Interim coordinator portal until the custom dashboard is built."""
    list_display = ("full_name", "membership_number", "electorate", "is_verified",
                    "review_flag", "id_card_printed", "registered_by", "server_synced_at")
    list_filter = ("is_verified", "review_flag", "id_card_printed", "source",
                   "electorate__province__region", "electorate__province")
    search_fields = ("full_name", "membership_number", "nid_number", "phone_number")
    readonly_fields = ("id", "membership_number", "client_created_at", "server_synced_at",
                       "verified_at", "verified_by", "id_card_printed_at", "registered_by")
    raw_id_fields = ("duplicate_of",)
    actions = ["verify_selected", "print_a4_10", "print_a4_8", "print_cr80"]

    def get_queryset(self, request):
        return members_visible_to(request.user)

    @admin.action(description="Verify selected members")
    def verify_selected(self, request, queryset):
        ok = skipped = 0
        for m in queryset.filter(is_verified=False):
            try:
                m.verify(request.user)
                ok += 1
            except ValueError:
                skipped += 1
        self.message_user(request, f"Verified {ok}. Skipped {skipped} flagged duplicate(s).",
                          messages.SUCCESS if not skipped else messages.WARNING)

    def _print(self, request, queryset, layout, per_page=10):
        members = list(queryset.filter(is_verified=True).select_related("electorate__province"))
        if not members:
            self.message_user(request, "Only verified members get cards.", messages.ERROR)
            return None
        return card_pdf_response(members, layout=layout, per_page=per_page,
                                 filename=f"member-cards-{layout}.pdf")

    @admin.action(description="Print ID cards — A4, 10 per sheet")
    def print_a4_10(self, request, queryset):
        return self._print(request, queryset, "batch", 10)

    @admin.action(description="Print ID cards — A4, 8 per sheet (with gutters)")
    def print_a4_8(self, request, queryset):
        return self._print(request, queryset, "batch", 8)

    @admin.action(description="Print ID cards — CR80 (PVC printer)")
    def print_cr80(self, request, queryset):
        return self._print(request, queryset, "single")


@admin.register(SyncLog)
class SyncLogAdmin(admin.ModelAdmin):
    list_display = ("agent", "received_at", "records_received", "created",
                    "already_synced", "flagged", "rejected")
    list_filter = ("agent",)
