"""
anpr-gate: la parte crítica de seguridad. Aquí se prueba la máquina de estados sin
hardware, el servicio con GPIO en memoria, y el lazo cerrado con el simulador de la
pluma (física + cableado de seguridad).
"""

import logging
import random
import uuid
from dataclasses import replace
from datetime import timedelta

import pytest

from anpr_edge.common.config import GateConfig
from anpr_edge.common.gpio import MemoryGpio
from anpr_edge.common.messages import Command, Fault, GateState, utcnow
from anpr_edge.gate.machine import GateMachine, Inputs, Motion, State
from anpr_edge.gate.service import GATE_INPUTS, RELAYS, GateService
from anpr_edge.sim.plant import Plant

CFG = GateConfig(
    travel_open_s=4,
    travel_close_s=4,
    travel_margin=0.2,
    reverse_pause_s=0.5,
    close_delay_s=1.0,
    open_hold_max_s=10,
    input_debounce_ms=0,
)
DT = 0.02

CLOSED = Inputs(at_open=False, at_closed=True, photocell_clear=True, estop_ok=True, auto_mode=True)
MIDDLE = replace(CLOSED, at_closed=False)
OPEN = replace(CLOSED, at_closed=False, at_open=True)


class Clock:
    def __init__(self) -> None:
        self.t = 100.0

    def run(self, m: GateMachine, i: Inputs, seconds: float) -> list[Motion]:
        out = []
        for _ in range(round(seconds / DT)):
            self.t += DT
            out.append(m.step(i, self.t))
        return out


@pytest.fixture
def clock() -> Clock:
    return Clock()


def closed_machine(clock: Clock) -> GateMachine:
    m = GateMachine(CFG)
    clock.run(m, CLOSED, 0.1)
    assert m.state == State.CLOSED
    return m


def start_opening(m: GateMachine, clock: Clock, event_id: str = "e1") -> None:
    """Orden de abrir; el brazo deja el tope solo después de que arranca el motor."""
    assert m.request_open(event_id, clock.t)[0]
    clock.run(m, CLOSED, DT)
    assert m.motion == Motion.OPEN


def open_machine(clock: Clock) -> GateMachine:
    m = closed_machine(clock)
    start_opening(m, clock)
    clock.run(m, MIDDLE, 1.0)
    clock.run(m, OPEN, 0.1)
    assert m.state == State.OPEN
    return m


# ---------- arranque ----------


def test_arranca_cerrada_y_quieta(clock):
    m = GateMachine(CFG)
    assert set(clock.run(m, CLOSED, 1)) == {Motion.STOP}
    assert m.state == State.CLOSED


def test_arranca_en_posicion_desconocida_y_hace_referencia_cerrando(clock):
    m = GateMachine(CFG)
    moves = clock.run(m, MIDDLE, 1)
    assert m.state == State.HOMING and moves[-1] == Motion.CLOSE
    clock.run(m, CLOSED, 0.1)
    assert m.state == State.CLOSED and m.motion == Motion.STOP


def test_referencia_espera_si_hay_algo_bajo_la_pluma(clock):
    m = GateMachine(CFG)
    moves = clock.run(m, replace(MIDDLE, photocell_clear=False), 3)
    assert set(moves) == {Motion.STOP} and m.state == State.HOMING
    assert clock.run(m, MIDDLE, 1)[-1] == Motion.CLOSE


def test_referencia_sin_llegar_al_tope_es_falla(clock):
    m = GateMachine(CFG)
    clock.run(m, MIDDLE, 4 * 1.2 + 0.5)
    assert m.state == State.FAULT and m.fault_code == "timeout_homing"


# ---------- ciclo normal ----------


def test_orden_abre_hasta_el_tope(clock):
    m = closed_machine(clock)
    assert m.request_open("e1", clock.t) == (True, "abriendo")
    clock.run(m, CLOSED, DT)
    moves = clock.run(m, MIDDLE, 1)
    assert Motion.OPEN in moves and Motion.CLOSE not in moves
    assert clock.run(m, OPEN, 0.1)[-1] == Motion.STOP
    assert m.state == State.OPEN


