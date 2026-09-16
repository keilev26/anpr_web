import enum
from datetime import UTC, datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Role(enum.StrEnum):
    student = "student"
    teacher = "teacher"
    administrator = "administrator"


def utcnow() -> datetime:
    """Todo se guarda en UTC. La conversión a America/Lima es cosa del cliente."""
    return datetime.now(UTC)


class User(Base):
    __tablename__ = "user"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    phone: Mapped[str | None] = mapped_column(String(32), default=None)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    role: Mapped[Role] = mapped_column(Enum(Role, native_enum=False), default=Role.student)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    # El legacy tenía una tabla `login` separada y huérfana; aquí va unificado.
    password_hash: Mapped[str | None] = mapped_column(String(255), default=None)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    created_by: Mapped[int | None] = mapped_column(
        ForeignKey("user.id", ondelete="SET NULL"), default=None
    )

    cars: Mapped[list["Car"]] = relationship(
        back_populates="owner",
        cascade="all, delete-orphan",
        lazy="selectin",  # evita el N+1 al listar usuarios con sus placas
        order_by="Car.id",
    )


class Car(Base):
    __tablename__ = "list_car"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    plate: Mapped[str] = mapped_column(String(16), unique=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("user.id", ondelete="CASCADE"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    owner: Mapped[User] = relationship(back_populates="cars")


class EventDetection(Base):
    __tablename__ = "event_detection"

    # BIGINT en MySQL por el volumen esperado, pero INTEGER en SQLite: ese
    # motor solo autoincrementa "INTEGER PRIMARY KEY", con BIGINT falla el INSERT.
    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True)

    # Texto suelto SIN FK a list_car, a propósito: hay que poder registrar
    # placas NO autorizadas, que por definición no están en la lista blanca.
    plate: Mapped[str] = mapped_column(String(16), index=True)

    detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    authorized: Mapped[bool] = mapped_column(Boolean, default=False)

    # Columnas que el legacy no tenía y el dashboard ya esperaba.
    confidence: Mapped[float | None] = mapped_column(Float, default=None)
    image_s3_key: Mapped[str | None] = mapped_column(String(512), default=None)
    camera_id: Mapped[str | None] = mapped_column(String(64), default=None)
    gate_opened: Mapped[bool | None] = mapped_column(Boolean, default=None)
    latency_ms: Mapped[int | None] = mapped_column(Integer, default=None)

    # Idempotencia: un reenvío por timeout no debe abrir la puerta dos veces.
    event_uuid: Mapped[str | None] = mapped_column(String(36), unique=True, default=None)

    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("user.id", ondelete="SET NULL"), default=None
    )
    user: Mapped[User | None] = relationship(lazy="selectin")

    __table_args__ = (Index("ix_event_plate_detected", "plate", "detected_at"),)


class LoginAttempt(Base):
    """
    Intentos fallidos de login por correo, para frenar la fuerza bruta.

    En la base de datos y no en memoria: en Lambda cada contenedor tiene su propia
    memoria, y un contador local se reiniciaría o se repartiría entre contenedores.
    La clave es el correo tal como llega, exista o no: bloquear solo correos
    registrados permitiría enumerarlos.
    """

    __tablename__ = "login_attempt"

    email: Mapped[str] = mapped_column(String(255), primary_key=True)
    failures: Mapped[int] = mapped_column(Integer, default=0)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )
