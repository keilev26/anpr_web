from typing import Annotated

from fastapi import Depends, Header, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.security import decode_token
from app.db.models import Role, User
from app.db.session import get_db

DbSession = Annotated[AsyncSession, Depends(get_db)]
Config = Annotated[Settings, Depends(get_settings)]


async def current_user(request: Request, db: DbSession) -> User:
    """
    Usuario autenticado. Va como dependencia en TODOS los routers salvo
    /health y /auth/login: en el legacy no había ninguna protección y un POST
    anónimo a /list/cars bastaba para abrir la puerta.
    """
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "No autenticado")

    user_id = decode_token(auth.removeprefix("Bearer "), expected="access")
    if user_id is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Token inválido o expirado")

    user = await db.get(User, user_id)
    if user is None or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Usuario inactivo o inexistente")
    return user


CurrentUser = Annotated[User, Depends(current_user)]


async def require_admin(user: CurrentUser) -> User:
    if user.role is not Role.administrator:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Requiere rol administrativo")
    return user


AdminUser = Annotated[User, Depends(require_admin)]


async def verify_device(
    settings: Config,
    x_device_key: Annotated[str | None, Header()] = None,
) -> None:
    """Autenticación del dispositivo de campo para POST /v1/detections."""
    if not settings.device_api_key:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "DEVICE_API_KEY no configurada")
    # Comparación en tiempo constante para no filtrar la clave por temporización.
    import hmac

    if x_device_key is None or not hmac.compare_digest(x_device_key, settings.device_api_key):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Clave de dispositivo inválida")
