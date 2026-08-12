"""Password and signed-cookie helpers compatible with V1 bcrypt hashes."""
from __future__ import annotations

import base64
import ctypes
import ctypes.util
import hashlib
import hmac
import json
import secrets
import threading
import time
from typing import Any


class InvalidSessionToken(ValueError):
    """Raised when a signed user session token is invalid or expired."""


_BCRYPT_ALPHABET = "./ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789"
_CRYPT_LOCK = threading.Lock()


def _bcrypt_base64(raw: bytes) -> str:
    result: list[str] = []
    offset = 0
    while offset < len(raw):
        c1 = raw[offset]
        offset += 1
        result.append(_BCRYPT_ALPHABET[(c1 >> 2) & 0x3F])
        c1 = (c1 & 0x03) << 4
        if offset >= len(raw):
            result.append(_BCRYPT_ALPHABET[c1 & 0x3F])
            break
        c2 = raw[offset]
        offset += 1
        c1 |= (c2 >> 4) & 0x0F
        result.append(_BCRYPT_ALPHABET[c1 & 0x3F])
        c1 = (c2 & 0x0F) << 2
        if offset >= len(raw):
            result.append(_BCRYPT_ALPHABET[c1 & 0x3F])
            break
        c2 = raw[offset]
        offset += 1
        c1 |= (c2 >> 6) & 0x03
        result.append(_BCRYPT_ALPHABET[c1 & 0x3F])
        result.append(_BCRYPT_ALPHABET[c2 & 0x3F])
    return "".join(result)


def _libcrypt_hash(password: str, salt_or_hash: str) -> str:
    library_name = ctypes.util.find_library("crypt")
    if not library_name:
        raise RuntimeError("bcrypt backend tidak tersedia pada sistem ini")
    library = ctypes.CDLL(library_name)
    library.crypt.argtypes = [ctypes.c_char_p, ctypes.c_char_p]
    library.crypt.restype = ctypes.c_char_p
    with _CRYPT_LOCK:
        result = library.crypt(password.encode("utf-8"), salt_or_hash.encode("ascii"))
    if not result:
        raise RuntimeError("gagal memproses hash password")
    return result.decode("ascii")


def hash_password(password: str, rounds: int = 12) -> str:
    if not password:
        raise ValueError("Password tidak boleh kosong.")
    try:
        import bcrypt  # type: ignore

        return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt(rounds)).decode("ascii")
    except ImportError:
        salt = _bcrypt_base64(secrets.token_bytes(16))[:22]
        return _libcrypt_hash(password, f"$2b${rounds:02d}${salt}")


def verify_password(password: str, hashed_password: str) -> bool:
    if not password or not hashed_password:
        return False
    try:
        import bcrypt  # type: ignore

        return bcrypt.checkpw(password.encode("utf-8"), hashed_password.encode("ascii"))
    except ImportError:
        try:
            calculated = _libcrypt_hash(password, hashed_password)
        except (RuntimeError, UnicodeError, ValueError):
            return False
        return hmac.compare_digest(calculated, hashed_password)
    except (ValueError, TypeError):
        return False


def _b64encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _b64decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(value + padding)


def create_session_token(*, user_id: int, secret: str, expires_seconds: int) -> str:
    now = int(time.time())
    payload = {"uid": int(user_id), "iat": now, "exp": now + int(expires_seconds)}
    encoded = _b64encode(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    signature = hmac.new(secret.encode("utf-8"), encoded.encode("ascii"), hashlib.sha256).digest()
    return f"{encoded}.{_b64encode(signature)}"


def decode_session_token(token: str, *, secret: str) -> dict[str, Any]:
    try:
        encoded, signature_text = token.split(".", 1)
        expected = hmac.new(secret.encode("utf-8"), encoded.encode("ascii"), hashlib.sha256).digest()
        supplied = _b64decode(signature_text)
        if not hmac.compare_digest(expected, supplied):
            raise InvalidSessionToken("Tanda tangan sesi tidak valid.")
        payload = json.loads(_b64decode(encoded).decode("utf-8"))
        if int(payload.get("exp", 0)) < int(time.time()):
            raise InvalidSessionToken("Sesi telah kedaluwarsa.")
        if int(payload.get("uid", 0)) <= 0:
            raise InvalidSessionToken("Identitas sesi tidak valid.")
        return payload
    except InvalidSessionToken:
        raise
    except (ValueError, TypeError, KeyError, json.JSONDecodeError, UnicodeError) as exc:
        raise InvalidSessionToken("Format sesi tidak valid.") from exc
