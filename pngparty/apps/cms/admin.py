from django.contrib import admin

from .models import NewsPost, PolicyDocument


@admin.register(NewsPost)
class NewsPostAdmin(admin.ModelAdmin):
    list_display = ("title", "kind", "is_published", "published_at")
    list_filter = ("kind", "is_published")
    search_fields = ("title", "summary", "body")
    prepopulated_fields = {"slug": ("title",)}


@admin.register(PolicyDocument)
class PolicyDocumentAdmin(admin.ModelAdmin):
    list_display = ("title", "pillar", "order", "is_published")
    list_filter = ("pillar", "is_published")
    list_editable = ("order", "is_published")
