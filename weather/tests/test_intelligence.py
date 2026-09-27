"""SMS subscriptions, risk engine, briefings, and alert deduplication."""

from __future__ import annotations

from datetime import timedelta
from unittest.mock import MagicMock, patch

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from weather.models import AlertDispatch, Location, SMSDelivery, SMSSubscriber
from weather.services.alert_pipeline import (
    AlertPipeline,
    event_fingerprint,
    subscriber_matches,
)
from weather.services.briefing import BriefingService
from weather.services.messages import localized_answer, render_sms
from weather.services.nowcasting import build_forecast_windows
from weather.services.phone import InvalidMobile, mask_mobile, normalize_indian_mobile
from weather.services.risk import AtmosphericRiskEngine
from weather.services.sms import SMSService
from weather.services.subscriptions import SubscriptionError, SubscriptionService


class PhoneTests(TestCase):
    def test_normalizes_local_and_country_forms(self):
        self.assertEqual(normalize_indian_mobile("9876543210"), "+919876543210")
        self.assertEqual(normalize_indian_mobile("+91 98765 43210"), "+919876543210")
        self.assertEqual(normalize_indian_mobile("09876543210"), "+919876543210")

    def test_rejects_short_or_landline_looking_numbers(self):
        with self.assertRaises(InvalidMobile):
            normalize_indian_mobile("12345")
        with self.assertRaises(InvalidMobile):
            normalize_indian_mobile("5876543210")

    def test_mask_hides_middle_digits(self):
        self.assertEqual(mask_mobile("+919876543210"), "+91******3210")
        self.assertNotIn("987654", mask_mobile("+919876543210"))


