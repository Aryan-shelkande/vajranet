"""SMS provider abstraction.

Demo mode records the message and never calls a network provider.
Live mode uses SMS_API_URL + SMS_API_KEY from the environment.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx
from django.conf import settings

from weather.services.phone import mask_mobile

logger = logging.getLogger(__name__)


class DemoSMSProvider:
    """Simulated SMS. Safe for development without credits."""

    name = "demo"

    def send(self, *, to: str, message: str) -> dict[str, Any]:
        masked = mask_mobile(to)
        logger.info("DEMO SMS prepared for %s (%s characters)", masked, len(message))
        return {
            "status": "DEMO",
            "provider": self.name,
            "simulated": True,
            "masked_recipient": masked,
            "message": message,
        }


def _http_error_code(status_code: int) -> str:
    if status_code == 401:
        return "provider_unauthorized"
    if status_code == 403:
        return "provider_forbidden"
    if status_code == 429:
        return "provider_rate_limited"
    if status_code >= 500:
        return "provider_unavailable"
    return "provider_rejected"


class ConfiguredSMSProvider:
    """HTTP SMS gateway.

    Live acceptance is an HTTP 2xx from SMS_API_URL. The request is:

    POST SMS_API_URL
    Authorization: Bearer SMS_API_KEY
    Content-Type: application/json
    {"to": "+91XXXXXXXXXX", "sender_id": "VAJRANET", "message": "..."}

    The gateway must return 2xx only when it accepts the message.
    """

    name = "http"

    def send(self, *, to: str, message: str) -> dict[str, Any]:
        masked = mask_mobile(to)
        url = (getattr(settings, "SMS_API_URL", "") or "").strip()
        key = (getattr(settings, "SMS_API_KEY", "") or "").strip()
        sender = (getattr(settings, "SMS_SENDER_ID", "") or "VAJRANET").strip()
        timeout = float(getattr(settings, "SMS_TIMEOUT_SECONDS", 8.0))
        error = "provider_connection"
        status_code = None
        try:
            with httpx.Client(timeout=timeout) as client:
                response = client.post(
                    url,
                    json={"to": to, "sender_id": sender, "message": message},
                    headers={
                        "Authorization": f"Bearer {key}",
                        "Content-Type": "application/json",
                    },
                )
                status_code = response.status_code
                response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            status_code = exc.response.status_code
            error = _http_error_code(status_code)
        except (httpx.TimeoutException, TimeoutError):
            error = "provider_timeout"
        except (httpx.HTTPError, OSError):
            error = "provider_connection"
        else:
            logger.info(
                "SMS accepted by provider for %s status=%s", masked, status_code
            )
            return {
                "status": "SENT",
                "provider": self.name,
                "simulated": False,
                "masked_recipient": masked,
                "message": message,
            }
        logger.warning(
            "SMS provider request failed for %s status=%s error=%s",
            masked,
            status_code if status_code is not None else "none",
            error,
        )
        return {
            "status": "FAILED",
            "provider": self.name,
            "simulated": False,
            "masked_recipient": masked,
            "message": message,
            "error": error,
        }


class SMSService:
    """Choose demo, live, or skipped delivery without exposing credentials."""

    def mode(self) -> str:
        enabled = bool(getattr(settings, "SMS_ENABLED", True))
        if not enabled:
            return "disabled"
        provider = (getattr(settings, "SMS_PROVIDER", "demo") or "demo").lower()
        demo = bool(getattr(settings, "SMS_DEMO_MODE", True)) or provider == "demo"
        if demo:
            return "demo"
        url = (getattr(settings, "SMS_API_URL", "") or "").strip()
        key = (getattr(settings, "SMS_API_KEY", "") or "").strip()
        if provider != "http" or not url or not key:
            logger.warning(
                "SMS live mode was requested but the HTTP provider is not "
                "configured. No message will be simulated. No credentials were logged."
            )
            return "unconfigured"
        return "live"

    def provider(self):
        if self.mode() == "live":
            return ConfiguredSMSProvider()
        return DemoSMSProvider()

    def deliver(self, *, to: str, message: str) -> dict[str, Any]:
        mode = self.mode()
        if mode == "disabled":
            return {
                "status": "SKIPPED",
                "provider": "none",
                "simulated": False,
                "masked_recipient": mask_mobile(to),
                "message": message,
            }
        if mode == "unconfigured":
            return {
                "status": "FAILED",
                "provider": "http",
                "simulated": False,
                "masked_recipient": mask_mobile(to),
                "message": message,
                "error": "invalid_configuration",
            }
        return self.provider().send(to=to, message=message)
