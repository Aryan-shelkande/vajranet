"""Hazard taxonomy and disaster event models."""

from __future__ import annotations

from django.db import models

from weather.models import Location, TimeStampedModel


class HazardType(TimeStampedModel):
    slug = models.SlugField(unique=True)
    name = models.CharField(max_length=100)
    category = models.CharField(max_length=64, blank=True)
    description = models.TextField(blank=True)
    icon = models.CharField(max_length=64, blank=True)
    phase1_focus = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class DisasterEvent(TimeStampedModel):
    """Observed hazard event from a verified public feed (e.g. USGS)."""

    class Origin(models.TextChoices):
        OBSERVED = "observed", "Observed"
        OFFICIAL = "official", "Official"
        DERIVED = "derived", "Derived"

    hazard_type = models.ForeignKey(
        HazardType, on_delete=models.PROTECT, related_name="events"
    )
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    location = models.ForeignKey(
        Location, on_delete=models.SET_NULL, null=True, blank=True, related_name="events"
    )
    magnitude = models.FloatField(null=True, blank=True)
    severity = models.CharField(max_length=32, blank=True)
    occurred_at = models.DateTimeField(db_index=True)
    source_name = models.CharField(max_length=120)
    source_url = models.URLField(blank=True)
    external_id = models.CharField(max_length=120, blank=True, db_index=True)
    origin = models.CharField(
        max_length=20, choices=Origin.choices, default=Origin.OBSERVED
    )
    metadata = models.JSONField(default=dict, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["-occurred_at"]
        indexes = [
            models.Index(fields=["hazard_type", "-occurred_at"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["source_name", "external_id"],
                name="uniq_disaster_source_external",
                condition=~models.Q(external_id=""),
            )
        ]

    def __str__(self) -> str:
        return self.title
