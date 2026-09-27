"""No-login SMS subscriptions and delivery audit rows."""

from __future__ import annotations

import logging
import re

from django.core import signing
from django.db import transaction
from django.utils import timezone

from weather.models import Location, SMSDelivery, SMSSubscriber
from weather.services.messages import CATEGORY_KEYS, LANGUAGE_KEYS, render_sms
from weather.services.phone import InvalidMobile, mask_mobile, normalize_indian_mobile
from weather.services.sms import SMSService

logger = logging.getLogger(__name__)

UNSUBSCRIBE_SALT = "vajranet-sms-unsub"


class SubscriptionError(Exception):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


def _clean_name(name: str) -> str:
    text = re.sub(r"\s+", " ", (name or "").strip())
    if len(text) < 2 or len(text) > 80:
        raise SubscriptionError("invalid_name")
    if re.search(r"[\x00-\x1f]", text):
        raise SubscriptionError("invalid_name")
    return text


class SubscriptionService:
    def subscribe(
        self,
        *,
        name: str,
        mobile_number: str,
        location_label: str,
        alert_types: list[str],
        language: str,
        consent: bool,
        unsubscribe_base_url: str,
    ) -> dict:
        if not consent:
            raise SubscriptionError("consent_required")
        try:
            normalized = normalize_indian_mobile(mobile_number)
        except InvalidMobile as exc:
            raise SubscriptionError("invalid_mobile") from exc
        types = []
        for item in alert_types or []:
            key = str(item).strip()
            if key in CATEGORY_KEYS and key not in types:
                types.append(key)
        if not types:
            raise SubscriptionError("alert_types_required")
        if language not in LANGUAGE_KEYS:
            raise SubscriptionError("invalid_language")
        label = re.sub(r"\s+", " ", (location_label or "").strip())
        if len(label) < 2 or len(label) > 160:
            raise SubscriptionError("invalid_location")
        clean_name = _clean_name(name)
        location = Location.objects.filter(
            name__iexact=label, country_code="IN"
        ).first()
        if location is None:
            raise SubscriptionError("invalid_location")
        now = timezone.now()
        with transaction.atomic():
            prior = (
                SMSSubscriber.objects.select_for_update()
                .filter(normalized_mobile_number=normalized)
                .first()
            )
            was_active = bool(prior and prior.is_active and prior.consent_given)
            subscriber, created = SMSSubscriber.objects.update_or_create(
                normalized_mobile_number=normalized,
                defaults={
                    "name": clean_name,
                    "mobile_number": normalized,
                    "location": location,
                    "location_label": location.name,
                    "latitude": location.latitude,
                    "longitude": location.longitude,
                    "language": language,
                    "alert_preferences": types,
                    "is_active": True,
                    "phone_verified": False,
                    "consent_given": True,
                    "consent_timestamp": now,
                },
            )
        day = timezone.localtime(now).date().isoformat()
        fingerprint = f"welcome:{subscriber.pk}:{language}:{day}"
        existing = None
        if was_active:
            accepted = "DEMO" if SMSService().mode() == "demo" else "SENT"
            existing = (
                SMSDelivery.objects.filter(fingerprint=fingerprint, status=accepted)
                .order_by("-created_at")
                .first()
            )
        message = render_sms(language, "confirm", place=location.name)
        if existing:
            delivery = existing
        else:
            result = SMSService().deliver(to=normalized, message=message)
            delivery = SMSDelivery.objects.create(
                subscriber=subscriber,
                masked_recipient=result["masked_recipient"],
                fingerprint=fingerprint,
                category="confirm",
                language=language,
                body=message,
                status=result["status"],
                provider=result["provider"],
                error_code=result.get("error") or "",
            )
        logger.info(
            "SMS subscription %s for %s route=%s",
            "created" if created else "updated",
            mask_mobile(normalized),
            "configured" if unsubscribe_base_url else "missing",
        )
        return {
            "created": created,
            "subscriber_id": subscriber.pk,
            "masked_mobile": mask_mobile(normalized),
            "location": location.name,
            "language": language,
            "alert_types": types,
            "repeated": bool(existing),
            "delivery": {
                "status": delivery.status,
                "provider": delivery.provider,
                "simulated": delivery.status == "DEMO",
                "masked_recipient": delivery.masked_recipient,
                "message": delivery.body,
            },
        }

    def unsubscribe_mobile(self, mobile_number: str) -> bool:
        try:
            normalized = normalize_indian_mobile(mobile_number)
        except InvalidMobile as exc:
            raise SubscriptionError("invalid_mobile") from exc
        updated = SMSSubscriber.objects.filter(
            normalized_mobile_number=normalized, is_active=True
        ).update(is_active=False, updated_at=timezone.now())
        logger.info("SMS unsubscribe requested for %s", mask_mobile(normalized))
        return bool(updated)

    def unsubscribe_token(self, token: str) -> None:
        try:
            data = signing.loads(
                token, salt=UNSUBSCRIBE_SALT, max_age=60 * 60 * 24 * 400
            )
            subscriber = SMSSubscriber.objects.get(pk=data["sid"])
        except (
            signing.BadSignature,
            signing.SignatureExpired,
            SMSSubscriber.DoesNotExist,
            KeyError,
            TypeError,
        ) as exc:
            raise SubscriptionError("invalid_token") from exc
        if subscriber.is_active:
            subscriber.is_active = False
            subscriber.save(update_fields=["is_active", "updated_at"])
        logger.info("SMS unsubscribe token applied for %s", subscriber.masked_number())
