"""
anpr-uplink: sube cada ráfaga a la nube y traduce el veredicto en una orden.

Reglas del contrato A (`contracts/detection-api.md`):
- Solo un 200 con `command.action == "open"` produce una orden de abrir.
- Se reintenta con el MISMO `event_id` (la API es idempotente), pero solo mientras
  quede plazo para abrir. Pasado el plazo, el auto ya no está esperando.
- 5xx o timeout: NO se abre. El evento queda pendiente y se reenvía más tarde con
  `late=true`, solo para que quede registrado (la API lo guarda como no abierto).

Es el único servicio que publica `gate/command` (la ACL de Mosquitto lo impone).
"""

import logging
import shutil
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Literal

import httpx
from pydantic import BaseModel, Field, ValidationError

from anpr_edge.common import spool
from anpr_edge.common.bus import Bus
from anpr_edge.common.config import EdgeConfig, UplinkConfig, read_secret
from anpr_edge.common.messages import Command, FramesReady, Message, Verdict, utcnow
from anpr_edge.common.service import Service

RETRY_STATUS = {500, 502, 503, 504}
REJECT_STATUS = {400, 401, 403, 409, 413}
MIN_ATTEMPT_S = 0.3
HOUSEKEEPING_EVERY_S = 60.0


class ApiCommand(BaseModel):
    action: Literal["open", "deny"]
    ttl_s: int = Field(ge=1, le=60)


class ApiVerdict(BaseModel):
    """La respuesta de la API, validada antes de actuar sobre ella."""

    event_id: str
    plate: str | None = None
    authorized: bool
    command: ApiCommand
    latency_ms: int | None = None


