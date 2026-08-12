from __future__ import annotations

import time

import pytest

from app.user.security import (
    InvalidSessionToken,
    create_session_token,
    decode_session_token,
    hash_password,
    verify_password,
)


def test_bcrypt_hash_and_v1_hash_are_compatible():
    hashed = hash_password("rahasia-ku")

    assert hashed.startswith(("$2a$", "$2b$", "$2y$"))
    assert verify_password("rahasia-ku", hashed) is True
    assert verify_password("salah", hashed) is False

    known_v1_hash = "$2b$12$abcdefghijklmnopqrstuutwZ1IOTtu3SsEBT5lI/LFncP31tIybm"
    assert verify_password("password", known_v1_hash) is True


def test_signed_session_token_rejects_tampering_and_expiry():
    token = create_session_token(user_id=42, secret="test-secret", expires_seconds=60)
    assert decode_session_token(token, secret="test-secret")["uid"] == 42

    with pytest.raises(InvalidSessionToken):
        decode_session_token(token + "x", secret="test-secret")

    expired = create_session_token(user_id=42, secret="test-secret", expires_seconds=-1)
    time.sleep(0.01)
    with pytest.raises(InvalidSessionToken):
        decode_session_token(expired, secret="test-secret")
