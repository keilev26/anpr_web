"""
Máquina de estados de la pluma. Pura: sin GPIO, sin red, sin reloj propio.

Recibe una foto de las entradas y la hora, y devuelve qué hacer con el motor. Así
se puede probar cada transición y cada falla sin hardware.

Esta lógica es la SEGUNDA barrera. La primera es el cableado: finales de carrera,
fotocelda y parada de emergencia cortan el motor por hardware aunque la Pi esté
apagada (`contracts/gpio-map.md`). Aquí se repiten esas reglas y se añaden las que
el hardware no puede hacer: tiempos máximos de marcha, pausa al invertir, cierre
automático tras pasar el auto e idempotencia de las órdenes.

    UNKNOWN ─► HOMING ─► CLOSED ─► OPENING ─► OPEN ─► CLOSING ─► CLOSED
                                        ▲                  │ fotocelda
                                        └──────────────────┘
    Cualquier estado ─► FAULT (emergencia, timeout, finales incoherentes, posición perdida)
    Cualquier estado ─► MANUAL (selector en MANUAL). Volver a AUTO es el único
    modo de salir de FAULT: exige que una persona lo decida en el sitio.
"""

from collections import deque
from dataclasses import dataclass
from enum import StrEnum

from anpr_edge.common.config import GateConfig


class Motion(StrEnum):
    STOP = "stop"
    OPEN = "open"
    CLOSE = "close"


class State(StrEnum):
    UNKNOWN = "unknown"
    HOMING = "homing"
    CLOSED = "closed"
    OPENING = "opening"
    OPEN = "open"
    CLOSING = "closing"
    FAULT = "fault"
    MANUAL = "manual"


@dataclass(frozen=True)
class Inputs:
    """Entradas ya interpretadas (y con antirrebote). True = la condición se cumple."""

    at_open: bool
    at_closed: bool
    photocell_clear: bool
    estop_ok: bool
    auto_mode: bool
    manual_pressed: bool = False


@dataclass(frozen=True)
class Event:
    kind: str  # "state" | "fault" | "info"
    code: str
    detail: str = ""


NEVER = float("-inf")


