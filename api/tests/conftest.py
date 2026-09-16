import os

os.environ.setdefault("SECRET_KEY", "clave-de-pruebas-no-usar-en-produccion")
os.environ.setdefault("DEVICE_API_KEY", "clave-dispositivo-test")
os.environ.setdefault("DEV_MODE", "true")

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.core.security import hash_password
from app.db.models import Base, Car, Role, User
from app.db.session import get_db
from app.main import app

TEST_PASSWORD = "contrasena-de-prueba"


@pytest.fixture
async def db_engine():
    # StaticPool + memoria compartida: sin esto, cada conexión vería una BD
    # distinta y las tablas creadas desaparecerían.
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest.fixture
async def session_factory(db_engine):
    return async_sessionmaker(db_engine, expire_on_commit=False, class_=AsyncSession)


@pytest.fixture
async def seed(session_factory):
    """Un administrador, un docente activo y un estudiante inactivo."""
    async with session_factory() as s:
        admin = User(
            name="Admin Uno", email="admin@uni.pe", role=Role.administrator,
            password_hash=hash_password(TEST_PASSWORD), is_active=True,
        )
        admin.cars = [Car(plate="CUB-604")]

        teacher = User(
            name="Docente Dos", email="docente@uni.pe", role=Role.teacher,
            password_hash=hash_password(TEST_PASSWORD), is_active=True,
        )
        teacher.cars = [Car(plate="ABC-123")]

        inactive = User(
            name="Baja Tres", email="baja@uni.pe", role=Role.student,
            password_hash=hash_password(TEST_PASSWORD), is_active=False,
        )
        inactive.cars = [Car(plate="XYZ-789")]

        s.add_all([admin, teacher, inactive])
        await s.commit()
        return {"admin": admin.id, "teacher": teacher.id, "inactive": inactive.id}


@pytest.fixture
async def client(session_factory, seed):
    async def _get_db():
        async with session_factory() as s:
            yield s

    app.dependency_overrides[get_db] = _get_db
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as c:
        yield c
    app.dependency_overrides.clear()


async def login_as(client: AsyncClient, email: str) -> str:
    r = await client.post("/auth/login", json={"email": email, "password": TEST_PASSWORD})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


@pytest.fixture
async def admin_headers(client):
    return {"Authorization": f"Bearer {await login_as(client, 'admin@uni.pe')}"}


@pytest.fixture
async def teacher_headers(client):
    return {"Authorization": f"Bearer {await login_as(client, 'docente@uni.pe')}"}
