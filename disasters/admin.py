from django.contrib import admin

from disasters.models import DisasterEvent, HazardType


@admin.register(HazardType)
class HazardTypeAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "category", "phase1_focus", "is_active")
    list_filter = ("phase1_focus", "is_active", "category")
    prepopulated_fields = {"slug": ("name",)}
    search_fields = ("name", "slug")


@admin.register(DisasterEvent)
class DisasterEventAdmin(admin.ModelAdmin):
    list_display = ("title", "hazard_type", "magnitude", "occurred_at", "source_name", "is_active")
    list_filter = ("hazard_type", "source_name", "is_active")
    search_fields = ("title", "external_id", "description")
    date_hierarchy = "occurred_at"
