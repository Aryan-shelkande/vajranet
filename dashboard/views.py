"""Dashboard page views."""

from __future__ import annotations

import json

from django.views.generic import TemplateView

from disasters.models import HazardType
from disasters.services import DisasterService
from safety.models import EmergencyKitItem, SafetyGuideline
from weather.models import DataSource, Location
from weather.providers.base import ProviderError
from weather.services.alert import AlertService
from weather.services.forecast import ForecastService
from weather.services.lightning import LightningService
from weather.services.nowcasting import NowcastingService
from weather.services.weather import LocationService, WeatherService


def platform_context(request):
    from django.conf import settings

    ai_provider = (getattr(settings, "AI_PROVIDER", "platform") or "platform").lower()
    openai_ready = bool(getattr(settings, "OPENAI_API_KEY", ""))
    return {
        "PLATFORM_NAME": settings.PLATFORM_NAME,
        "PLATFORM_SUBTITLE": settings.PLATFORM_SUBTITLE,
        "DISCLAIMER": settings.DISCLAIMER,
        "MAP_TILE_STYLE_URL": settings.MAP_TILE_STYLE_URL,
        "MAP_TILE_URL": settings.MAP_TILE_STYLE_URL,
        "MAP_TILE_ATTRIBUTION": settings.MAP_TILE_ATTRIBUTION,
        "MAP_TILE_MAX_ZOOM": settings.MAP_TILE_MAX_ZOOM,
        "AI_PROVIDER": ai_provider,
        "AI_LLM_READY": ai_provider == "openai" and openai_ready,
        "NASA_FIRMS_CONFIGURED": bool(getattr(settings, "NASA_FIRMS_MAP_KEY", "")),
    }


class HomeView(TemplateView):
    template_name = "dashboard/home.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        city = self.request.GET.get("city", "Pune")
        view_mode = self.request.GET.get("view", "citizen")
        weather = WeatherService()
        forecast = ForecastService()
        alerts = AlertService()
        locations = LocationService()
        if not Location.objects.filter(is_featured=True).exists():
            locations.ensure_featured()

        error = None
        current = None
        hourly = []
        daily = []
        alert_payload = {"alerts": []}
        nowcast_payload = None
        overview = {
            "temperature_c": None,
            "rainfall_mm": None,
            "wind_speed_kmh": None,
            "humidity_pct": None,
            "cities": 0,
        }
        try:
            # Order matters for cache warmth: current + forecast first.
            # AlertService internally reuses the same cached current/forecast/nowcast.
            current = weather.get_current(city=city)
            fc = forecast.get_forecast(city=city)
            hourly = fc.get("hourly") or []
            daily = fc.get("daily") or []
            alert_payload = alerts.get_alerts(city=city)
            # Prefer a single nowcast assess after caches are warm (AlertService already ran one).
            nowcast_payload = NowcastingService().assess(city=city)
        except ProviderError as exc:
            error = str(exc)
        except Exception as exc:  # noqa: BLE001 — keep dashboard alive
            error = str(exc)

        try:
            overview = _india_overview(weather.get_map_overview())
        except Exception:  # noqa: BLE001
            overview = {
                "temperature_c": None,
                "rainfall_mm": None,
                "wind_speed_kmh": None,
                "humidity_pct": None,
                "cities": 0,
            }

        ctx.update(
            {
                "city": city,
                "view_mode": view_mode,
                "current": current,
                "hourly": hourly[:24],
                "daily": daily[:7],
                "alerts": alert_payload.get("alerts") or [],
                "alert_note": alert_payload.get("note"),
                "nowcast": nowcast_payload,
                "featured": Location.objects.filter(is_featured=True)[:20],
                "overview": overview,
                "error": error,
                "page_title": "India Atmospheric Intelligence",
                "current_json": json.dumps(current, default=str) if current else "null",
                "nowcast_json": (
                    json.dumps(nowcast_payload, default=str)
                    if nowcast_payload
                    else "null"
                ),
                "alerts_json": json.dumps(
                    alert_payload.get("alerts") or [], default=str
                ),
                **_theme_context("sunrise", current=current, nowcast=nowcast_payload),
            }
        )
        return ctx


