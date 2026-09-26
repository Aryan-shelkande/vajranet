"""Audit smoke checks using a properly initialized Django environment.

This command exists because importing Django models via bare ``python -c``
(without manage.py / django.setup) raises ImproperlyConfigured. That is
expected Django behavior, not a broken settings module.
"""

from __future__ import annotations

import json
from django.core.cache import cache
from django.core.management.base import BaseCommand
from django.test import Client

from weather.providers.base import ProviderError
from weather.services.lightning import LightningService
from weather.services.nowcasting import NowcastingService
from weather.services.weather import LocationService, WeatherService


class Command(BaseCommand):
    help = "Run foundation smoke checks with Django fully configured"

    def handle(self, *args, **options):
        failures: list[str] = []

        # 1) Settings are configured in this process
        from django.conf import settings

        self.stdout.write(f"DJANGO_SETTINGS_MODULE ok · DEBUG={settings.DEBUG}")

        # 2) Live provider (optional network) for Pune/Mumbai
        LocationService().ensure_featured()
        weather = WeatherService()
        for city in ("Pune", "Mumbai"):
            try:
                cache.delete(f"weather:current:{LocationService().resolve(city=city).id}")
                data = weather.get_current(city=city)
                self.stdout.write(
                    f"LIVE {city}: {data.get('temperature_c')}°C "
                    f"source={data.get('source')} kind={data.get('data_kind')} "
                    f"tz={data.get('timezone')} at={data.get('observed_at')}"
                )
                if data.get("temperature_c") is None:
                    failures.append(f"{city} missing temperature")
            except ProviderError as exc:
                failures.append(f"{city} provider error: {exc}")

        # 3) Cache hit
        loc = LocationService().resolve(city="Pune")
        first = weather.get_current(location_id=loc.id)
        second = weather.get_current(location_id=loc.id)
        if not second.get("from_cache"):
            failures.append("expected second Pune current weather to be from_cache=True")
        else:
            self.stdout.write("CACHE: second Pune request served from cache")

        # 4) Lightning unavailable (no fake data)
        lightning = LightningService().get_recent_india()
        if lightning.get("available") or lightning.get("strikes"):
            failures.append("lightning unexpectedly available or non-empty")
        else:
            self.stdout.write("LIGHTNING: correctly unavailable")

        # 5) Nowcasting is rule-based
        nowcast = NowcastingService().assess(city="Pune")
        if nowcast.get("data_kind") != "model_estimate":
            failures.append("nowcast data_kind unexpected")
        if "rule-based" not in (nowcast.get("disclaimer") or "").lower():
            failures.append("nowcast disclaimer missing rule-based wording")
        self.stdout.write(
            f"NOWCAST: {nowcast.get('risk_level')} score={nowcast.get('risk_score')} "
            f"engine={nowcast.get('engine_type')}"
        )

        # 6) HTTP endpoints via Django test client (no PowerShell $HOME trap)
        # Client default host is "testserver"; production ALLOWED_HOSTS may omit it.
        client = Client(HTTP_HOST="127.0.0.1")
        for path in ("/health/", "/", "/api/weather/current/?city=Pune", "/lightning/"):
            response = client.get(path)
            if response.status_code >= 500:
                failures.append(f"{path} returned {response.status_code}")
            else:
                self.stdout.write(f"HTTP {response.status_code} {path}")

        health = client.get("/health/")
        if health.status_code != 200:
            failures.append(f"health returned {health.status_code}")
        else:
            body = json.loads(health.content.decode())
            if body.get("status") != "ok":
                failures.append("health payload invalid")

        if failures:
            for item in failures:
                self.stderr.write(self.style.ERROR(f"FAIL: {item}"))
            raise SystemExit(1)

        self.stdout.write(self.style.SUCCESS("SMOKE AUDIT PASSED"))
