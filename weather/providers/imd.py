"""IMD provider stub — API exists at api.imd.gov.in but requires authenticated access (401 without key)."""

from __future__ import annotations

from django.conf import settings

from weather.providers.base import (
    ForecastBundle,
    ProviderUnavailable,
    WeatherProvider,
    WeatherSnapshot,
)


class IMDProvider(WeatherProvider):
    """Adapter reserved for official IMD integration when credentials are available."""

    name = "imd"

    def _unavailable(self) -> None:
        if not settings.IMD_API_KEY:
            raise ProviderUnavailable(
                "IMD API requires registration/API credentials. "
                "See https://api.imd.gov.in/public/api_reference.html"
            )
        raise ProviderUnavailable(
            "IMD authenticated adapter is scaffolded but not yet wired to production credentials."
        )

    def get_current_weather(self, latitude: float, longitude: float) -> WeatherSnapshot:
        self._unavailable()
        raise AssertionError("unreachable")

    def get_forecast(self, latitude: float, longitude: float) -> ForecastBundle:
        self._unavailable()
        raise AssertionError("unreachable")
