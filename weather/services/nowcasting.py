"""Baseline thunderstorm nowcasting engine (rule-based, explainable)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
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
                factors.append(
                    {"name": "Humidity", "value": humidity, "signal": "High"}
                )
            elif humidity >= 65:
                score += 12
                factors.append(
                    {"name": "Humidity", "value": humidity, "signal": "Elevated"}
                )
            else:
                factors.append(
                    {"name": "Humidity", "value": humidity, "signal": "Moderate/Low"}
                )

        cape = atmospheric.get("cape_jkg")
        if cape is not None:
            if cape >= 2000:
                score += 30
                factors.append(
                    {"name": "CAPE", "value": cape, "signal": "Very high instability"}
                )
            elif cape >= 1000:
                score += 22
                factors.append(
                    {"name": "CAPE", "value": cape, "signal": "High instability"}
                )
            elif cape >= 500:
                score += 12
                factors.append(
                    {"name": "CAPE", "value": cape, "signal": "Moderate instability"}
                )
            else:
                factors.append({"name": "CAPE", "value": cape, "signal": "Low"})

        lifted = atmospheric.get("lifted_index")
        if lifted is not None:
            if lifted <= -4:
                score += 15
                factors.append(
                    {"name": "Lifted index", "value": lifted, "signal": "Unstable"}
                )
            elif lifted <= -2:
                score += 8
                factors.append(
                    {
                        "name": "Lifted index",
                        "value": lifted,
                        "signal": "Marginally unstable",
                    }
                )

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
            "weather_code": (95 if thunder_hint else current.get("weather_code")),
            "lightning_available": False,
            "lightning_count": 0,
        }
        result = self.engine.predict(atmospheric)
        radar = _radar_signal()
        windows = build_forecast_windows(
            next_hours,
            storm_score=result.risk_score,
            radar=radar,
        )
        confidence = _confidence(current, next_hours)
        signals = _signals(windows, radar, thunder_hint, atmospheric)
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
                "Baseline thunderstorm score does not use radar, satellite, temperature, "
                "or pressure. Radar status is reported separately and does not change "
                "the score. Lightning is unavailable and does not contribute."
            ),
            "experimental_label": "MODEL ESTIMATE — EXPERIMENTAL",
            "windows": windows,
            "precipitation_trend": windows.get("precipitation_trend"),
            "radar": radar,
            "confidence": confidence,
            "confidence_note": (
                "Confidence reflects input completeness, not verified forecast skill."
            ),
            "signals": signals,
            "weather_snapshot": {
                "temperature_c": current.get("temperature_c"),
                "humidity_pct": current.get("humidity_pct"),
                "weather_description": current.get("weather_description"),
                "data_kind": current.get("data_kind"),
            },
        }


def _parse_time(value: Any) -> datetime | None:
    if not value:
        return None
    text = str(value).replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def _clock(value: datetime | None) -> str:
    if value is None:
        return ""
    return value.strftime("%I:%M %p").lstrip("0")


def _level_from_score(score: int) -> str:
    if score >= 75:
        return "HIGH"
    if score >= 50:
        return "MODERATE"
    if score >= 25:
        return "LOW"
    return "LOW"


def build_forecast_windows(
    hourly: list[dict[str, Any]] | None,
    *,
    storm_score: int = 0,
    radar: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Short-range windows from hourly forecast rows already retrieved."""
    rows = list(hourly or [])
    trend = _precipitation_trend(rows)
    return {
        "next_60_minutes": _window(rows[:1], "Next 60 minutes", storm_score),
        "next_3_hours": _window(rows[:3], "Next 3 hours", storm_score, slots=rows[:4]),
        "precipitation_trend": trend,
        "radar": radar or {"status": "unavailable", "trend": "unavailable"},
        "experimental_label": "MODEL ESTIMATE — EXPERIMENTAL",
    }