@override_settings(SMS_ENABLED=True, SMS_DEMO_MODE=True, SMS_PROVIDER="demo")
class SubscriptionTests(TestCase):
    def setUp(self):
        self.location = Location.objects.create(
            name="Pune",
            state="Maharashtra",
            latitude="18.520400",
            longitude="73.856700",
            is_featured=True,
        )
        self.service = SubscriptionService()
        self.payload = {
            "name": "Asha",
            "mobile_number": "9876543210",
            "location_label": "Pune",
            "alert_types": ["heavy_rain", "thunderstorm"],
            "language": "en",
            "consent": True,
            "unsubscribe_base_url": "http://testserver/alerts/unsubscribe",
        }

    def test_creates_subscriber_and_demo_sms(self):
        result = self.service.subscribe(**self.payload)
        self.assertTrue(result["created"])
        self.assertEqual(result["masked_mobile"], "+91******3210")
        self.assertEqual(result["delivery"]["status"], "DEMO")
        self.assertIn("VAJRANET", result["delivery"]["message"])
        self.assertIn("Welcome", result["delivery"]["message"])
        self.assertIn("Pune", result["delivery"]["message"])
        self.assertNotIn("http", result["delivery"]["message"])
        self.assertEqual(SMSSubscriber.objects.count(), 1)
        row = SMSSubscriber.objects.get()
        self.assertTrue(row.consent_given)
        self.assertIsNotNone(row.consent_timestamp)
        self.assertEqual(row.location_id, self.location.id)
        self.assertFalse(row.phone_verified)

    def test_duplicate_mobile_updates_instead_of_inserting(self):
        self.service.subscribe(**self.payload)
        again = dict(self.payload)
        again["name"] = "Asha K"
        again["alert_types"] = ["flood"]
        result = self.service.subscribe(**again)
        self.assertFalse(result["created"])
        self.assertEqual(SMSSubscriber.objects.count(), 1)
        row = SMSSubscriber.objects.get()
        self.assertEqual(row.name, "Asha K")
        self.assertEqual(row.alert_preferences, ["flood"])
        self.assertEqual(
            SMSDelivery.objects.filter(status="DEMO", category="confirm").count(), 1
        )

    def test_consent_is_required(self):
        payload = dict(self.payload)
        payload["consent"] = False
        with self.assertRaises(SubscriptionError) as caught:
            self.service.subscribe(**payload)
        self.assertEqual(caught.exception.code, "consent_required")
        self.assertEqual(SMSSubscriber.objects.count(), 0)

    def test_unknown_city_is_rejected(self):
        payload = dict(self.payload)
        payload["location_label"] = "NotARealCity"
        with self.assertRaises(SubscriptionError) as caught:
            self.service.subscribe(**payload)
        self.assertEqual(caught.exception.code, "invalid_location")
        self.assertEqual(SMSSubscriber.objects.count(), 0)

    def test_reactivation_sends_a_new_welcome(self):
        self.service.subscribe(**self.payload)
        self.assertTrue(self.service.unsubscribe_mobile("9876543210"))
        result = self.service.subscribe(**self.payload)
        self.assertFalse(result["created"])
        self.assertFalse(result["repeated"])
        self.assertEqual(
            SMSDelivery.objects.filter(status="DEMO", category="confirm").count(), 2
        )
        self.assertIn("Welcome", result["delivery"]["message"])

    def test_form_success_hides_the_raw_message(self):
        response = self.client.post(
            "/sms/subscribe/",
            {
                "name": "  Asha  ",
                "mobile_number": "98765 43210",
                "location": "Pune",
                "alert_types": ["heavy_rain"],
                "language": "en",
                "consent": "on",
            },
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Alerts Activated")
        self.assertContains(response, "Welcome SMS simulated")
        self.assertContains(response, "Demo mode")
        self.assertNotContains(response, "DEMO SMS")
        self.assertNotContains(response, "No promotional messages")
        self.assertEqual(SMSDelivery.objects.count(), 1)

    def test_form_shows_mobile_and_consent_errors(self):
        invalid = self.client.post(
            "/sms/subscribe/",
            {
                "name": "Asha",
                "mobile_number": "12345",
                "location": "Pune",
                "alert_types": ["flood"],
                "language": "en",
                "consent": "on",
            },
            follow=True,
        )
        self.assertContains(invalid, "Unable to activate alerts")
        self.assertContains(invalid, "sms-mobile-error")
        self.assertEqual(SMSSubscriber.objects.count(), 0)
        missing = self.client.post(
            "/sms/subscribe/",
            {
                "name": "Asha",
                "mobile_number": "9876543210",
                "location": "Pune",
                "alert_types": ["flood"],
                "language": "en",
            },
            follow=True,
        )
        self.assertContains(missing, "sms-consent-error")
        self.assertContains(missing, "Consent is required")
        self.assertEqual(SMSSubscriber.objects.count(), 0)

    @patch("weather.services.subscriptions.SMSService.deliver")
    def test_form_does_not_claim_success_when_the_gateway_rejects(self, mock_deliver):
        mock_deliver.return_value = {
            "status": "FAILED",
            "provider": "http",
            "simulated": False,
            "masked_recipient": "+91******3210",
            "message": "VAJRANET welcome",
            "error": "provider_rejected",
        }
        response = self.client.post(
            "/sms/subscribe/",
            {
                "name": "Asha",
                "mobile_number": "9876543210",
                "location": "Pune",
                "alert_types": ["heavy_rain"],
                "language": "en",
                "consent": "on",
            },
            follow=True,
        )
        self.assertContains(response, "send the welcome SMS. Please try again.")
        self.assertNotContains(response, "Alerts Activated")
        self.assertNotContains(response, "provider_rejected")
        self.assertEqual(SMSDelivery.objects.get().status, "FAILED")

    def test_unsubscribe_deactivates(self):
        self.service.subscribe(**self.payload)
        self.assertTrue(self.service.unsubscribe_mobile("9876543210"))
        self.assertFalse(SMSSubscriber.objects.get().is_active)
        self.assertFalse(self.service.unsubscribe_mobile("9876543210"))


@override_settings(
    SMS_ENABLED=True,
    SMS_DEMO_MODE=False,
    SMS_PROVIDER="http",
    SMS_API_URL="https://sms.example/send",
    SMS_API_KEY="secret-key",
    SMS_SENDER_ID="VAJRANET",
)
class SMSProviderTests(TestCase):
    @patch("weather.services.sms.httpx.Client")
    def test_live_provider_posts_without_logging_the_number(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client.__enter__.return_value = mock_client
        mock_client.__exit__.return_value = False
        mock_client_cls.return_value = mock_client
        response = MagicMock()
        response.raise_for_status = MagicMock()
        mock_client.post.return_value = response
        result = SMSService().deliver(to="+919876543210", message="VAJRANET ALERT")
        self.assertEqual(result["status"], "SENT")
        self.assertEqual(SMSService().mode(), "live")
        body = mock_client.post.call_args.kwargs["json"]
        headers = mock_client.post.call_args.kwargs["headers"]
        self.assertEqual(body["to"], "+919876543210")
        self.assertEqual(body["sender_id"], "VAJRANET")
        self.assertEqual(body["message"], "VAJRANET ALERT")
        self.assertEqual(headers["Authorization"], "Bearer secret-key")
        self.assertEqual(headers["Content-Type"], "application/json")
        self.assertNotIn("secret-key", result["message"])

    @patch("weather.services.sms.httpx.Client")
    def test_provider_failure_is_failed_not_raised(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client.__enter__.return_value = mock_client
        mock_client.__exit__.return_value = False
        mock_client.post.side_effect = TimeoutError("slow")
        mock_client_cls.return_value = mock_client
        result = SMSService().deliver(to="+919876543210", message="hello")
        self.assertEqual(result["status"], "FAILED")
        self.assertEqual(result["error"], "provider_timeout")
        self.assertEqual(result["masked_recipient"], "+91******3210")
        self.assertFalse(result["simulated"])

    def _http_response(self, status_code: int):
        import httpx

        return httpx.Response(
            status_code, request=httpx.Request("POST", "https://sms.example/send")
        )

    @patch("weather.services.sms.httpx.Client")
    def test_provider_rejection_is_failed(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client.__enter__.return_value = mock_client
        mock_client.__exit__.return_value = False
        mock_client.post.return_value = self._http_response(400)
        mock_client_cls.return_value = mock_client
        result = SMSService().deliver(to="+919876543210", message="hello")
        self.assertEqual(result["status"], "FAILED")
        self.assertEqual(result["error"], "provider_rejected")
        self.assertFalse(result["simulated"])

    @patch("weather.services.sms.httpx.Client")
    def test_provider_unauthorized_and_server_error(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client.__enter__.return_value = mock_client
        mock_client.__exit__.return_value = False
        mock_client_cls.return_value = mock_client
        mock_client.post.return_value = self._http_response(401)
        denied = SMSService().deliver(to="+919876543210", message="hello")
        self.assertEqual(denied["error"], "provider_unauthorized")
        mock_client.post.return_value = self._http_response(429)
        limited = SMSService().deliver(to="+919876543210", message="hello")
        self.assertEqual(limited["error"], "provider_rate_limited")
        mock_client.post.return_value = self._http_response(500)
        down = SMSService().deliver(to="+919876543210", message="hello")
        self.assertEqual(down["error"], "provider_unavailable")

    @override_settings(SMS_API_URL="", SMS_API_KEY="")
    def test_missing_credentials_do_not_simulate(self):
        result = SMSService().deliver(to="+919876543210", message="hello")
        self.assertEqual(SMSService().mode(), "unconfigured")
        self.assertEqual(result["status"], "FAILED")
        self.assertEqual(result["error"], "invalid_configuration")
        self.assertFalse(result["simulated"])

    @override_settings(SMS_PROVIDER="other", SMS_API_URL="https://sms.example/send")
    def test_unknown_provider_is_invalid_configuration(self):
        result = SMSService().deliver(to="+919876543210", message="hello")
        self.assertEqual(result["status"], "FAILED")
        self.assertEqual(result["error"], "invalid_configuration")

    @override_settings(SMS_DEMO_MODE=True, SMS_PROVIDER="demo")
    @patch("weather.services.sms.httpx.Client")
    def test_demo_mode_does_not_call_the_gateway(self, mock_client_cls):
        result = SMSService().deliver(to="+919876543210", message="hello")
        self.assertEqual(result["status"], "DEMO")
        self.assertTrue(result["simulated"])
        mock_client_cls.assert_not_called()


@override_settings(
    SMS_ENABLED=True,
    SMS_DEMO_MODE=False,
    SMS_PROVIDER="http",
    SMS_API_URL="https://sms.example/send",
    SMS_API_KEY="secret-key",
    SMS_SENDER_ID="VAJRANET",
)
class SendTestSMSCommandTests(TestCase):
    @patch("weather.services.sms.httpx.Client")
    def test_command_sends_one_live_message(self, mock_client_cls):
        import httpx

        mock_client = MagicMock()
        mock_client.__enter__.return_value = mock_client
        mock_client.__exit__.return_value = False
        mock_client.post.return_value = httpx.Response(
            200, request=httpx.Request("POST", "https://sms.example/send")
        )
        mock_client_cls.return_value = mock_client
        call_command("send_test_sms", phone="9876543210")
        self.assertEqual(mock_client.post.call_count, 1)
        self.assertEqual(SMSDelivery.objects.get().status, "SENT")
        self.assertNotEqual(SMSDelivery.objects.get().status, "DEMO")

    @patch("weather.services.sms.httpx.Client")
    def test_command_reports_rejection(self, mock_client_cls):
        import httpx

        mock_client = MagicMock()
        mock_client.__enter__.return_value = mock_client
        mock_client.__exit__.return_value = False
        mock_client.post.return_value = httpx.Response(
            403, request=httpx.Request("POST", "https://sms.example/send")
        )
        mock_client_cls.return_value = mock_client
        with self.assertRaises(CommandError) as caught:
            call_command("send_test_sms", phone="9876543210")
        self.assertIn("did not accept", str(caught.exception))
        self.assertNotIn("secret-key", str(caught.exception))
        self.assertEqual(SMSDelivery.objects.get().error_code, "provider_forbidden")

    @override_settings(SMS_DEMO_MODE=True, SMS_PROVIDER="demo")
    def test_command_refuses_demo_mode(self):
        with self.assertRaises(CommandError) as caught:
            call_command("send_test_sms", phone="9876543210")
        self.assertIn("No message was sent", str(caught.exception))
        self.assertEqual(SMSDelivery.objects.count(), 0)


@override_settings(SMS_ENABLED=False, SMS_DEMO_MODE=False, SMS_PROVIDER="http")
class SMSDisabledTests(TestCase):
    def test_disabled_sender_skips(self):
        result = SMSService().deliver(to="+919876543210", message="hello")
        self.assertEqual(result["status"], "SKIPPED")


class RiskEngineTests(TestCase):
    def test_low_profile(self):
        result = AtmosphericRiskEngine().evaluate(
            current={
                "temperature_c": 24,
                "humidity_pct": 40,
                "rainfall_mm": 0,
                "wind_speed_kmh": 8,
                "weather_description": "Clear",
                "data_kind": "forecast",
                "source": "Open-Meteo",
                "location": {"name": "Pune"},
            },
            hourly=[
                {"precipitation_probability_pct": 5, "precipitation_mm": 0},
                {"precipitation_probability_pct": 10, "precipitation_mm": 0},
                {"precipitation_probability_pct": 8, "precipitation_mm": 0},
            ],
            nowcast={"risk_score": 10, "risk_level": "LOW", "factors": []},
        )
        self.assertEqual(result["overall"]["level"], "LOW")
        self.assertEqual(result["label"], "VAJRANET MODEL ESTIMATE")
        self.assertFalse(result["validated"])
        self.assertIn(result["categories"]["rain"]["level"], {"LOW", "MODERATE"})

    def test_heavy_rain_and_storm_raise_categories(self):
        result = AtmosphericRiskEngine().evaluate(
            current={
                "rainfall_mm": 12,
                "wind_speed_kmh": 48,
                "humidity_pct": 90,
                "data_kind": "forecast",
                "source": "Open-Meteo",
                "location": {"name": "Pune"},
            },
            hourly=[
                {"precipitation_probability_pct": 85, "precipitation_mm": 8},
                {"precipitation_probability_pct": 90, "precipitation_mm": 10},
            ],
            nowcast={
                "risk_score": 82,
                "risk_level": "VERY HIGH",
                "factors": [{"name": "CAPE", "signal": "High instability"}],
            },
            radar={"status": "unavailable"},
        )
        self.assertIn(result["overall"]["level"], {"HIGH", "SEVERE"})
        self.assertIn(result["categories"]["rain"]["level"], {"HIGH", "SEVERE"})
        self.assertIn(result["categories"]["storm"]["level"], {"HIGH", "SEVERE"})
        self.assertIn(result["categories"]["wind"]["level"], {"HIGH", "SEVERE"})
        self.assertIn("Rain probability", result["why"])
        self.assertEqual(result["data_kind"], "model_estimate")


class NowcastWindowTests(TestCase):
    def test_three_hour_window_and_trend(self):
        windows = build_forecast_windows(
            [
                {
                    "time": "2026-09-27T16:00",
                    "precipitation_probability_pct": 20,
                    "precipitation_mm": 0.1,
                    "thunderstorm_hint": False,
                },
                {
                    "time": "2026-09-27T17:00",
                    "precipitation_probability_pct": 40,
                    "precipitation_mm": 0.4,
                    "thunderstorm_hint": False,
                },
                {
                    "time": "2026-09-27T18:00",
                    "precipitation_probability_pct": 70,
                    "precipitation_mm": 2,
                    "thunderstorm_hint": True,
                },
            ],
            storm_score=40,
            radar={"status": "available", "trend": "nowcast_sequence"},
        )
        self.assertTrue(windows["next_60_minutes"]["available"])
        self.assertEqual(windows["precipitation_trend"], "increasing")
        self.assertEqual(windows["experimental_label"], "MODEL ESTIMATE — EXPERIMENTAL")
        self.assertGreaterEqual(windows["next_3_hours"]["thunderstorm_risk_pct"], 70)
        self.assertIn("PM", windows["next_60_minutes"]["expected_window"])


class BriefingTests(TestCase):
    def test_deterministic_briefing_uses_only_supplied_numbers(self):
        text = BriefingService().compose(
            city="Pune",
            current={
                "location": {"name": "Pune"},
                "weather_description": "Humid",
                "temperature_c": 29,
                "humidity_pct": 78,
            },
            nowcast={"risk_level": "MODERATE"},
            risk={"categories": {"storm": {"level": "MODERATE"}}},
            hourly=[{"precipitation_probability_pct": 60}],
            language="en",
            allow_llm=False,
        )
        self.assertIn("Pune", text["text"])
        self.assertIn("29", text["text"])
        self.assertIn("60", text["text"])
        self.assertEqual(text["mode"], "deterministic")
        self.assertIn("not an official forecast", text["text"])

    def test_hindi_template_does_not_invent_a_temperature(self):
        from weather.services.messages import briefing_text

        text = briefing_text(
            "hi",
            place="Pune",
            condition=None,
            temp=None,
            humidity=None,
            rain_prob=None,
            storm_level=None,
        )
        self.assertIn("Pune", text)
        self.assertIn("unavailable", text)
        self.assertNotIn("32", text)


class MessageTemplateTests(TestCase):
    def test_marathi_heavy_rain_template(self):
        text = render_sms(
            "mr", "heavy_rain", place="Pune", severity="HIGH", window="3 PM–5 PM"
        )
        self.assertIn("Pune", text)
        self.assertIn("मुसळधार", text)
        self.assertIn("HIGH", text)

    def test_hindi_answer_mentions_model_not_official(self):
        text = localized_answer(
            "risk kyon high hai",
            {
                "city": "Pune",
                "risk": {"overall_level": "HIGH", "why": "Rain probability is 80%."},
            },
            "hi",
        )
        self.assertIn("Pune", text)
        self.assertIn("मॉडल", text)


@override_settings(SMS_ENABLED=True, SMS_DEMO_MODE=True, SMS_PROVIDER="demo")
class AlertPipelineTests(TestCase):
    def setUp(self):
        self.location = Location.objects.create(
            name="Pune",
            state="Maharashtra",
            latitude="18.520400",
            longitude="73.856700",
        )
        self.subscriber = SMSSubscriber.objects.create(
            name="Asha",
            mobile_number="+919876543210",
            normalized_mobile_number="+919876543210",
            location=self.location,
            location_label="Pune",
            latitude=self.location.latitude,
            longitude=self.location.longitude,
            language="en",
            alert_preferences=["heavy_rain"],
            is_active=True,
            consent_given=True,
            consent_timestamp=timezone.now(),
        )
        self.event = {
            "category": "heavy_rain",
            "place": "Pune",
            "location_id": self.location.id,
            "latitude": 18.52,
            "longitude": 73.86,
            "severity": "HIGH",
            "window": "3 PM–5 PM",
        }

    def test_preference_filter_skips_other_hazards(self):
        storm = dict(self.event)
        storm["category"] = "thunderstorm"
        counts = AlertPipeline().dispatch_events([storm])
        self.assertEqual(counts["demo"], 0)
        self.assertEqual(SMSDelivery.objects.count(), 0)

    def test_location_match_and_dedup(self):
        self.assertTrue(subscriber_matches(self.subscriber, self.event))
        first = AlertPipeline().dispatch_events([self.event])
        second = AlertPipeline().dispatch_events([self.event])
        self.assertEqual(first["demo"], 1)
        self.assertEqual(second["demo"], 0)
        self.assertGreaterEqual(second["skipped"], 1)
        self.assertEqual(SMSDelivery.objects.filter(status="DEMO").count(), 1)
        self.assertEqual(AlertDispatch.objects.count(), 1)
        delivery = SMSDelivery.objects.get()
        self.assertNotIn("9876543210", delivery.masked_recipient)
        self.assertIn("Heavy rainfall", delivery.body)

    def test_fingerprint_changes_when_severity_changes(self):
        low = event_fingerprint("heavy_rain", "1", "MODERATE")
        high = event_fingerprint("heavy_rain", "1", "HIGH")
        self.assertNotEqual(low, high)

    def test_distant_subscriber_does_not_match(self):
        other = SMSSubscriber(
            location_label="Delhi",
            latitude="28.613900",
            longitude="77.209000",
        )
        event = {
            "place": "Pune",
            "latitude": 18.52,
            "longitude": 73.85,
        }
        self.assertFalse(subscriber_matches(other, event))


class IntelligenceAPITests(TestCase):
    def setUp(self):
        self.client = APIClient()
        Location.objects.create(
            name="Pune",
            state="Maharashtra",
            latitude="18.520400",
            longitude="73.856700",
            is_featured=True,
        )

    @override_settings(SMS_ENABLED=True, SMS_DEMO_MODE=True, SMS_PROVIDER="demo")
    def test_subscribe_and_unsubscribe_endpoints(self):
        created = self.client.post(
            "/api/sms/subscribe/",
            {
                "name": "Asha",
                "mobile_number": "9876543210",
                "location": "Pune",
                "alert_types": ["thunderstorm"],
                "language": "mr",
                "consent": True,
            },
            format="json",
        )
        self.assertEqual(created.status_code, 201)
        body = created.json()
        self.assertEqual(body["delivery"]["status"], "DEMO")
        self.assertIn("हवामान", body["delivery"]["message"])
        removed = self.client.post(
            "/api/sms/unsubscribe/",
            {"mobile_number": "9876543210"},
            format="json",
        )
        self.assertEqual(removed.status_code, 200)
        self.assertFalse(SMSSubscriber.objects.get().is_active)

    def test_subscribe_without_consent_is_400(self):
        res = self.client.post(
            "/api/sms/subscribe/",
            {
                "name": "Asha",
                "mobile_number": "9876543210",
                "location": "Pune",
                "alert_types": ["flood"],
                "consent": False,
            },
            format="json",
        )
        self.assertEqual(res.status_code, 400)
        self.assertEqual(res.json()["error"], "consent_required")

    def test_subscribe_unknown_location_is_400(self):
        res = self.client.post(
            "/api/sms/subscribe/",
            {
                "name": "Asha",
                "mobile_number": "9876543210",
                "location": "NotARealCity",
                "alert_types": ["flood"],
                "consent": True,
            },
            format="json",
        )
        self.assertEqual(res.status_code, 400)
        self.assertEqual(res.json()["error"], "invalid_location")
        self.assertEqual(SMSSubscriber.objects.count(), 0)

    def test_assistant_radar_does_not_invent_a_reading(self):
        res = self.client.post(
            "/api/assistant/",
            {
                "question": "What does the radar show?",
                "context": {"city": "Pune", "radar_status": "unavailable"},
            },
            format="json",
        )
        self.assertEqual(res.status_code, 200)
        answer = res.json()["answer"].lower()
        self.assertIn("unavailable", answer)
        self.assertNotIn("mm/h", answer)

    def test_pages_render_when_weather_provider_fails(self):
        with patch(
            "dashboard.views.WeatherService.get_current",
            side_effect=RuntimeError("provider down"),
        ), patch(
            "dashboard.views.ForecastService.get_forecast",
            side_effect=RuntimeError("provider down"),
        ), patch(
            "dashboard.views.AlertService.get_alerts",
            side_effect=RuntimeError("provider down"),
        ), patch(
            "dashboard.views.NowcastingService.assess",
            side_effect=RuntimeError("provider down"),
        ), patch(
            "dashboard.views.WeatherService.get_map_overview",
            return_value=[],
        ):
            home = self.client.get("/")
            weather = self.client.get("/weather/")
            radar = self.client.get("/radar/")
            alerts = self.client.get("/alerts/")
            safety = self.client.get("/safety/")
            monitoring = self.client.get("/monitoring/")
            nowcast = self.client.get("/nowcasting/")
        self.assertEqual(home.status_code, 200)
        self.assertContains(home, "Stay ahead of changing conditions")
        self.assertContains(home, "theme-sunrise")
        self.assertContains(weather, "theme-clear")
        self.assertContains(weather, "show-rainbow")
        self.assertContains(radar, "theme-storm")
        self.assertContains(alerts, "theme-rain")
        self.assertContains(monitoring, "theme-night")
        self.assertContains(nowcast, "theme-sunset")
        self.assertContains(home, "Ask VajraNet")
        for response in (weather, radar, alerts, safety, monitoring, nowcast):
            self.assertEqual(response.status_code, 200)
        unsub = self.client.get("/alerts/unsubscribe/")
        self.assertEqual(unsub.status_code, 200)

    def test_home_renders_intelligence_markup(self):
        current = {
            "location": {"name": "Pune", "state": "Maharashtra"},
            "temperature_c": 29,
            "feels_like_c": 31,
            "humidity_pct": 70,
            "wind_speed_kmh": 12,
            "pressure_hpa": 1008,
            "rainfall_mm": 1,
            "weather_description": "Humid",
            "weather_code": 2,
            "data_kind": "forecast",
            "source": "Open-Meteo",
            "observed_at": "2026-09-27T12:00",
            "timezone": "Asia/Kolkata",
            "stale": False,
            "from_cache": False,
        }
        forecast = {
            "hourly": [
                {
                    "time": "2026-09-27T12:00",
                    "temperature_c": 29,
                    "precipitation_probability_pct": 40,
                    "precipitation_mm": 0.2,
                    "thunderstorm_hint": False,
                }
            ],
            "daily": [
                {
                    "time": "2026-09-27",
                    "temperature_min_c": 22,
                    "temperature_max_c": 31,
                    "precipitation_mm": 1,
                }
            ],
        }
        nowcast = {
            "location": {"name": "Pune"},
            "risk_level": "MODERATE",
            "risk_score": 40,
            "label": "Thunderstorm risk: MODERATE",
            "factors": [{"name": "Humidity", "signal": "Elevated", "value": 70}],
            "experimental_label": "MODEL ESTIMATE — EXPERIMENTAL",
            "confidence": "MEDIUM",
            "confidence_note": "Confidence reflects input completeness.",
            "precipitation_trend": "steady",
            "signals": ["No elevated short-range signal in the available fields"],
            "radar": {"status": "unavailable", "note": "Radar data is unavailable."},
            "windows": {
                "next_3_hours": {
                    "available": True,
                    "slots": [
                        {
                            "label": "12:00 PM",
                            "precipitation_probability_pct": 40,
                            "thunderstorm_risk_pct": 20,
                        }
                    ],
                }
            },
            "observed_at": "2026-09-27T12:00",
            "timezone": "Asia/Kolkata",
            "engine_type": "rule_based_baseline",
        }
        alerts = {
            "alerts": [
                {
                    "title": "Moderate thunderstorm risk",
                    "area_name": "Pune",
                    "severity": "moderate",
                    "origin": "derived",
                    "data_kind": "model_estimate",
                    "description": "Elevated convective potential.",
                    "recommended_action": "Stay weather aware.",
                    "source": "VajraNet",
                }
            ],
            "note": "Model estimates are not official warnings.",
        }
        with patch(
            "dashboard.views.WeatherService.get_current", return_value=current
        ), patch(
            "dashboard.views.ForecastService.get_forecast", return_value=forecast
        ), patch(
            "dashboard.views.AlertService.get_alerts", return_value=alerts
        ), patch(
            "dashboard.views.NowcastingService.assess", return_value=nowcast
        ), patch(
            "dashboard.views.WeatherService.get_map_overview", return_value=[]
        ):
            response = self.client.get("/?city=Pune")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "AI atmospheric risk")
        self.assertContains(response, "VAJRANET MODEL ESTIMATE")
        self.assertContains(response, "Why this risk?")
        self.assertContains(response, "AI weather briefing")
        self.assertContains(response, "Activate SMS Alerts")
        self.assertContains(response, "Model estimate")


class DedupWindowTests(TestCase):
    def test_recent_dispatch_is_inside_window(self):
        location = Location.objects.create(
            name="Pune",
            state="Maharashtra",
            latitude="18.520400",
            longitude="73.856700",
        )
        fingerprint = event_fingerprint("heavy_rain", str(location.id), "HIGH")
        AlertDispatch.objects.create(
            event_type="heavy_rain",
            location=location,
            location_label="Pune",
            severity="HIGH",
            fingerprint=fingerprint,
            last_sent_at=timezone.now() - timedelta(hours=1),
            send_count=1,
        )
        self.assertTrue(AlertPipeline()._recently_sent(fingerprint))
