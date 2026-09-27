"""Transparent multi-hazard risk estimate from platform fields.

The score is rule-based. It is a VajraNet model estimate, not a validated forecast.
"""

from __future__ import annotations

from typing import Any


def _band(score: int) -> str:
    if score >= 75:
        return "SEVERE"
    if score >= 50:
        return "HIGH"
    if score >= 25:
        return "MODERATE"
    return "LOW"


def _clamp(score: float) -> int:
    return max(0, min(100, round(score)))


def _num(value) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None


class AtmosphericRiskEngine:
    """Weighted rules over rain, storm, wind, and a rainfall flood proxy."""

    def evaluate(
        self,
        *,
        current: dict[str, Any] | None = None,
        hourly: list[dict[str, Any]] | None = None,
        nowcast: dict[str, Any] | None = None,
        alerts: list[dict[str, Any]] | None = None,
        radar: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        current = current or {}
        hourly = hourly or []
        nowcast = nowcast or {}
        alerts = alerts or []
        radar = radar or {}
        near = hourly[:3]

        rain_mm = _num(current.get("rainfall_mm")) or 0.0
        probs = [_num(row.get("precipitation_probability_pct")) or 0.0 for row in near]
        rain_prob = (
            max(probs)
            if probs
            else _num(
                (nowcast.get("inputs") or {}).get("precipitation_probability_pct")
            )
        )
        rain_prob = rain_prob or 0.0
        hour_precip = max(
            (_num(row.get("precipitation_mm")) or 0.0 for row in near), default=0.0
        )
        rain_mm = max(rain_mm, hour_precip)

        rain_score = 0
        rain_factors: list[str] = []
        if rain_prob >= 80:
            rain_score += 70
            rain_factors.append(f"Rain probability is {rain_prob:.0f}%.")
        elif rain_prob >= 60:
            rain_score += 50
            rain_factors.append(f"Rain probability is elevated at {rain_prob:.0f}%.")
        elif rain_prob >= 40:
            rain_score += 30
            rain_factors.append(f"Rain probability is {rain_prob:.0f}%.")
        elif rain_prob > 0:
            rain_factors.append(f"Rain probability is {rain_prob:.0f}%.")
        if rain_mm >= 10:
            rain_score += 25
            rain_factors.append(f"Precipitation is {rain_mm:.1f} mm.")
        elif rain_mm >= 2:
            rain_score += 12
            rain_factors.append(f"Precipitation is {rain_mm:.1f} mm.")
        rain_score = _clamp(rain_score)

        storm_score = _clamp(_num(nowcast.get("risk_score")) or 0)
        storm_factors: list[str] = []
        if nowcast.get("risk_level"):
            storm_factors.append(
                f"Thunderstorm baseline is {nowcast.get('risk_level')} "
                f"({storm_score}/100)."
            )
        for factor in (nowcast.get("factors") or [])[:4]:
            if isinstance(factor, dict) and factor.get("signal"):
                storm_factors.append(f"{factor.get('name')}: {factor.get('signal')}.")

        wind = _num(current.get("wind_speed_kmh")) or _num(
            (nowcast.get("inputs") or {}).get("wind_speed_kmh")
        )
        wind = wind or 0.0
        if wind >= 60:
            wind_score = 85
            wind_factors = [f"Wind speed is {wind:.0f} km/h."]
        elif wind >= 40:
            wind_score = 65
            wind_factors = [f"Wind speed is {wind:.0f} km/h."]
        elif wind >= 25:
            wind_score = 40
            wind_factors = [f"Wind speed is {wind:.0f} km/h."]
        else:
            wind_score = 10 if wind else 0
            wind_factors = (
                [f"Wind speed is {wind:.0f} km/h."]
                if wind
                else ["Wind speed is unavailable."]
            )

        if rain_prob >= 70 and rain_mm >= 8:
            flood_score = 78
            flood_factors = [
                "Flood score is a rainfall proxy, not a river or drainage model.",
                f"Short-range rain signal is {rain_mm:.1f} mm at {rain_prob:.0f}% probability.",
            ]
        elif rain_prob >= 60 or rain_mm >= 15:
            flood_score = 55
            flood_factors = [
                "Flood score is a rainfall proxy, not a hydrological model.",
                f"Rain probability is {rain_prob:.0f}%.",
            ]
        elif rain_prob >= 40:
            flood_score = 30
            flood_factors = [
                "Flood score is a rainfall proxy only.",
                f"Rain probability is {rain_prob:.0f}%.",
            ]
        else:
            flood_score = 8
            flood_factors = [
                "No elevated short-range rainfall signal for a flood proxy."
            ]

        if (
            radar.get("status") == "available"
            and radar.get("trend") == "nowcast_sequence"
        ):
            storm_factors.append(
                "A radar nowcast sequence is available. It is not a local trend for this city."
            )
        elif radar.get("status") == "unavailable":
            storm_factors.append("Radar activity for this city is unavailable.")

        official = [
            a
            for a in alerts
            if str(a.get("origin") or a.get("data_kind") or "").lower() == "official"
        ]
        if official:
            storm_score = _clamp(storm_score + 10)
            storm_factors.append("An official alert is present in platform records.")

        overall = _clamp(
            rain_score * 0.30
            + storm_score * 0.35
            + wind_score * 0.20
            + flood_score * 0.15
        )
        categories = {
            "rain": {
                "level": _band(rain_score),
                "score": rain_score,
                "factors": rain_factors,
            },
            "storm": {
                "level": _band(storm_score),
                "score": storm_score,
                "factors": storm_factors,
            },
            "wind": {
                "level": _band(wind_score),
                "score": wind_score,
                "factors": wind_factors,
            },
            "flood": {
                "level": _band(flood_score),
                "score": flood_score,
                "factors": flood_factors,
            },
        }
        why_bits = []
        for key in ("rain", "storm", "wind", "flood"):
            if categories[key]["level"] in {"HIGH", "SEVERE", "MODERATE"}:
                why_bits.extend(categories[key]["factors"][:2])
        if not why_bits:
            why_bits.append(
                "No category is elevated from the fields currently available."
            )
        stale = bool(current.get("stale")) or current.get("data_kind") == "cached"
        has_core = current.get("humidity_pct") is not None and (
            near or nowcast.get("risk_score") is not None
        )
        if stale or not current:
            confidence = "LOW"
        elif has_core and near:
            confidence = "HIGH"
        else:
            confidence = "MEDIUM"
        location = current.get("location") or nowcast.get("location") or {}
        return {
            "label": "VAJRANET MODEL ESTIMATE",
            "data_kind": "model_estimate",
            "validated": False,
            "location": location,
            "overall": {"level": _band(overall), "score": overall},
            "categories": categories,
            "why": " ".join(why_bits),
            "confidence": confidence,
            "confidence_note": (
                "Confidence reflects whether inputs were present and fresh. "
                "It is not a measure of scientific forecast skill."
            ),
            "observed_at": current.get("observed_at") or nowcast.get("observed_at"),
            "freshness": (
                "cached" if stale else (current.get("data_kind") or "unavailable")
            ),
            "sources": {
                "weather": current.get("source"),
                "nowcast": nowcast.get("engine_type") or "rule_based_baseline",
                "radar": radar.get("source") or "unavailable",
            },
            "disclaimer": (
                "VajraNet model estimate for situational awareness. "
                "Not a scientifically validated prediction and not an official warning."
            ),
        }
