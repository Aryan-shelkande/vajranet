"""Weather domain services — cache, fallback, location resolution."""

from __future__ import annotations

import logging
from dataclasses import asdict
from decimal import Decimal
from typing import Any

from django.conf import settings
from django.core.cache import cache
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from weather.models import DataSource, Location, WeatherObservation
from weather.providers.base import ProviderError, WeatherSnapshot
from weather.providers.imd import IMDProvider
from weather.providers.open_meteo import OpenMeteoGeocodingProvider, OpenMeteoProvider

logger = logging.getLogger(__name__)

FEATURED_CITIES: list[dict[str, Any]] = [
    {"name": "Pune", "state": "Maharashtra", "lat": 18.5204, "lon": 73.8567},
    {"name": "Mumbai", "state": "Maharashtra", "lat": 19.0760, "lon": 72.8777},
    {"name": "Delhi", "state": "Delhi", "lat": 28.6139, "lon": 77.2090},
    {"name": "Bengaluru", "state": "Karnataka", "lat": 12.9716, "lon": 77.5946},
    {"name": "Hyderabad", "state": "Telangana", "lat": 17.3850, "lon": 78.4867},
    {"name": "Chennai", "state": "Tamil Nadu", "lat": 13.0827, "lon": 80.2707},
    {"name": "Kolkata", "state": "West Bengal", "lat": 22.5726, "lon": 88.3639},
    {"name": "Ahmedabad", "state": "Gujarat", "lat": 23.0225, "lon": 72.5714},
    {"name": "Jaipur", "state": "Rajasthan", "lat": 26.9124, "lon": 75.7873},
    {"name": "Lucknow", "state": "Uttar Pradesh", "lat": 26.8467, "lon": 80.9462},
    {"name": "Nagpur", "state": "Maharashtra", "lat": 21.1458, "lon": 79.0882},
    {"name": "Nashik", "state": "Maharashtra", "lat": 19.9975, "lon": 73.7898},
    {"name": "Guwahati", "state": "Assam", "lat": 26.1445, "lon": 91.7362},
    {"name": "Srinagar", "state": "Jammu and Kashmir", "lat": 34.0837, "lon": 74.7973},
    {
        "name": "Thiruvananthapuram",
        "state": "Kerala",
        "lat": 8.5241,
        "lon": 76.9366,
    },
    {"name": "Bhubaneswar", "state": "Odisha", "lat": 20.2961, "lon": 85.8245},
    {"name": "Patna", "state": "Bihar", "lat": 25.5941, "lon": 85.1376},
    {"name": "Chandigarh", "state": "Chandigarh", "lat": 30.7333, "lon": 76.7794},
    {"name": "Bhopal", "state": "Madhya Pradesh", "lat": 23.2599, "lon": 77.4126},
    {"name": "Indore", "state": "Madhya Pradesh", "lat": 22.7196, "lon": 75.8577},
]


def get_weather_provider():
    name = settings.DEFAULT_WEATHER_PROVIDER
    if name == "imd":
        return IMDProvider()
    return OpenMeteoProvider()


