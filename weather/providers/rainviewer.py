"""RainViewer radar metadata provider (verified public tile API)."""

from __future__ import annotations

from typing import Any

from weather.providers.base import http_get_json

RAINVIEWER_MAPS_URL = "https://api.rainviewer.com/public/weather-maps.json"


class RainViewerProvider:
    name = "rainviewer"

    def get_maps(self) -> dict[str, Any]:
        data = http_get_json(RAINVIEWER_MAPS_URL, provider=self.name)
        host = data.get("host") or "https://tilecache.rainviewer.com"
        past = (data.get("radar") or {}).get("past") or []
        nowcast = (data.get("radar") or {}).get("nowcast") or []
        frames = []
        for frame in past[-12:]:
            frames.append(
                {
                    "time": frame.get("time"),
                    "path": f"{host}{frame.get('path')}/256/{{z}}/{{x}}/{{y}}/2/1_1.png",
                    "kind": "observed",
                }
            )
        for frame in nowcast[:6]:
            frames.append(
                {
                    "time": frame.get("time"),
                    "path": f"{host}{frame.get('path')}/256/{{z}}/{{x}}/{{y}}/2/1_1.png",
                    "kind": "nowcast",
                }
            )
        return {
            "available": True,
            "source": "RainViewer",
            "attribution": "Radar data via RainViewer (https://www.rainviewer.com/)",
            "generated": data.get("generated"),
            "frames": frames,
            "data_kind": "observed",
            "notes": "Free API for personal/educational use; attribute RainViewer.",
        }
