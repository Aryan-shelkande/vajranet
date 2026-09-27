"""Assemble assistant context from services already used by the dashboard."""

from __future__ import annotations

import logging
from typing import Any

from weather.services.alert import AlertService
from weather.services.briefing import BriefingService
from weather.services.forecast import ForecastService
from weather.services.nowcasting import NowcastingService
from weather.services.risk import AtmosphericRiskEngine
from weather.services.weather import WeatherService

logger = logging.getLogger(__name__)


def _bundle(city: str) -> dict[str, Any]:
    current = WeatherService().get_current(city=city)
    hourly = ForecastService().get_hourly(city=city)
    nowcast = NowcastingService().assess(city=city)
    alerts_payload = AlertService().get_alerts(city=city)
    alerts = alerts_payload.get("alerts") or []
    radar = nowcast.get("radar") or {}
    risk = AtmosphericRiskEngine().evaluate(
        current=current,
        hourly=hourly.get("hourly") or [],
        nowcast=nowcast,
        alerts=alerts,
        radar=radar,
    )
    return {
        "current": current,
        "hourly": hourly.get("hourly") or [],
        "nowcast": nowcast,
        "alerts": alerts,
        "risk": risk,
    }


def build_risk(city: str) -> dict[str, Any]:
    bundle = _bundle(city)
    return bundle["risk"]


def build_briefing(
    city: str, *, language: str = "en", allow_llm: bool = False
) -> dict[str, Any]:
    bundle = _bundle(city)
    return BriefingService().compose(
        city=city,
        current=bundle["current"],
        nowcast=bundle["nowcast"],
        risk=bundle["risk"],
        hourly=bundle["hourly"],
        language=language,
        allow_llm=allow_llm,
    )


def build_live_context(city: str) -> dict[str, Any] | None:
    try:
        bundle = _bundle(city)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Live assistant context unavailable: %s", exc.__class__.__name__)
        return None
    current = bundle["current"]
    nowcast = bundle["nowcast"]
    risk = bundle["risk"]
    radar = nowcast.get("radar") or {}
    return {
        "city": (current.get("location") or {}).get("name") or city,
        "location": current.get("location") or {},
        "weather": {
            "temperature_c": current.get("temperature_c"),
            "feels_like_c": current.get("feels_like_c"),
            "humidity_pct": current.get("humidity_pct"),
            "wind_speed_kmh": current.get("wind_speed_kmh"),
            "rainfall_mm": current.get("rainfall_mm"),
            "weather_code": current.get("weather_code"),
            "weather_description": current.get("weather_description"),
            "data_kind": current.get("data_kind"),
            "source": current.get("source"),
        },
        "nowcast": {
            "risk_level": nowcast.get("risk_level"),
            "risk_score": nowcast.get("risk_score"),
            "label": nowcast.get("label"),
            "engine_type": nowcast.get("engine_type"),
            "data_kind": nowcast.get("data_kind"),
            "factors": nowcast.get("factors") or [],
        },
        "windows": nowcast.get("windows") or {},
        "alerts": bundle["alerts"][:6],
        "risk": {
            "overall_level": (risk.get("overall") or {}).get("level"),
            "overall_score": (risk.get("overall") or {}).get("score"),
            "label": risk.get("label"),
            "why": risk.get("why"),
        },
        "radar_status": radar.get("status") or "unavailable",
        "radar_note": radar.get("note") or "",
        "lightning_status": "unavailable",
    }
