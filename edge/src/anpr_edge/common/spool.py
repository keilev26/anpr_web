"""
Spool en disco de las ráfagas: `<spool>/events/<event_id>/`.

- `anpr-capture` crea el directorio con los JPEG y `meta.json`.
- `anpr-uplink` añade `status.json` (enviado, pendiente, rechazado) y hace la limpieza.

Todo se escribe de forma atómica (temporal + fsync + rename): un corte de luz a
mitad de escritura deja o el evento completo o nada, nunca fotos a medias que el
uplink intente subir.
"""

import json
import os
import shutil
import time
from pathlib import Path
from uuid import UUID

EVENTS = "events"
TMP_PREFIX = ".tmp-"


class SpoolError(ValueError):
    pass


def _fsync_dir(path: Path) -> None:
    fd = os.open(path, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _write_file(path: Path, data: bytes) -> None:
    with open(path, "wb") as f:
        f.write(data)
        f.flush()
        os.fsync(f.fileno())


def events_dir(spool: Path) -> Path:
    return spool / EVENTS


def write_event(spool: Path, event_id: UUID, frames: list[bytes], meta: dict) -> Path:
    base = events_dir(spool)
    base.mkdir(parents=True, exist_ok=True)
    final = base / str(event_id)
    if final.exists():
        raise SpoolError(f"El evento {event_id} ya existe")
    tmp = base / f"{TMP_PREFIX}{event_id}-{os.getpid()}"
    shutil.rmtree(tmp, ignore_errors=True)
    tmp.mkdir()
    for i, jpeg in enumerate(frames):
        _write_file(tmp / f"frame_{i:02d}.jpg", jpeg)
    _write_file(tmp / "meta.json", json.dumps(meta, default=str).encode())
    _fsync_dir(tmp)
    os.rename(tmp, final)
    _fsync_dir(base)
    return final


def resolve_event(spool: Path, path: str) -> Path:
    """
    Valida que una ruta recibida por el bus esté dentro del spool. Un mensaje no
    debe poder hacer que el uplink lea o suba archivos de otra parte del sistema.
    """
    base = events_dir(spool).resolve()
    p = Path(path).resolve()
    if p.parent != base or p.name.startswith(TMP_PREFIX):
        raise SpoolError(f"Ruta fuera del spool: {path}")
    return p


def read_frames(event_dir: Path) -> list[bytes]:
    frames = [p.read_bytes() for p in sorted(event_dir.glob("frame_*.jpg"))]
    if not frames:
        raise SpoolError(f"Sin frames en {event_dir}")
    return frames


def read_meta(event_dir: Path) -> dict:
    return json.loads((event_dir / "meta.json").read_text())


def read_status(event_dir: Path) -> dict | None:
    try:
        return json.loads((event_dir / "status.json").read_text())
    except FileNotFoundError:
        return None


def write_status(event_dir: Path, status: dict) -> None:
    tmp = event_dir / "status.json.tmp"
    _write_file(tmp, json.dumps(status, default=str).encode())
    os.rename(tmp, event_dir / "status.json")


def dir_size(path: Path) -> int:
    return sum(f.stat().st_size for f in path.iterdir() if f.is_file())


def event_time(event_dir: Path) -> float:
    """Momento de la captura (mtime de meta.json, que no cambia al escribir el estado)."""
    meta = event_dir / "meta.json"
    return (meta if meta.exists() else event_dir).stat().st_mtime


def list_events(spool: Path) -> list[Path]:
    """Eventos completos, del más antiguo al más reciente."""
    base = events_dir(spool)
    if not base.exists():
        return []
    dirs = [d for d in base.iterdir() if d.is_dir() and not d.name.startswith(TMP_PREFIX)]
    return sorted(dirs, key=event_time)


def clean_orphans(spool: Path, older_than_s: float = 600) -> int:
    """Temporales que dejó un proceso que murió a mitad de escritura."""
    base = events_dir(spool)
    if not base.exists():
        return 0
    n = 0
    for d in base.glob(f"{TMP_PREFIX}*"):
        if time.time() - d.stat().st_mtime > older_than_s:
            shutil.rmtree(d, ignore_errors=True)
            n += 1
    return n
