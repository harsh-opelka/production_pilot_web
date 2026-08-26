"""
service_config.py
------------------
Reads/writes production_pilot/service_config.json — holds the salted
password hashes for BOTH access levels: Management (read-only Dashboard
+ Statistics) and Service (also the Installation Wizard, config, scan,
and KPI history controls). Auto-created with defaults ("1111" management
/ "0000" service) on first access, so a fresh checkout doesn't need a
manual setup step.

Passwords are never stored (or compared) in plaintext: PBKDF2-HMAC-
SHA256 with a random per-install salt, verified with a constant-time
comparison so a timing attack can't leak how much of a guess matched.
"""

from __future__ import annotations

import hashlib
import json
import secrets
from pathlib import Path

_CONFIG_PATH = Path(__file__).resolve().parent / "service_config.json"
_DEFAULT_MANAGEMENT_PASSWORD = "1111"
_DEFAULT_SERVICE_PASSWORD = "0000"
_PBKDF2_ITERATIONS = 200_000


def _hash_password(password: str, salt_hex: str) -> str:
    salt = bytes.fromhex(salt_hex)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, _PBKDF2_ITERATIONS)
    return digest.hex()


def _new_credential(password: str) -> tuple[str, str]:
    """Returns (password_hash, salt) for one level's password."""
    salt = secrets.token_hex(16)
    return _hash_password(password, salt), salt


def _default_config() -> dict:
    mgmt_hash, mgmt_salt = _new_credential(_DEFAULT_MANAGEMENT_PASSWORD)
    svc_hash, svc_salt = _new_credential(_DEFAULT_SERVICE_PASSWORD)
    return {
        "management_password_hash": mgmt_hash,
        "management_salt": mgmt_salt,
        "service_password_hash": svc_hash,
        "service_salt": svc_salt,
    }


def load_service_config() -> dict:
    """
    Returns {"management_password_hash", "management_salt",
    "service_password_hash", "service_salt"}. Transparently migrates
    older formats, treating whatever single password already existed as
    the Service level and generating a fresh default Management
    password — the file is rewritten in the new two-level format and
    the old value never touches disk again:
      - V2's original single-hash {"password_hash", "salt"}
      - V1's plaintext {"service_password": "..."}
    """
    if not _CONFIG_PATH.exists():
        config = _default_config()
        save_service_config(config)
        return config

    try:
        with open(_CONFIG_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError):
        config = _default_config()
        save_service_config(config)
        return config

    if "management_password_hash" in data and "service_password_hash" in data:
        return data

    if "password_hash" in data and "salt" in data:
        print(
            "[service_config] Migrating single-password config to two levels: "
            "the existing password becomes the Service level, a fresh default "
            f'Management password ("{_DEFAULT_MANAGEMENT_PASSWORD}") was generated.'
        )
        mgmt_hash, mgmt_salt = _new_credential(_DEFAULT_MANAGEMENT_PASSWORD)
        config = {
            "management_password_hash": mgmt_hash,
            "management_salt": mgmt_salt,
            "service_password_hash": data["password_hash"],
            "service_salt": data["salt"],
        }
        save_service_config(config)
        return config

    if "service_password" in data:
        print(
            "[service_config] Migrating plaintext password to two hashed levels: "
            "the existing password becomes the Service level, a fresh default "
            f'Management password ("{_DEFAULT_MANAGEMENT_PASSWORD}") was generated.'
        )
        svc_hash, svc_salt = _new_credential(str(data["service_password"]))
        mgmt_hash, mgmt_salt = _new_credential(_DEFAULT_MANAGEMENT_PASSWORD)
        config = {
            "management_password_hash": mgmt_hash,
            "management_salt": mgmt_salt,
            "service_password_hash": svc_hash,
            "service_salt": svc_salt,
        }
        save_service_config(config)
        return config

    # Unrecognized/corrupt shape — fall back to defaults rather than
    # locking a technician out of a config they've never set up.
    config = _default_config()
    save_service_config(config)
    return config


def save_service_config(data: dict) -> None:
    _CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(_CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def verify_password(password: str) -> str | None:
    """Checks `password` against both levels. Returns "management" or
    "service" on a match, None if it matches neither."""
    config = load_service_config()
    if secrets.compare_digest(
        _hash_password(password, config["management_salt"]), config["management_password_hash"]
    ):
        return "management"
    if secrets.compare_digest(
        _hash_password(password, config["service_salt"]), config["service_password_hash"]
    ):
        return "service"
    return None


def verify_service_password(password: str) -> bool:
    """Narrower check used by the Change Password flow: that feature must
    be gated on the CURRENT *Service* password specifically, not any
    valid credential — a Management-level match doesn't count here."""
    return verify_password(password) == "service"


def set_service_password(new_password: str) -> None:
    """Changes only the Service-level password; Management is untouched.
    This is what ServiceHome's "Change Password" card calls, and that
    card is only reachable once already logged in at the Service level."""
    config = load_service_config()
    new_hash, new_salt = _new_credential(new_password)
    config["service_password_hash"] = new_hash
    config["service_salt"] = new_salt
    save_service_config(config)
