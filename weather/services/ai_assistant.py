"""Vajra AI — configurable LLM assistant with platform guidance fallback.

When an LLM provider/API key is unavailable, answers are structured from
platform context only. Those responses are labeled as platform guidance,
not as model-generated speech.
"""

from __future__ import annotations

import logging
import re
from typing import Any

import httpx
from django.conf import settings

logger = logging.getLogger(__name__)

SAFETY_DISCLAIMER = (
    "Follow official instructions from local authorities such as IMD, NDMA, "
    "or your state disaster management agency. This assistant does not issue "
    "official warnings, evacuation orders, or medical advice."
)

SYSTEM_PROMPT = """You are Vajra AI, an atmospheric safety assistant for VajraNet,
an India-focused weather and disaster intelligence platform.

Rules:
- Use only the provided platform context. Do not invent observations.
- Never claim to issue official government warnings or evacuation orders.
- Never claim guaranteed predictions or certainty about dangerous weather.
- Never give medical advice.
- Clearly distinguish observed, forecast, cached, model estimate, and derived risk.
- For dangerous conditions, tell users to follow official authorities.
- Keep answers concise (under 180 words), calm, and actionable.
- If lightning or wildfire data is unavailable, say so plainly.
"""


class AIAssistant:
    """Answer user questions using optional LLM + platform context."""

    def answer(
        self, question: str, context: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        question = (question or "").strip()
        context = context or {}
        if not question:
            return {
                "answer": "Ask about weather, alerts, nowcast risk, or safety for a city.",
                "mode": "platform",
                "provider": "platform",
                "label": "Platform Assistant",
                "disclaimer": SAFETY_DISCLAIMER,
            }

        provider = (getattr(settings, "AI_PROVIDER", "platform") or "platform").lower()
        api_key = getattr(settings, "OPENAI_API_KEY", "") or ""

        if provider == "openai" and api_key:
            try:
                llm_answer = self._openai_answer(question, context, api_key)
                return {
                    "answer": llm_answer,
                    "mode": "llm",
                    "provider": "openai",
                    "label": "Vajra AI — AI model enabled",
                    "disclaimer": SAFETY_DISCLAIMER,
                }
            except Exception as exc:  # noqa: BLE001 — graceful degrade
                logger.warning("AI provider failed: %s", exc)
                fallback = self._platform_answer(question, context)
                fallback["provider_error"] = (
                    "AI assistant unavailable — showing platform guidance"
                )
                return fallback

        if provider == "ollama":
            try:
                llm_answer = self._ollama_answer(question, context)
                return {
                    "answer": llm_answer,
                    "mode": "llm",
                    "provider": "ollama",
                    "label": "Vajra AI — local model enabled",
                    "disclaimer": SAFETY_DISCLAIMER,
                }
            except Exception as exc:  # noqa: BLE001
                logger.warning("Ollama provider failed: %s", exc)
                fallback = self._platform_answer(question, context)
                fallback["provider_error"] = (
                    "Local AI unavailable — showing platform guidance"
                )
                return fallback

        result = self._platform_answer(question, context)
        if provider == "openai" and not api_key:
            result["provider_error"] = (
                "AI assistant unavailable — showing platform guidance"
            )
        return result

    def _ollama_answer(self, question: str, context: dict[str, Any]) -> str:
        base = (
            getattr(settings, "OLLAMA_BASE_URL", "http://127.0.0.1:11434") or ""
        ).rstrip("/")
        model = getattr(settings, "OLLAMA_MODEL", "llama3.2") or "llama3.2"
        timeout = float(getattr(settings, "HTTP_TIMEOUT_SECONDS", 15.0))
        payload = {
            "model": model,
            "stream": False,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": (
                        f"Platform context:\n{self._format_context(context)}\n\n"
                        f"User question: {question}"
                    ),
                },
            ],
        }
        with httpx.Client(timeout=timeout) as client:
            res = client.post(f"{base}/api/chat", json=payload)
            res.raise_for_status()
            data = res.json()
        text = ((data.get("message") or {}).get("content") or "").strip()
        if not text:
            raise RuntimeError("empty_ollama_response")
        return text

    def _openai_answer(
        self, question: str, context: dict[str, Any], api_key: str
    ) -> str:
        model = getattr(settings, "OPENAI_MODEL", "gpt-4o-mini") or "gpt-4o-mini"
        timeout = float(getattr(settings, "HTTP_TIMEOUT_SECONDS", 15.0))
        payload = {
            "model": model,
            "temperature": 0.2,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": (
                        f"Platform context (JSON-like summary):\n"
                        f"{self._format_context(context)}\n\n"
                        f"User question: {question}"
                    ),
                },
            ],
        }
        with httpx.Client(timeout=timeout) as client:
            res = client.post(
                "https://api.openai.com/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
            res.raise_for_status()
            data = res.json()
        choice = (data.get("choices") or [{}])[0]
        message = (choice.get("message") or {}).get("content") or ""
        text = message.strip()
        if not text:
            raise RuntimeError("empty_llm_response")
        return text

    def _platform_answer(
        self, question: str, context: dict[str, Any]
    ) -> dict[str, Any]:
        q = question.lower()
        city = (
            context.get("city")
            or (context.get("location") or {}).get("name")
            or "the selected location"
        )
        weather = context.get("weather") or {}
        nowcast = context.get("nowcast") or {}
        alerts = context.get("alerts") or []
        safety = context.get("safety") or {}

        temp = weather.get("temperature_c")
        desc = weather.get("weather_description") or "unavailable"
        rain = weather.get("rainfall_mm")
        humidity = weather.get("humidity_pct")
        wind = weather.get("wind_speed_kmh")
        risk = nowcast.get("risk_level") or "unavailable"
        risk_label = nowcast.get("label") or ""

        lines: list[str] = []

        if any(k in q for k in ("safe", "outside", "go out", "outdoor", "leave home")):
            lines.append(self._outdoor_guidance(city, risk, alerts, weather))
        elif any(k in q for k in ("lightning", "thunder")):
            lines.append(
                f"For {city}: thunderstorm baseline risk is {risk}"
                + (f" ({risk_label})" if risk_label else "")
                + ". Live lightning observations are unavailable unless a redistributable "
                "provider is configured. Stay indoors during storms, avoid open fields "
                "and tall isolated objects."
            )
        elif any(k in q for k in ("alert", "warning", "advisory")):
            if alerts:
                titles = "; ".join(
                    f"{a.get('title', 'Alert')} ({a.get('severity', 'unknown')}, "
                    f"{a.get('data_kind') or a.get('origin') or 'derived'})"
                    for a in alerts[:4]
                )
                lines.append(
                    f"Active platform alerts for {city}: {titles}. "
                    "These may be derived risk estimates — verify with IMD / NDMA."
                )
            else:
                lines.append(
                    f"No active platform-derived alerts for {city} right now. "
                    "Still check IMD Mausam and NDMA SACHET for official notices."
                )
        elif any(k in q for k in ("rain", "rainfall", "precip")):
            lines.append(
                f"In {city}, current precipitation is "
                f"{rain if rain is not None else 'unavailable'} mm"
                f"{f' with humidity {humidity:.0f}%' if isinstance(humidity, (int, float)) else ''}."
                f" Condition: {desc}."
            )
        elif any(k in q for k in ("temp", "heat", "hot", "cold", "weather")):
            feels = weather.get("feels_like_c")
            lines.append(
                f"Weather in {city}: {temp if temp is not None else '—'}°C"
                f"{f' (feels like {feels:.0f}°C)' if isinstance(feels, (int, float)) else ''}, "
                f"{desc}."
                f"{f' Wind {wind:.0f} km/h.' if isinstance(wind, (int, float)) else ''}"
            )
            if isinstance(temp, (int, float)) and temp >= 38:
                lines.append(
                    "Heat advisory conditions: limit outdoor exposure, hydrate, "
                    "and follow local heat guidance."
                )
        elif any(
            k in q
            for k in ("flood", "cyclone", "earthquake", "wildfire", "heatwave", "hail")
        ):
            topic = next(
                (
                    t
                    for t in (
                        "flood",
                        "cyclone",
                        "earthquake",
                        "wildfire",
                        "heatwave",
                        "hail",
                    )
                    if t in q
                ),
                "hazard",
            )
            tip = (safety.get(topic) or safety.get("general") or "").strip()
            lines.append(
                tip
                or (
                    f"Open the Safety Center for {topic} guidance. "
                    "In emergencies, follow local authority instructions."
                )
            )
        elif any(k in q for k in ("nowcast", "risk", "storm")):
            factors = nowcast.get("factors") or []
            factor_bits = ", ".join(
                f"{f.get('name')}: {f.get('signal')}"
                for f in factors[:4]
                if isinstance(f, dict)
            )
            lines.append(
                f"Baseline nowcast for {city}: {risk}"
                + (f" — {risk_label}" if risk_label else "")
                + ". This is a derived model estimate, not an official warning."
                + (f" Factors: {factor_bits}." if factor_bits else "")
            )
        else:
            lines.append(
                f"Platform snapshot for {city}: {temp if temp is not None else '—'}°C, "
                f"{desc}; rainfall {rain if rain is not None else '—'} mm; "
                f"thunderstorm baseline risk {risk}. "
                "Ask about going outside, rainfall, alerts, or lightning safety for more detail."
            )

        lines.append(SAFETY_DISCLAIMER)
        return {
            "answer": " ".join(lines),
            "mode": "platform",
            "provider": "platform",
            "label": "Platform Assistant",
            "disclaimer": SAFETY_DISCLAIMER,
        }

    def _outdoor_guidance(
        self,
        city: str,
        risk: str,
        alerts: list,
        weather: dict[str, Any],
    ) -> str:
        risk_u = str(risk).upper()
        rain = weather.get("rainfall_mm") or 0
        code = weather.get("weather_code")
        high_risk = risk_u in {"HIGH", "VERY HIGH"} or any(
            str(a.get("severity", "")).lower() in {"high", "extreme"} for a in alerts
        )
        stormy = code in {95, 96, 99} or (isinstance(rain, (int, float)) and rain >= 5)

        if high_risk or stormy:
            return (
                f"Conditions around {city} look unsettled (thunderstorm baseline risk: {risk}). "
                "Prefer staying indoors or delaying non-essential outdoor plans until "
                "official guidance and local conditions improve."
            )
        if risk_u == "MODERATE":
            return (
                f"Outdoor conditions in {city} are usable with caution. "
                f"Thunderstorm baseline risk is {risk}. Keep an eye on sky conditions "
                "and official IMD/NDMA updates."
            )
        return (
            f"Based on available platform data for {city}, outdoor conditions look relatively "
            f"settled (baseline risk {risk}). Still verify local forecasts before long trips."
        )

    def _format_context(self, context: dict[str, Any]) -> str:
        """Compact, non-private context string for the LLM."""
        weather = context.get("weather") or {}
        nowcast = context.get("nowcast") or {}
        alerts = context.get("alerts") or []
        location = context.get("location") or {}
        city = context.get("city") or location.get("name") or "unknown"
        parts = [
            f"Location: {city}",
            f"Temperature: {weather.get('temperature_c', 'n/a')}°C",
            f"Condition: {weather.get('weather_description', 'n/a')}",
            f"Weather code: {weather.get('weather_code', 'n/a')}",
            f"Rain: {weather.get('rainfall_mm', 'n/a')} mm",
            f"Humidity: {weather.get('humidity_pct', 'n/a')}%",
            f"Wind: {weather.get('wind_speed_kmh', 'n/a')} km/h",
            (
                f"Thunderstorm risk: {nowcast.get('risk_level', 'n/a')} "
                f"(engine={nowcast.get('engine_type', 'baseline')}, "
                f"kind={nowcast.get('data_kind', 'model_estimate')})"
            ),
            f"Lightning data: {context.get('lightning_status', 'unavailable')}",
        ]
        if alerts:
            alert_txt = "; ".join(
                f"{a.get('title')} [{a.get('severity')}/{a.get('data_kind') or a.get('origin')}]"
                for a in alerts[:5]
            )
            parts.append(f"Active alerts: {alert_txt}")
        else:
            parts.append("Active alerts: none")
        return "\n".join(parts)


def sanitize_ai_context(raw: dict[str, Any] | None) -> dict[str, Any]:
    """Allowlist context fields so private user data is not forwarded."""
    if not isinstance(raw, dict):
        return {}
    out: dict[str, Any] = {}
    if isinstance(raw.get("city"), str):
        out["city"] = raw["city"][:80]
    if isinstance(raw.get("lightning_status"), str):
        out["lightning_status"] = raw["lightning_status"][:80]
    loc = raw.get("location")
    if isinstance(loc, dict):
        out["location"] = {
            "name": str(loc.get("name") or "")[:80],
            "state": str(loc.get("state") or "")[:80],
            "country_code": str(loc.get("country_code") or "IN")[:8],
        }
    weather = raw.get("weather")
    if isinstance(weather, dict):
        out["weather"] = {
            k: weather.get(k)
            for k in (
                "temperature_c",
                "feels_like_c",
                "humidity_pct",
                "wind_speed_kmh",
                "pressure_hpa",
                "rainfall_mm",
                "weather_code",
                "weather_description",
                "cloud_cover_pct",
                "data_kind",
                "source",
            )
        }
    nowcast = raw.get("nowcast")
    if isinstance(nowcast, dict):
        factors = nowcast.get("factors")
        clean_factors = []
        if isinstance(factors, list):
            for f in factors[:8]:
                if isinstance(f, dict):
                    clean_factors.append(
                        {
                            "name": str(f.get("name") or "")[:60],
                            "signal": str(f.get("signal") or "")[:60],
                            "value": str(f.get("value") or "")[:60],
                        }
                    )
        out["nowcast"] = {
            "risk_level": str(nowcast.get("risk_level") or "")[:40],
            "risk_score": nowcast.get("risk_score"),
            "label": str(nowcast.get("label") or "")[:120],
            "engine_type": str(nowcast.get("engine_type") or "")[:60],
            "data_kind": str(nowcast.get("data_kind") or "")[:60],
            "factors": clean_factors,
        }
    alerts = raw.get("alerts")
    if isinstance(alerts, list):
        clean_alerts = []
        for a in alerts[:6]:
            if isinstance(a, dict):
                clean_alerts.append(
                    {
                        "title": str(a.get("title") or "")[:120],
                        "severity": str(a.get("severity") or "")[:40],
                        "data_kind": str(a.get("data_kind") or a.get("origin") or "")[
                            :60
                        ],
                        "area_name": str(a.get("area_name") or "")[:80],
                    }
                )
        out["alerts"] = clean_alerts
    safety = raw.get("safety")
    if isinstance(safety, dict):
        out["safety"] = {
            str(k)[:40]: str(v)[:400]
            for k, v in list(safety.items())[:12]
            if isinstance(v, str)
        }
    return out


def is_question_safe_length(question: str) -> bool:
    return (
        bool(question)
        and len(question) <= 500
        and not re.search(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", question)
    )
