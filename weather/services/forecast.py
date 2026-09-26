"""Forecast service with caching."""

from __future__ import annotations

import logging
from typing import Any

from django.conf import settings
from django.core.cache import cache

from weather.providers.base import ProviderError
from weather.services.weather import LocationService, get_weather_provider, _location_dict

logger = logging.getLogger(__name__)


class ForecastService:
    def __init__(self):
        self.provider = get_weather_provider()
        self.locations = LocationService()

    def get_forecast(
        self, *, city: str | None = None, location_id: int | None = None
    ) -> dict[str, Any]:
        location = self.locations.resolve(city=city, location_id=location_id)
        cache_key = f"weather:forecast:{location.id}"
        cached = cache.get(cache_key)
        if cached:
            cached = dict(cached)
            cached["from_cache"] = True
            return cached

        try:
            bundle = self.provider.get_forecast(
                float(location.latitude), float(location.longitude)
            )
        except ProviderError:
            logger.error("Forecast API failed for %s", location)
            raise

        payload = {
            "location": _location_dict(location),
            "hourly": bundle.hourly,
            "daily": bundle.daily,
            "source": bundle.source,
            "data_kind": bundle.data_kind,
            "timezone": bundle.timezone,
            "from_cache": False,
            "message": None,
        }
        cache.set(cache_key, payload, settings.FORECAST_CACHE_SECONDS)
        return payload

    def get_hourly(self, **kwargs) -> dict[str, Any]:
        data = self.get_forecast(**kwargs)
        return {
            "location": data["location"],
            "hourly": data["hourly"],
            "source": data["source"],
            "data_kind": data["data_kind"],
            "from_cache": data.get("from_cache", False),
        }

    def get_daily(self, **kwargs) -> dict[str, Any]:
        data = self.get_forecast(**kwargs)
        return {
            "location": data["location"],
            "daily": data["daily"],
            "source": data["source"],
            "data_kind": data["data_kind"],
            "from_cache": data.get("from_cache", False),
        }
