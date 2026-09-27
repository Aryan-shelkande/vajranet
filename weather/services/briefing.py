"""Deterministic weather briefing. LLM text is optional and never required."""

from __future__ import annotations

import hashlib
import logging
from typing import Any

from django.conf import settings
from django.core.cache import cache

from weather.services.messages import briefing_text

logger = logging.getLogger(__name__)


class BriefingService:
    def compose(
        self,
        *,
        city: str,
        current: dict[str, Any] | None,
        nowcast: dict[str, Any] | None,
        risk: dict[str, Any] | None,
        hourly: list[dict[str, Any]] | None = None,
        language: str = "en",
        allow_llm: bool = False,
    ) -> dict[str, Any]:
        current = current or {}
        nowcast = nowcast or {}
        risk = risk or {}
        place = ((current.get("location") or {}).get("name")) or city or "This location"
        near = (hourly or [])[:3]
        probs = [
            row.get("precipitation_probability_pct")
            for row in near
            if isinstance(row.get("precipitation_probability_pct"), (int, float))
        ]
        rain_prob = max(probs) if probs else None
        storm = (risk.get("categories") or {}).get("storm", {}).get(
            "level"
        ) or nowcast.get("risk_level")
        text = briefing_text(
            language,
            place=place,
            condition=current.get("weather_description"),
            temp=current.get("temperature_c"),
            humidity=current.get("humidity_pct"),
            rain_prob=rain_prob,
            storm_level=storm,
        )
        payload = {
            "place": place,
            "language": language if language in {"en", "hi", "mr"} else "en",
            "text": text,
            "label": "Automated interpretation of platform data",
            "data_kind": "model_estimate",
            "mode": "deterministic",
            "provider": "platform",
            "cached": False,
            "disclaimer": (
                "This briefing restates available VajraNet fields. "
                "It is not an official forecast and not a validated AI prediction."
            ),
        }
        if not allow_llm:
            return payload

        fingerprint = hashlib.sha256(f"{place}|{language}|{text}".encode()).hexdigest()[
            :16
        ]
        cache_key = f"ai:briefing:{fingerprint}"
        cached = cache.get(cache_key)
        if cached:
            cached = dict(cached)
            cached["cached"] = True
            return cached

        try:
            from weather.services.ai_assistant import AIAssistant

            result = AIAssistant().answer(
                "Write a two sentence weather briefing using only the platform context.",
                {
                    "city": place,
                    "weather": current,
                    "nowcast": nowcast,
                    "risk": {
                        "overall_level": (risk.get("overall") or {}).get("level"),
                        "why": risk.get("why"),
                        "label": risk.get("label"),
                    },
                },
                language=language,
            )
            if result.get("mode") == "llm" and result.get("answer"):
                payload["text"] = result["answer"]
                payload["mode"] = "llm"
                payload["provider"] = result.get("provider") or "llm"
                payload["label"] = "AI interpretation of platform data"
        except Exception as exc:  # noqa: BLE001
            logger.warning("Briefing LLM skipped: %s", exc.__class__.__name__)
        ttl = int(getattr(settings, "AI_BRIEFING_CACHE_SECONDS", 600))
        cache.set(cache_key, payload, ttl)
        return payload
