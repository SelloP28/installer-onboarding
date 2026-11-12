"""Helpers for parsing installer access tokens."""

from urllib.parse import parse_qs, urlsplit
from uuid import UUID


def parse_access_token(raw: str) -> str | None:
    """Parse and validate a raw installer token, URL, or query string."""
    value = raw.strip()
    if not value:
        return None

    if "access_token=" in value:
        query = urlsplit(value).query or value.lstrip("?")
        values = parse_qs(query).get("access_token", [])
        if not values:
            return None
        value = values[0].strip()

    try:
        return str(UUID(value))
    except (AttributeError, TypeError, ValueError):
        return None
