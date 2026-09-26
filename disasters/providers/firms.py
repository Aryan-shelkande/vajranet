"""NASA FIRMS wildfire hotspot provider — requires free MAP_KEY."""

from __future__ import annotations

from typing import Any

from django.conf import settings

from weather.providers.base import ProviderUnavailable

# India approx bbox: west,south,east,north
INDIA_AREA = "68,6,98,37.5"


class NASAFirmsProvider:
    name = "nasa_firms"

    def get_hotspots(self, *, day_range: int = 1) -> dict[str, Any]:
        key = settings.NASA_FIRMS_MAP_KEY
        if not key:
            raise ProviderUnavailable(
                "NASA FIRMS requires a free MAP_KEY. "
                "Register at https://firms.modaps.eosdis.nasa.gov/api/map_key/"
            )
        # CSV endpoint; we keep adapter ready and parse lightly when key exists.
        url = (
            f"https://firms.modaps.eosdis.nasa.gov/api/area/csv/"
            f"{key}/VIIRS_SNPP_NRT/{INDIA_AREA}/{day_range}"
        )
        # http_get_json expects JSON; FIRMS returns CSV — fetch via httpx directly.
        import httpx

        with httpx.Client(timeout=settings.HTTP_TIMEOUT_SECONDS) as client:
            response = client.get(url)
        if response.status_code >= 400:
            raise ProviderUnavailable(f"FIRMS returned {response.status_code}")
        lines = response.text.strip().splitlines()
        if len(lines) <= 1:
            return {
                "available": True,
                "source": "NASA FIRMS",
                "hotspots": [],
                "data_kind": "observed",
            }
        headers = [h.strip() for h in lines[0].split(",")]
        hotspots = []
        for line in lines[1:200]:
            parts = line.split(",")
            row = dict(zip(headers, parts))
            try:
                hotspots.append(
                    {
                        "latitude": float(row.get("latitude") or 0),
                        "longitude": float(row.get("longitude") or 0),
                        "brightness": row.get("bright_ti4") or row.get("brightness"),
                        "acq_date": row.get("acq_date"),
                        "acq_time": row.get("acq_time"),
                        "confidence": row.get("confidence"),
                        "satellite": row.get("satellite"),
                    }
                )
            except ValueError:
                continue
        return {
            "available": True,
            "source": "NASA FIRMS",
            "hotspots": hotspots,
            "data_kind": "observed",
            "attribution": "NASA FIRMS / LANCE",
        }