def test_cierra_cuando_el_auto_termino_de_pasar(clock):
    m = open_machine(clock)
    clock.run(m, replace(OPEN, photocell_clear=False), 2)  # el auto cruza
    assert m.state == State.OPEN
    clock.run(m, OPEN, CFG.close_delay_s - 0.1)
    assert m.state == State.OPEN, "espera close_delay_s tras liberarse la fotocelda"
    clock.run(m, OPEN, 0.8)  # pasa la pausa de inversión
    assert m.state == State.CLOSING and m.motion == Motion.CLOSE
    clock.run(m, CLOSED, 0.1)
    assert m.state == State.CLOSED


def test_si_nadie_cruza_cierra_tras_el_maximo(clock):
    m = open_machine(clock)
    clock.run(m, OPEN, CFG.open_hold_max_s - 0.5)
    assert m.state == State.OPEN
    clock.run(m, OPEN, 1.5)
    assert m.state == State.CLOSING


def test_nunca_cierra_con_la_fotocelda_interrumpida(clock):
    m = open_machine(clock)
    moves = clock.run(m, replace(OPEN, photocell_clear=False), CFG.open_hold_max_s * 3)
    assert set(moves) == {Motion.STOP} and m.state == State.OPEN


def test_fotocelda_al_cerrar_para_y_vuelve_a_subir_tras_la_pausa(clock):
    m = open_machine(clock)
    clock.run(m, OPEN, CFG.open_hold_max_s + 1)
    clock.run(m, MIDDLE, 0.5)
    assert m.motion == Motion.CLOSE
    blocked = replace(MIDDLE, photocell_clear=False)
    moves = clock.run(m, blocked, 1.0)
    assert moves[0] == Motion.STOP, "debe parar en el mismo instante"
    stop_run = next(i for i, mv in enumerate(moves) if mv == Motion.OPEN)
    assert stop_run * DT >= CFG.reverse_pause_s - DT
    assert m.state == State.OPENING


def test_otra_orden_con_la_pluma_abierta_la_mantiene(clock):
    m = open_machine(clock)
    clock.run(m, OPEN, CFG.open_hold_max_s - 1)
    assert m.request_open("e2", clock.t)[0]
    clock.run(m, OPEN, 5)
    assert m.state == State.OPEN


# ---------- órdenes ----------


def test_orden_duplicada_no_abre_dos_veces(clock):
    m = closed_machine(clock)
    assert m.request_open("e1", clock.t)[0]
    assert m.request_open("e1", clock.t) == (False, "orden duplicada")


def test_orden_durante_el_cierre_se_rechaza(clock):
    m = open_machine(clock)
    clock.run(m, OPEN, CFG.open_hold_max_s + 1)
    clock.run(m, MIDDLE, 0.3)
    assert m.state == State.CLOSING
    ok, _ = m.request_open("e9", clock.t)
    assert not ok and m.state == State.CLOSING


def test_boton_manual_abre_una_vez_por_pulsacion(clock):
    m = closed_machine(clock)
    pressed = lambda i: replace(i, manual_pressed=True)  # noqa: E731
    clock.run(m, pressed(CLOSED), DT)
    assert m.state == State.OPENING
    # Se mantiene apretado durante todo el ciclo: no debe reabrir al cerrarse.
    clock.run(m, pressed(MIDDLE), 1)
    clock.run(m, pressed(OPEN), CFG.open_hold_max_s + 1)
    clock.run(m, pressed(MIDDLE), 1)
    clock.run(m, pressed(CLOSED), 3)
    assert m.state == State.CLOSED and m.motion == Motion.STOP
    # Soltar y volver a apretar sí abre.
    clock.run(m, CLOSED, DT)
    clock.run(m, pressed(CLOSED), DT)
    assert m.state == State.OPENING


# ---------- fallas ----------


