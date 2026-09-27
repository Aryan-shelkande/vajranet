from django.contrib import admin

from weather.models import (
    AlertDispatch,
    APIRequestLog,
    DataSource,
    Location,
    SMSDelivery,
    SMSSubscriber,
    WeatherAlert,
    WeatherForecast,
    WeatherObservation,
)


@admin.register(Location)
class LocationAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "state",
        "country_code",
        "latitude",
        "longitude",
        "is_featured",
    )
    list_filter = ("country_code", "is_featured", "state")
    search_fields = ("name", "state", "district")
    ordering = ("name",)


@admin.register(DataSource)
class DataSourceAdmin(admin.ModelAdmin):
    list_display = ("name", "data_type", "status", "update_frequency", "is_active")
    list_filter = ("status", "is_active")
    search_fields = ("name", "slug", "data_type")
    prepopulated_fields = {"slug": ("name",)}


@admin.register(WeatherObservation)
class WeatherObservationAdmin(admin.ModelAdmin):
    list_display = ("location", "observed_at", "temperature_c", "data_kind", "source")
    list_filter = ("data_kind",)
    search_fields = ("location__name",)
    date_hierarchy = "observed_at"


@admin.register(WeatherForecast)
class WeatherForecastAdmin(admin.ModelAdmin):
    list_display = (
        "location",
        "period",
        "forecast_time",
        "temperature_c",
        "precipitation_mm",
    )
    list_filter = ("period",)
    search_fields = ("location__name",)


@admin.register(WeatherAlert)
class WeatherAlertAdmin(admin.ModelAdmin):
    list_display = (
        "title",
        "hazard_type",
        "severity",
        "origin",
        "location",
        "is_active",
    )
    list_filter = ("severity", "origin", "hazard_type", "is_active")
    search_fields = ("title", "area_name", "description")


@admin.register(APIRequestLog)
class APIRequestLogAdmin(admin.ModelAdmin):
    list_display = ("provider", "success", "status_code", "latency_ms", "created_at")
    list_filter = ("provider", "success")
    readonly_fields = (
        "provider",
        "endpoint",
        "success",
        "status_code",
        "latency_ms",
        "error_message",
        "created_at",
    )


@admin.register(SMSSubscriber)
class SMSSubscriberAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "masked_mobile",
        "location_label",
        "language",
        "is_active",
        "consent_given",
        "last_alert_sent_at",
    )
    list_filter = ("language", "is_active", "consent_given")
    search_fields = ("name", "location_label")
    readonly_fields = ("masked_mobile", "consent_timestamp", "created_at", "updated_at")
    exclude = ("mobile_number", "normalized_mobile_number")

    @admin.display(description="Mobile")
    def masked_mobile(self, obj: SMSSubscriber) -> str:
        return obj.masked_number()

    def has_add_permission(self, request):
        return False


@admin.register(SMSDelivery)
class SMSDeliveryAdmin(admin.ModelAdmin):
    list_display = (
        "created_at",
        "status",
        "category",
        "masked_recipient",
        "language",
        "provider",
    )
    list_filter = ("status", "provider", "language", "category")
    readonly_fields = (
        "subscriber",
        "masked_recipient",
        "fingerprint",
        "category",
        "language",
        "body",
        "status",
        "provider",
        "error_code",
        "created_at",
    )


@admin.register(AlertDispatch)
class AlertDispatchAdmin(admin.ModelAdmin):
    list_display = (
        "event_type",
        "location_label",
        "severity",
        "last_sent_at",
        "send_count",
    )
    list_filter = ("event_type", "severity")
    readonly_fields = (
        "event_type",
        "location",
        "location_label",
        "severity",
        "valid_until",
        "fingerprint",
        "last_sent_at",
        "send_count",
        "created_at",
        "updated_at",
    )