def _window(
    rows: list[dict[str, Any]],
    label: str,
    storm_score: int,
    slots: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    if not rows:
        return {
            "label": label,
            "available": False,
            "data_kind": "unavailable",
            "experimental_label": "MODEL ESTIMATE — EXPERIMENTAL",
        }
    probs = [float(row.get("precipitation_probability_pct") or 0) for row in rows]
    precips = [float(row.get("precipitation_mm") or 0) for row in rows]
    thunder = any(bool(row.get("thunderstorm_hint")) for row in rows)
    peak_prob = max(probs) if probs else 0
    risk_pct = int(min(100, max(storm_score, peak_prob, 70 if thunder else 0)))
    start = _parse_time(rows[0].get("time"))
    end_source = _parse_time(rows[-1].get("time"))
    end = end_source + timedelta(hours=1) if end_source else None
    slot_rows = slots if slots is not None else rows
    return {
        "label": label,
        "available": True,
        "data_kind": "forecast",
        "experimental_label": "MODEL ESTIMATE — EXPERIMENTAL",
        "precipitation_probability_pct": round(peak_prob, 1),
        "precipitation_mm": round(sum(precips), 2),
        "thunderstorm_risk_pct": risk_pct,
        "thunderstorm_level": _level_from_score(risk_pct),
        "expected_window": _span(start, end),
        "thunderstorm_hint": thunder,
        "slots": [_slot(row, storm_score) for row in slot_rows],
    }


def _slot(row: dict[str, Any], storm_score: int) -> dict[str, Any]:
    start = _parse_time(row.get("time"))
    prob = row.get("precipitation_probability_pct")
    hint = bool(row.get("thunderstorm_hint"))
    prob_value = float(prob) if isinstance(prob, (int, float)) else None
    risk_pct = None
    if prob_value is not None:
        risk_pct = int(min(100, max(storm_score * 0.5, prob_value, 70 if hint else 0)))
    return {
        "time": row.get("time"),
        "label": _clock(start) or str(row.get("time") or ""),
        "precipitation_probability_pct": prob_value,
        "thunderstorm_risk_pct": risk_pct,
        "data_kind": "forecast",
    }


def _span(start: datetime | None, end: datetime | None) -> str:
    if start and end:
        return f"{_clock(start)} – {_clock(end)}"
    if start:
        return _clock(start)
    return ""


def _precipitation_trend(rows: list[dict[str, Any]]) -> str:
    if len(rows) < 2:
        return "unavailable"
    first = rows[0].get("precipitation_probability_pct")
    later = rows[min(2, len(rows) - 1)].get("precipitation_probability_pct")
    if not isinstance(first, (int, float)) or not isinstance(later, (int, float)):
        return "unavailable"
    if later - first >= 15:
        return "increasing"
    if first - later >= 15:
        return "decreasing"
    return "steady"


def _confidence(current: dict[str, Any], hourly: list[dict[str, Any]]) -> str:
    stale = bool(current.get("stale")) or current.get("data_kind") == "cached"
    if stale or not hourly:
        return "LOW"
    if current.get("humidity_pct") is not None and len(hourly) >= 3:
        return "HIGH"
    return "MEDIUM"


def _signals(
    windows: dict[str, Any],
    radar: dict[str, Any],
    thunder_hint: bool,
    atmospheric: dict[str, Any],
) -> list[str]:
    signals: list[str] = []
    if windows.get("precipitation_trend") == "increasing":
        signals.append("Increasing precipitation")
    if radar.get("trend") == "nowcast_sequence":
        signals.append("Radar nowcast sequence available")
    if thunder_hint or atmospheric.get("weather_code") in {95, 96, 99}:
        signals.append("Elevated thunderstorm indicators")
    if not signals:
        signals.append("No elevated short-range signal in the available fields")
    return signals


def _radar_signal() -> dict[str, Any]:
    try:
        from weather.services.lightning import RadarService

        payload = RadarService().get_radar()
    except Exception:  # noqa: BLE001 — radar must not break nowcast
        payload = {"available": False, "frames": []}
    frames = payload.get("frames") or []
    nowcast_frames = [frame for frame in frames if frame.get("kind") == "nowcast"]
    observed = [frame for frame in frames if frame.get("kind") == "observed"]
    if not payload.get("available"):
        return {
            "status": "unavailable",
            "trend": "unavailable",
            "source": None,
            "data_kind": "unavailable",
            "note": "Radar data is unavailable.",
        }
    trend = "nowcast_sequence" if nowcast_frames else "observed_only"
    note = (
        "RainViewer mosaic includes a short nowcast sequence. "
        "This is not a measured local radar trend for the selected city."
        if nowcast_frames
        else "Radar mosaic is available without a nowcast sequence."
    )
    return {
        "status": "available",
        "trend": trend,
        "observed_frames": len(observed),
        "nowcast_frames": len(nowcast_frames),
        "source": payload.get("source") or "RainViewer",
        "data_kind": "observed",
        "note": note,
    }
