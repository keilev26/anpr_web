"""
Bucle común de los servicios.

Un solo hilo ejecuta la lógica: consume la bandeja del bus y llama a `on_tick`
periódicamente. Así ningún servicio necesita cerrojos y el comportamiento es
reproducible en tests. El mismo bucle alimenta el watchdog de systemd: si la lógica
se cuelga, deja de enviarse `WATCHDOG=1` y systemd reinicia el servicio.
"""

import logging
import queue
import signal
import time

from anpr_edge.common import sdnotify
from anpr_edge.common.bus import Bus
from anpr_edge.common.messages import Message

WATCHDOG_EVERY_S = 1.0


class Service:
    tick_s: float = 0.05

    def __init__(self, bus: Bus, log: logging.Logger) -> None:
        self.bus = bus
        self.log = log
        self._running = False

    # ---------- a implementar por cada servicio ----------

    def on_start(self) -> None:
        """Suscripciones y estado inicial."""

    def on_message(self, msg: Message) -> None:
        """Un mensaje ya validado del bus."""

    def on_tick(self, now: float) -> None:
        """Llamado cada `tick_s` con time.monotonic()."""

    def on_stop(self) -> None:
        """Dejar todo en estado seguro."""

    # ---------- bucle ----------

    def stop(self, *_: object) -> None:
        self._running = False

    def run(self) -> None:
        signal.signal(signal.SIGTERM, self.stop)
        signal.signal(signal.SIGINT, self.stop)
        self.on_start()
        self.bus.start()
        sdnotify.ready()
        self._running = True
        last_wd = 0.0
        try:
            while self._running:
                self.step(timeout=self.tick_s)
                now = time.monotonic()
                if now - last_wd >= WATCHDOG_EVERY_S:
                    sdnotify.watchdog()
                    last_wd = now
        finally:
            sdnotify.stopping()
            self.on_stop()
            self.bus.stop()

    def step(self, timeout: float = 0.0) -> None:
        """Una vuelta del bucle. Separada de `run` para poder probarla sin hilos."""
        try:
            msg = self.bus.inbox.get(timeout=timeout) if timeout else self.bus.inbox.get_nowait()
        except queue.Empty:
            msg = None
        while msg is not None:
            self._safe(self.on_message, msg)
            try:
                msg = self.bus.inbox.get_nowait()
            except queue.Empty:
                msg = None
        self._safe(self.on_tick, time.monotonic())

    def _safe(self, fn, *args) -> None:
        # Una excepción en la lógica se registra y el servicio sigue: un mensaje raro no
        # debe tumbar el proceso. Si la lógica queda inservible, el watchdog lo reinicia.
        try:
            fn(*args)
        except Exception:
            self.log.exception("Error en %s", fn.__name__)