def _avg(values: list[float]) -> float | None:
    if not values:
        return None
    return round(sum(values) / len(values), 1)


def _india_overview(cities: list[dict]) -> dict:
    temps, rains, winds, hums = [], [], [], []
    for item in cities or []:
        if item.get("temperature_c") is not None:
            temps.append(float(item["temperature_c"]))
        if item.get("rainfall_mm") is not None:
            rains.append(float(item["rainfall_mm"]))
        if item.get("wind_speed_kmh") is not None:
            winds.append(float(item["wind_speed_kmh"]))
        if item.get("humidity_pct") is not None:
            hums.append(float(item["humidity_pct"]))
    return {
        "temperature_c": _avg(temps),
        "rainfall_mm": _avg(rains),
        "wind_speed_kmh": _avg(winds),
        "humidity_pct": _avg(hums),
        "cities": len(cities or []),
    }


def _atmosphere_state(current: dict | None, nowcast: dict | None) -> str:
    """Map observed/forecast fields to a CSS atmosphere class."""
    if not current:
        return "partly-cloudy"
    code = current.get("weather_code")
    temp = current.get("temperature_c")
    rain = current.get("rainfall_mm") or 0
    risk = (nowcast or {}).get("risk_level") or ""
    try:
        code_i = int(code) if code is not None else None
    except (TypeError, ValueError):
        code_i = None
    if code_i in {95, 96, 99} or str(risk).upper() in {"HIGH", "VERY HIGH"}:
        return "thunderstorm"
    if code_i in {65, 67, 82} or (isinstance(rain, (int, float)) and rain >= 8):
        return "heavy-rain"
    if code_i is not None and code_i in {
        51,
        53,
        55,
        56,
        57,
        61,
        63,
        66,
        80,
        81,
    }:
        return "rain"
    if isinstance(temp, (int, float)) and temp >= 38:
        return "extreme-heat"
    if code_i in {0, 1}:
        return "sunny"
    if code_i == 2:
        return "partly-cloudy"
    if code_i in {3, 45, 48}:
        return "cloudy"
    return "partly-cloudy"


def _atm_intensity(condition: str, nowcast: dict | None = None) -> str:
    risk = str((nowcast or {}).get("risk_level") or "").upper()
    if risk in {"HIGH", "VERY HIGH"} or condition in {"thunderstorm", "heavy-rain"}:
        return "high"
    if condition in {"rain", "cloudy", "extreme-heat"}:
        return "medium"
    return "low"


def _theme_context(
    theme: str,
    *,
    current: dict | None = None,
    nowcast: dict | None = None,
) -> dict:
    condition = _atmosphere_state(current, nowcast)
    return {
        "page_theme": theme,
        "atmosphere": condition,
        "atm_intensity": _atm_intensity(condition, nowcast),
    }


class NowcastingPage(TemplateView):
    template_name = "weather/nowcasting.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        city = self.request.GET.get("city", "Pune")
        try:
            ctx["nowcast"] = NowcastingService().assess(city=city)
            ctx["current"] = WeatherService().get_current(city=city)
            ctx["error"] = None
        except Exception as exc:  # noqa: BLE001
            ctx["nowcast"] = None
            ctx["current"] = None
            ctx["error"] = str(exc)
        ctx["city"] = city
        ctx["page_title"] = "Thunderstorm Nowcasting"
        ctx.update(
            _theme_context(
                "night", current=ctx.get("current"), nowcast=ctx.get("nowcast")
            )
        )
        return ctx


class LightningPage(TemplateView):
    template_name = "weather/lightning.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["lightning"] = LightningService().get_recent_india()
        ctx["page_title"] = "Lightning Monitoring"
        ctx.update(_theme_context("storm"))
        return ctx


