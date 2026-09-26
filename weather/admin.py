from django.contrib import admin

from weather.models import (
    APIRequestLog,
    DataSource,
    Location,
    WeatherAlert,
    WeatherForecast,
    WeatherObservation,
)


@admin.register(Location)
class LocationAdmin(admin.ModelAdmin):
    list_display = ("name", "state", "country_code", "latitude", "longitude", "is_featured")
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
    list_display = ("location", "period", "forecast_time", "temperature_c", "precipitation_mm")
    list_filter = ("period",)
    search_fields = ("location__name",)


@admin.register(WeatherAlert)
class WeatherAlertAdmin(admin.ModelAdmin):
    list_display = ("title", "hazard_type", "severity", "origin", "location", "is_active")
    list_filter = ("severity", "origin", "hazard_type", "is_active")
    search_fields = ("title", "area_name", "description")


@admin.register(APIRequestLog)
class APIRequestLogAdmin(admin.ModelAdmin):
    list_display = ("provider", "success", "status_code", "latency_ms", "created_at")
    list_filter = ("provider", "success")
    readonly_fields = ("provider", "endpoint", "success", "status_code", "latency_ms", "error_message", "created_at")
