import logging
import time
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy import select

from app.core.config import get_settings
from app.core.deps import DbSession, verify_device
from app.db.models import EventDetection
from app.schemas.common import normalize_plate
from app.schemas.event import GateCommand, Verdict
from app.schemas.user import UserOut
from app.services.authorization import resolve_plate
from app.services.plate_reader import (
    InferenceError,
    LambdaPlateReader,
    PlateReader,
    StubPlateReader,
)

router = APIRouter(prefix="/v1", tags=["detections"])
log = logging.getLogger("anpr.detections")

GATE_COMMAND_TTL_S = 10

# Límite del cuerpo de una invocación síncrona de Lambda: 6 MB. Los frames viajan
# en base64 (+33 %), así que se deja margen.
MAX_FRAMES_BYTES = 4 * 1024 * 1024

_reader: PlateReader | None = None


def get_plate_reader() -> PlateReader:
    """Lambda de inferencia si está configurado; si no, stub (desarrollo y tests).
    Se crea una vez: el cliente de boto3 es costoso de construir."""
    global _reader
    if _reader is None:
        fn = get_settings().infer_function_name
        _reader = LambdaPlateReader(fn) if fn else StubPlateReader()
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

    datos = [await f.read() for f in frames]
    if sum(len(d) for d in datos) > MAX_FRAMES_BYTES:
        raise HTTPException(
            status.HTTP_413_CONTENT_TOO_LARGE,
            "La ráfaga supera 4 MB: reducir resolución o fotogramas",
        )
    try:
        raw_plate, confidence = await reader.read(datos)
    except InferenceError:
        # 503 y no 500 genérico: el contrato dice que ante 5xx la Pi reintenta y
        # NO abre. Se registra con traza para diagnosticar el Lambda de inferencia.
        log.exception("Fallo del Lambda de inferencia en el evento %s", event_id)
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, "Inferencia no disponible, reintentar"
        ) from None
    if raw_plate is None:
        raise HTTPException(422, "Ninguna placa legible en la ráfaga")

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
        command=GateCommand(action="open" if authorized else "deny", ttl_s=GATE_COMMAND_TTL_S),
        latency_ms=latency,
    )
