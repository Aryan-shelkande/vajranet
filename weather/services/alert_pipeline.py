"""Alert dispatch: dedupe, match location, filter preferences, send SMS."""

from __future__ import annotations

import hashlib
import logging
from datetime import timedelta
from math import asin, cos, radians, sin, sqrt
from typing import Any

from django.db import transaction
from django.utils import timezone

from weather.models import AlertDispatch, SMSDelivery, SMSSubscriber
from weather.services.messages import HAZARD_TO_CATEGORY, render_sms
from weather.services.sms import SMSService

logger = logging.getLogger(__name__)

SEND_SEVERITIES = {"high", "extreme", "HIGH", "SEVERE", "VERY HIGH"}
MATCH_RADIUS_KM = 40.0
DEDUPE_HOURS = 12


def event_fingerprint(
    category: str, location_key: str, severity: str, when=None
) -> str:
    moment = when or timezone.now()
    day = timezone.localtime(moment).date().isoformat()
    raw = f"{category}|{location_key}|{str(severity).upper()}|{day}"
    return hashlib.sha256(raw.encode()).hexdigest()[:32]


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    radius = 6371.0
    phi1, phi2 = radians(lat1), radians(lat2)
    d_phi = radians(lat2 - lat1)
    d_lambda = radians(lon2 - lon1)
    a = sin(d_phi / 2) ** 2 + cos(phi1) * cos(phi2) * sin(d_lambda / 2) ** 2
    return 2 * radius * asin(sqrt(a))


def subscriber_matches(subscriber: SMSSubscriber, event: dict[str, Any]) -> bool:
    event_location_id = event.get("location_id")
    if (
        subscriber.location_id
        and event_location_id
        and subscriber.location_id == event_location_id
    ):
        return True
    event_place = str(event.get("place") or "").split(",")[0].strip().lower()
    if subscriber.location_id and subscriber.location:
        subscriber_place = subscriber.location.name.strip().lower()
    else:
        subscriber_place = (subscriber.location_label or "").strip().lower()
    if event_place and subscriber_place and event_place == subscriber_place:
        return True
    if (
        subscriber.latitude is not None
        and subscriber.longitude is not None
        and event.get("latitude") is not None
        and event.get("longitude") is not None
    ):
        distance = haversine_km(
            float(subscriber.latitude),
            float(subscriber.longitude),
            float(event["latitude"]),
            float(event["longitude"]),
        )
        return distance <= MATCH_RADIUS_KM
    return False


def _normalize_severity(raw: str) -> str:
    text = str(raw or "").strip().lower()
    if text in {"extreme", "severe"}:
        return "SEVERE"
    if text in {"high", "very high"}:
        return "HIGH"
    return str(raw or "HIGH").upper()


