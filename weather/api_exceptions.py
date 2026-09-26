"""DRF exception handler."""

from __future__ import annotations

from rest_framework.response import Response
from rest_framework.views import exception_handler

from weather.providers.base import ProviderError, ProviderUnavailable


def custom_exception_handler(exc, context):
    response = exception_handler(exc, context)
    if response is not None:
        return response
    if isinstance(exc, ProviderUnavailable):
        return Response(
            {
                "error": "provider_unavailable",
                "message": str(exc),
                "data_kind": "unavailable",
            },
            status=503,
        )
    if isinstance(exc, ProviderError):
        return Response(
            {
                "error": "provider_error",
                "message": str(exc),
                "data_kind": "unavailable",
            },
            status=502,
        )
    return None
