from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import User


@admin.register(User)
class PartyUserAdmin(UserAdmin):
    list_display = ("username", "get_full_name", "role", "assigned_province", "assigned_electorate", "is_active")
    list_filter = ("role", "assigned_province", "is_active")
    fieldsets = UserAdmin.fieldsets + (
        ("Party role", {"fields": ("phone_number", "role", "assigned_province", "assigned_electorate")}),
    )
