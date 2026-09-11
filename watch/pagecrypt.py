"""Password-encrypt the ntfy topic for the public status page.

The page is static, so the only way to gate the "send test push" button behind a
password is to embed the topic encrypted. PBKDF2-HMAC-SHA256 derives a key from
the password; AES-256-GCM encrypts the topic. The browser reverses this with
WebCrypto, so both sides must agree on these parameters exactly.
"""
from __future__ import annotations

import base64
import hashlib
import os

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

ITERATIONS = 600_000
_SALT_LEN = 16
_IV_LEN = 12


def _b64(raw: bytes) -> str:
    return base64.b64encode(raw).decode("ascii")


def _key(password: str, salt: bytes, iterations: int) -> bytes:
    return hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations, dklen=32)


def encrypt(plaintext: str, password: str) -> dict:
    """Return {"salt", "iv", "ct", "iter"}; salt/iv/ct are base64, ct includes the GCM tag."""
    salt = os.urandom(_SALT_LEN)
    iv = os.urandom(_IV_LEN)
    ct = AESGCM(_key(password, salt, ITERATIONS)).encrypt(iv, plaintext.encode("utf-8"), None)
    return {"salt": _b64(salt), "iv": _b64(iv), "ct": _b64(ct), "iter": ITERATIONS}


def decrypt(blob: dict, password: str) -> str:
    """Inverse of encrypt; raises ValueError on a wrong password or corrupt blob."""
    salt = base64.b64decode(blob["salt"])
    iv = base64.b64decode(blob["iv"])
    ct = base64.b64decode(blob["ct"])
    try:
        return AESGCM(_key(password, salt, int(blob["iter"]))).decrypt(iv, ct, None).decode("utf-8")
    except InvalidTag as e:
        raise ValueError("wrong password or corrupt blob") from e
