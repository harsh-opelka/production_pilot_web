"""
service_config.py
------------------
Reads/writes production_pilot/service_config.json — holds the salted
password hash that gates the Service screen. Auto-created with a
default password ("0000") on first access, so a fresh checkout doesn't
need a manual setup step.

The password is never stored (or compared) in plaintext: PBKDF2-HMAC-
SHA256 with a random per-install salt, verified with a constant-time
comparison so a timing attack can't leak how much of a guess matched.
"""

from __future__ import annotations

import hashlib
import json
import secrets
from pathlib import Path

_CONFIG_PATH = Path(__file__).resolve().parent / "service_config.json"
_DEFAULT_PASSWORD = "0000"
_PBKDF2_ITERATIONS = 200_000


def _hash_password(password: str, salt_hex: str) -> str:
    salt = bytes.fromhex(salt_hex)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, _PBKDF2_ITERATIONS)
    return digest.hex()


def _new_credentials(password: str) -> dict:
    salt = secrets.token_hex(16)
    return {"password_hash": _hash_password(password, salt), "salt": salt}


def load_service_config() -> dict:
    """
    Returns {"password_hash": ..., "salt": ...}. Transparently migrates
    V1's plaintext {"service_password": "..."} format on first read: the
    plaintext value is hashed once, the file is rewritten in the new
    format, and the plaintext never touches disk again.
    """
    if not _CONFIG_PATH.exists():
        config = _new_credentials(_DEFAULT_PASSWORD)
        save_service_config(config)
        return config

    try:
        with open(_CONFIG_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError):
        config = _new_credentials(_DEFAULT_PASSWORD)
        save_service_config(config)
        return config

    if "password_hash" in data and "salt" in data:
        return data

    if "service_password" in data:
        print("[service_config] Migrating plaintext password to a salted hash.")
        config = _new_credentials(str(data["service_password"]))
        save_service_config(config)
        return config

    # Unrecognized/corrupt shape — fall back to the default rather than
    # locking the technician out of a service screen they've never set up.
    config = _new_credentials(_DEFAULT_PASSWORD)
    save_service_config(config)
    return config


def save_service_config(data: dict) -> None:
    _CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(_CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def verify_password(password: str) -> bool:
    config = load_service_config()
    candidate = _hash_password(password, config["salt"])
    return secrets.compare_digest(candidate, config["password_hash"])


def set_password(new_password: str) -> None:
    save_service_config(_new_credentials(new_password))
