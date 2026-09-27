"""Send one live test SMS through the existing SMSService."""

from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from weather.models import SMSDelivery
from weather.services.messages import render_sms
from weather.services.phone import InvalidMobile, mask_mobile, normalize_indian_mobile
from weather.services.sms import SMSService


class Command(BaseCommand):
    help = (
        "Send one welcome SMS through the configured live gateway. "
        "Refuses to simulate a message."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--phone",
            required=True,
            help="Indian mobile number, for example +9198XXXXXXXX.",
        )

    def handle(self, *args, **options):
        try:
            normalized = normalize_indian_mobile(options["phone"])
        except InvalidMobile as exc:
            raise CommandError(
                "Enter a valid Indian mobile number. No message was sent."
            ) from exc
        service = SMSService()
        mode = service.mode()
        if mode != "live":
            raise CommandError(
                f"Live SMS is not configured (mode={mode}). "
                "Set SMS_ENABLED=True, SMS_DEMO_MODE=False, SMS_PROVIDER=http, "
                "SMS_API_URL, and SMS_API_KEY in the environment. "
                "No message was sent."
            )
        masked = mask_mobile(normalized)
        message = render_sms("en", "confirm", place="your area")
        result = service.deliver(to=normalized, message=message)
        SMSDelivery.objects.create(
            subscriber=None,
            masked_recipient=result["masked_recipient"],
            fingerprint=f"test:{timezone.now().strftime('%Y%m%d%H%M%S%f')}",
            category="confirm",
            language="en",
            body=message,
            status=result["status"],
            provider=result["provider"],
            error_code=result.get("error") or "",
        )
        if result["status"] != "SENT":
            raise CommandError(
                "The SMS gateway did not accept the message for "
                f"{masked}. status={result['status']} "
                f"error={result.get('error') or 'provider_error'}"
            )
        self.stdout.write(
            self.style.SUCCESS(f"Provider accepted the SMS for {masked}.")
        )
