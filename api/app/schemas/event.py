from pydantic import BaseModel, ConfigDict, Field

from app.schemas.common import UtcDatetime
from app.schemas.user import UserOut


class EventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    plate: str
    detected_at: UtcDatetime
    authorized: bool
    confidence: float | None = None
    image_url: str | None = None
    gate_opened: bool | None = None
    latency_ms: int | None = None
    camera_id: str | None = None
    user: UserOut | None = None


class GateCommand(BaseModel):
    action: str = Field(examples=["open", "deny"])
    ttl_s: int = Field(
        default=10,
        description="La Pi descarta el veredicto si llega después de este plazo.",
    )


class Verdict(BaseModel):
    """Respuesta del camino crítico Pi -> nube."""

    event_id: str
    plate: str | None = None
    confidence: float | None = None
    authorized: bool
    user: UserOut | None = None
    command: GateCommand
    latency_ms: int
