"""Alert generation from forecast/nowcast signals — clearly labeled derived estimates."""

from __future__ import annotations

from typing import Any

from django.utils import timezone

from weather.models import WeatherAlert
from weather.services.nowcasting import NowcastingService
from weather.services.weather import LocationService, WeatherService
from weather.services.forecast import ForecastService


RECOMMENDATIONS = {
    "thunderstorm": "Stay indoors if possible, avoid open fields and isolated trees, and follow IMD/NDMA guidance.",
    "heavy_rain": "Avoid waterlogged roads, delay non-essential travel, and monitor local authority updates.",
    "extreme_heat": "Stay hydrated, avoid peak afternoon outdoor activity, and check on vulnerable persons.",
    "extreme_cold": "Wear layered clothing, limit outdoor exposure, and keep emergency heating plans ready.",
    "strong_wind": "Secure loose outdoor objects and avoid temporary structures.",
}


class AlertService:
    def __init__(self):
        self.weather = WeatherService()
        self.forecast = ForecastService()
        self.nowcast = NowcastingService()
        self.locations = LocationService()

    def get_alerts(
        self, *, city: str | None = None, location_id: int | None = None
    ) -> dict[str, Any]:
        location = self.locations.resolve(city=city, location_id=location_id)
        current = self.weather.get_current(location_id=location.id)
        forecast = self.forecast.get_forecast(location_id=location.id)
        nowcast = self.nowcast.assess(location_id=location.id)

        derived: list[dict[str, Any]] = []

        if nowcast["risk_level"] in {"HIGH", "VERY HIGH"}:
            derived.append(
                self._alert(
                    hazard_type="thunderstorm",
                    title=f"{nowcast['risk_level'].title()} thunderstorm risk",
                    description=(
                        f"Baseline nowcast indicates {nowcast['risk_level']} thunderstorm risk "
                        f"near {location.name}."
                    ),
                    severity="high" if nowcast["risk_level"] == "HIGH" else "extreme",
                    location=location,
                    recommended_action=RECOMMENDATIONS["thunderstorm"],
                    metadata={"risk_score": nowcast["risk_score"]},
                )
            )
        elif nowcast["risk_level"] == "MODERATE":
            derived.append(
                self._alert(
                    hazard_type="thunderstorm",
                    title="Moderate thunderstorm risk",
                    description=f"Atmospheric indicators suggest elevated convective potential near {location.name}.",
                    severity="moderate",
                    location=location,
                    recommended_action=RECOMMENDATIONS["thunderstorm"],
                    metadata={"risk_score": nowcast["risk_score"]},
                )
            )

        daily = forecast.get("daily") or []
        today = daily[0] if daily else {}
        precip = today.get("precipitation_mm") or 0
        precip_prob = today.get("precipitation_probability_pct") or 0
        if precip >= 50 or precip_prob >= 80:
            derived.append(
                self._alert(
                    hazard_type="heavy_rain",
                    title="Heavy rainfall possible",
                    description=(
                        f"Forecast indicates significant rainfall potential for {location.name} "
                        f"({precip} mm / {precip_prob}% probability)."
                    ),
                    severity="high" if precip >= 80 else "moderate",
                    location=location,
                    recommended_action=RECOMMENDATIONS["heavy_rain"],
                )
            )

        temp = current.get("temperature_c")
        if temp is not None and temp >= 42:
            derived.append(
                self._alert(
                    hazard_type="extreme_heat",
                    title="Extreme heat conditions",
                    description=f"Model temperature near {location.name} is {temp}°C.",
                    severity="high",
                    location=location,
                    recommended_action=RECOMMENDATIONS["extreme_heat"],
                )
            )
        if temp is not None and temp <= 5:
            derived.append(
                self._alert(
                    hazard_type="extreme_cold",
                    title="Extreme cold conditions",
                    description=f"Model temperature near {location.name} is {temp}°C.",
                    severity="high",
                    location=location,
                    recommended_action=RECOMMENDATIONS["extreme_cold"],
                )
            )

        wind = current.get("wind_speed_kmh") or 0
        if wind >= 50:
            derived.append(
                self._alert(
                    hazard_type="strong_wind",
                    title="Strong wind conditions",
                    description=f"Wind speed near {location.name} is {wind} km/h.",
                    severity="moderate",
                    location=location,
                    recommended_action=RECOMMENDATIONS["strong_wind"],
                )
            )

        # Persist active derived alerts for admin visibility (best-effort)
        for item in derived:
            WeatherAlert.objects.update_or_create(
                hazard_type=item["hazard_type"],
                location=location,
                title=item["title"],
                defaults={
                    "description": item["description"],
                    "severity": item["severity"],
                    "origin": WeatherAlert.Origin.DERIVED,
                    "area_name": location.name,
                    "starts_at": timezone.now(),
                    "source_name": "VajraNet baseline rules + Open-Meteo",
                    "recommended_action": item["recommended_action"],
                    "is_active": True,
                    "metadata": item.get("metadata") or {},
                },
            )

        db_alerts = WeatherAlert.objects.filter(
            is_active=True, location=location
        ).order_by("-updated_at")[:20]

        return {
            "location": {
                "id": location.id,
                "name": location.name,
                "state": location.state,
            },
            "alerts": [
                {
                    "hazard_type": a.hazard_type,
                    "title": a.title,
                    "description": a.description,
                    "severity": a.severity,
                    "origin": a.origin,
                    "area_name": a.area_name or location.name,
                    "starts_at": a.starts_at.isoformat() if a.starts_at else None,
                    "ends_at": a.ends_at.isoformat() if a.ends_at else None,
                    "source": a.source_name,
                    "recommended_action": a.recommended_action,
                    "data_kind": "model_estimate"
                    if a.origin == WeatherAlert.Origin.DERIVED
                    else a.origin,
                }
                for a in db_alerts
            ]
            or derived,
            "note": (
                "Alerts marked model-derived are platform estimates, not official IMD/NDMA warnings. "
                "For official alerts visit https://mausam.imd.gov.in/ and https://sachet.ndma.gov.in/"
            ),
        }

    def _alert(self, **kwargs) -> dict[str, Any]:
        location = kwargs.pop("location")
        return {
            "hazard_type": kwargs["hazard_type"],
            "title": kwargs["title"],
            "description": kwargs["description"],
            "severity": kwargs["severity"],
            "origin": "derived",
            "area_name": location.name,
            "starts_at": timezone.now().isoformat(),
            "ends_at": None,
            "source": "VajraNet baseline rules + Open-Meteo",
            "recommended_action": kwargs["recommended_action"],
            "data_kind": "model_estimate",
            "metadata": kwargs.get("metadata") or {},
        }
