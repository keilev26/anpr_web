import logging

import httpx

from anpr_edge.common.config import HealthConfig
from anpr_edge.common.gpio import MemoryGpio
from anpr_edge.common.messages import CameraStatus, GateState, HealthSummary, ServiceStatus, utcnow
from anpr_edge.health.service import HealthService, check_cloud


def make(bus, tmp_path):
    gpio = MemoryGpio(outputs=["LED_STATUS"])
    svc = HealthService(HealthConfig(), "http://nube", tmp_path, gpio, bus, logging.getLogger("t"))
    return svc, gpio


def all_ok(svc):
    for s in svc.cfg.services:
        svc.on_message(ServiceStatus(service=s, status="online"))
    svc.on_message(GateState(state="closed", position_known=True, ts=utcnow()))
    svc.on_message(CameraStatus(online=True, fps=15, last_frame_age_s=0.1, ts=utcnow()))
    svc.cloud = "ok"


def test_todo_bien_led_fijo(bus, tmp_path):
    svc, gpio = make(bus, tmp_path)
    all_ok(svc)
    assert svc.evaluate() == []
    assert bus.of(HealthSummary)[-1].ok
    svc.on_tick(0.3)
    assert gpio.out["LED_STATUS"] is True and svc.led_pattern() == "solid"


def test_servicio_caido_y_nube_inalcanzable(bus, tmp_path):
    svc, _ = make(bus, tmp_path)
    all_ok(svc)
    svc.on_message(ServiceStatus(service="uplink", status="offline"))
    svc.cloud = "unreachable"
    problems = svc.evaluate()
    assert "servicio uplink: offline" in problems and "nube: unreachable" in problems
    assert svc.led_pattern() == "slow"


def test_pluma_en_falla_parpadeo_rapido(bus, tmp_path):
    svc, gpio = make(bus, tmp_path)
    all_ok(svc)
    svc.on_message(GateState(state="fault", position_known=False, ts=utcnow()))
    svc.evaluate()
    assert svc.led_pattern() == "fast"
    states = set()
    for k in range(20):
        svc.on_tick(1000 + k * 0.05)
        states.add(gpio.out["LED_STATUS"])
    assert states == {True, False}


def test_chequeo_de_la_nube():
    def client(resp):
        return httpx.Client(transport=httpx.MockTransport(lambda r: resp))

    assert check_cloud(client(httpx.Response(200, json={"db": True})), "http://x/health") == "ok"
    assert check_cloud(client(httpx.Response(200, json={"db": False})), "http://x") == "degraded"
    assert check_cloud(client(httpx.Response(502)), "http://x") == "unreachable"

    def boom(r):
        raise httpx.ConnectError("sin red", request=r)

    c = httpx.Client(transport=httpx.MockTransport(boom))
    assert check_cloud(c, "http://x") == "unreachable"
