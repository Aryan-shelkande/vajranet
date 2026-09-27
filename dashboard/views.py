"""Dashboard page views."""

from __future__ import annotations

import json
from urllib.parse import quote

from django.contrib import messages
from django.shortcuts import redirect, render
from django.views import View
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
                "language": _page_language(self.request),
                "alert_categories": _alert_categories(),
                "sms_languages": _sms_languages(),
                "current": current,
                "hourly": hourly[:24],
                "daily": daily[:7],
                "alerts": alert_payload.get("alerts") or [],
                "alert_note": alert_payload.get("note"),
                "nowcast": nowcast_payload,
                "risk": _safe_risk(current, hourly, nowcast_payload, alert_payload),
                "briefing": None,
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
                "sms_form": self.request.session.pop("sms_form", None),
                "sms_success": self.request.session.pop("sms_success", None),
                "ask_result": self.request.session.pop("ask_result", None),
                **_theme_context(
                    "sunrise",
                    current=current,
                    nowcast=nowcast_payload,
                ),
            }
        )
        ctx["atmosphere"] = "partly-cloudy"
        ctx["show_rainbow"] = False
        ctx["body_class"] = "sky-lock"
        ctx["briefing"] = _safe_briefing(
            city,
            current,
            nowcast_payload,
            ctx.get("risk"),
            hourly,
            ctx["language"],
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
    dynamic: bool = False,
) -> dict:
    condition = _atmosphere_state(current, nowcast)
    show_rainbow = False
    if dynamic:
        theme, show_rainbow = _dynamic_home_theme(condition, nowcast)
    return {
        "page_theme": theme,
        "atmosphere": condition,
        "atm_intensity": _atm_intensity(condition, nowcast),
        "show_rainbow": show_rainbow,
    }


def _dynamic_home_theme(condition: str, nowcast: dict | None) -> tuple[str, bool]:
    from django.utils import timezone

    hour = timezone.localtime().hour
    risk = str((nowcast or {}).get("risk_level") or "").upper()
    if condition == "thunderstorm" or risk in {"HIGH", "VERY HIGH"}:
        return "storm", False
    if condition in {"rain", "heavy-rain"}:
        return "storm", False
    if hour < 5 or hour >= 20:
        return "night", False
    if hour < 10:
        return "sunrise", False
    if hour >= 17:
        return "sunset", False
    rainbow = condition == "sunny" and risk in {"", "LOW"}
    if condition == "sunny":
        return "clear", rainbow
    return "clear", False


def _page_language(request) -> str:
    language = (request.GET.get("lang") or "en").lower()
    if language not in {"en", "hi", "mr"}:
        return "en"
    return language


def _alert_categories():
    from weather.services.messages import ALERT_CATEGORIES

    return ALERT_CATEGORIES


def _sms_languages():
    from weather.services.messages import LANGUAGES

    return LANGUAGES


def _safe_risk(current, hourly, nowcast, alert_payload):
    if not current and not nowcast:
        return None
    try:
        from weather.services.risk import AtmosphericRiskEngine

        return AtmosphericRiskEngine().evaluate(
            current=current,
            hourly=hourly,
            nowcast=nowcast,
            alerts=(alert_payload or {}).get("alerts") or [],
            radar=(nowcast or {}).get("radar"),
        )
    except Exception:  # noqa: BLE001
        return None


def _safe_briefing(city, current, nowcast, risk, hourly, language):
    if not risk and not current:
        return None
    try:
        from weather.services.briefing import BriefingService

        return BriefingService().compose(
            city=city,
            current=current,
            nowcast=nowcast,
            risk=risk,
            hourly=hourly,
            language=language,
            allow_llm=False,
        )
    except Exception:  # noqa: BLE001
        return None


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
        ctx.update(_theme_context("sunset"))
        ctx["page_theme"] = "sunset"
        ctx["atmosphere"] = "partly-cloudy"
        ctx["body_class"] = "sky-lock"
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
    """Citizen weather observation surface with a clear post-rain sky."""

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["page_title"] = "Weather"
        ctx["page_theme"] = "clear"
        ctx["atmosphere"] = "partly-cloudy"
        ctx["show_rainbow"] = True
        ctx["body_class"] = "sky-lock"
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
        ctx.update(_theme_context("storm"))
        ctx["page_theme"] = "storm"
        ctx["atmosphere"] = "thunderstorm"
        ctx["body_class"] = "sky-lock"
        return ctx


class AlertsPage(TemplateView):
    template_name = "weather/alerts.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        city = self.request.GET.get("city", "Pune")
        ctx["payload"] = {"alerts": [], "note": ""}
        try:
            ctx["payload"] = AlertService().get_alerts(city=city)
        except Exception as exc:  # noqa: BLE001
            logger = __import__("logging").getLogger(__name__)
            logger.warning(
                "Alerts page could not load alerts: %s", exc.__class__.__name__
            )
            ctx["payload"] = {
                "alerts": [],
                "note": "Alerts are temporarily unavailable.",
            }
        ctx["city"] = city
        ctx["page_title"] = "Weather Alerts"
        ctx.update(_theme_context("rain"))
        ctx["page_theme"] = "rain"
        ctx["atmosphere"] = "rain"
        ctx["body_class"] = "sky-lock"
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
        ctx.update(_theme_context("plain"))
        ctx["page_theme"] = "plain"
        ctx["atmosphere"] = "partly-cloudy"
        ctx["body_class"] = "sky-lock"
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
        ctx.update(_theme_context("night"))
        ctx["page_theme"] = "night"
        ctx["atmosphere"] = "partly-cloudy"
        ctx["body_class"] = "sky-lock"
        return ctx


