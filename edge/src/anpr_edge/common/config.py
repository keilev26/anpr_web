"""
Configuración de los servicios de campo.

Un solo archivo TOML (`/etc/anpr/edge.toml` en la Pi) con una sección por área.
Lo que cambia entre la laptop y la Pi vive aquí, nunca en el código: así lo probado
en la laptop es exactamente lo que corre en la Pi.

Falla al arrancar si el archivo no existe o tiene un error: un servicio que arranca
con valores por defecto sin avisar puede abrir la pluma con tiempos equivocados.
"""

import os
import tomllib
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

DEFAULT_PATH = Path("/etc/anpr/edge.toml")
ENV_VAR = "ANPR_EDGE_CONFIG"


class _Section(BaseModel):
    # Una clave mal escrita en el TOML es un error, no un valor que se ignora en silencio.
    model_config = ConfigDict(extra="forbid", frozen=True)


class MqttConfig(_Section):
    host: str = "127.0.0.1"
    port: int = 1883
    # En la Pi, cada servicio entra con su propio usuario (= nombre del servicio) y la
    # ACL de Mosquitto limita qué puede publicar. La contraseña llega por LoadCredential.
    auth: bool = False
    password_dir: Path = Path("/etc/anpr/mqtt")


class CameraConfig(_Section):
    rpc_url: str = "http://192.168.122.1:10000/sony/camera"
    liveview_size: Literal["L", "M"] = "M"
    timeout_s: float = Field(default=5.0, gt=0)
    stale_after_s: float = Field(
        default=3.0, gt=0, description="Sin frames durante este tiempo = reconectar"
    )


class CaptureConfig(_Section):
    # El contrato A pide al menos 3: el consenso de la nube exige 2 lecturas iguales.
    frames: int = Field(default=5, ge=3, le=10)
    spacing_ms: int = Field(default=150, ge=0)
    spool_dir: Path = Path("/var/spool/anpr")
    # Por debajo de los 4 MB de la API para no recibir un 413.
    max_burst_bytes: int = Field(default=3_500_000, gt=0)
    buffer_s: float = Field(default=2.0, gt=0, description="Frames recientes en memoria")
    timeout_s: float = Field(
        default=3.0, gt=0, description="Plazo para juntar la ráfaga tras el disparo"
    )
    trigger_max_age_s: float = Field(
        default=3.0, gt=0, description="Un disparo más viejo se ignora (llegó tarde)"
    )


class UplinkConfig(_Section):
    api_url: str = "https://d22z1x91kqav4d.cloudfront.net/api"
    gate_id: str = "puerta-2"
    device_key_file: Path = Path("/etc/anpr/secrets/device_api_key")
    open_deadline_s: float = Field(
        default=6.0, gt=0, description="Pasado este plazo desde la captura ya no se abre"
    )
    connect_timeout_s: float = Field(default=2.0, gt=0)
    request_timeout_s: float = Field(default=5.0, gt=0)
    # Eventos que no llegaron a tiempo: se reenvían solo para dejar registro.
    pending_retry_s: float = Field(default=60.0, gt=0)
    pending_max_days: float = Field(default=7.0, gt=0)
    # Limpieza del spool: fotos ya enviadas.
    keep_sent_hours: float = Field(default=24.0, ge=0)
    spool_max_mb: float = Field(default=1024.0, gt=0)


class TriggerConfig(_Section):
    debounce_ms: int = Field(default=300, ge=0, description="Presencia estable para disparar")
    release_ms: int = Field(default=1500, ge=0, description="Ausencia estable = el auto se fue")
    verdict_timeout_s: float = Field(default=10.0, gt=0)
    max_attempts: int = Field(default=3, ge=1, le=10)
    retry_delay_s: float = Field(default=1.5, ge=0)


class GateConfig(_Section):
    # Recorrido medido en sitio (pendiente de la visita). Mientras tanto, conservador.
    travel_open_s: float = Field(default=6.0, gt=0)
    travel_close_s: float = Field(default=6.0, gt=0)
    travel_margin: float = Field(default=0.2, ge=0, le=1)
    reverse_pause_s: float = Field(default=0.5, ge=0.5)
    close_delay_s: float = Field(
        default=1.0, ge=0, description="Espera tras pasar el auto antes de bajar"
    )
    open_hold_max_s: float = Field(
        default=30.0, gt=0, description="Si nadie cruza la fotocelda, baja tras este tiempo"
    )
    input_debounce_ms: int = Field(default=60, ge=0)
    open_relay: Literal["RELAY_FWD", "RELAY_REV"] = "RELAY_FWD"


class HealthConfig(_Section):
    check_every_s: float = Field(default=30.0, gt=0)
    services: list[str] = ["trigger", "capture", "uplink", "gate"]


class GpioConfig(_Section):
    backend: Literal["gpiozero", "sim", "memory"] = "gpiozero"
    # Nombre de señal (contrato C) -> número BCM. Pendiente de F6.
    pins: dict[str, int] = {}


class EdgeConfig(_Section):
    mqtt: MqttConfig = MqttConfig()
    camera: CameraConfig = CameraConfig()
    capture: CaptureConfig = CaptureConfig()
    uplink: UplinkConfig = UplinkConfig()
    gpio: GpioConfig = GpioConfig()
    trigger: TriggerConfig = TriggerConfig()
    gate: GateConfig = GateConfig()
    health: HealthConfig = HealthConfig()


def load_config(path: Path | None = None) -> EdgeConfig:
    """Orden: argumento, variable ANPR_EDGE_CONFIG, /etc/anpr/edge.toml."""
    if path is None:
        path = Path(os.environ.get(ENV_VAR, DEFAULT_PATH))
    with open(path, "rb") as f:
        return EdgeConfig.model_validate(tomllib.load(f))


def read_secret(name: str, fallback: Path) -> str:
    """
    Lee un secreto. En la Pi llega por `LoadCredential=` de systemd, que lo deja en
    $CREDENTIALS_DIRECTORY solo legible por el servicio; en la laptop, desde un archivo.
    """
    cred_dir = os.environ.get("CREDENTIALS_DIRECTORY")
    path = Path(cred_dir) / name if cred_dir else fallback
    value = path.read_text(encoding="utf-8").strip()
    if not value:
        raise ValueError(f"El secreto {name} está vacío ({path})")
    return value
