from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, HTTPException, Request, Response, status
from sqlalchemy import select

from app.core.config import get_settings
from app.core.deps import CurrentUser, DbSession
from app.core.security import (
    create_token,
    decode_token,
    hash_password,
    needs_rehash,
    verify_password,
)
from app.db.models import LoginAttempt, User, utcnow
from app.schemas.auth import LoginRequest, LoginResponse
from app.schemas.user import UserOut

router = APIRouter(prefix="/auth", tags=["auth"])

REFRESH_COOKIE = "anpr_refresh"


def _set_refresh_cookie(response: Response, token: str) -> None:
    settings = get_settings()
    # HttpOnly: inaccesible desde JavaScript, así un XSS no puede robar la sesión.
    # El access token, en cambio, vive solo en memoria del cliente.
    response.set_cookie(
        REFRESH_COOKIE,
        token,
        httponly=True,
        secure=not settings.dev_mode,
        samesite="lax",
        max_age=settings.refresh_token_days * 24 * 3600,
        # Path="/" y no "/auth": el navegador solo envía una cookie cuando la
        # ruta de la petición empieza por su Path, y el frontend llama a la API
        # bajo un prefijo (/api/auth/refresh). Con Path="/auth" la cookie no se
        # enviaba nunca y el refresh siempre daba 401.
        path="/",
    )


def _login_response(user: User, response: Response) -> LoginResponse:
    settings = get_settings()
    _set_refresh_cookie(response, create_token(user.id, "refresh"))
    return LoginResponse(
        access_token=create_token(user.id, "access"),
        expires_in=settings.access_token_minutes * 60,
        user=UserOut.model_validate(user),
    )


def _as_utc(dt: datetime) -> datetime:
    # SQLite devuelve fechas sin zona aunque la columna sea timezone=True.
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


async def _check_not_locked(db: DbSession, email: str) -> LoginAttempt | None:
    attempt = await db.get(LoginAttempt, email)
    if attempt and attempt.locked_until:
        remaining = (_as_utc(attempt.locked_until) - utcnow()).total_seconds()
        if remaining > 0:
            # Se responde antes de verificar la contraseña: ni siquiera la correcta
            # entra, y así el bloqueo no le sirve al atacante como oráculo.
            raise HTTPException(
                status.HTTP_429_TOO_MANY_REQUESTS,
                "Demasiados intentos fallidos. Inténtalo más tarde.",
                headers={"Retry-After": str(int(remaining) + 1)},
            )
    return attempt


async def _register_failure(db: DbSession, email: str, attempt: LoginAttempt | None) -> None:
    settings = get_settings()
    if attempt is None:
        attempt = LoginAttempt(email=email, failures=0)
        db.add(attempt)
    if attempt.locked_until:  # bloqueo anterior ya vencido: empieza de cero
        attempt.locked_until = None
        attempt.failures = 0
    attempt.failures += 1
    if attempt.failures >= settings.login_max_failures:
        attempt.locked_until = utcnow() + timedelta(minutes=settings.login_lock_minutes)
    await db.commit()


@router.post("/login", response_model=LoginResponse)
async def login(body: LoginRequest, response: Response, db: DbSession) -> LoginResponse:
    email = str(body.email).lower()
    attempt = await _check_not_locked(db, email)

    stmt = select(User).where(User.email == body.email)
    user = (await db.execute(stmt)).scalar_one_or_none()

    # Mismo mensaje y mismo coste tanto si el correo no existe como si la
    # contraseña falla: distinguirlos permitiría enumerar usuarios.
    if (
        user is None
        or not user.password_hash
        or not verify_password(body.password, user.password_hash)
    ):
        await _register_failure(db, email, attempt)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Credenciales inválidas")

    if not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Credenciales inválidas")

    if attempt is not None:
        await db.delete(attempt)

    # Si Argon2 subió sus parámetros, se regenera el hash aprovechando que
    # aquí sí tenemos la contraseña en claro.
    if needs_rehash(user.password_hash):
        user.password_hash = hash_password(body.password)
    await db.commit()

    return _login_response(user, response)


@router.post("/refresh", response_model=LoginResponse)
async def refresh(request: Request, response: Response, db: DbSession) -> LoginResponse:
    token = request.cookies.get(REFRESH_COOKIE)
    user_id = decode_token(token, expected="refresh") if token else None
    if user_id is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Sesión expirada")

    user = await db.get(User, user_id)
    if user is None or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Sesión inválida")

    return _login_response(user, response)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(response: Response) -> None:
    response.delete_cookie(REFRESH_COOKIE, path="/")


@router.get("/me", response_model=UserOut)
async def me(user: CurrentUser) -> User:
    return user