def test_emergencia_para_y_queda_en_falla_hasta_pasar_por_manual(clock):
    m = closed_machine(clock)
    start_opening(m, clock)
    clock.run(m, MIDDLE, 0.5)
    assert clock.run(m, replace(MIDDLE, estop_ok=False), DT)[0] == Motion.STOP
    assert m.state == State.FAULT and m.fault_code == "estop"
    # Soltar la emergencia no basta: una persona debe pasar por MANUAL.
    assert set(clock.run(m, MIDDLE, 2)) == {Motion.STOP}
    clock.run(m, replace(MIDDLE, auto_mode=False), 0.1)
    assert m.state == State.MANUAL
    clock.run(m, MIDDLE, 0.1)
    assert m.state == State.HOMING and m.fault_code is None


def test_timeout_al_abrir_es_falla(clock):
    m = closed_machine(clock)
    start_opening(m, clock)
    clock.run(m, MIDDLE, 4 * 1.2 + 0.2)
    assert m.state == State.FAULT and m.fault_code == "timeout_open"
    assert m.motion == Motion.STOP


def test_ambos_finales_activos_es_falla(clock):
    m = closed_machine(clock)
    clock.run(m, replace(CLOSED, at_open=True), DT)
    assert m.state == State.FAULT and m.fault_code == "limits"


def test_perder_la_posicion_cerrada_sin_orden_es_falla(clock):
    m = closed_machine(clock)
    clock.run(m, MIDDLE, DT)
    assert m.state == State.FAULT and m.fault_code == "position_lost"


def test_en_manual_la_pi_no_acciona_nada(clock):
    m = closed_machine(clock)
    manual = replace(CLOSED, auto_mode=False)
    clock.run(m, manual, 0.1)
    assert not m.request_open("e1", clock.t)[0]
    assert set(clock.run(m, replace(manual, manual_pressed=True), 1)) == {Motion.STOP}


# ---------- invariantes con entradas aleatorias ----------


def test_invariantes_de_seguridad_con_entradas_aleatorias():
    """
    20 000 pasos con entradas al azar (incluidas combinaciones absurdas). Nunca:
    - se mueve con la emergencia activa, en MANUAL o en FAULT,
    - baja con la fotocelda interrumpida,
    - invierte el sentido sin la pausa obligatoria.
    """
    rng = random.Random(1234)
    m = GateMachine(CFG)
    t, last_active, last_dir = 0.0, float("-inf"), Motion.STOP
    for step in range(20_000):
        t += DT
        if step % 50 == 0 and rng.random() < 0.3:
            m.request_open(str(uuid.uuid4()), t)
        i = Inputs(
            at_open=rng.random() < 0.2,
            at_closed=rng.random() < 0.3,
            photocell_clear=rng.random() < 0.8,
            estop_ok=rng.random() < 0.97,
            auto_mode=rng.random() < 0.98,
            manual_pressed=rng.random() < 0.05,
        )
        mv = m.step(i, t)
        if mv != Motion.STOP:
            assert i.estop_ok and i.auto_mode
            assert m.state not in (State.FAULT, State.MANUAL)
            if mv == Motion.CLOSE:
                assert i.photocell_clear
            if last_dir not in (Motion.STOP, mv):
                pytest.fail("invirtió sin parar")
            if last_dir == Motion.STOP:
                assert t - last_active >= CFG.reverse_pause_s - 1e-9
            last_active = t
        elif last_dir != Motion.STOP:
            last_active = t
        last_dir = mv


# ---------- servicio (GPIO en memoria) ----------


def make_service(bus, cfg=CFG):
    gpio = MemoryGpio(inputs=GATE_INPUTS, outputs=RELAYS)
    set_levels(gpio, Plant())
    return GateService(cfg, gpio, bus, logging.getLogger("t")), gpio


def set_levels(gpio: MemoryGpio, plant: Plant, now: float = 0.0) -> None:
    for name, level in plant.inputs(now).items():
        if name in gpio.levels:
            gpio.levels[name] = level


def command(event_id=None, age_s=0.0, ttl_s=10):
    return Command(
        event_id=event_id or uuid.uuid4(),
        action="open",
        ttl_s=ttl_s,
        issued_at=utcnow() - timedelta(seconds=age_s),
    )


