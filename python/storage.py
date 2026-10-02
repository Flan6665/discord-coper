"""Persist exported server configs to disk, keyed by a short random ID."""
from __future__ import annotations

import json
import secrets
import string
from pathlib import Path

CONFIG_DIR = Path(__file__).parent / "configs"
_ID_ALPHABET = string.ascii_lowercase + string.digits
_ID_LENGTH = 8


def _new_id() -> str:
    return "".join(secrets.choice(_ID_ALPHABET) for _ in range(_ID_LENGTH))


def _path_for(config_id: str) -> Path:
    return CONFIG_DIR / f"{config_id}.json"


def save_config(config: dict, *, owner_id: int) -> str:
    """Store ``config`` and return the generated ID used to retrieve it."""
    CONFIG_DIR.mkdir(exist_ok=True)
    config_id = _new_id()
    while _path_for(config_id).exists():
        config_id = _new_id()
    payload = dict(config)
    payload["_owner_id"] = owner_id
    _path_for(config_id).write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return config_id


def load_config(config_id: str) -> dict | None:
    """Load a config by ID, or return None if there is no such config.

    The ID is validated against the known alphabet/length first so a caller
    cannot use it to read arbitrary files via path traversal.
    """
    if (
        len(config_id) != _ID_LENGTH
        or any(c not in _ID_ALPHABET for c in config_id)
    ):
        return None
    path = _path_for(config_id)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
