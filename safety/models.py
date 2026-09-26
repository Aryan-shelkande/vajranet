"""Safety guidelines and emergency preparedness content."""

from __future__ import annotations

from django.db import models

from weather.models import TimeStampedModel


class SafetyGuideline(TimeStampedModel):
    slug = models.SlugField(unique=True)
    hazard_name = models.CharField(max_length=100)
    title = models.CharField(max_length=200)
    summary = models.TextField()
    instructions = models.JSONField(default=list)
    official_sources = models.JSONField(default=list, blank=True)
    display_order = models.PositiveSmallIntegerField(default=0)
    is_published = models.BooleanField(default=True)

    class Meta:
        ordering = ["display_order", "hazard_name"]

    def __str__(self) -> str:
        return self.title


class EmergencyKitItem(TimeStampedModel):
    slug = models.SlugField(unique=True)
    name = models.CharField(max_length=100)
    description = models.CharField(max_length=255, blank=True)
    icon = models.CharField(max_length=64, blank=True)
    display_order = models.PositiveSmallIntegerField(default=0)
    is_essential = models.BooleanField(default=True)

    class Meta:
        ordering = ["display_order", "name"]

    def __str__(self) -> str:
        return self.name
