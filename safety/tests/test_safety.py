from django.test import TestCase

from safety.models import EmergencyKitItem, SafetyGuideline
from weather.management.commands.seed_platform import Command


class SafetySeedTests(TestCase):
    def test_seed_creates_guidelines_and_kit(self):
        Command().handle()
        self.assertGreaterEqual(SafetyGuideline.objects.count(), 8)
        self.assertEqual(EmergencyKitItem.objects.count(), 12)
