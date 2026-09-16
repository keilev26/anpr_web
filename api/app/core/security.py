from datetime import UTC, datetime, timedelta
from typing import Literal

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerificationError, VerifyMismatchError

from app.core.config import get_settings

ALGORITHM = "HS256"
TokenKind = Literal["access", "refresh"]

# Argon2id es el ganador del Password Hashing Competition y el recomendado
# actual de OWASP. El legacy usaba el pbkdf2 por defecto de Werkzeug.
_hasher = PasswordHasher()


def hash_password(plain: str) -> str:
    return _hasher.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    try:
        _hasher.verify(hashed, plain)
        return True
    except (VerifyMismatchError, VerificationError):
        return False


def needs_rehash(hashed: str) -> bool:
    """True si el hash usa parámetros antiguos y conviene regenerarlo al entrar."""
    return _hasher.check_needs_rehash(hashed)


def create_token(subject: int, kind: TokenKind) -> str:
    settings = get_settings()
    now = datetime.now(UTC)
    expires = (
        timedelta(minutes=settings.access_token_minutes)
        if kind == "access"
        else timedelta(days=settings.refresh_token_days)
    )
    payload = {
        "sub": str(subject),
        "typ": kind,
        "iat": int(now.timestamp()),
        "exp": int((now + expires).timestamp()),
    }
    return jwt.encode(payload, settings.secret_key, algorithm=ALGORITHM)


def decode_token(token: str, expected: TokenKind) -> int | None:
    """Devuelve el id de usuario, o None si el token es inválido o no es del tipo esperado."""
    try:
        payload = jwt.decode(token, get_settings().secret_key, algorithms=[ALGORITHM])
    except jwt.PyJWTError:
        return None
    # Sin esta comprobación, un refresh token serviría como access token y
    # duraría 14 días en lugar de 15 minutos.
    if payload.get("typ") != expected:
        return None
    try:
        return int(payload["sub"])
    except (KeyError, TypeError, ValueError):
        return None