class AlertPipeline:
    def collect(self, city: str) -> list[dict[str, Any]]:
        from weather.services.alert import AlertService

        payload = AlertService().get_alerts(city=city)
        location = payload.get("location") or {}
        events = []
        for alert in payload.get("alerts") or []:
            category = HAZARD_TO_CATEGORY.get(alert.get("hazard_type") or "")
            severity = str(alert.get("severity") or "").lower()
            if not category or severity not in {"high", "extreme"}:
                continue
            events.append(
                {
                    "category": category,
                    "place": alert.get("area_name") or location.get("name") or city,
                    "location_id": location.get("id"),
                    "latitude": None,
                    "longitude": None,
                    "severity": _normalize_severity(severity),
                    "window": "",
                    "origin": alert.get("origin") or "derived",
                }
            )
        return events

    def dispatch_events(
        self, events: list[dict[str, Any]], *, unsubscribe_base_url: str = ""
    ) -> dict[str, int]:
        counts = {"demo": 0, "sent": 0, "failed": 0, "skipped": 0}
        subscribers = list(
            SMSSubscriber.objects.filter(
                is_active=True, consent_given=True
            ).select_related("location")
        )
        for event in events:
            category = event.get("category") or "severe_weather"
            place = event.get("place") or "your area"
            severity = _normalize_severity(event.get("severity") or "HIGH")
            if severity not in {"HIGH", "SEVERE"}:
                counts["skipped"] += 1
                continue
            location_key = str(event.get("location_id") or place).lower()
            fingerprint = event_fingerprint(category, location_key, severity)
            if self._recently_sent(fingerprint):
                counts["skipped"] += 1
                continue
            matched = [
                sub
                for sub in subscribers
                if subscriber_matches(sub, event)
                and category in (sub.alert_preferences or [])
            ]
            if not matched:
                counts["skipped"] += 1
                continue
            any_delivered = False
            for subscriber in matched:
                if self._subscriber_already_notified(subscriber.pk, fingerprint):
                    counts["skipped"] += 1
                    continue
                message = render_sms(
                    subscriber.language,
                    category,
                    place=place,
                    severity=severity,
                    window=event.get("window") or "",
                    url=unsubscribe_base_url,
                )
                result = SMSService().deliver(
                    to=subscriber.normalized_mobile_number, message=message
                )
                SMSDelivery.objects.create(
                    subscriber=subscriber,
                    masked_recipient=result["masked_recipient"],
                    fingerprint=fingerprint,
                    category=category,
                    language=subscriber.language,
                    body=message,
                    status=result["status"],
                    provider=result["provider"],
                    error_code=result.get("error") or "",
                )
                status = result["status"]
                if status == "DEMO":
                    counts["demo"] += 1
                    any_delivered = True
                elif status == "SENT":
                    counts["sent"] += 1
                    any_delivered = True
                elif status == "FAILED":
                    counts["failed"] += 1
                else:
                    counts["skipped"] += 1
                if status in {"DEMO", "SENT"}:
                    SMSSubscriber.objects.filter(pk=subscriber.pk).update(
                        last_alert_sent_at=timezone.now()
                    )
            if any_delivered:
                self._mark_sent(fingerprint, event, place, severity)
        return counts

    def dispatch(self, *, city: str, unsubscribe_base_url: str = "") -> dict[str, int]:
        try:
            events = self.collect(city)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Alert collection failed: %s", exc.__class__.__name__)
            return {"demo": 0, "sent": 0, "failed": 0, "skipped": 0, "error": 1}
        counts = self.dispatch_events(events, unsubscribe_base_url=unsubscribe_base_url)
        counts["error"] = 0
        return counts

    def _recently_sent(self, fingerprint: str) -> bool:
        cutoff = timezone.now() - timedelta(hours=DEDUPE_HOURS)
        return AlertDispatch.objects.filter(
            fingerprint=fingerprint, last_sent_at__gte=cutoff
        ).exists()

    def _subscriber_already_notified(
        self, subscriber_id: int, fingerprint: str
    ) -> bool:
        return SMSDelivery.objects.filter(
            subscriber_id=subscriber_id,
            fingerprint=fingerprint,
            status__in=["DEMO", "SENT"],
        ).exists()

    def _mark_sent(
        self, fingerprint: str, event: dict[str, Any], place: str, severity: str
    ) -> None:
        now = timezone.now()
        with transaction.atomic():
            (
                dispatch,
                _created,
            ) = AlertDispatch.objects.select_for_update().get_or_create(
                fingerprint=fingerprint,
                defaults={
                    "event_type": event.get("category") or "severe_weather",
                    "location_id": event.get("location_id"),
                    "location_label": place[:160],
                    "severity": severity[:20],
                    "valid_until": now + timedelta(hours=6),
                    "last_sent_at": now,
                    "send_count": 1,
                },
            )
            if not _created:
                dispatch.last_sent_at = now
                dispatch.send_count = (dispatch.send_count or 0) + 1
                dispatch.save(
                    update_fields=["last_sent_at", "send_count", "updated_at"]
                )
