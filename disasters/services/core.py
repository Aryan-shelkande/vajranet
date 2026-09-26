"""Disaster-related API and services."""

from __future__ import annotations

import logging
from datetime import datetime, timezone as dt_timezone
from typing import Any

from django.conf import settings
from django.core.cache import cache
from django.utils import timezone
from rest_framework.response import Response
from rest_framework.views import APIView

from disasters.models import DisasterEvent, HazardType
from disasters.providers.firms import NASAFirmsProvider
from disasters.providers.usgs import USGSEarthquakeProvider
from weather.providers.base import ProviderError, ProviderUnavailable

logger = logging.getLogger(__name__)


class DisasterService:
    def __init__(self):
        self.usgs = USGSEarthquakeProvider()
        self.firms = NASAFirmsProvider()

    def get_earthquakes(self) -> dict[str, Any]:
        cache_key = "disasters:earthquakes"
        cached = cache.get(cache_key)
        if cached:
            return cached
        try:
            events = self.usgs.get_recent()
        except ProviderError as exc:
            logger.error("USGS earthquake fetch failed: %s", exc)
            return {
                "available": False,
                "events": [],
                "message": "Earthquake data temporarily unavailable.",
                "source": "USGS",
                "data_kind": "unavailable",
            }
        hazard, _ = HazardType.objects.get_or_create(
            slug="earthquake",
            defaults={
                "name": "Earthquake",
                "category": "geophysical",
                "phase1_focus": False,
            },
        )
        for event in events:
            occurred = event.get("occurred_at")
            if isinstance(occurred, (int, float)):
                occurred_at = datetime.fromtimestamp(
                    occurred / 1000.0, tz=dt_timezone.utc
                )
            else:
                occurred_at = timezone.now()
            DisasterEvent.objects.update_or_create(
                source_name="USGS",
                external_id=event.get("external_id") or "",
                defaults={
                    "hazard_type": hazard,
                    "title": event.get("title") or "Earthquake",
                    "description": event.get("place") or "",
                    "latitude": event.get("latitude"),
                    "longitude": event.get("longitude"),
                    "magnitude": event.get("magnitude"),
                    "occurred_at": occurred_at,
                    "source_url": event.get("url") or "",
                    "origin": DisasterEvent.Origin.OBSERVED,
                    "metadata": {"depth_km": event.get("depth_km")},
                    "is_active": True,
                },
            )
        payload = {
            "available": True,
            "events": events,
            "source": "USGS",
            "data_kind": "observed",
            "message": None,
        }
        cache.set(cache_key, payload, settings.EARTHQUAKE_CACHE_SECONDS)
        return payload

    def get_wildfires(self) -> dict[str, Any]:
        cache_key = "disasters:wildfires"
        cached = cache.get(cache_key)
        if cached:
            return cached
        try:
            payload = self.firms.get_hotspots()
            cache.set(cache_key, payload, 1800)
            return payload
        except (ProviderUnavailable, ProviderError) as exc:
            return {
                "available": False,
                "hotspots": [],
                "message": str(exc),
                "source": "NASA FIRMS",
                "data_kind": "unavailable",
            }

    def list_hazards(self) -> list[dict[str, Any]]:
        return list(
            HazardType.objects.filter(is_active=True).values(
                "slug", "name", "category", "description", "phase1_focus"
            )
        )


class EarthquakeAPI(APIView):
    def get(self, request):
        return Response(DisasterService().get_earthquakes())


class WildfireAPI(APIView):
    def get(self, request):
        return Response(DisasterService().get_wildfires())


class DisasterListAPI(APIView):
    def get(self, request):
        service = DisasterService()
        return Response(
            {
                "hazards": service.list_hazards(),
                "earthquakes": service.get_earthquakes(),
                "wildfires": service.get_wildfires(),
            }
        )
