"""Core weather and atmospheric data models."""

from __future__ import annotations

from django.db import models
from django.utils import timezone


class TimeStampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class DataSource(TimeStampedModel):
    """Documented external providers shown on /data-sources/."""

    class Status(models.TextChoices):
        AVAILABLE = "available", "Available"
        REQUIRES_KEY = "requires_key", "Requires API key"
        UNAVAILABLE = "unavailable", "Unavailable"
        PLANNED = "planned", "Planned integration"

    slug = models.SlugField(unique=True)
    name = models.CharField(max_length=120)
    data_type = models.CharField(max_length=120)
    update_frequency = models.CharField(max_length=80, blank=True)
    coverage = models.CharField(max_length=120, blank=True)
    attribution = models.TextField(blank=True)
    homepage_url = models.URLField(blank=True)
    docs_url = models.URLField(blank=True)
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.PLANNED
    )
    notes = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class Location(TimeStampedModel):
    """Searchable Indian (and optionally global) locations."""

    name = models.CharField(max_length=120, db_index=True)
    state = models.CharField(max_length=120, blank=True, db_index=True)
    district = models.CharField(max_length=120, blank=True)
    country_code = models.CharField(max_length=2, default="IN", db_index=True)
    latitude = models.DecimalField(max_digits=9, decimal_places=6)
    longitude = models.DecimalField(max_digits=9, decimal_places=6)
    timezone = models.CharField(max_length=64, default="Asia/Kolkata")
    population = models.PositiveIntegerField(null=True, blank=True)
    is_featured = models.BooleanField(default=False, db_index=True)
    external_geoname_id = models.PositiveIntegerField(
        null=True, blank=True, unique=True
    )

    class Meta:
        ordering = ["name"]
        indexes = [
            models.Index(fields=["name", "state"]),
            models.Index(fields=["latitude", "longitude"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["name", "state", "country_code"],
                name="uniq_location_name_state_country",
            )
        ]

    def __str__(self) -> str:
        if self.state:
            return f"{self.name}, {self.state}"
        return self.name


class WeatherObservation(TimeStampedModel):
    """Cached current weather observation for a location."""

    class DataKind(models.TextChoices):
        LIVE = "live", "Live observation"
        FORECAST = "forecast", "Forecast"
        MODEL = "model", "Model-derived"
        CACHED = "cached", "Cached"

    location = models.ForeignKey(
        Location, on_delete=models.CASCADE, related_name="observations"
    )
    source = models.ForeignKey(
        DataSource, on_delete=models.SET_NULL, null=True, blank=True
    )
    observed_at = models.DateTimeField(db_index=True)
    data_kind = models.CharField(
        max_length=20, choices=DataKind.choices, default=DataKind.LIVE
    )
    temperature_c = models.FloatField(null=True, blank=True)
    feels_like_c = models.FloatField(null=True, blank=True)
    humidity_pct = models.FloatField(null=True, blank=True)
    pressure_hpa = models.FloatField(null=True, blank=True)
    wind_speed_kmh = models.FloatField(null=True, blank=True)
    wind_direction_deg = models.FloatField(null=True, blank=True)
    visibility_km = models.FloatField(null=True, blank=True)
    cloud_cover_pct = models.FloatField(null=True, blank=True)
    rainfall_mm = models.FloatField(null=True, blank=True)
    uv_index = models.FloatField(null=True, blank=True)
    weather_code = models.PositiveSmallIntegerField(null=True, blank=True)
    weather_description = models.CharField(max_length=120, blank=True)
    cape_jkg = models.FloatField(null=True, blank=True)
    raw_payload = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["-observed_at"]
        indexes = [
            models.Index(fields=["location", "-observed_at"]),
        ]

    def __str__(self) -> str:
        return f"{self.location} @ {self.observed_at:%Y-%m-%d %H:%M}"


class WeatherForecast(TimeStampedModel):
    """Hourly or daily forecast rows."""

    class Period(models.TextChoices):
        HOURLY = "hourly", "Hourly"
        DAILY = "daily", "Daily"

    location = models.ForeignKey(
        Location, on_delete=models.CASCADE, related_name="forecasts"
    )
    source = models.ForeignKey(
        DataSource, on_delete=models.SET_NULL, null=True, blank=True
    )
    period = models.CharField(max_length=10, choices=Period.choices)
    forecast_time = models.DateTimeField(db_index=True)
    temperature_c = models.FloatField(null=True, blank=True)
    temperature_min_c = models.FloatField(null=True, blank=True)
    temperature_max_c = models.FloatField(null=True, blank=True)
    humidity_pct = models.FloatField(null=True, blank=True)
    precipitation_mm = models.FloatField(null=True, blank=True)
    precipitation_probability_pct = models.FloatField(null=True, blank=True)
    wind_speed_kmh = models.FloatField(null=True, blank=True)
    weather_code = models.PositiveSmallIntegerField(null=True, blank=True)
    weather_description = models.CharField(max_length=120, blank=True)
    thunderstorm_hint = models.BooleanField(default=False)

    class Meta:
        ordering = ["forecast_time"]
        indexes = [
            models.Index(fields=["location", "period", "forecast_time"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["location", "period", "forecast_time"],
                name="uniq_forecast_location_period_time",
            )
        ]

    def __str__(self) -> str:
        return f"{self.period} {self.location} {self.forecast_time}"


class WeatherAlert(TimeStampedModel):
    """Platform alerts — derived or ingested; never fake official warnings."""

    class Severity(models.TextChoices):
        INFO = "info", "Info"
        LOW = "low", "Low"
        MODERATE = "moderate", "Moderate"
        HIGH = "high", "High"
        EXTREME = "extreme", "Extreme"

    class Origin(models.TextChoices):
        DERIVED = "derived", "Model-derived estimate"
        OFFICIAL = "official", "Official authority"
        OBSERVED = "observed", "Observed condition"

    hazard_type = models.CharField(max_length=64, db_index=True)
    title = models.CharField(max_length=200)
    description = models.TextField()
    severity = models.CharField(max_length=20, choices=Severity.choices)
    origin = models.CharField(
        max_length=20, choices=Origin.choices, default=Origin.DERIVED
    )
    location = models.ForeignKey(
        Location,
        on_delete=models.CASCADE,
        related_name="alerts",
        null=True,
        blank=True,
    )
    area_name = models.CharField(max_length=200, blank=True)
    starts_at = models.DateTimeField(null=True, blank=True)
    ends_at = models.DateTimeField(null=True, blank=True)
    source_name = models.CharField(max_length=120, blank=True)
    recommended_action = models.TextField(blank=True)
    is_active = models.BooleanField(default=True, db_index=True)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["-severity", "-updated_at"]

    def __str__(self) -> str:
        return f"{self.severity.upper()} {self.hazard_type}: {self.title}"

    @property
    def is_current(self) -> bool:
        now = timezone.now()
        if not self.is_active:
            return False
        if self.ends_at and self.ends_at < now:
            return False
        return True


class APIRequestLog(models.Model):
    """Lightweight audit of outbound provider calls."""

    provider = models.CharField(max_length=64, db_index=True)
    endpoint = models.CharField(max_length=255)
    success = models.BooleanField(default=False)
    status_code = models.PositiveSmallIntegerField(null=True, blank=True)
    latency_ms = models.PositiveIntegerField(null=True, blank=True)
    error_message = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.provider} {'OK' if self.success else 'FAIL'}"


class SMSSubscriber(TimeStampedModel):
    """Visitor SMS opt-in. No user account. Full numbers are masked in admin lists."""

    class Language(models.TextChoices):
        EN = "en", "English"
        HI = "hi", "Hindi"
        MR = "mr", "Marathi"

    name = models.CharField(max_length=80)
    mobile_number = models.CharField(max_length=16)
    normalized_mobile_number = models.CharField(max_length=16, unique=True)
    location = models.ForeignKey(
        Location,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="sms_subscribers",
    )
    location_label = models.CharField(max_length=160)
    latitude = models.DecimalField(
        max_digits=9, decimal_places=6, null=True, blank=True
    )
    longitude = models.DecimalField(
        max_digits=9, decimal_places=6, null=True, blank=True
    )
    language = models.CharField(
        max_length=8, choices=Language.choices, default=Language.EN
    )
    alert_preferences = models.JSONField(default=list)
    is_active = models.BooleanField(default=True, db_index=True)
    phone_verified = models.BooleanField(default=False)
    consent_given = models.BooleanField(default=False)
    consent_timestamp = models.DateTimeField(null=True, blank=True)
    last_alert_sent_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("-created_at",)
        indexes = (
            models.Index(fields=["is_active", "language"]),
            models.Index(fields=["location", "is_active"]),
        )

    def masked_number(self) -> str:
        from weather.services.phone import mask_mobile

        return mask_mobile(self.normalized_mobile_number)

    def __str__(self) -> str:
        return f"{self.name} {self.masked_number()}"


class SMSDelivery(models.Model):
    """Audit of an SMS attempt. Stores a masked recipient, never a raw number."""

    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending"
        SENT = "SENT", "Sent"
        FAILED = "FAILED", "Failed"
        SKIPPED = "SKIPPED", "Skipped"
        DEMO = "DEMO", "Demo"

    subscriber = models.ForeignKey(
        SMSSubscriber,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="deliveries",
    )
    masked_recipient = models.CharField(max_length=20)
    fingerprint = models.CharField(max_length=64, db_index=True)
    category = models.CharField(max_length=32)
    language = models.CharField(max_length=8, default="en")
    body = models.TextField()
    status = models.CharField(max_length=16, choices=Status.choices, db_index=True)
    provider = models.CharField(max_length=32, default="demo")
    error_code = models.CharField(max_length=64, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ("-created_at",)

    def __str__(self) -> str:
        return f"{self.status} {self.category} {self.masked_recipient}"


class AlertDispatch(TimeStampedModel):
    """Dedup record so the same hazard is not texted repeatedly."""

    event_type = models.CharField(max_length=32, db_index=True)
    location = models.ForeignKey(
        Location,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="alert_dispatches",
    )
    location_label = models.CharField(max_length=160, blank=True)
    severity = models.CharField(max_length=20)
    valid_until = models.DateTimeField(null=True, blank=True)
    fingerprint = models.CharField(max_length=64, unique=True)
    last_sent_at = models.DateTimeField(null=True, blank=True, db_index=True)
    send_count = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ("-last_sent_at",)

    def __str__(self) -> str:
        return f"{self.event_type} {self.location_label} {self.severity}"