class UplinkService(Service):
    def __init__(
        self,
        cfg: UplinkConfig,
        spool_dir: Path,
        device_key: str,
        bus: Bus,
        log: logging.Logger,
        client: httpx.Client | None = None,
    ) -> None:
        super().__init__(bus, log)
        self.cfg, self.spool_dir = cfg, spool_dir
        self.client = client or httpx.Client(base_url=cfg.api_url)
        self.headers = {"X-Device-Key": device_key}
        self._next_pending = 0.0
        self._next_housekeeping = 0.0

    def on_start(self) -> None:
        self.bus.subscribe(FramesReady)

    def on_stop(self) -> None:
        self.client.close()

    def on_message(self, msg: Message) -> None:
        if isinstance(msg, FramesReady):
            self.handle(msg)

    def on_tick(self, now: float) -> None:
        if now >= self._next_housekeeping:
            self._next_housekeeping = now + HOUSEKEEPING_EVERY_S
            self.housekeeping()
        if now >= self._next_pending:
            self._next_pending = now + self.cfg.pending_retry_s
            self.retry_one_pending()

    # ---------- camino crítico ----------

    def handle(self, msg: FramesReady) -> None:
        ev = {"event_id": str(msg.event_id)}
        try:
            event_dir = spool.resolve_event(self.spool_dir, msg.path)
            if event_dir.name != str(msg.event_id):
                raise spool.SpoolError("la ruta no corresponde al evento")
            if spool.read_status(event_dir) is not None:
                return  # ya procesado (mensaje duplicado)
            frames = spool.read_frames(event_dir)
        except (spool.SpoolError, OSError) as e:
            self.log.error("Ráfaga inválida: %s", e, extra=ev)
            return

        deadline = msg.captured_at + timedelta(seconds=self.cfg.open_deadline_s)
        started = time.monotonic()
        resp = self._post_until(msg, frames, deadline)
        latency = int((time.monotonic() - started) * 1000)
        code = resp.status_code if isinstance(resp, httpx.Response) else None
        outcome, plate, state = self._decide(msg, resp, deadline)

        extra = ev | {"outcome": outcome, "http_status": code, "latency_ms": latency}
        if outcome == "unavailable":
            extra["error"] = str(resp) if not isinstance(resp, httpx.Response) else resp.text[:200]
        self.log.info("Veredicto", extra=extra)
        spool.write_status(
            event_dir,
            {
                "state": state,
                "outcome": outcome,
                "http_status": code,
                "attempts": 0,
                "next_try": time.time(),
            },
        )
        self.bus.publish(
            Verdict(
                event_id=msg.event_id,
                outcome=outcome,
                plate=plate,
                http_status=code,
                latency_ms=latency,
                ts=utcnow(),
            )
        )

    def _decide(self, msg: FramesReady, resp, deadline) -> tuple[str, str | None, str]:
        """(outcome, placa, estado en el spool). Publica la orden si corresponde."""
        if not isinstance(resp, httpx.Response) or resp.status_code in RETRY_STATUS:
            return "unavailable", None, "pending"
        code = resp.status_code
        if code == 422:
            return "unreadable", None, "sent"
        if code != 200:
            if code == 401:
                self.log.critical("La nube rechaza la clave del dispositivo")
            return "rejected", None, "rejected"
        try:
            v = ApiVerdict.model_validate_json(resp.content)
            if v.event_id != str(msg.event_id):
                raise ValueError(f"event_id distinto: {v.event_id}")
        except (ValidationError, ValueError) as e:
            self.log.error("Respuesta inválida de la nube: %s", e)
            return "rejected", None, "rejected"
        now = utcnow()
        if now > deadline:
            return "late", v.plate, "sent"
        if v.command.action == "open":
            self.bus.publish(
                Command(event_id=msg.event_id, action="open", ttl_s=v.command.ttl_s, issued_at=now)
            )
            return "open", v.plate, "sent"
        return "deny", v.plate, "sent"

    def _post_until(self, msg: FramesReady, frames: list[bytes], deadline):
        """Reintenta mientras quede plazo. Devuelve la última respuesta o excepción."""
        last: httpx.Response | Exception = TimeoutError("sin plazo para intentar")
        while True:
            remaining = (deadline - utcnow()).total_seconds()
            if remaining < MIN_ATTEMPT_S:
                return last
            timeout = httpx.Timeout(
                min(self.cfg.request_timeout_s, remaining),
                connect=min(self.cfg.connect_timeout_s, remaining),
            )
            try:
                last = self._post(msg.event_id, msg.captured_at, frames, timeout, late=False)
                if last.status_code not in RETRY_STATUS:
                    return last
            except httpx.HTTPError as e:
                last = e
            time.sleep(min(0.2, max(0.0, remaining - MIN_ATTEMPT_S)))

    def _post(self, event_id, captured_at, frames, timeout, late: bool) -> httpx.Response:
        data = {
            "gate_id": self.cfg.gate_id,
            "event_id": str(event_id),
            "captured_at": captured_at.isoformat(),
        }
        if late:
            data["late"] = "true"
        files = [
            ("frames", (f"frame_{i:02d}.jpg", jpeg, "image/jpeg")) for i, jpeg in enumerate(frames)
        ]
        return self.client.post(
            "/v1/detections", data=data, files=files, headers=self.headers, timeout=timeout
        )

    # ---------- reenvíos tardíos, solo para registro ----------

    def retry_one_pending(self) -> None:
        for event_dir in spool.list_events(self.spool_dir):
            st = spool.read_status(event_dir)
            if not st or st.get("state") != "pending" or st.get("next_try", 0) > time.time():
                continue
            ev = {"event_id": event_dir.name}
            try:
                meta = spool.read_meta(event_dir)
                resp = self._post(
                    event_dir.name,
                    datetime.fromisoformat(meta["captured_at"]),
                    spool.read_frames(event_dir),
                    httpx.Timeout(10.0, connect=self.cfg.connect_timeout_s),
                    late=True,
                )
                code = resp.status_code
            except httpx.HTTPError as e:
                code, resp = None, e
            except (OSError, KeyError, ValueError) as e:
                self.log.error("Pendiente ilegible, se descarta: %s", e, extra=ev)
                spool.write_status(event_dir, st | {"state": "rejected"})
                return
            if code is None or code in RETRY_STATUS:
                attempts = st.get("attempts", 0) + 1
                wait = self.cfg.pending_retry_s * min(2**attempts, 16)
                spool.write_status(
                    event_dir, st | {"attempts": attempts, "next_try": time.time() + wait}
                )
                self.log.info("Reenvío tardío fallido", extra=ev | {"attempts": attempts})
            else:
                state = "sent" if code in (200, 422) else "rejected"
                spool.write_status(event_dir, st | {"state": state, "late_http_status": code})
                self.log.info("Reenvío tardío registrado", extra=ev | {"http_status": code})
            return  # uno por vuelta: no bloquear el camino crítico

    # ---------- limpieza del spool ----------

    def housekeeping(self) -> None:
        spool.clean_orphans(self.spool_dir)
        now = time.time()
        events = spool.list_events(self.spool_dir)
        for event_dir in events:
            st = spool.read_status(event_dir)
            age = now - spool.event_time(event_dir)
            if st is None:
                # Nadie lo procesó (el uplink estaba caído): ya es tarde para abrir.
                if age > self.cfg.open_deadline_s + 10:
                    spool.write_status(
                        event_dir,
                        {
                            "state": "pending",
                            "outcome": "unavailable",
                            "attempts": 0,
                            "next_try": now,
                        },
                    )
                continue
            if st["state"] == "pending":
                if age > self.cfg.pending_max_days * 86400:
                    self.log.warning(
                        "Pendiente demasiado viejo, se borra", extra={"event_id": event_dir.name}
                    )
                    shutil.rmtree(event_dir, ignore_errors=True)
            elif age > self.cfg.keep_sent_hours * 3600:
                shutil.rmtree(event_dir, ignore_errors=True)

        # Tope de tamaño: primero lo ya enviado, y solo si no alcanza, lo pendiente.
        events = spool.list_events(self.spool_dir)
        total = sum(spool.dir_size(d) for d in events)
        limit = self.cfg.spool_max_mb * 1024 * 1024
        for keep_pending in (True, False):
            for event_dir in list(events):
                if total <= limit:
                    return
                st = spool.read_status(event_dir) or {}
                if keep_pending and st.get("state") in ("pending", None):
                    continue
                total -= spool.dir_size(event_dir)
                shutil.rmtree(event_dir, ignore_errors=True)
                events.remove(event_dir)
                if not keep_pending:
                    self.log.warning(
                        "Spool lleno: pendiente borrado", extra={"event_id": event_dir.name}
                    )


def build(cfg: EdgeConfig, bus: Bus, log: logging.Logger) -> UplinkService:
    # Sin clave no hay nada que hacer: falla al arrancar, systemd lo reintenta.
    key = read_secret("device_api_key", cfg.uplink.device_key_file)
    return UplinkService(cfg.uplink, cfg.capture.spool_dir, key, bus, log)


def main() -> None:
    from anpr_edge.common.runner import run

    run("uplink", build)
