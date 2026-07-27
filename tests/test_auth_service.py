from datetime import timedelta

import pytest

from app.services.auth_service import (
    AuthTokenError,
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)


def test_password_hash_and_verify() -> None:
    password_hash = hash_password("demo123456")

    assert password_hash != "demo123456"
    assert verify_password("demo123456", password_hash)
    assert not verify_password("wrong-password", password_hash)
    assert not verify_password("demo123456", "UNUSABLE_PASSWORD")


def test_access_token_round_trip() -> None:
    token = create_access_token("default_user", expires_delta=timedelta(minutes=5))

    assert decode_access_token(token) == "default_user"


def test_expired_access_token_is_rejected() -> None:
    token = create_access_token("default_user", expires_delta=timedelta(minutes=-1))

    with pytest.raises(AuthTokenError):
        decode_access_token(token)
