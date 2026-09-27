"""Indian mobile normalization. Full numbers are never written to logs."""

from __future__ import annotations

import re

_TEN_DIGIT = re.compile(r"^[6-9]\d{9}$")


class InvalidMobile(ValueError):
    """Raised when a number is not a usable Indian mobile."""


def normalize_indian_mobile(raw: str) -> str:
    """Return E.164 (+91XXXXXXXXXX) or raise InvalidMobile."""
    digits = re.sub(r"\D", "", raw or "")
    if len(digits) == 12 and digits.startswith("91"):
        digits = digits[2:]
    elif len(digits) == 11 and digits.startswith("0"):
        digits = digits[1:]
    if not _TEN_DIGIT.match(digits):
        raise InvalidMobile("invalid_mobile")
    return f"+91{digits}"


def mask_mobile(normalized: str) -> str:
    """Mask everything except the country prefix and last four digits."""
    digits = re.sub(r"\D", "", normalized or "")
    tail = digits[-4:] if len(digits) >= 4 else "0000"
    return f"+91******{tail}"
