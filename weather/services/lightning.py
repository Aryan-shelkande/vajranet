"""Lightning and radar service facades."""

from __future__ import annotations

import logging
from typing import Any

from django.core.cache import cache

from weather.providers.base import ProviderError
from weather.providers.lightning import UnavailableLightningProvider
from weather.providers.rainviewer import RainViewerProvider

logger = logging.getLogger(__name__)


class LightningService:
    def __init__(self):
        self.provider = UnavailableLightningProvider()

    def get_recent_india(self, *, minutes: int = 60) -> dict[str, Any]:
        cache_key = f"lightning:india:{minutes}"
        cached = cache.get(cache_key)
        if cached:
            return cached
        try:
            bundle = self.provider.get_recent(
                west=68.0, south=6.0, east=98.0, north=37.5, minutes=minutes
            )
        except ProviderError as exc:
            logger.warning("Lightning provider unavailable: %s", exc)
            return {
                "available": False,
                "strikes": [],
                "message": str(exc),
                "window_minutes": minutes,
                "source": "None",
                "data_kind": "unavailable",
            }
        payload = {
            "available": bundle.available,
            "strikes": [
                {
                    "latitude": s.latitude,
                    "longitude": s.longitude,
                    "observed_at": s.observed_at,
                    "intensity": s.intensity,
                    "polarity": s.polarity,
                    "source": s.source,
                }
                for s in bundle.strikes
            ],
            "message": bundle.message,
            "window_minutes": bundle.window_minutes,
            "source": bundle.source,
            "data_kind": bundle.data_kind,
            "count": len(bundle.strikes),
        }
        cache.set(cache_key, payload, 120)
        return payload


class RadarService:
    def __init__(self):
        self.provider = RainViewerProvider()

    def get_radar(self) -> dict[str, Any]:
        cache_key = "radar:rainviewer"
        cached = cache.get(cache_key)
        if cached:
            return cached
        try:
            payload = self.provider.get_maps()
            cache.set(cache_key, payload, 300)
            return payload
        except ProviderError as exc:
            logger.warning("Radar provider unavailable: %s", exc)
            return {
                "available": False,
                "frames": [],
                "message": "Radar data temporarily unavailable.",
                "source": "RainViewer",
                "data_kind": "unavailable",
            }
