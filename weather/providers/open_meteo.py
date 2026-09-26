"""Open-Meteo weather + geocoding providers (verified public APIs, no key required)."""

from __future__ import annotations

from typing import Any

from weather.providers.base import (
    ForecastBundle,
    GeoResult,
    GeocodingProvider,
    WeatherProvider,
    WeatherSnapshot,
    http_get_json,
)
from weather.providers.wmo import describe_weather_code

FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"

CURRENT_FIELDS = [
    "temperature_2m",
    "relative_humidity_2m",
    "apparent_temperature",
    "precipitation",
    "weather_code",
    "cloud_cover",
    "pressure_msl",
    "wind_speed_10m",
    "wind_direction_10m",
    "visibility",
    "cape",
    "convective_inhibition",
    "lifted_index",
]

HOURLY_FIELDS = [
    "temperature_2m",
    "relative_humidity_2m",
    "precipitation_probability",
    "precipitation",
    "weather_code",
    "wind_speed_10m",
    "cloud_cover",
    "cape",
]

DAILY_FIELDS = [
    "weather_code",
    "temperature_2m_max",
    "temperature_2m_min",
    "precipitation_sum",
    "precipitation_probability_max",
    "wind_speed_10m_max",
    "sunrise",
    "sunset",
]


class OpenMeteoProvider(WeatherProvider):
    name = "open_meteo"

    def get_current_weather(self, latitude: float, longitude: float) -> WeatherSnapshot:
        params = {
            "latitude": latitude,
            "longitude": longitude,
            "current": ",".join(CURRENT_FIELDS),
            "daily": "sunrise,sunset",
            "forecast_days": 1,
            "timezone": "Asia/Kolkata",
            "wind_speed_unit": "kmh",
        }
        data = http_get_json(FORECAST_URL, params=params, provider=self.name)
        current = data.get("current") or {}
        daily = data.get("daily") or {}
        code = current.get("weather_code")
        visibility_m = current.get("visibility")
        return WeatherSnapshot(
            latitude=float(data.get("latitude", latitude)),
            longitude=float(data.get("longitude", longitude)),
            observed_at=str(current.get("time") or ""),
            temperature_c=_f(current.get("temperature_2m")),
            feels_like_c=_f(current.get("apparent_temperature")),
            humidity_pct=_f(current.get("relative_humidity_2m")),
            pressure_hpa=_f(current.get("pressure_msl")),
            wind_speed_kmh=_f(current.get("wind_speed_10m")),
            wind_direction_deg=_f(current.get("wind_direction_10m")),
            visibility_km=(visibility_m / 1000.0) if visibility_m is not None else None,
            cloud_cover_pct=_f(current.get("cloud_cover")),
            rainfall_mm=_f(current.get("precipitation")),
            weather_code=int(code) if code is not None else None,
            weather_description=describe_weather_code(code),
            sunrise=_first(daily.get("sunrise")),
            sunset=_first(daily.get("sunset")),
            cape_jkg=_f(current.get("cape")),
            convective_inhibition=_f(current.get("convective_inhibition")),
            lifted_index=_f(current.get("lifted_index")),
            source="Open-Meteo",
            data_kind="forecast",  # model analysis / nowcast blend — not station observation
            timezone=data.get("timezone") or "Asia/Kolkata",
            raw=data,
        )

    def get_forecast(self, latitude: float, longitude: float) -> ForecastBundle:
        params = {
            "latitude": latitude,
            "longitude": longitude,
            "hourly": ",".join(HOURLY_FIELDS),
            "daily": ",".join(DAILY_FIELDS),
            "forecast_days": 7,
            "timezone": "Asia/Kolkata",
            "wind_speed_unit": "kmh",
        }
        data = http_get_json(FORECAST_URL, params=params, provider=self.name)
        hourly_raw = data.get("hourly") or {}
        daily_raw = data.get("daily") or {}
        hourly = _zip_series(hourly_raw, limit=24)
        daily = _zip_series(daily_raw, limit=7)

        for row in hourly:
            code = row.get("weather_code")
            row["weather_description"] = describe_weather_code(code)
            row["thunderstorm_hint"] = _is_thunder_code(code) or (
                (row.get("cape") or 0) >= 1000
            )
            row["temperature_c"] = row.pop("temperature_2m", None)
            row["humidity_pct"] = row.pop("relative_humidity_2m", None)
            row["precipitation_mm"] = row.pop("precipitation", None)
            row["precipitation_probability_pct"] = row.pop(
                "precipitation_probability", None
            )
            row["wind_speed_kmh"] = row.pop("wind_speed_10m", None)
            row["cloud_cover_pct"] = row.pop("cloud_cover", None)

        for row in daily:
            code = row.get("weather_code")
            row["weather_description"] = describe_weather_code(code)
            row["thunderstorm_hint"] = _is_thunder_code(code)
            row["temperature_max_c"] = row.pop("temperature_2m_max", None)
            row["temperature_min_c"] = row.pop("temperature_2m_min", None)
            row["precipitation_mm"] = row.pop("precipitation_sum", None)
            row["precipitation_probability_pct"] = row.pop(
                "precipitation_probability_max", None
            )
            row["wind_speed_kmh"] = row.pop("wind_speed_10m_max", None)

        return ForecastBundle(
            hourly=hourly,
            daily=daily,
            source="Open-Meteo",
            data_kind="forecast",
            generated_at=str((data.get("current") or {}).get("time") or ""),
            timezone=data.get("timezone") or "Asia/Kolkata",
            raw=data,
        )


class OpenMeteoGeocodingProvider(GeocodingProvider):
    name = "open_meteo_geocoding"

    def search(
        self, query: str, *, country_code: str = "IN", count: int = 8
    ) -> list[GeoResult]:
        params: dict[str, Any] = {
            "name": query.strip(),
            "count": count,
            "language": "en",
            "format": "json",
        }
        if country_code:
            params["countryCode"] = country_code
        data = http_get_json(GEOCODING_URL, params=params, provider=self.name)
        results = []
        for item in data.get("results") or []:
            results.append(
                GeoResult(
                    name=item.get("name") or query,
                    latitude=float(item["latitude"]),
                    longitude=float(item["longitude"]),
                    country_code=item.get("country_code") or country_code or "",
                    state=item.get("admin1") or "",
                    district=item.get("admin2") or "",
                    timezone=item.get("timezone") or "Asia/Kolkata",
                    population=item.get("population"),
                    geoname_id=item.get("id"),
                )
            )
        return results


def _f(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _first(values: Any) -> str | None:
    if isinstance(values, list) and values:
        return str(values[0])
    return None


def _zip_series(series: dict[str, Any], *, limit: int) -> list[dict[str, Any]]:
    times = series.get("time") or []
    keys = [k for k in series.keys() if k != "time"]
    rows: list[dict[str, Any]] = []
    for idx, t in enumerate(times[:limit]):
        row: dict[str, Any] = {"time": t}
        for key in keys:
            values = series.get(key) or []
            row[key] = values[idx] if idx < len(values) else None
        rows.append(row)
    return rows


def _is_thunder_code(code: Any) -> bool:
    try:
        c = int(code)
    except (TypeError, ValueError):
        return False
    return c in {95, 96, 99}
