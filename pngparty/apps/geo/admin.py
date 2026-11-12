from django.contrib import admin

from .models import Electorate, Province


@admin.register(Province)
class ProvinceAdmin(admin.ModelAdmin):
    list_display = ("name", "code", "region")
    list_filter = ("region",)


@admin.register(Electorate)
class ElectorateAdmin(admin.ModelAdmin):
    list_display = ("name", "province", "electorate_type")
    list_filter = ("province__region", "province", "electorate_type")
    search_fields = ("name",)