class RainfallPage(TemplateView):
    template_name = "weather/rainfall.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        city = self.request.GET.get("city", "Pune")
        try:
            ctx["current"] = WeatherService().get_current(city=city)
            ctx["forecast"] = ForecastService().get_forecast(city=city)
            ctx["error"] = None
        except Exception as exc:  # noqa: BLE001
            ctx["current"] = None
            ctx["forecast"] = None
            ctx["error"] = str(exc)
        ctx["city"] = city
        ctx["page_title"] = "Rainfall Monitoring"
        ctx.update(_theme_context("cloudy", current=ctx.get("current")))
        return ctx


class TemperaturePage(TemplateView):
    template_name = "weather/temperature.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        city = self.request.GET.get("city", "Pune")
        try:
            ctx["current"] = WeatherService().get_current(city=city)
            ctx["forecast"] = ForecastService().get_forecast(city=city)
            ctx["error"] = None
        except Exception as exc:  # noqa: BLE001
            ctx["current"] = None
            ctx["forecast"] = None
            ctx["error"] = str(exc)
        ctx["city"] = city
        ctx["page_title"] = "Temperature Monitoring"
        ctx.update(_theme_context("cloudy", current=ctx.get("current")))
        return ctx


class WeatherPage(TemperaturePage):
    """Citizen weather observation surface (cloudy atmospheric identity)."""

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["page_title"] = "Weather"
        return ctx


class RadarPage(TemplateView):
    template_name = "weather/radar.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        city = self.request.GET.get("city", "Pune")
        try:
            ctx["current"] = WeatherService().get_current(city=city)
            ctx["error"] = None
        except Exception as exc:  # noqa: BLE001
            ctx["current"] = None
            ctx["error"] = str(exc)
        ctx["city"] = city
        ctx["page_title"] = "Radar"
        ctx.update(_theme_context("sunset", current=ctx.get("current")))
        return ctx


class AlertsPage(TemplateView):
    template_name = "weather/alerts.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        city = self.request.GET.get("city", "Pune")
        current = None
        nowcast = None
        try:
            current = WeatherService().get_current(city=city)
            nowcast = NowcastingService().assess(city=city)
        except Exception as exc:  # noqa: BLE001
            logger = __import__("logging").getLogger(__name__)
            logger.debug("Alerts page weather context skipped: %s", exc)
            current = None
            nowcast = None
        ctx["payload"] = AlertService().get_alerts(city=city)
        ctx["city"] = city
        ctx["page_title"] = "Weather Alerts"
        ctx.update(_theme_context("storm", current=current, nowcast=nowcast))
        return ctx


class SafetyPage(TemplateView):
    template_name = "safety/center.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["guidelines"] = SafetyGuideline.objects.filter(is_published=True)
        ctx["kit_items"] = EmergencyKitItem.objects.all()
        ctx["page_title"] = "Disaster Preparedness"
        ctx.update(_theme_context("cloudy"))
        return ctx


class DataSourcesPage(TemplateView):
    template_name = "dashboard/data_sources.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["sources"] = DataSource.objects.filter(is_active=True)
        ctx["page_title"] = "Data Sources"
        ctx.update(_theme_context("sunrise"))
        return ctx


class MonitoringPage(TemplateView):
    template_name = "dashboard/monitoring.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        city = self.request.GET.get("city", "Pune")
        try:
            ctx["current"] = WeatherService().get_current(city=city)
            ctx["nowcast"] = NowcastingService().assess(city=city)
            ctx["earthquakes"] = DisasterService().get_earthquakes()
            ctx["wildfires"] = DisasterService().get_wildfires()
            ctx["lightning"] = LightningService().get_recent_india()
            ctx["error"] = None
        except Exception as exc:  # noqa: BLE001
            ctx["error"] = str(exc)
        ctx["city"] = city
        ctx["hazards"] = HazardType.objects.filter(is_active=True)
        ctx["page_title"] = "Monitoring View"
        ctx.update(
            _theme_context(
                "night", current=ctx.get("current"), nowcast=ctx.get("nowcast")
            )
        )
        return ctx