class SMSSubscribeView(View):
    """Form POST for no-login SMS opt-in. Works without JavaScript."""

    def post(self, request):
        from weather.services.subscriptions import (
            SubscriptionError,
            SubscriptionService,
        )

        city = (
            request.POST.get("location") or request.POST.get("city") or "Pune"
        ).strip()
        try:
            result = SubscriptionService().subscribe(
                name=request.POST.get("name") or "",
                mobile_number=request.POST.get("mobile_number") or "",
                location_label=city,
                alert_types=request.POST.getlist("alert_types"),
                language=(request.POST.get("language") or "en").lower(),
                consent=request.POST.get("consent") == "on"
                or request.POST.get("consent") == "true",
                unsubscribe_base_url=request.build_absolute_uri("/alerts/unsubscribe"),
            )
        except SubscriptionError as exc:
            request.session["sms_form"] = {
                "field": _subscribe_field(exc.code),
                "message": _subscribe_error(exc.code),
                "name": (request.POST.get("name") or "").strip(),
                "mobile_number": (request.POST.get("mobile_number") or "").strip(),
                "location": city,
                "language": (request.POST.get("language") or "en").lower(),
                "alert_types": request.POST.getlist("alert_types"),
            }
        else:
            status = result["delivery"]["status"]
            if status in {"SENT", "DEMO"}:
                request.session.pop("sms_form", None)
                request.session["sms_success"] = {
                    "location": result["location"],
                    "status": status,
                    "simulated": status == "DEMO",
                    "repeated": bool(result.get("repeated")),
                }
            else:
                request.session.pop("sms_success", None)
                request.session["sms_form"] = {
                    "field": "form",
                    "message": "We couldn't send the welcome SMS. Please try again.",
                    "name": (request.POST.get("name") or "").strip(),
                    "mobile_number": (request.POST.get("mobile_number") or "").strip(),
                    "location": city,
                    "language": (request.POST.get("language") or "en").lower(),
                    "alert_types": request.POST.getlist("alert_types"),
                }
        return redirect(
            f"/?city={quote(city)}&lang={request.POST.get('language') or 'en'}#sms-alerts"
        )


class SMSUnsubscribeView(View):
    def get(self, request, token=None):
        if token:
            return self._apply_token(request, token)
        return render(
            request,
            "weather/unsubscribe.html",
            {
                "page_title": "Unsubscribe",
                "page_theme": "cloudy",
                "atmosphere": "cloudy",
            },
        )

    def post(self, request, token=None):
        if token:
            return self._apply_token(request, token)
        from weather.services.subscriptions import (
            SubscriptionError,
            SubscriptionService,
        )

        try:
            SubscriptionService().unsubscribe_mobile(
                request.POST.get("mobile_number") or ""
            )
        except SubscriptionError:
            messages.error(request, "Enter a valid 10-digit Indian mobile number.")
            return redirect("sms-unsubscribe")
        messages.success(
            request,
            "If this number was subscribed, SMS alerts are now turned off.",
        )
        return redirect("sms-unsubscribe")

    def _apply_token(self, request, token):
        from weather.services.subscriptions import (
            SubscriptionError,
            SubscriptionService,
        )

        try:
            SubscriptionService().unsubscribe_token(token)
        except SubscriptionError:
            messages.error(request, "This unsubscribe link is invalid or has expired.")
        else:
            messages.success(
                request, "SMS alerts are now turned off for this subscription."
            )
        return redirect("sms-unsubscribe")


class AskVajraNetView(View):
    def post(self, request):
        from weather.services.ai_assistant import AIAssistant, is_question_safe_length
        from weather.services.live_context import build_live_context

        question = (request.POST.get("question") or "").strip()
        city = (request.POST.get("city") or "Pune").strip()
        language = (request.POST.get("language") or "en").lower()
        if language not in {"en", "hi", "mr"}:
            language = "en"
        if not is_question_safe_length(question):
            messages.error(request, "Enter a question using 500 characters or fewer.")
            return redirect(f"/?city={quote(city)}#ask-vajranet")
        try:
            context = build_live_context(city) or {"city": city}
            result = AIAssistant().answer(question, context, language=language)
        except Exception:  # noqa: BLE001 — keep the page available
            messages.error(
                request,
                "The assistant is temporarily unavailable. Platform data may still be on the page.",
            )
            return redirect(f"/?city={quote(city)}#ask-vajranet")
        request.session["ask_result"] = {
            "question": question,
            "answer": result.get("answer") or "",
            "label": result.get("label") or "Platform Assistant",
            "mode": result.get("mode") or "platform",
            "provider_error": result.get("provider_error") or "",
        }
        return redirect(f"/?city={quote(city)}&lang={language}#ask-vajranet")


def _subscribe_error(code: str) -> str:
    return {
        "consent_required": "Consent is required before VajraNet can send SMS alerts.",
        "invalid_mobile": "Enter a valid 10-digit Indian mobile number.",
        "alert_types_required": "Choose at least one alert type.",
        "invalid_language": "Choose English, Hindi, or Marathi.",
        "invalid_location": "Choose a city from the list.",
        "invalid_name": "Enter your name using 2 to 80 characters.",
    }.get(code, "The subscription could not be saved. Please try again.")


def _subscribe_field(code: str) -> str:
    return {
        "consent_required": "consent",
        "invalid_mobile": "mobile_number",
        "alert_types_required": "alert_types",
        "invalid_language": "language",
        "invalid_location": "location",
        "invalid_name": "name",
    }.get(code, "form")
