"""Send due SMS alerts for one city. Safe to run repeatedly; duplicates are skipped."""

from __future__ import annotations

from django.core.management.base import BaseCommand

from weather.services.alert_pipeline import AlertPipeline


class Command(BaseCommand):
    help = "Match active SMS subscribers to current model alerts and deliver messages."

    def add_arguments(self, parser):
        parser.add_argument("--city", default="Pune")

    def handle(self, *args, **options):
        city = options["city"]
        counts = AlertPipeline().dispatch(city=city)
        self.stdout.write(
            "SMS dispatch for {city}: demo={demo} sent={sent} failed={failed} skipped={skipped}".format(
                city=city, **counts
            )
        )
