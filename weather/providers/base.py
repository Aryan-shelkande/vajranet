"""Provider exceptions and base HTTP helpers."""

from __future__ import annotations

import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

import httpx
from django.conf import settings

logger = logging.getLogger(__name__)


class ProviderError(Exception):
    """Raised when an external provider fails."""

    def __init__(self, message: str, *, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


class ProviderUnavailable(ProviderError):
    """Provider exists in architecture but is not currently usable."""


@dataclass
class WeatherSnapshot:
    """Normalized current weather payload."""

    latitude: float
    longitude: float
    observed_at: str
    temperature_c: float | None = None
    feels_like_c: float | None = None
    humidity_pct: float | None = None
    pressure_hpa: float | None = None
    wind_speed_kmh: float | None = None
    wind_direction_deg: float | None = None
    visibility_km: float | None = None
    cloud_cover_pct: float | None = None
    rainfall_mm: float | None = None
    uv_index: float | None = None
    weather_code: int | None = None
    weather_description: str = ""
    sunrise: str | None = None
    sunset: str | None = None
    cape_jkg: float | None = None
    convective_inhibition: float | None = None
    lifted_index: float | None = None
    source: str = ""
    data_kind: str = "forecast"  # Open-Meteo current is model analysis, not station obs
    timezone: str = "Asia/Kolkata"
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass
class ForecastBundle:
    hourly: list[dict[str, Any]]
    daily: list[dict[str, Any]]
    source: str
    data_kind: str = "forecast"
    generated_at: str | None = None
    timezone: str = "Asia/Kolkata"
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass
class GeoResult:
    name: str
    latitude: float
    longitude: float
    country_code: str = "IN"
    state: str = ""
    district: str = ""
    timezone: str = "Asia/Kolkata"
    population: int | None = None
    geoname_id: int | None = None


class WeatherProvider(ABC):
    name: str = "base"

    @abstractmethod
    def get_current_weather(self, latitude: float, longitude: float) -> WeatherSnapshot:
        raise NotImplementedError

    @abstractmethod
    def get_forecast(self, latitude: float, longitude: float) -> ForecastBundle:
        raise NotImplementedError


class GeocodingProvider(ABC):
    name: str = "base"

    @abstractmethod
    def search(self, query: str, *, country_code: str = "IN", count: int = 8) -> list[GeoResult]:
        raise NotImplementedError


def _log_api_request(**kwargs: Any) -> None:
    try:
        from weather.models import APIRequestLog

        APIRequestLog.objects.create(**kwargs)
    except Exception:  # noqa: BLE001 — never break weather fetch on audit logging
        logger.debug("APIRequestLog write skipped", exc_info=True)


def http_get_json(
    url: str,
    *,
    params: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    provider: str = "unknown",
) -> dict[str, Any]:
    """GET JSON with timeout, limited retries, and structured logging."""
    timeout = settings.HTTP_TIMEOUT_SECONDS
    retries = settings.HTTP_MAX_RETRIES
    last_error: Exception | None = None

    for attempt in range(retries + 1):
        started = time.perf_counter()
        try:
            with httpx.Client(timeout=timeout, follow_redirects=True) as client:
                response = client.get(url, params=params, headers=headers)
            latency_ms = int((time.perf_counter() - started) * 1000)
            if response.status_code >= 500:
                raise ProviderError(
                    f"{provider} returned {response.status_code}",
                    status_code=response.status_code,
                )
            if response.status_code >= 400:
                _log_api_request(
                    provider=provider,
                    endpoint=url[:255],
                    success=False,
                    status_code=response.status_code,
                    latency_ms=latency_ms,
                    error_message=response.text[:500],
                )
                raise ProviderError(
                    f"{provider} client error {response.status_code}",
                    status_code=response.status_code,
                )
            try:
                payload = response.json()
            except ValueError as exc:
                raise ProviderError(f"{provider} returned invalid JSON") from exc

            _log_api_request(
                provider=provider,
                endpoint=url[:255],
                success=True,
                status_code=response.status_code,
                latency_ms=latency_ms,
            )
            logger.info(
                "Weather provider request successful provider=%s status=%s latency_ms=%s",
                provider,
                response.status_code,
                latency_ms,
            )
            return payload
        except (httpx.TimeoutException, httpx.TransportError, ProviderError) as exc:
            last_error = exc
            logger.warning(
                "Provider request failed provider=%s attempt=%s error=%s",
                provider,
                attempt + 1,
                exc,
            )
            if isinstance(exc, ProviderError) and exc.status_code and 400 <= exc.status_code < 500:
                break
            time.sleep(0.4 * (attempt + 1))

    _log_api_request(
        provider=provider,
        endpoint=url[:255],
        success=False,
        error_message=str(last_error)[:500],
    )
    raise ProviderError(f"{provider} unavailable: {last_error}") from last_error