class LocationService:
    def __init__(self):
        self.geocoder = OpenMeteoGeocodingProvider()

    def search(self, query: str, *, limit: int = 8) -> list[dict[str, Any]]:
        query = (query or "").strip()
        if len(query) < 2:
            return []
        cache_key = f"geo:search:{query.lower()}:{limit}"
        cached = cache.get(cache_key)
        if cached is not None:
            return cached

        local = list(
            Location.objects.filter(name__icontains=query, country_code="IN")[:limit]
        )
        results: list[dict[str, Any]] = [
            {
                "id": loc.id,
                "name": loc.name,
                "state": loc.state,
                "district": loc.district,
                "latitude": float(loc.latitude),
                "longitude": float(loc.longitude),
                "country_code": loc.country_code,
                "source": "database",
            }
            for loc in local
        ]
        try:
            remote = self.geocoder.search(query, country_code="IN", count=limit)
            for item in remote:
                if any(
                    abs(r["latitude"] - item.latitude) < 0.05
                    and abs(r["longitude"] - item.longitude) < 0.05
                    for r in results
                ):
                    continue
                results.append(
                    {
                        "id": None,
                        "name": item.name,
                        "state": item.state,
                        "district": item.district,
                        "latitude": item.latitude,
                        "longitude": item.longitude,
                        "country_code": item.country_code,
                        "population": item.population,
                        "geoname_id": item.geoname_id,
                        "source": "open_meteo_geocoding",
                    }
                )
        except ProviderError as exc:
            logger.warning("Geocoding unavailable: %s", exc)

        results = results[:limit]
        cache.set(cache_key, results, 3600)
        return results

    def resolve(self, city: str | None = None, location_id: int | None = None) -> Location:
        if location_id:
            return Location.objects.get(pk=location_id)
        if not city:
            city = "Pune"
        city = city.strip()
        existing = Location.objects.filter(name__iexact=city, country_code="IN").first()
        if existing:
            return existing
        results = self.search(city, limit=1)
        if not results:
            raise Location.DoesNotExist(f"No location found for '{city}'")
        hit = results[0]
        location, _ = Location.objects.update_or_create(
            name=hit["name"],
            state=hit.get("state") or "",
            country_code=hit.get("country_code") or "IN",
            defaults={
                "latitude": Decimal(str(hit["latitude"])),
                "longitude": Decimal(str(hit["longitude"])),
                "district": hit.get("district") or "",
                "population": hit.get("population"),
                "external_geoname_id": hit.get("geoname_id"),
            },
        )
        return location

    def ensure_featured(self) -> int:
        created = 0
        for city in FEATURED_CITIES:
            _, was_created = Location.objects.update_or_create(
                name=city["name"],
                state=city["state"],
                country_code="IN",
                defaults={
                    "latitude": Decimal(str(city["lat"])),
                    "longitude": Decimal(str(city["lon"])),
                    "is_featured": True,
                    "timezone": "Asia/Kolkata",
                },
            )
            if was_created:
                created += 1
        return created