class GateMachine:
    def __init__(self, cfg: GateConfig) -> None:
        self.cfg = cfg
        self.state = State.UNKNOWN
        self.motion = Motion.STOP
        self.fault_code: str | None = None
        self.events: list[Event] = []
        self._motion_since = NEVER
        self._stopped_at = NEVER  # último momento en que se apagó un relé
        self._executed: deque[str] = deque(maxlen=500)
        self._open_requested = False
        self._manual_was_pressed = False
        self._open_since = NEVER
        self._car_blocked = False
        self._clear_since: float | None = None

    # ---------- API ----------

    @property
    def position_known(self) -> bool:
        return self.state in (State.CLOSED, State.OPEN, State.OPENING, State.CLOSING)

    def request_open(self, event_id: str, now: float) -> tuple[bool, str]:
        """Orden de abrir de la nube. Nunca mueve nada por sí sola: la aplica `step`."""
        if event_id in self._executed:
            return False, "orden duplicada"
        if self.state == State.CLOSED:
            self._executed.append(event_id)
            self._open_requested = True
            return True, "abriendo"
        if self.state == State.OPENING:
            self._executed.append(event_id)
            return True, "ya está abriendo"
        if self.state == State.OPEN:
            self._executed.append(event_id)
            self._hold_open(now)  # otro auto autorizado: se mantiene abierta
            return True, "se mantiene abierta"
        # Contrato C: se rechazan órdenes durante el cierre y en estados sin control.
        return False, f"rechazada en estado {self.state}"

    def step(self, i: Inputs, now: float) -> Motion:
        # 1. El selector manda sobre todo: en MANUAL la Pi no acciona nada.
        if not i.auto_mode:
            if self.state != State.MANUAL:
                self._go(State.MANUAL)
            return self._stop(now)
        if self.state == State.MANUAL:
            self.fault_code = None
            self._go(State.UNKNOWN)  # posición desconocida: pudieron moverla a mano

        # 2. En falla no se mueve hasta que una persona pase por MANUAL.
        if self.state == State.FAULT:
            return self._stop(now)

        # 3. Condiciones que llevan a falla desde cualquier estado.
        if not i.estop_ok:
            return self._fail("estop", "Parada de emergencia activada", now)
        if i.at_open and i.at_closed:
            return self._fail("limits", "Ambos finales de carrera activos: sensor o cable", now)

        manual_edge = i.manual_pressed and not self._manual_was_pressed
        self._manual_was_pressed = i.manual_pressed

        match self.state:
            case State.UNKNOWN:
                self._go(State.CLOSED if i.at_closed else State.HOMING)
                return self._stop(now)
            case State.HOMING:
                return self._homing(i, now)
            case State.CLOSED:
                return self._closed(i, now, manual_edge)
            case State.OPENING:
                return self._opening(i, now)
            case State.OPEN:
                return self._open(i, now, manual_edge)
            case State.CLOSING:
                return self._closing(i, now)
        return self._stop(now)

    # ---------- estados ----------

    def _homing(self, i: Inputs, now: float) -> Motion:
        if i.at_closed:
            self._go(State.CLOSED)
            return self._stop(now)
        if not i.photocell_clear:
            return self._stop(now)  # sin posición conocida no se reabre: se espera
        return self._drive(Motion.CLOSE, self.cfg.travel_close_s, "timeout_homing", now)

    def _closed(self, i: Inputs, now: float, manual_edge: bool) -> Motion:
        if not i.at_closed:
            return self._fail("position_lost", "La pluma dejó de estar cerrada sin orden", now)
        if self._open_requested or manual_edge:
            self._open_requested = False
            if manual_edge:
                self.events.append(Event("info", "manual_open", "Botón manual"))
            self._go(State.OPENING)
            return self._opening(i, now)
        return self._stop(now)

    def _opening(self, i: Inputs, now: float) -> Motion:
        if i.at_open:
            self._go(State.OPEN)
            self._hold_open(now)
            return self._stop(now)
        return self._drive(Motion.OPEN, self.cfg.travel_open_s, "timeout_open", now)

    def _open(self, i: Inputs, now: float, manual_edge: bool) -> Motion:
        if not i.at_open:
            return self._fail("position_lost", "La pluma dejó de estar abierta sin orden", now)
        if manual_edge:
            self._hold_open(now)
        # Paso del vehículo: la fotocelda se interrumpe y luego se libera.
        if not i.photocell_clear:
            self._car_blocked, self._clear_since = True, None
            return self._stop(now)  # nunca se cierra con la fotocelda interrumpida
        if self._car_blocked and self._clear_since is None:
            self._clear_since = now
        passed = self._clear_since is not None and now - self._clear_since >= self.cfg.close_delay_s
        nobody = not self._car_blocked and now - self._open_since >= self.cfg.open_hold_max_s
        if passed or nobody:
            self._go(State.CLOSING)
            return self._closing(i, now)
        return self._stop(now)

    def _closing(self, i: Inputs, now: float) -> Motion:
        if not i.photocell_clear:
            # Alguien o algo bajo la pluma: parar ya y volver a subir.
            self.events.append(Event("info", "reopen", "Fotocelda interrumpida al cerrar"))
            self._go(State.OPENING)
            return self._stop(now)  # la pausa de inversión la impone _drive
        if i.at_closed:
            self._go(State.CLOSED)
            return self._stop(now)
        return self._drive(Motion.CLOSE, self.cfg.travel_close_s, "timeout_close", now)

    # ---------- motor ----------

    def _drive(self, direction: Motion, travel_s: float, timeout_code: str, now: float) -> Motion:
        if self.motion == direction:
            if now - self._motion_since > travel_s * (1 + self.cfg.travel_margin):
                return self._fail(
                    timeout_code, f"No llegó al final de carrera en {travel_s:.1f} s + margen", now
                )
            return direction
        if self.motion != Motion.STOP:
            return self._stop(now)  # invertir: primero apagar
        if now - self._stopped_at < self.cfg.reverse_pause_s:
            return Motion.STOP  # pausa obligatoria entre relés
        self.motion, self._motion_since = direction, now
        return direction

    def _stop(self, now: float) -> Motion:
        if self.motion != Motion.STOP:
            self._stopped_at = now
        self.motion = Motion.STOP
        return Motion.STOP

    def _hold_open(self, now: float) -> None:
        self._open_since = now
        self._car_blocked, self._clear_since = False, None

    def _fail(self, code: str, detail: str, now: float) -> Motion:
        self.fault_code = code
        self.events.append(Event("fault", code, detail))
        self._go(State.FAULT)
        self._open_requested = False
        return self._stop(now)

    def _go(self, state: State) -> None:
        if state != self.state:
            self.state = state
            self.events.append(Event("state", state.value))
