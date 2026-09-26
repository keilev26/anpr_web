import logging

from anpr_edge.common.config import TriggerConfig
from anpr_edge.common.gpio import MemoryGpio
from anpr_edge.common.messages import GateState, Trigger, Verdict, utcnow
from anpr_edge.trigger.service import Phase, TriggerService

CFG = TriggerConfig(
    debounce_ms=300, release_ms=1500, verdict_timeout_s=10, max_attempts=3, retry_delay_s=1.5
)
DT = 0.05


class Lane:
    def __init__(self, bus) -> None:
        self.gpio = MemoryGpio(inputs=["PRESENCE"])
        self.bus = bus
        self.svc = TriggerService(CFG, self.gpio, bus, logging.getLogger("t"))
        self.t = 0.0
        self.car(False)

    def car(self, present: bool) -> None:
        self.gpio.levels["PRESENCE"] = 0 if present else 1

    def run(self, seconds: float) -> None:
        for _ in range(round(seconds / DT)):
            self.t += DT
            self.svc.on_tick(self.t)

    def verdict(self, outcome: str) -> None:
        last = self.bus.of(Trigger)[-1]
        self.svc.on_message(Verdict(event_id=last.event_id, outcome=outcome, ts=utcnow()))

    def gate(self, state: str) -> None:
        self.svc.on_message(GateState(state=state, position_known=True, ts=utcnow()))

    @property
    def triggers(self) -> int:
        return len(self.bus.of(Trigger))


def test_un_disparo_por_llegada(bus):
    lane = Lane(bus)
    lane.car(True)
    lane.run(5)
    assert lane.triggers == 1


def test_un_rebote_corto_no_dispara(bus):
    lane = Lane(bus)
    lane.car(True)
    lane.run(0.2)
    lane.car(False)
    lane.run(2)
    assert lane.triggers == 0


def test_placa_ilegible_reintenta_con_evento_nuevo_hasta_el_maximo(bus):
    lane = Lane(bus)
    lane.car(True)
    lane.run(0.5)
    for _ in range(CFG.max_attempts):
        lane.verdict("unreadable")
        lane.run(CFG.retry_delay_s + 0.1)
    assert lane.triggers == CFG.max_attempts
    assert len({t.event_id for t in bus.of(Trigger)}) == CFG.max_attempts
    assert lane.svc.phase == Phase.DONE


def test_denegada_no_se_reintenta(bus):
    lane = Lane(bus)
    lane.car(True)
    lane.run(0.5)
    lane.verdict("deny")
    lane.run(10)
    assert lane.triggers == 1


def test_sin_veredicto_a_tiempo_reintenta(bus):
    lane = Lane(bus)
    lane.car(True)
    lane.run(0.5)
    lane.run(CFG.verdict_timeout_s + CFG.retry_delay_s + 0.2)
    assert lane.triggers == 2


def test_si_el_auto_se_fue_no_reintenta(bus):
    lane = Lane(bus)
    lane.car(True)
    lane.run(0.5)
    lane.car(False)
    lane.run(2)  # ausencia estable
    lane.verdict("unreadable")
    lane.run(5)
    assert lane.triggers == 1


def test_veredicto_de_otro_evento_se_ignora(bus):
    lane = Lane(bus)
    lane.car(True)
    lane.run(0.5)
    import uuid

    lane.svc.on_message(Verdict(event_id=uuid.uuid4(), outcome="deny", ts=utcnow()))
    assert lane.svc.phase == Phase.WAITING


def test_cola_de_autos_tras_un_ciclo_de_la_pluma(bus):
    """El primer auto pasa y el segundo queda sobre el sensor sin que se libere."""
    lane = Lane(bus)
    lane.car(True)
    lane.run(0.5)
    lane.verdict("open")
    lane.gate("opening")
    lane.gate("open")
    lane.run(3)
    assert lane.triggers == 1
    lane.gate("closing")
    lane.gate("closed")
    lane.run(0.5)
    assert lane.triggers == 2


def test_nuevo_auto_tras_irse_el_anterior(bus):
    lane = Lane(bus)
    lane.car(True)
    lane.run(0.5)
    lane.verdict("open")
    lane.car(False)
    lane.run(2)
    assert lane.svc.phase == Phase.IDLE
    lane.car(True)
    lane.run(0.5)
    assert lane.triggers == 2