def test_servicio_descarta_orden_vencida(bus):
    svc, gpio = make_service(bus)
    svc.on_start()
    svc.on_tick(1.0)
    svc.on_message(command(age_s=30))
    for k in range(20):
        svc.on_tick(1.0 + k * DT)
    assert svc.machine.state == State.CLOSED
    assert gpio.out == {"RELAY_FWD": False, "RELAY_REV": False}


def test_servicio_apaga_los_reles_si_su_logica_falla(bus):
    svc, gpio = make_service(bus)
    gpio.out["RELAY_FWD"] = True

    def boom(*_):
        raise RuntimeError("bug")

    svc.machine.step = boom
    with pytest.raises(RuntimeError):
        svc.on_tick(1.0)
    assert gpio.out == {"RELAY_FWD": False, "RELAY_REV": False}


def test_servicio_publica_estado_retenido_y_fallas(bus):
    svc, gpio = make_service(bus)
    svc.on_tick(1.0)
    gpio.levels["ESTOP_OK"] = 1
    svc.on_tick(1.02)
    assert [s.state for s in bus.of(GateState)][-1] == "fault"
    assert bus.of(Fault)[-1].code == "estop"


def test_cable_cortado_se_lee_como_inseguro(bus):
    """Sin simulador ni sensores (todo a 1): no hay AUTO ni vía libre, nada se mueve."""
    gpio = MemoryGpio(inputs=GATE_INPUTS, outputs=RELAYS)
    svc = GateService(CFG, gpio, bus, logging.getLogger("t"))
    for k in range(50):
        svc.on_tick(1.0 + k * DT)
    assert svc.machine.state == State.MANUAL
    assert not any(gpio.out.values())


# ---------- lazo cerrado con el simulador de la pluma ----------


class Loop:
    """Servicio de la pluma + física y cableado simulados, sin MQTT."""

    def __init__(self, bus, travel_s: float = 4.0) -> None:
        self.svc, self.gpio = make_service(bus)
        self.plant = Plant(travel_s=travel_s)
        self.t = 0.0

    def run(self, seconds: float) -> None:
        for _ in range(round(seconds / DT)):
            self.t += DT
            set_levels(self.gpio, self.plant, self.t)
            self.svc.on_tick(self.t)
            self.plant.relays.update(self.gpio.out)
            self.plant.step(DT, self.t)


def test_lazo_cerrado_un_auto_autorizado_pasa_y_la_pluma_baja(bus):
    loop = Loop(bus)
    loop.run(0.2)
    loop.plant.car_arrives(loop.t)
    loop.svc.on_message(command())
    loop.run(15)
    p = loop.plant
    assert p.cars_passed == 1 and p.angle == 0
    assert loop.svc.machine.state == State.CLOSED
    assert p.shorts == 0 and p.pushing_s < 0.1


def test_lazo_cerrado_alguien_bajo_la_pluma_al_cerrar(bus):
    loop = Loop(bus)
    loop.run(0.2)
    loop.svc.on_message(command())
    loop.run(4.5)  # abierta
    loop.run(CFG.open_hold_max_s)  # nadie cruza: empieza a bajar
    loop.run(1.0)
    assert loop.svc.machine.state == State.CLOSING
    angle = loop.plant.angle
    loop.plant.blocked = True
    loop.run(3)
    assert loop.plant.angle >= angle, "no debe seguir bajando"
    loop.plant.blocked = False
    loop.run(CFG.close_delay_s + CFG.open_hold_max_s + 6)
    assert loop.plant.angle == 0 and loop.plant.shorts == 0


def test_lazo_cerrado_emergencia_detiene_el_brazo(bus):
    loop = Loop(bus)
    loop.run(0.2)
    loop.svc.on_message(command())
    loop.run(1.5)
    loop.plant.estop = True
    angle = loop.plant.angle
    loop.run(3)
    assert loop.plant.angle == angle
    assert loop.svc.machine.state == State.FAULT
    assert not any(loop.gpio.out.values())
