import base64
import re
from datetime import UTC, datetime
from typing import Annotated

from pydantic import BaseModel, BeforeValidator, Field, PlainSerializer

PLATE_RE = re.compile(r"^[A-Z][A-Z0-9]{2}-\d{3}$")
_NON_ALNUM = re.compile(r"[^A-Za-z0-9]")


def normalize_plate(value: str) -> str:
    """
    Formato canónico de placa peruana.

    La normalización vive AQUÍ, en un solo sitio, y no en cada cliente: el join
    `event_detection.plate = list_car.plate` es sobre texto, así que un espacio
    o una minúscula bastan para que una placa autorizada salga como denegada.

    Acepta "abc123", "ABC 123", "abc-123" y devuelve "ABC-123".
    """
    if not isinstance(value, str):
        return value
    clean = _NON_ALNUM.sub("", value).upper()
    if len(clean) == 6:
        clean = f"{clean[:3]}-{clean[3:]}"
    return clean


Plate = Annotated[
    str,
    BeforeValidator(normalize_plate),
    Field(pattern=PLATE_RE.pattern, examples=["CUB-604"]),
]


def _serialize_utc(value: datetime) -> str:
    """
    Serializa SIEMPRE con sufijo Z.

    Sin él, `new Date("2026-09-16T04:05:01")` en el navegador interpreta la
    fecha como hora LOCAL, no UTC, y el dashboard mostraría las detecciones
    desplazadas. SQLite no guarda la zona, así que a los datetime ingenuos se
    les asume UTC, que es lo único que esta API escribe.
    """
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


UtcDatetime = Annotated[datetime, PlainSerializer(_serialize_utc, return_type=str)]


def encode_cursor(last_id: int) -> str:
    """Cursor opaco. Es keyset, no offset: no se descoloca si se insertan filas."""
    return base64.urlsafe_b64encode(str(last_id).encode()).decode()


def decode_cursor(cursor: str | None) -> int | None:
    if not cursor:
        return None
    try:
        return int(base64.urlsafe_b64decode(cursor.encode()).decode())
    except (ValueError, UnicodeDecodeError):
        return None


class Page[T](BaseModel):
    items: list[T]
    next_cursor: str | None = None


class Message(BaseModel):
    detail: str
    code: str | None = None
