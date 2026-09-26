from django.test import TestCase
from unittest.mock import patch

from disasters.providers.usgs import USGSEarthquakeProvider
from disasters.services import DisasterService


class USGSProviderTests(TestCase):
    @patch("disasters.providers.usgs.http_get_json")
    def test_parse_events(self, mock_get):
        mock_get.return_value = {
            "features": [
                {
                    "id": "us123",
                    "properties": {
                        "title": "M 4.5 - India",
                        "place": "India",
                        "mag": 4.5,
                        "time": 1727350000000,
                        "url": "https://example.com",
                    },
                    "geometry": {"coordinates": [77.2, 28.6, 10]},
                }
            ]
        }
        events = USGSEarthquakeProvider().get_recent()
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["magnitude"], 4.5)
        self.assertEqual(events[0]["data_kind"], "observed")


class WildfireUnavailableTests(TestCase):
    @patch.object(DisasterService, "__init__", lambda self: None)
    def test_firms_without_key(self):
        service = DisasterService()
        from weather.providers.base import ProviderUnavailable

        service.firms = type(
            "F",
            (),
            {"get_hotspots": staticmethod(lambda **k: (_ for _ in ()).throw(ProviderUnavailable("need key")))},
        )()
        payload = service.get_wildfires()
        self.assertFalse(payload["available"])
