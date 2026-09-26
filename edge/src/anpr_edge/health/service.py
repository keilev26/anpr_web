"""
anpr-health: vigila el sistema y lo muestra con el LED del gabinete.

Escucha el bus (servicios vivos por su Last Will, estado de la pluma, cámara, fallas)
y comprueba periódicamente la nube, el disco, la temperatura y el reloj. Publica un
resumen retenido en `health/summary`.

LED_STATUS:
    fijo           todo bien
    parpadeo lento algo degradado (sin nube, cámara caída, servicio caído, disco...)
    parpadeo rápido la pluma está en falla: requiere a una persona
    apagado        anpr-health no corre (o no hay energía)

No toca los relés. Es el único servicio, junto al uplink, que sale a internet.
"""

import logging
import shutil
import subprocess
import threading
from pathlib import Path

import httpx

from anpr_edge.common.bus import Bus
from anpr_edge.common.config import EdgeConfig, HealthConfig
from anpr_edge.common.gpio import Gpio, open_gpio
from anpr_edge.common.messages import (
    CameraStatus,
    Fault,
    GateState,
    HealthSummary,
    Message,
    ServiceStatus,
    utcnow,
)
from anpr_edge.common.service import Service

MIN_FREE_MB = 500
MAX_TEMP_C = 80.0
THERMAL = Path("/sys/class/thermal/thermal_zone0/temp")


def check_cloud(client: httpx.Client, url: str) -> str:
    try:
        r = client.get(url, timeout=5.0)
        if r.status_code != 200:
            return "unreachable"
        return "ok" if r.json().get("db") else "degraded"
    except (httpx.HTTPError, ValueError):
        return "unreachable"


def clock_synced() -> bool | None:
    """None si no se puede saber (sin systemd-timedated)."""
    try:
        out = subprocess.run(
            ["timedatectl", "show", "-p", "NTPSynchronized", "--value"],
            capture_output=True,
            text=True,
            timeout=3,
        )
        return out.stdout.strip() == "yes" if out.returncode == 0 else None
    except (OSError, subprocess.TimeoutExpired):
        return None


def cpu_temp_c() -> float | None:
    try:
        return int(THERMAL.read_text()) / 1000
    except (OSError, ValueError):
        return None


class HealthService(Service):
    def __init__(
        self,
        cfg: HealthConfig,
        api_url: str,
        spool_dir: Path,
        gpio: Gpio | None,
        bus: Bus,
        log: logging.Logger,
        client: httpx.Client | None = None,
    ) -> None:
        super().__init__(bus, log)
        self.cfg, self.spool_dir, self.gpio = cfg, spool_dir, gpio
        self.health_url = api_url.rstrip("/") + "/health"
        self.client = client or httpx.Client()
        self.services = {s: "unknown" for s in cfg.services}
        self.gate_state: str | None = None
        self.camera_online: bool | None = None
        self.cloud = "unknown"
        self.clock_ok: bool | None = None
        self.problems: list[str] = []
        self._next_check = 0.0
        self._checking = False

    def on_start(self) -> None:
        self.bus.subscribe(ServiceStatus, "svc/+/status")
        self.bus.subscribe(GateState)
        self.bus.subscribe(CameraStatus)
        self.bus.subscribe(Fault)

    def on_stop(self) -> None:
        if self.gpio:
            self.gpio.close()
        self.client.close()

    def on_message(self, msg: Message) -> None:
        if isinstance(msg, ServiceStatus):
            if msg.service in self.services:
                self.services[msg.service] = msg.status
        elif isinstance(msg, GateState):
            self.gate_state = msg.state
        elif isinstance(msg, CameraStatus):
            self.camera_online = msg.online
        elif isinstance(msg, Fault):
            self.log.warning("Falla reportada: %s", msg.detail, extra={"code": msg.code})

    def on_tick(self, now: float) -> None:
        if now >= self._next_check and not self._checking:
            self._next_check = now + self.cfg.check_every_s
            self._checking = True
            # La red puede tardar segundos: fuera del bucle, para que el LED no se congele.
            threading.Thread(target=self._slow_checks, daemon=True).start()
        self._led(now)

    def _slow_checks(self) -> None:
        try:
            self.cloud = check_cloud(self.client, self.health_url)
            self.clock_ok = clock_synced()
            self.evaluate()
        except Exception:
            self.log.exception("Error en los chequeos")
        finally:
            self._checking = False

    def evaluate(self) -> list[str]:
        problems = [f"servicio {s}: {st}" for s, st in self.services.items() if st != "online"]
        if self.gate_state in ("fault", None, "unknown"):
            problems.append(f"pluma: {self.gate_state or 'sin datos'}")
        if self.camera_online is False:
            problems.append("cámara sin frames")
        if self.cloud != "ok":
            problems.append(f"nube: {self.cloud}")
        if self.clock_ok is False:
            problems.append("reloj sin sincronizar")
        try:
            free_mb = shutil.disk_usage(self.spool_dir).free / 2**20
            if free_mb < MIN_FREE_MB:
                problems.append(f"disco: {free_mb:.0f} MB libres")
        except OSError:
            problems.append("spool inaccesible")
        if (t := cpu_temp_c()) is not None and t > MAX_TEMP_C:
            problems.append(f"temperatura {t:.0f} °C")

        if problems != self.problems:
            (self.log.warning if problems else self.log.info)(
                "Estado de salud", extra={"problems": problems}
            )
        self.problems = problems
        self.bus.publish(
            HealthSummary(
                ok=not problems,
                problems=problems,
                services=dict(self.services),
                gate_state=self.gate_state,
                cloud=self.cloud,
                ts=utcnow(),
            ),
            retain=True,
        )
        return problems

    def led_pattern(self) -> str:
        if self.gate_state == "fault":
            return "fast"
        return "slow" if self.problems else "solid"

    def _led(self, now: float) -> None:
        if not self.gpio:
            return
        pattern = self.led_pattern()
        on = True if pattern == "solid" else (now * (4 if pattern == "fast" else 1)) % 1 < 0.5
        self.gpio.set("LED_STATUS", on)


def build(cfg: EdgeConfig, bus: Bus, log: logging.Logger) -> HealthService:
    gpio = open_gpio("health", cfg.gpio, cfg.mqtt, outputs=["LED_STATUS"])
    return HealthService(cfg.health, cfg.uplink.api_url, cfg.capture.spool_dir, gpio, bus, log)


def main() -> None:
    from anpr_edge.common.runner import run

    run("health", build)
