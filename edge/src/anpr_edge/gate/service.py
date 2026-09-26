"""
anpr-gate: el ÚNICO servicio que acciona los relés de la pluma.

- Sin internet (systemd: IPAddressDeny salvo localhost). Si el bus se cae, sigue
  funcionando con sus entradas: el botón manual abre y la pluma termina su ciclo.
- Descarta órdenes vencidas (TTL) o repetidas.
- Lee las entradas cada 20 ms. Antirrebote asimétrico: lo peligroso (fotocelda
  interrumpida, emergencia, llegar al tope, modo manual) se aplica al instante; lo
  seguro exige estabilidad.
- Si su propia lógica falla, apaga los relés antes de nada.
"""

import logging
import time

from anpr_edge.common import gpio as g
from anpr_edge.common.bus import Bus
from anpr_edge.common.config import EdgeConfig, GateConfig
from anpr_edge.common.debounce import Debouncer
from anpr_edge.common.gpio import Gpio, open_gpio
from anpr_edge.common.messages import Command, Fault, GateState, Message, utcnow
from anpr_edge.common.service import Service
from anpr_edge.gate.machine import GateMachine, Inputs, Motion

GATE_INPUTS = ["LIMIT_OPEN", "LIMIT_CLOSED", "PHOTOCELL_OK", "ESTOP_OK", "MODE_AUTO", "MANUAL_BTN"]
RELAYS = ["RELAY_FWD", "RELAY_REV"]
STATE_EVERY_S = 10.0


class GateService(Service):
    tick_s = 0.02

    def __init__(self, cfg: GateConfig, gpio: Gpio, bus: Bus, log: logging.Logger) -> None:
        super().__init__(bus, log)
        self.cfg, self.gpio = cfg, gpio
        self.machine = GateMachine(cfg)
        self.open_relay = cfg.open_relay
        self.close_relay = "RELAY_REV" if cfg.open_relay == "RELAY_FWD" else "RELAY_FWD"
        self.now = time.monotonic()
        self._last_state_pub = 0.0
        d = cfg.input_debounce_ms / 1000
        # (valor inicial, espera para pasar a True, espera para pasar a False)
        self._deb = {
            "at_open": Debouncer(True, 0, d),  # llegar al tope: inmediato
            "at_closed": Debouncer(True, 0, d),
            "photocell_clear": Debouncer(False, d, 0),  # interrumpirse: inmediato
            "estop_ok": Debouncer(False, d, 0),
            "auto_mode": Debouncer(False, d, 0),  # pasar a manual: inmediato
            "manual_pressed": Debouncer(False, d, 0),
        }
        self._first_read = True

    def on_start(self) -> None:
        self._apply(Motion.STOP)
        self.bus.subscribe(Command)

    def on_stop(self) -> None:
        self.gpio.close()  # relés abiertos

    def on_message(self, msg: Message) -> None:
        if not isinstance(msg, Command):
            return
        ev = {"event_id": str(msg.event_id)}
        if msg.expired():
            self.log.warning("Orden vencida descartada", extra=ev)
            return
        ok, reason = self.machine.request_open(str(msg.event_id), self.now)
        (self.log.info if ok else self.log.warning)(f"Orden de abrir: {reason}", extra=ev)

    def on_tick(self, now: float) -> None:
        self.now = now
        try:
            motion = self.machine.step(self.read_inputs(now), now)
            self._apply(motion)
        except Exception:
            self._apply(Motion.STOP)  # ante cualquier error propio, relés abiertos
            raise
        self._publish_events()
        if now - self._last_state_pub >= STATE_EVERY_S:
            self._publish_state()

    def read_inputs(self, now: float) -> Inputs:
        raw = {
            "at_open": g.at_open_limit(self.gpio),
            "at_closed": g.at_closed_limit(self.gpio),
            "photocell_clear": g.photocell_clear(self.gpio),
            "estop_ok": g.estop_ok(self.gpio),
            "auto_mode": g.auto_mode(self.gpio),
            "manual_pressed": g.manual_pressed(self.gpio),
        }
        if self._first_read:  # la primera lectura se toma tal cual
            for k, v in raw.items():
                self._deb[k].value = v
            self._first_read = False
        for k, v in raw.items():
            self._deb[k].update(v, now)
        return Inputs(**{k: d.value for k, d in self._deb.items()})

    def _apply(self, motion: Motion) -> None:
        # Siempre se apaga primero el relé que no corresponde: nunca los dos a la vez.
        if motion == Motion.OPEN:
            self.gpio.set(self.close_relay, False)
            self.gpio.set(self.open_relay, True)
        elif motion == Motion.CLOSE:
            self.gpio.set(self.open_relay, False)
            self.gpio.set(self.close_relay, True)
        else:
            self.gpio.set(self.open_relay, False)
            self.gpio.set(self.close_relay, False)

    def _publish_events(self) -> None:
        events, self.machine.events = self.machine.events, []
        for e in events:
            if e.kind == "state":
                self.log.info("Estado: %s", e.code)
                self._publish_state()
            elif e.kind == "fault":
                self.log.error("Falla: %s", e.detail, extra={"code": e.code})
                self.bus.publish(Fault(code=e.code, detail=e.detail, ts=utcnow()))
            else:
                self.log.info(e.detail, extra={"code": e.code})

    def _publish_state(self) -> None:
        self._last_state_pub = self.now
        self.bus.publish(
            GateState(
                state=self.machine.state.value,
                position_known=self.machine.position_known,
                ts=utcnow(),
            ),
            retain=True,
        )


def build(cfg: EdgeConfig, bus: Bus, log: logging.Logger) -> GateService:
    gpio = open_gpio("gate", cfg.gpio, cfg.mqtt, inputs=GATE_INPUTS, outputs=RELAYS)
    return GateService(cfg.gate, gpio, bus, log)


def main() -> None:
    from anpr_edge.common.runner import run

    run("gate", build)
