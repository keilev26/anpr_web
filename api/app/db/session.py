import ssl
from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import Settings, get_settings


def engine_options(settings: Settings) -> dict:
    """
    Opciones del motor, compartidas con Alembic (`alembic/env.py`) para que las
    migraciones se conecten exactamente igual que la API.
    """
    options: dict = {"pool_pre_ping": True}
    if settings.db_ssl_ca:
        # cadata en vez de un fichero: en Lambda el certificado llega desde SSM.
        # create_default_context verifica también el nombre del host.
        options["connect_args"] = {"ssl": ssl.create_default_context(cadata=settings.db_ssl_ca)}
    if settings.db_nullpool:
        options["poolclass"] = NullPool
        options.pop("pool_pre_ping")  # sin pool no hay conexiones que comprobar
    return options


settings = get_settings()

# Una sola capa de acceso a datos. El legacy tenía dos contradictorias:
# connect.py abría una conexión TCP+TLS nueva por consulta, y db.py una por
# request en flask.g.
engine = create_async_engine(settings.database_url, echo=False, **engine_options(settings))

SessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with SessionLocal() as session:
        yield session
