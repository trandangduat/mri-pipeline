"""Shared safeguards for values that must never leave process memory.

The backend writes configuration exports, job registry entries, and user-facing
errors through different code paths.  Keeping the key matching rules here
prevents one of those paths from accidentally retaining an SSH password or API
credential when another path has already been fixed.
"""
from __future__ import annotations

import re
from typing import TypeAlias


JsonValue: TypeAlias = str | int | float | bool | None | list["JsonValue"] | dict[str, "JsonValue"]

_SECRET_KEY_RE = re.compile(
    r"(?:^|_)(?:api_)?(?:password|passwd|passphrase|secret|token|authorization|credential|private_key)(?:$|_)",
    re.IGNORECASE,
)


def is_secret_key(key: object) -> bool:
    """Return whether *key* names credential material rather than metadata."""
    raw = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", str(key).strip())
    normalized = re.sub(r"[^a-z0-9]+", "_", raw.lower()).strip("_")
    return bool(normalized and _SECRET_KEY_RE.search(normalized))


def redact_secrets(value: JsonValue) -> JsonValue:
    """Return a deep copy with credential-bearing fields removed.

    Removal, instead of replacing values with a marker, makes the returned
    object safe to persist and avoids later accidentally sending a marker as a
    password.  Non-secret keys, including SSH key paths, remain available for
    reconnect metadata.
    """
    if isinstance(value, list):
        return [redact_secrets(item) for item in value]
    if isinstance(value, dict):
        return {
            str(key): redact_secrets(item)
            for key, item in value.items()
            if not is_secret_key(key)
        }
    return value


def secret_values(value: JsonValue) -> tuple[str, ...]:
    """Extract non-empty secrets for redacting an already-formatted error."""
    values: list[str] = []

    def visit(item: JsonValue, secret_context: bool = False) -> None:
        if isinstance(item, dict):
            for key, child in item.items():
                visit(child, secret_context or is_secret_key(key))
            return
        if isinstance(item, list):
            for child in item:
                visit(child, secret_context)
            return
        if secret_context and isinstance(item, str) and item:
            values.append(item)

    visit(value)
    # Longest first prevents a shorter value from partially masking a longer
    # password that happens to contain it.
    return tuple(sorted(set(values), key=len, reverse=True))


def redact_text(message: object, *secrets: object) -> str:
    """Mask supplied values in text intended for logs, SSE, or API errors."""
    result = str(message)
    for secret in sorted({str(value) for value in secrets if str(value)}, key=len, reverse=True):
        result = result.replace(secret, "[redacted]")
    return result
