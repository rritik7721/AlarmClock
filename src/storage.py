"""Persistent JSON store for alarms.

One file per alarm type, e.g. ~/.local/share/alarm/alarm.json
"""

import json
import os
from typing import Any


def default_store_path(name: str) -> str:
    """Return the default JSON store path for alarm type ``name``.

    Honors ``ALARM_STORE_DIR`` when set. Otherwise uses the platform's
    per-user app-data directory: ``~/.local/share/alarm`` on Unix and
    ``%APPDATA%/alarm`` on Windows.
    """
    base = os.environ.get("ALARM_STORE_DIR")
    if not base:
        if os.name == "nt":
            base = os.environ.get("APPDATA") or os.path.expanduser("~")
        else:
            base = os.path.expanduser("~/.local/share/alarm")
    os.makedirs(base, exist_ok=True)
    return os.path.join(base, f"{name}.json")


def load_alarms(path: str) -> list[dict[str, Any]]:
    """Load alarms from ``path``. Returns [] if missing/empty/invalid."""
    if not os.path.exists(path):
        return []
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, json.JSONDecodeError):
        return []
    if not isinstance(data, list):
        return []
    return [a for a in data if isinstance(a, dict)]


def save_alarms(path: str, alarms: list[dict[str, Any]]) -> None:
    """Atomically write alarms to ``path``."""
    directory = os.path.dirname(os.path.abspath(path))
    os.makedirs(directory, exist_ok=True)
    tmp = f"{path}.tmp.{os.getpid()}"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(alarms, fh, indent=2, sort_keys=True)
        fh.write("\n")
    os.replace(tmp, path)