"""Alarm id helpers."""

import secrets


def make_id(prefix: str = "a") -> str:
    """Return a short random id like ``a9f2c1``."""
    return f"{prefix}{secrets.token_hex(3)}"