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
from app.db.models import User
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
        path="/auth",
    )


def _login_response(user: User, response: Response) -> LoginResponse:
    settings = get_settings()
    _set_refresh_cookie(response, create_token(user.id, "refresh"))
    return LoginResponse(
        access_token=create_token(user.id, "access"),
        expires_in=settings.access_token_minutes * 60,
        user=UserOut.model_validate(user),
    )


@router.post("/login", response_model=LoginResponse)
async def login(body: LoginRequest, response: Response, db: DbSession) -> LoginResponse:
    stmt = select(User).where(User.email == body.email)
    user = (await db.execute(stmt)).scalar_one_or_none()

    # Mismo mensaje y mismo coste tanto si el correo no existe como si la
    # contraseña falla: distinguirlos permitiría enumerar usuarios.
    if user is None or not user.password_hash or not verify_password(
        body.password, user.password_hash
    ):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Credenciales inválidas")

    if not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Credenciales inválidas")

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
    response.delete_cookie(REFRESH_COOKIE, path="/auth")


@router.get("/me", response_model=UserOut)
async def me(user: CurrentUser) -> User:
    return user