class WeatherService:
    def __init__(self):
        self.provider = get_weather_provider()
        self.locations = LocationService()

    def get_current(
        self, *, city: str | None = None, location_id: int | None = None
    ) -> dict[str, Any]:
        location = self.locations.resolve(city=city, location_id=location_id)
        cache_key = f"weather:current:{location.id}"
        cached = cache.get(cache_key)
        if cached:
            cached = dict(cached)
            cached["from_cache"] = True
            logger.info("Using cached weather data location_id=%s", location.id)
            return cached

        try:
            snapshot = self.provider.get_current_weather(
                float(location.latitude), float(location.longitude)
            )
            payload = self._serialize_snapshot(location, snapshot, from_cache=False)
            self._persist_observation(location, snapshot)
            cache.set(cache_key, payload, settings.WEATHER_CACHE_SECONDS)
            return payload
        except ProviderError as exc:
            logger.error("Forecast/current API failed: %s", exc)
            fallback = (
                WeatherObservation.objects.filter(location=location)
                .order_by("-observed_at")
                .first()
            )
            if fallback:
                return {
                    "location": _location_dict(location),
                    "temperature_c": fallback.temperature_c,
                    "feels_like_c": fallback.feels_like_c,
                    "humidity_pct": fallback.humidity_pct,
                    "pressure_hpa": fallback.pressure_hpa,
                    "wind_speed_kmh": fallback.wind_speed_kmh,
                    "wind_direction_deg": fallback.wind_direction_deg,
                    "visibility_km": fallback.visibility_km,
                    "cloud_cover_pct": fallback.cloud_cover_pct,
                    "rainfall_mm": fallback.rainfall_mm,
                    "uv_index": fallback.uv_index,
                    "weather_code": fallback.weather_code,
                    "weather_description": fallback.weather_description,
                    "cape_jkg": fallback.cape_jkg,
                    "observed_at": fallback.observed_at.isoformat(),
                    "source": fallback.source.name if fallback.source else "cache",
                    "data_kind": "cached",
                    "from_cache": True,
                    "stale": True,
                    "message": (
                        "Live weather data temporarily unavailable. "
                        f"Showing the most recent available observation from "
                        f"{timezone.localtime(fallback.observed_at):%H:%M IST}."
                    ),
                }
            raise

    def get_map_overview(self) -> list[dict[str, Any]]:
        """Featured-city snapshot for the map. Aggregate-cached to avoid 20 cold API fan-outs."""
        cache_key = "weather:map_overview:featured"
        cached = cache.get(cache_key)
        if cached is not None:
            return cached

        cities = Location.objects.filter(is_featured=True, country_code="IN")
        overview = []
        for loc in cities:
            try:
                current = self.get_current(location_id=loc.id)
                overview.append(
                    {
                        "location": _location_dict(loc),
                        "temperature_c": current.get("temperature_c"),
                        "rainfall_mm": current.get("rainfall_mm"),
                        "weather_description": current.get("weather_description"),
                        "weather_code": current.get("weather_code"),
                        "humidity_pct": current.get("humidity_pct"),
                        "wind_speed_kmh": current.get("wind_speed_kmh"),
                        "data_kind": current.get("data_kind"),
                        "source": current.get("source"),
                        "observed_at": current.get("observed_at"),
                        "timezone": current.get("timezone"),
                    }
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning("Map overview skip %s: %s", loc, exc)
        cache.set(cache_key, overview, settings.WEATHER_CACHE_SECONDS)
        return overview

    def _serialize_snapshot(
        self, location: Location, snapshot: WeatherSnapshot, *, from_cache: bool
    ) -> dict[str, Any]:
        return {
            "location": _location_dict(location),
            "temperature_c": snapshot.temperature_c,
            "feels_like_c": snapshot.feels_like_c,
            "humidity_pct": snapshot.humidity_pct,
            "pressure_hpa": snapshot.pressure_hpa,
            "wind_speed_kmh": snapshot.wind_speed_kmh,
            "wind_direction_deg": snapshot.wind_direction_deg,
            "visibility_km": snapshot.visibility_km,
            "cloud_cover_pct": snapshot.cloud_cover_pct,
            "rainfall_mm": snapshot.rainfall_mm,
            "uv_index": snapshot.uv_index,
            "weather_code": snapshot.weather_code,
            "weather_description": snapshot.weather_description,
            "sunrise": snapshot.sunrise,
            "sunset": snapshot.sunset,
            "cape_jkg": snapshot.cape_jkg,
            "convective_inhibition": snapshot.convective_inhibition,
            "lifted_index": snapshot.lifted_index,
            "observed_at": snapshot.observed_at,
            "timezone": snapshot.timezone,
            "source": snapshot.source,
            "data_kind": snapshot.data_kind,
            "from_cache": from_cache,
            "stale": False,
            "message": None,
        }

    def _persist_observation(self, location: Location, snapshot: WeatherSnapshot) -> None:
        source, _ = DataSource.objects.get_or_create(
            slug="open-meteo",
            defaults={
                "name": "Open-Meteo",
                "data_type": "Weather forecast / model analysis",
                "update_frequency": "Hourly–3-hourly model updates",
                "coverage": "Global including India",
                "attribution": "Open-Meteo.com (CC BY 4.0)",
                "homepage_url": "https://open-meteo.com/",
                "docs_url": "https://open-meteo.com/en/docs",
                "status": DataSource.Status.AVAILABLE,
            },
        )
        observed_at = parse_datetime(snapshot.observed_at)
        if observed_at is None:
            observed_at = timezone.now()
        elif timezone.is_naive(observed_at):
            observed_at = timezone.make_aware(
                observed_at, timezone.get_current_timezone()
            )
        WeatherObservation.objects.create(
            location=location,
            source=source,
            observed_at=observed_at,
            data_kind=WeatherObservation.DataKind.FORECAST,
            temperature_c=snapshot.temperature_c,
            feels_like_c=snapshot.feels_like_c,
            humidity_pct=snapshot.humidity_pct,
            pressure_hpa=snapshot.pressure_hpa,
            wind_speed_kmh=snapshot.wind_speed_kmh,
            wind_direction_deg=snapshot.wind_direction_deg,
            visibility_km=snapshot.visibility_km,
            cloud_cover_pct=snapshot.cloud_cover_pct,
            rainfall_mm=snapshot.rainfall_mm,
            uv_index=snapshot.uv_index,
            weather_code=snapshot.weather_code,
            weather_description=snapshot.weather_description,
            cape_jkg=snapshot.cape_jkg,
            raw_payload=asdict(snapshot) if hasattr(snapshot, "__dataclass_fields__") else {},
        )


def _location_dict(location: Location) -> dict[str, Any]:
    return {
        "id": location.id,
        "name": location.name,
        "state": location.state,
        "district": location.district,
        "latitude": float(location.latitude),
        "longitude": float(location.longitude),
        "country_code": location.country_code,
        "timezone": location.timezone,
    }
