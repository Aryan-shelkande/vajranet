"""Unit tests for nowcasting engine and providers (mocked HTTP)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from weather.models import DataSource, Location
from weather.providers.base import ProviderError, WeatherSnapshot
from weather.providers.open_meteo import OpenMeteoProvider
from weather.providers.wmo import describe_weather_code
from weather.services.nowcasting import NowcastingEngine, NowcastingService
from weather.services.weather import LocationService, WeatherService


class NowcastingEngineTests(TestCase):
    def test_low_risk_baseline(self):
        result = NowcastingEngine().predict(
            {
                "humidity_pct": 40,
                "cape_jkg": 100,
                "cloud_cover_pct": 20,
                "rainfall_mm": 0,
                "precipitation_probability_pct": 10,
                "wind_speed_kmh": 10,
                "weather_code": 0,
                "lightning_available": False,
            }
        )
        self.assertEqual(result.risk_level, "LOW")
        self.assertEqual(result.data_kind, "model_estimate")

    def test_high_risk_with_thunder_and_cape(self):
        result = NowcastingEngine().predict(
            {
                "humidity_pct": 85,
                "cape_jkg": 2200,
                "lifted_index": -5,
                "cloud_cover_pct": 90,
                "rainfall_mm": 5,
                "precipitation_probability_pct": 80,
                "wind_speed_kmh": 45,
                "weather_code": 95,
                "lightning_available": False,
            }
        )
        self.assertIn(result.risk_level, {"HIGH", "VERY HIGH"})
        self.assertTrue(any(f["name"] == "CAPE" for f in result.factors))


class WMOTests(TestCase):
    def test_known_code(self):
        self.assertEqual(describe_weather_code(95), "Thunderstorm")

    def test_unknown_code(self):
        self.assertIn("Weather code", describe_weather_code(1234))


class OpenMeteoProviderTests(TestCase):
    @patch("weather.providers.open_meteo.http_get_json")
    def test_current_weather_parsing(self, mock_get):
        mock_get.return_value = {
            "latitude": 18.52,
            "longitude": 73.85,
            "timezone": "Asia/Kolkata",
            "current": {
                "time": "2026-09-26T17:00",
                "temperature_2m": 29.0,
                "apparent_temperature": 31.0,
                "relative_humidity_2m": 72,
                "pressure_msl": 1008,
                "wind_speed_10m": 14,
                "wind_direction_10m": 180,
                "visibility": 10000,
                "cloud_cover": 40,
                "precipitation": 0.2,
                "weather_code": 61,
                "cape": 800,
            },
            "daily": {"sunrise": ["2026-09-26T06:20"], "sunset": ["2026-09-26T18:30"]},
        }
        snap = OpenMeteoProvider().get_current_weather(18.52, 73.85)
        self.assertEqual(snap.temperature_c, 29.0)
        self.assertEqual(snap.visibility_km, 10.0)
        self.assertEqual(snap.data_kind, "forecast")
        self.assertEqual(snap.source, "Open-Meteo")

    @patch("weather.providers.open_meteo.http_get_json")
    def test_provider_error_bubbles(self, mock_get):
        mock_get.side_effect = ProviderError("timeout")
        with self.assertRaises(ProviderError):
            OpenMeteoProvider().get_current_weather(18.52, 73.85)


class WeatherServiceCacheTests(TestCase):
    def setUp(self):
        self.location = Location.objects.create(
            name="Pune",
            state="Maharashtra",
            latitude="18.520400",
            longitude="73.856700",
            is_featured=True,
        )
        DataSource.objects.create(
            slug="open-meteo",
            name="Open-Meteo",
            data_type="weather",
            status=DataSource.Status.AVAILABLE,
        )

    @patch.object(WeatherService, "__init__", lambda self: None)
    def test_fallback_to_cached_observation(self):
        service = WeatherService()
        service.provider = MagicMock()
        service.provider.get_current_weather.side_effect = ProviderError("down")
        service.locations = LocationService()
        from django.utils import timezone

        from weather.models import WeatherObservation

        WeatherObservation.objects.create(
            location=self.location,
            observed_at=timezone.now(),
            temperature_c=28,
            weather_description="Partly cloudy",
            data_kind="cached",
        )
        payload = service.get_current(city="Pune")
        self.assertTrue(payload["stale"])
        self.assertEqual(payload["data_kind"], "cached")
        self.assertIn("temporarily unavailable", payload["message"])


class APIEndpointTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        Location.objects.create(
            name="Pune",
            state="Maharashtra",
            latitude="18.520400",
            longitude="73.856700",
            is_featured=True,
        )

    @patch("weather.api.WeatherService.get_current")
    def test_current_weather_api(self, mock_current):
        mock_current.return_value = {
            "location": {"name": "Pune"},
            "temperature_c": 29,
            "data_kind": "forecast",
            "source": "Open-Meteo",
        }
        res = self.client.get("/api/weather/current/", {"city": "Pune"})
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["temperature_c"], 29)

    def test_location_search_short_query(self):
        res = self.client.get("/api/locations/search/", {"q": "a"})
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["results"], [])

    @patch("weather.api.LightningService.get_recent_india")
    def test_lightning_unavailable(self, mock_lightning):
        mock_lightning.return_value = {
            "available": False,
            "strikes": [],
            "message": "Lightning data source unavailable",
            "data_kind": "unavailable",
        }
        res = self.client.get("/api/lightning/recent/")
        self.assertEqual(res.status_code, 200)
        self.assertFalse(res.json()["available"])

    def test_health(self):
        res = self.client.get("/health/")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["status"], "ok")

    def test_invalid_location_id_returns_400(self):
        res = self.client.get("/api/weather/current/", {"location_id": "abc"})
        self.assertEqual(res.status_code, 400)
        self.assertEqual(res.json()["error"], "invalid_location_id")

    def test_invalid_lightning_minutes_returns_400(self):
        res = self.client.get("/api/lightning/recent/", {"minutes": "nope"})
        self.assertEqual(res.status_code, 400)

    @patch("weather.api.WeatherService.get_current")
    def test_unknown_city_404(self, mock_current):
        mock_current.side_effect = Location.DoesNotExist("missing")
        res = self.client.get("/api/weather/current/", {"city": "NotARealCityXYZ"})
        self.assertEqual(res.status_code, 404)


class CacheBehaviorTests(TestCase):
    def setUp(self):
        self.location = Location.objects.create(
            name="Delhi",
            state="Delhi",
            latitude="28.613900",
            longitude="77.209000",
            is_featured=True,
        )

    @patch("weather.services.weather.get_weather_provider")
    def test_second_request_uses_cache(self, mock_provider_factory):
        provider = MagicMock()
        provider.get_current_weather.return_value = WeatherSnapshot(
            latitude=28.61,
            longitude=77.21,
            observed_at="2026-09-26T17:00",
            temperature_c=31.0,
            humidity_pct=50,
            source="Open-Meteo",
            data_kind="forecast",
            timezone="Asia/Kolkata",
        )
        mock_provider_factory.return_value = provider
        service = WeatherService()
        first = service.get_current(location_id=self.location.id)
        second = service.get_current(location_id=self.location.id)
        self.assertFalse(first["from_cache"])
        self.assertTrue(second["from_cache"])
        self.assertEqual(provider.get_current_weather.call_count, 1)


class RainViewerProviderTests(TestCase):
    @patch("weather.providers.rainviewer.http_get_json")
    def test_radar_frames(self, mock_get):
        from weather.providers.rainviewer import RainViewerProvider

        mock_get.return_value = {
            "version": "2.0",
            "generated": 1790422523,
            "host": "https://tilecache.rainviewer.com",
            "radar": {
                "past": [{"time": 1790415000, "path": "/v2/radar/abc"}],
                "nowcast": [{"time": 1790415600, "path": "/v2/radar/def"}],
            },
        }
        payload = RainViewerProvider().get_maps()
        self.assertTrue(payload["available"])
        self.assertEqual(payload["source"], "RainViewer")
        self.assertTrue(payload["frames"])
        self.assertIn("{z}", payload["frames"][0]["path"])


class NowcastingLabelTests(TestCase):
    @patch.object(NowcastingService, "assess")
    def test_api_exposes_engine_type_when_service_returns_it(self, mock_assess):
        mock_assess.return_value = {
            "risk_level": "LOW",
            "risk_score": 10,
            "data_kind": "model_estimate",
            "engine_type": "rule_based_baseline",
            "disclaimer": "Baseline rule-based estimate",
        }
        client = APIClient()
        res = client.get("/api/nowcasting/", {"city": "Pune"})
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["engine_type"], "rule_based_baseline")


@pytest.mark.django_db
def test_seed_featured_cities():
    count = LocationService().ensure_featured()
    assert Location.objects.filter(is_featured=True).count() >= 20
    assert count >= 0


class AIAssistantTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.context = {
            "city": "Pune",
            "weather": {
                "temperature_c": 29,
                "rainfall_mm": 4.2,
                "humidity_pct": 72,
                "weather_code": 95,
                "weather_description": "Thunderstorm",
            },
            "nowcast": {
                "risk_level": "HIGH",
                "risk_score": 78,
                "label": "Elevated thunderstorm potential",
                "engine_type": "rule_based_baseline",
                "data_kind": "model_estimate",
                "factors": [{"name": "CAPE", "signal": "elevated", "value": "1800"}],
            },
            "alerts": [
                {
                    "title": "Thunderstorm Risk",
                    "severity": "high",
                    "data_kind": "derived_risk",
                }
            ],
            "lightning_status": "unavailable",
        }

    def test_valid_question_platform_fallback(self):
        res = self.client.post(
            "/api/assistant/",
            {"question": "Is it safe to go outside in Pune?", "context": self.context},
            format="json",
        )
        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertEqual(body["mode"], "platform")
        self.assertIn("Pune", body["answer"])
        self.assertIn("authorities", body["answer"].lower())

    @override_settings(AI_PROVIDER="openai", OPENAI_API_KEY="")
    def test_missing_api_key_uses_platform_guidance(self):
        res = self.client.post(
            "/api/assistant/",
            {"question": "Weather in Pune", "context": self.context},
            format="json",
        )
        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertEqual(body["provider"], "platform")
        self.assertIn("platform guidance", body.get("provider_error", "").lower())

    @override_settings(AI_PROVIDER="openai", OPENAI_API_KEY="sk-test")
    @patch("weather.services.ai_assistant.httpx.Client")
    def test_provider_failure_falls_back(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client.__enter__.return_value = mock_client
        mock_client.__exit__.return_value = False
        mock_client.post.side_effect = Exception("timeout")
        mock_client_cls.return_value = mock_client
        res = self.client.post(
            "/api/assistant/",
            {"question": "Explain this alert", "context": self.context},
            format="json",
        )
        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertEqual(body["mode"], "platform")
        self.assertIn("unavailable", body.get("provider_error", "").lower())

    @override_settings(AI_PROVIDER="openai", OPENAI_API_KEY="sk-test")
    @patch("weather.services.ai_assistant.httpx.Client")
    def test_llm_success_path(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client.__enter__.return_value = mock_client
        mock_client.__exit__.return_value = False
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {
            "choices": [
                {
                    "message": {
                        "content": "Stay indoors in Pune while thunderstorm risk is elevated. Follow official instructions from local authorities."
                    }
                }
            ]
        }
        mock_client.post.return_value = mock_resp
        mock_client_cls.return_value = mock_client
        res = self.client.post(
            "/api/assistant/",
            {"question": "Is it safe outside?", "context": self.context},
            format="json",
        )
        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertEqual(body["mode"], "llm")
        self.assertEqual(body["provider"], "openai")
        self.assertIn("authorities", body["answer"].lower())

    def test_malformed_request(self):
        res = self.client.post("/api/assistant/", {"question": ""}, format="json")
        self.assertEqual(res.status_code, 400)
        res2 = self.client.post("/api/assistant/", {}, format="json")
        self.assertEqual(res2.status_code, 400)

    def test_safety_context_mentions_derived_risk(self):
        from weather.services.ai_assistant import AIAssistant

        result = AIAssistant().answer("Explain the active alerts", self.context)
        self.assertIn("derived", result["answer"].lower())
        self.assertEqual(result["mode"], "platform")
