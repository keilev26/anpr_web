"""
Mensajes del bus interno (contrato B, `contracts/mqtt-topics.md`).

Cada tópico tiene un modelo. Quien publica construye el modelo; quien recibe lo
valida con `decode` y descarta lo inválido. Un mensaje malformado nunca llega a la
lógica de un servicio, y menos a `anpr-gate`.
"""

from datetime import UTC, datetime
from typing import ClassVar, Literal
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, ValidationError


def utcnow() -> datetime:
    return datetime.now(UTC)


class Message(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    TOPIC: ClassVar[str] = ""  # lo fija cada subclase; no forma parte del contenido

    def encode(self) -> bytes:
        return self.model_dump_json().encode()


class Trigger(Message):
    TOPIC = "gate/trigger"
    event_id: UUID
    source: Literal["loop", "manual"]
    ts: AwareDatetime


class FramesReady(Message):
    TOPIC = "gate/frames_ready"
    event_id: UUID
    path: str
    count: int = Field(ge=1, le=10)
    # Añadido al contrato: el uplink lo necesita para `captured_at` y para su plazo.
    captured_at: AwareDatetime


class Command(Message):
    TOPIC = "gate/command"
    event_id: UUID
    action: Literal["open"]
    ttl_s: int = Field(ge=1, le=60)
    issued_at: AwareDatetime

    def expired(self, now: datetime | None = None) -> bool:
        now = now or utcnow()
        return (now - self.issued_at).total_seconds() > self.ttl_s


class GateState(Message):
    TOPIC = "gate/state"
    state: Literal["unknown", "homing", "closed", "opening", "open", "closing", "fault", "manual"]
    position_known: bool
    ts: AwareDatetime


class Fault(Message):
    TOPIC = "gate/fault"
    code: str
    detail: str
    ts: AwareDatetime


class Verdict(Message):
    """Resultado de un evento, para `anpr-trigger` (reintentos) y `anpr-health`."""

    TOPIC = "gate/verdict"
    event_id: UUID
    outcome: Literal["open", "deny", "unreadable", "rejected", "unavailable", "late"]
    plate: str | None = None
    http_status: int | None = None
    latency_ms: int | None = None
    ts: AwareDatetime


class ServiceStatus(Message):
    """Retenido, y también el Last Will: si un servicio muere, el broker publica offline."""

    TOPIC = "svc/{service}/status"
    service: str
    status: Literal["online", "offline"]


class CameraStatus(Message):
    """Retenido. Lo publica `anpr-capture` periódicamente."""

    TOPIC = "camera/status"
    online: bool
    fps: float | None = None
    last_frame_age_s: float | None = None
    ts: AwareDatetime


class HealthSummary(Message):
    """Retenido. Resumen de `anpr-health`: `mosquitto_sub -t health/summary -v`."""

    TOPIC = "health/summary"
    ok: bool
    problems: list[str]
    services: dict[str, str]
    gate_state: str | None = None
    cloud: Literal["ok", "degraded", "unreachable", "unknown"]
    ts: AwareDatetime


BY_TOPIC: dict[str, type[Message]] = {
    m.TOPIC: m
    for m in (Trigger, FramesReady, Command, GateState, Fault, Verdict, CameraStatus, HealthSummary)
}


class InvalidMessage(ValueError):
    pass


def decode(model: type[Message], payload: bytes) -> Message:
    try:
        return model.model_validate_json(payload)
    except ValidationError as e:
        raise InvalidMessage(str(e)) from None
