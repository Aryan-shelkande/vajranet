from django.contrib import admin

from safety.models import EmergencyKitItem, SafetyGuideline


@admin.register(SafetyGuideline)
class SafetyGuidelineAdmin(admin.ModelAdmin):
    list_display = ("title", "hazard_name", "display_order", "is_published")
    list_filter = ("is_published",)
    search_fields = ("title", "hazard_name", "summary")
    prepopulated_fields = {"slug": ("hazard_name",)}


@admin.register(EmergencyKitItem)
class EmergencyKitItemAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "display_order", "is_essential")
    prepopulated_fields = {"slug": ("name",)}
    search_fields = ("name",)
