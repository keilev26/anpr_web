"""
anpr-trigger: detecta la llegada de un vehículo y dispara la captura.

- Un disparo por llegada: la presencia debe mantenerse estable (`debounce_ms`), y
  el auto se da por ido solo tras una ausencia estable (`release_ms`).
- Si la placa salió ilegible o la nube no respondió, y el auto sigue ahí, vuelve a
  disparar (con un `event_id` nuevo) hasta `max_attempts`. Una denegación no se
  reintenta.
- Cola de autos: si la pluma completó un ciclo (abrió y cerró) y sigue habiendo
  presencia, es el siguiente auto y se dispara de nuevo.

No toca internet ni relés: solo lee PRESENCE y publica en el bus local.
"""

import logging
import time
import uuid
from enum import StrEnum

from anpr_edge.common.bus import Bus
from anpr_edge.common.config import EdgeConfig, TriggerConfig
from anpr_edge.common.debounce import Debouncer
from anpr_edge.common.gpio import Gpio, open_gpio, presence
from anpr_edge.common.messages import GateState, Message, Trigger, Verdict, utcnow
from anpr_edge.common.service import Service

RETRYABLE = {"unreadable", "unavailable"}


class Phase(StrEnum):
    IDLE = "idle"  # sin vehículo
    WAITING = "waiting"  # disparo enviado, esperando veredicto
    DONE = "done"  # atendido; esperando a que se vaya o a que la pluma cumpla su ciclo


class TriggerService(Service):
    def __init__(self, cfg: TriggerConfig, gpio: Gpio, bus: Bus, log: logging.Logger) -> None:
        super().__init__(bus, log)
        self.cfg, self.gpio = cfg, gpio
        self.presence = Debouncer(False, cfg.debounce_ms / 1000, cfg.release_ms / 1000)
        self.phase = Phase.IDLE
        self.event_id: uuid.UUID | None = None
        self.attempts = 0
        self.sent_at = 0.0
        self.retry_at: float | None = None
        self._saw_open = False
        self._cycle_done = False
        self.now = time.monotonic()

    def on_start(self) -> None:
        self.bus.subscribe(Verdict)
        self.bus.subscribe(GateState)

    def on_stop(self) -> None:
        self.gpio.close()

    def on_message(self, msg: Message) -> None:
        if isinstance(msg, GateState):
            if msg.state in ("opening", "open"):
                self._saw_open = True
            elif msg.state == "closed" and self._saw_open:
                self._cycle_done = True
        elif (
            isinstance(msg, Verdict)
            and self.phase == Phase.WAITING
            and msg.event_id == self.event_id
        ):
            self._resolve(msg.outcome)

    def on_tick(self, now: float) -> None:
        self.now = now
        self.presence.update(presence(self.gpio), now)
        present = self.presence.value

        if self.phase == Phase.IDLE:
            if present:
                self.attempts = 0
                self._fire()
        elif self.phase == Phase.WAITING:
            if self.retry_at is not None:
                if now >= self.retry_at:
                    if present and self.attempts < self.cfg.max_attempts:
                        self._fire()
                    else:
                        self._done()
            elif now - self.sent_at > self.cfg.verdict_timeout_s:
                self.log.warning("Sin veredicto a tiempo", extra={"event_id": str(self.event_id)})
                self._resolve("unavailable")
        elif self.phase == Phase.DONE:
            if not present:
                self.phase = Phase.IDLE
            elif self._cycle_done:
                # La pluma abrió y cerró y sigue habiendo un auto: es el siguiente.
                self.log.info("Siguiente vehículo en cola")
                self.phase = Phase.IDLE

    def _resolve(self, outcome: str) -> None:
        if outcome in RETRYABLE and self.attempts < self.cfg.max_attempts:
            self.retry_at = self.now + self.cfg.retry_delay_s
            self.log.info(
                "Se reintentará",
                extra={
                    "event_id": str(self.event_id),
                    "outcome": outcome,
                    "attempt": self.attempts,
                },
            )
        else:
            self._done()

    def _fire(self) -> None:
        self.event_id = uuid.uuid4()
        self.attempts += 1
        self.phase = Phase.WAITING
        self.sent_at, self.retry_at = self.now, None
        self._saw_open = self._cycle_done = False
        self.bus.publish(Trigger(event_id=self.event_id, source="loop", ts=utcnow()))
        self.log.info("Disparo", extra={"event_id": str(self.event_id), "attempt": self.attempts})

    def _done(self) -> None:
        self.phase = Phase.DONE
        self.retry_at = None


def build(cfg: EdgeConfig, bus: Bus, log: logging.Logger) -> TriggerService:
    gpio = open_gpio("trigger", cfg.gpio, cfg.mqtt, inputs=["PRESENCE"])
    return TriggerService(cfg.trigger, gpio, bus, log)


def main() -> None:
    from anpr_edge.common.runner import run

    run("trigger", build)
