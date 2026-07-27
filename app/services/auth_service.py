import os
from datetime import datetime, timedelta, timezone
from typing import Any

import bcrypt
import jwt

from app.core.config import load_environment


class AuthError(Exception):
    pass


class AuthTokenError(AuthError):
    pass


def _get_jwt_secret_key() -> str:
    load_environment()
    return os.getenv("JWT_SECRET_KEY", "dev-only-change-me")


def _get_jwt_algorithm() -> str:
    load_environment()
    return os.getenv("JWT_ALGORITHM", "HS256")


def _get_access_token_expire_minutes() -> int:
    load_environment()
    return int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "1440"))


def hash_password(password: str) -> str:
    password_bytes = password.encode("utf-8")
    return bcrypt.hashpw(password_bytes, bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    if not password_hash or password_hash == "UNUSABLE_PASSWORD":
        return False

    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except ValueError:
        return False


def create_access_token(user_id: str, expires_delta: timedelta | None = None) -> str:
    expires_at = datetime.now(timezone.utc) + (
        expires_delta or timedelta(minutes=_get_access_token_expire_minutes())
    )
    payload: dict[str, Any] = {
        "sub": user_id,
        "exp": expires_at,
        "iat": datetime.now(timezone.utc),
    }
    return jwt.encode(payload, _get_jwt_secret_key(), algorithm=_get_jwt_algorithm())


def decode_access_token(token: str) -> str:
    try:
        payload = jwt.decode(token, _get_jwt_secret_key(), algorithms=[_get_jwt_algorithm()])
    except jwt.PyJWTError as exc:
        raise AuthTokenError("invalid or expired access token") from exc

    user_id = payload.get("sub")
    if not isinstance(user_id, str) or not user_id:
        raise AuthTokenError("access token missing subject")

    return user_id
