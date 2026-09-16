import time
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy import select

from app.core.deps import DbSession, verify_device
from app.db.models import EventDetection
from app.schemas.common import normalize_plate
from app.schemas.event import GateCommand, Verdict
from app.schemas.user import UserOut
from app.services.authorization import resolve_plate
from app.services.plate_reader import PlateReader, StubPlateReader

router = APIRouter(prefix="/v1", tags=["detections"])

GATE_COMMAND_TTL_S = 10

# F4 sustituye esto por el cliente del Lambda de inferencia. Se inyecta como
# dependencia para que los tests puedan fijar la lectura sin tocar el router.
_reader: PlateReader = StubPlateReader()


def get_plate_reader() -> PlateReader:
    return _reader


@router.post("/detections", response_model=Verdict)
async def create_detection(
    db: DbSession,
    gate_id: str = Form(...),
    event_id: str = Form(...),
    captured_at: datetime = Form(...),
    frames: list[UploadFile] = File(...),
    reader: PlateReader = Depends(get_plate_reader),
    _: None = Depends(verify_device),
) -> Verdict:
    """
    Camino crítico Pi -> nube. Presupuesto de latencia: < 4 s.

    Devuelve el veredicto en la MISMA respuesta HTTP. MQTT queda fuera del
    camino crítico: la Pi que detecta es la misma que abre, así que un broker
    intermedio solo añadiría un componente más que puede fallar.
    """
    started = time.perf_counter()

    try:
        uuid.UUID(event_id)
    except ValueError:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "event_id debe ser un UUID") from None

    if not 1 <= len(frames) <= 10:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Se esperan entre 1 y 10 frames")

    # Idempotencia: un reenvío por timeout no debe abrir la puerta dos veces.
    existing = (
        await db.execute(select(EventDetection).where(EventDetection.event_uuid == event_id))
    ).scalar_one_or_none()
    if existing is not None:
        return Verdict(
            event_id=event_id,
            plate=existing.plate,
            confidence=existing.confidence,
            authorized=existing.authorized,
            user=UserOut.model_validate(existing.user) if existing.user else None,
            command=GateCommand(
                action="open" if existing.authorized else "deny", ttl_s=GATE_COMMAND_TTL_S
            ),
            latency_ms=int((time.perf_counter() - started) * 1000),
        )

    raw_plate, confidence = await reader.read([await f.read() for f in frames])
    if raw_plate is None:
        raise HTTPException(
            422, "Ninguna placa legible en la ráfaga"
        )

    plate = normalize_plate(raw_plate)
    authorized, owner = await resolve_plate(db, plate)
    latency = int((time.perf_counter() - started) * 1000)

    event = EventDetection(
        plate=plate,
        detected_at=captured_at.astimezone(UTC) if captured_at.tzinfo else captured_at,
        authorized=authorized,
        confidence=confidence,
        camera_id=gate_id,
        gate_opened=authorized,
        latency_ms=latency,
        event_uuid=event_id,
        user_id=owner.id if owner else None,
    )
    db.add(event)
    await db.commit()

    return Verdict(
        event_id=event_id,
        plate=plate,
        confidence=confidence,
        authorized=authorized,
        user=UserOut.model_validate(owner) if owner else None,
        command=GateCommand(
            action="open" if authorized else "deny", ttl_s=GATE_COMMAND_TTL_S
        ),
        latency_ms=latency,
    )
