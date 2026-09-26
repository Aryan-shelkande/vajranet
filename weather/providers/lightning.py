"""Lightning data provider abstraction.

Blitzortung/LightningMaps raw feeds require participant credentials and prohibit
commercial redistribution of raw strike data. Without credentials we report
unavailable rather than inventing strikes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from django.conf import settings

from weather.providers.base import ProviderUnavailable


@dataclass
class LightningStrike:
    latitude: float
    longitude: float
    observed_at: str
    intensity: float | None = None
    polarity: str | None = None
    source: str = ""


@dataclass
class LightningBundle:
    available: bool
    strikes: list[LightningStrike] = field(default_factory=list)
    message: str = ""
    window_minutes: int = 60
    source: str = ""
    data_kind: str = "observed"
    metadata: dict[str, Any] = field(default_factory=dict)


class LightningProvider:
    name = "base"

    def get_recent(
        self,
        *,
        west: float,
        south: float,
        east: float,
        north: float,
        minutes: int = 60,
    ) -> LightningBundle:
        raise NotImplementedError


class UnavailableLightningProvider(LightningProvider):
    name = "unavailable"

    def get_recent(
        self,
        *,
        west: float,
        south: float,
        east: float,
        north: float,
        minutes: int = 60,
    ) -> LightningBundle:
        has_creds = bool(
            settings.BLITZORTUNG_USERNAME and settings.BLITZORTUNG_PASSWORD
        )
        if has_creds:
            # Credentials present but live fetch not implemented without legal review.
            raise ProviderUnavailable(
                "Blitzortung credentials are configured, but raw strike redistribution "
                "requires project participation terms compliance. Integration pending."
            )
        return LightningBundle(
            available=False,
            strikes=[],
            message=(
                "Lightning data source unavailable. No public redistributable lightning "
                "API is configured. Blitzortung requires participant credentials; "
                "commercial use of raw data is prohibited."
            ),
            window_minutes=minutes,
            source="None",
            data_kind="unavailable",
        )
