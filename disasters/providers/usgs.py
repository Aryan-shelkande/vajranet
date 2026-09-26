"""USGS earthquake provider for India bbox (public, no API key)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from weather.providers.base import http_get_json

USGS_URL = "https://earthquake.usgs.gov/fdsnws/event/1/query"

# Approximate India + nearby waters bounding box
INDIA_BBOX = {
    "minlatitude": 6.0,
    "maxlatitude": 37.5,
    "minlongitude": 68.0,
    "maxlongitude": 98.0,
}


class USGSEarthquakeProvider:
    name = "usgs"

    def get_recent(
        self, *, days: int = 7, min_magnitude: float = 3.5, limit: int = 50
    ) -> list[dict[str, Any]]:
        start = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d")
        params = {
            "format": "geojson",
            "starttime": start,
            "minmagnitude": min_magnitude,
            "limit": limit,
            **INDIA_BBOX,
            "orderby": "time",
        }
        data = http_get_json(USGS_URL, params=params, provider=self.name)
        events = []
        for feature in data.get("features") or []:
            props = feature.get("properties") or {}
            geom = feature.get("geometry") or {}
            coords = geom.get("coordinates") or [None, None, None]
            events.append(
                {
                    "external_id": feature.get("id") or "",
                    "title": props.get("title") or props.get("place") or "Earthquake",
                    "place": props.get("place") or "",
                    "magnitude": props.get("mag"),
                    "occurred_at": props.get("time"),
                    "longitude": coords[0],
                    "latitude": coords[1],
                    "depth_km": coords[2],
                    "url": props.get("url") or "",
                    "source": "USGS",
                    "origin": "observed",
                    "data_kind": "observed",
                }
            )
        return events
