"""Baseline thunderstorm nowcasting engine (rule-based, explainable)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from weather.services.forecast import ForecastService
from weather.services.weather import WeatherService


@dataclass
class NowcastResult:
    risk_level: str
    risk_score: int
    label: str
    factors: list[dict[str, Any]] = field(default_factory=list)
    inputs: dict[str, Any] = field(default_factory=dict)
    data_kind: str = "model_estimate"
    disclaimer: str = (
        "Baseline rule-based estimate for situational awareness only. "
        "Not a scientifically validated AI prediction model and not an official warning."
    )


class NowcastingEngine:
    """Transparent baseline engine — replaceable by ML models later."""

    LEVELS = (
        (25, "LOW"),
        (50, "MODERATE"),
        (75, "HIGH"),
        (101, "VERY HIGH"),
    )

    def predict(self, atmospheric: dict[str, Any]) -> NowcastResult:
        score = 0
        factors: list[dict[str, Any]] = []

        humidity = atmospheric.get("humidity_pct")
        if humidity is not None:
            if humidity >= 80:
                score += 20
                factors.append({"name": "Humidity", "value": humidity, "signal": "High"})
            elif humidity >= 65:
                score += 12
                factors.append({"name": "Humidity", "value": humidity, "signal": "Elevated"})
            else:
                factors.append({"name": "Humidity", "value": humidity, "signal": "Moderate/Low"})

        cape = atmospheric.get("cape_jkg")
        if cape is not None:
            if cape >= 2000:
                score += 30
                factors.append({"name": "CAPE", "value": cape, "signal": "Very high instability"})
            elif cape >= 1000:
                score += 22
                factors.append({"name": "CAPE", "value": cape, "signal": "High instability"})
            elif cape >= 500:
                score += 12
                factors.append({"name": "CAPE", "value": cape, "signal": "Moderate instability"})
            else:
                factors.append({"name": "CAPE", "value": cape, "signal": "Low"})

        lifted = atmospheric.get("lifted_index")
        if lifted is not None:
            if lifted <= -4:
                score += 15
                factors.append({"name": "Lifted index", "value": lifted, "signal": "Unstable"})
            elif lifted <= -2:
                score += 8
                factors.append({"name": "Lifted index", "value": lifted, "signal": "Marginally unstable"})

        cloud = atmospheric.get("cloud_cover_pct")
        if cloud is not None and cloud >= 70:
            score += 8
            factors.append({"name": "Cloud cover", "value": cloud, "signal": "High"})

        rain = atmospheric.get("rainfall_mm") or 0
        rain_prob = atmospheric.get("precipitation_probability_pct") or 0
        if rain >= 2 or rain_prob >= 60:
            score += 15
            factors.append(
                {
                    "name": "Rainfall / rain probability",
                    "value": {"rainfall_mm": rain, "probability_pct": rain_prob},
                    "signal": "Increasing / elevated",
                }
            )

        wind = atmospheric.get("wind_speed_kmh") or 0
        if wind >= 40:
            score += 10
            factors.append({"name": "Wind", "value": wind, "signal": "Strong"})
        elif wind >= 25:
            score += 5
            factors.append({"name": "Wind", "value": wind, "signal": "Breezy"})

        code = atmospheric.get("weather_code")
        if code in {95, 96, 99}:
            score += 25
            factors.append(
                {
                    "name": "Weather code",
                    "value": code,
                    "signal": "Thunderstorm indicated by forecast model",
                }
            )

        lightning_available = atmospheric.get("lightning_available")
        lightning_count = atmospheric.get("lightning_count") or 0
        if lightning_available is False:
            factors.append(
                {
                    "name": "Lightning activity",
                    "value": None,
                    "signal": "Data source unavailable",
                }
            )
        elif lightning_count:
            score += min(20, 5 + lightning_count)
            factors.append(
                {
                    "name": "Lightning activity",
                    "value": lightning_count,
                    "signal": "Elevated",
                }
            )

        score = max(0, min(100, score))
        level = "LOW"
        for threshold, name in self.LEVELS:
            if score < threshold:
                level = name
                break

        return NowcastResult(
            risk_level=level,
            risk_score=score,
            label=f"Thunderstorm risk: {level}",
            factors=factors,
            inputs=atmospheric,
        )


class NowcastingService:
    def __init__(self):
        self.engine = NowcastingEngine()
        self.weather = WeatherService()
        self.forecast = ForecastService()

    def assess(
        self, *, city: str | None = None, location_id: int | None = None
    ) -> dict[str, Any]:
        current = self.weather.get_current(city=city, location_id=location_id)
        hourly = self.forecast.get_hourly(city=city, location_id=location_id)
        next_hours = hourly.get("hourly") or []
        near = next_hours[:3]
        max_rain_prob = max(
            (h.get("precipitation_probability_pct") or 0 for h in near), default=0
        )
        max_precip = max((h.get("precipitation_mm") or 0 for h in near), default=0)
        thunder_hint = any(h.get("thunderstorm_hint") for h in near)

        # Only inputs that the baseline engine actually consumes.
        # Radar / satellite / temperature / pressure are NOT used.
        atmospheric = {
            "humidity_pct": current.get("humidity_pct"),
            "cape_jkg": current.get("cape_jkg"),
            "lifted_index": current.get("lifted_index"),
            "cloud_cover_pct": current.get("cloud_cover_pct"),
            "rainfall_mm": max(current.get("rainfall_mm") or 0, max_precip),
            "precipitation_probability_pct": max_rain_prob,
            "wind_speed_kmh": current.get("wind_speed_kmh"),
            "weather_code": (
                95 if thunder_hint else current.get("weather_code")
            ),
            "lightning_available": False,
            "lightning_count": 0,
        }
        result = self.engine.predict(atmospheric)
        return {
            "location": current.get("location"),
            "risk_level": result.risk_level,
            "risk_score": result.risk_score,
            "label": result.label,
            "factors": result.factors,
            "inputs": result.inputs,
            "data_kind": result.data_kind,
            "engine_type": "rule_based_baseline",
            "disclaimer": result.disclaimer,
            "observed_at": current.get("observed_at"),
            "timezone": current.get("timezone") or "Asia/Kolkata",
            "source_inputs": {
                "weather": current.get("source"),
                "forecast": hourly.get("source"),
                "lightning": "unavailable",
                "radar": "not_used",
                "satellite": "not_used",
            },
            "unused_inputs_note": (
                "Baseline engine does not use radar, satellite, temperature, or pressure. "
                "Lightning is unavailable and does not contribute to the score."
            ),
            "weather_snapshot": {
                "temperature_c": current.get("temperature_c"),
                "humidity_pct": current.get("humidity_pct"),
                "weather_description": current.get("weather_description"),
                "data_kind": current.get("data_kind"),
            },
        }
