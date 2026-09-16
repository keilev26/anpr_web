from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import get_settings

settings = get_settings()

# Una sola capa de acceso a datos. El legacy tenía dos contradictorias:
# connect.py abría una conexión TCP+TLS nueva por consulta, y db.py una por
# request en flask.g.
engine = create_async_engine(
    settings.database_url,
    echo=False,
    pool_pre_ping=True,
    future=True,
)

SessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with SessionLocal() as session:
        yield session
