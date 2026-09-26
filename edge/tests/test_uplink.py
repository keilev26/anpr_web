"""anpr-uplink contra respuestas simuladas y contra la nube falsa (mismo contrato que la API)."""

import json
import logging
import os
import time
import uuid
from datetime import timedelta
from pathlib import Path

import httpx
import pytest
from starlette.testclient import TestClient

from anpr_edge.common import spool
from anpr_edge.common.config import UplinkConfig
from anpr_edge.common.messages import Command, FramesReady, Verdict, utcnow
from anpr_edge.sim.cloud import Scenario, create_app
from anpr_edge.uplink.service import UplinkService

JPEGS = [p.read_bytes() for p in sorted((Path(__file__).parent / "fixtures/frames").glob("*.jpg"))]
CFG = UplinkConfig(
    api_url="http://nube",
    open_deadline_s=2.0,
    request_timeout_s=1.0,
    connect_timeout_s=0.5,
    pending_retry_s=60,
)
LOG = logging.getLogger("t")


def verdict_json(event_id: str, action: str = "open") -> dict:
    return {
        "event_id": event_id,
        "plate": "CUB-604",
        "authorized": action == "open",
        "command": {"action": action, "ttl_s": 10},
        "latency_ms": 5,
    }


def make(bus, tmp_path, handler, cfg=CFG):
    client = httpx.Client(base_url=cfg.api_url, transport=httpx.MockTransport(handler))
    return UplinkService(cfg, tmp_path, "clave", bus, LOG, client=client)


def event(tmp_path, age_s: float = 0.0) -> FramesReady:
    eid = uuid.uuid4()
    captured = utcnow() - timedelta(seconds=age_s)
    path = spool.write_event(tmp_path, eid, JPEGS, {"captured_at": captured.isoformat()})
    return FramesReady(event_id=eid, path=str(path), count=3, captured_at=captured)


def status(tmp_path, msg: FramesReady) -> dict:
    return spool.read_status(Path(msg.path))


def test_abre_solo_con_200_y_open(bus, tmp_path):
    seen = {}

    def handler(req: httpx.Request):
        seen["key"] = req.headers["x-device-key"]
        body = req.content
        seen["frames"] = body.count(b'name="frames"')
        eid = body.split(b'name="event_id"\r\n\r\n')[1].split(b"\r\n")[0].decode()
        return httpx.Response(200, json=verdict_json(eid))

    svc = make(bus, tmp_path, handler)
    msg = event(tmp_path)
    svc.handle(msg)
    cmd = bus.of(Command)
    assert len(cmd) == 1 and cmd[0].event_id == msg.event_id and cmd[0].ttl_s == 10
    assert bus.of(Verdict)[0].outcome == "open"
    assert seen == {"key": "clave", "frames": 3}
    assert status(tmp_path, msg)["state"] == "sent"


def test_denegada_no_manda_orden(bus, tmp_path):
    msg = event(tmp_path)
    svc = make(
        bus, tmp_path, lambda r: httpx.Response(200, json=verdict_json(str(msg.event_id), "deny"))
    )
    svc.handle(msg)
    assert bus.of(Command) == [] and bus.of(Verdict)[0].outcome == "deny"


@pytest.mark.parametrize(
    ("code", "outcome", "state"),
    [
        (422, "unreadable", "sent"),
        (401, "rejected", "rejected"),
        (413, "rejected", "rejected"),
        (503, "unavailable", "pending"),
    ],
)
def test_codigos_de_error_nunca_abren(bus, tmp_path, code, outcome, state):
    svc = make(bus, tmp_path, lambda r: httpx.Response(code, json={"detail": "x"}))
    msg = event(tmp_path)
    svc.handle(msg)
    assert bus.of(Command) == []
    assert bus.of(Verdict)[0].outcome == outcome
    assert status(tmp_path, msg)["state"] == state


def test_reintenta_5xx_dentro_del_plazo_con_el_mismo_evento(bus, tmp_path):
    calls = []

    def handler(req):
        eid = req.content.split(b'name="event_id"\r\n\r\n')[1].split(b"\r\n")[0].decode()
        calls.append(eid)
        if len(calls) < 3:
            return httpx.Response(503)
        return httpx.Response(200, json=verdict_json(eid))

    svc = make(bus, tmp_path, handler)
    msg = event(tmp_path)
    svc.handle(msg)
    assert len(calls) == 3 and len(set(calls)) == 1
    assert bus.of(Command)[0].event_id == msg.event_id


def test_timeout_hasta_agotar_el_plazo_no_abre(bus, tmp_path):
    def handler(req):
        raise httpx.ReadTimeout("lento", request=req)

    svc = make(bus, tmp_path, handler)
    msg = event(tmp_path)
    t = time.monotonic()
    svc.handle(msg)
    assert time.monotonic() - t <= CFG.open_deadline_s + 0.5
    assert bus.of(Command) == [] and bus.of(Verdict)[0].outcome == "unavailable"


def test_evento_que_ya_vencio_no_se_intenta(bus, tmp_path):
    calls = []
    svc = make(bus, tmp_path, lambda r: calls.append(1) or httpx.Response(200))
    svc.handle(event(tmp_path, age_s=10))
    assert calls == [] and bus.of(Command) == []


def test_respuesta_invalida_no_abre(bus, tmp_path):
    msg = event(tmp_path)
    bad = verdict_json(str(uuid.uuid4()))  # event_id de otro evento
    svc = make(bus, tmp_path, lambda r: httpx.Response(200, json=bad))
    svc.handle(msg)
    assert bus.of(Command) == [] and bus.of(Verdict)[0].outcome == "rejected"


def test_ruta_fuera_del_spool_se_rechaza(bus, tmp_path):
    calls = []
    svc = make(bus, tmp_path, lambda r: calls.append(1) or httpx.Response(200))
    msg = FramesReady(event_id=uuid.uuid4(), path="/etc", count=3, captured_at=utcnow())
    svc.handle(msg)
    assert calls == [] and bus.published == []


def test_mensaje_duplicado_se_procesa_una_vez(bus, tmp_path):
    calls = []
    msg = event(tmp_path)

    def handler(r):
        calls.append(1)
        return httpx.Response(200, json=verdict_json(str(msg.event_id)))

    svc = make(bus, tmp_path, handler)
    svc.handle(msg)
    svc.handle(msg)
    assert len(calls) == 1 and len(bus.of(Command)) == 1


def test_pendiente_se_reenvia_tarde_solo_para_registro(bus, tmp_path):
    bodies = []

    def handler(req):
        bodies.append(req.content)
        return (
            httpx.Response(503) if len(bodies) <= 1 else httpx.Response(200, json=verdict_json("x"))
        )

    cfg = CFG.model_copy(update={"open_deadline_s": 0.5})
    svc = make(bus, tmp_path, handler, cfg)
    msg = event(tmp_path)
    svc.handle(msg)
    assert status(tmp_path, msg)["state"] == "pending"
    bus.published.clear()
    svc.retry_one_pending()
    assert b'name="late"\r\n\r\ntrue' in bodies[-1]
    assert status(tmp_path, msg)["state"] == "sent"
    assert bus.of(Command) == [], "un reenvío tardío nunca abre"


def test_limpieza_marca_lo_no_procesado_y_borra_lo_viejo(bus, tmp_path):
    svc = make(bus, tmp_path, lambda r: httpx.Response(503))
    lost = event(tmp_path, age_s=0)
    old = event(tmp_path)
    spool.write_status(Path(old.path), {"state": "sent"})
    past = time.time() - 3 * 86400
    for d in (Path(lost.path), Path(old.path)):
        os.utime(d / "meta.json", (past, past))
    orphan = tmp_path / spool.EVENTS / f"{spool.TMP_PREFIX}x"
    orphan.mkdir()
    os.utime(orphan, (past, past))
    svc.housekeeping()
    assert status(tmp_path, lost)["state"] == "pending"  # nadie lo subió: queda pendiente
    assert not Path(old.path).exists()  # enviado hace 3 días: se borra
    assert not orphan.exists()


def test_tope_de_tamano_borra_primero_lo_enviado(bus, tmp_path):
    cfg = CFG.model_copy(update={"spool_max_mb": 0.03})  # ~30 KB: caben ~1 evento
    svc = make(bus, tmp_path, lambda r: httpx.Response(503), cfg)
    sent, pending = event(tmp_path), event(tmp_path)
    spool.write_status(Path(sent.path), {"state": "sent"})
    spool.write_status(Path(pending.path), {"state": "pending"})
    svc.housekeeping()
    assert not Path(sent.path).exists() and Path(pending.path).exists()


# ---------- contra la nube falsa (mismo contrato que la API real) ----------


@pytest.mark.parametrize(
    ("mode", "outcome", "opens"),
    [
        ("open", "open", True),
        ("deny", "deny", False),
        ("unreadable", "unreadable", False),
        ("unavailable", "unavailable", False),
    ],
)
def test_contra_la_nube_simulada(bus, tmp_path, mode, outcome, opens):
    app = create_app(Scenario(mode=mode), device_key="clave")
    cfg = CFG.model_copy(update={"api_url": "http://testserver"})
    svc = UplinkService(cfg, tmp_path, "clave", bus, LOG, client=TestClient(app))
    msg = event(tmp_path)
    svc.handle(msg)
    assert bus.of(Verdict)[0].outcome == outcome
    assert bool(bus.of(Command)) is opens
    ev = app.state.events[0]
    assert ev["frames"] == 3 and ev["late"] is False


def test_clave_equivocada_contra_la_nube_simulada(bus, tmp_path):
    app = create_app(Scenario(mode="open"), device_key="otra")
    cfg = CFG.model_copy(update={"api_url": "http://testserver"})
    svc = UplinkService(cfg, tmp_path, "clave", bus, LOG, client=TestClient(app))
    svc.handle(event(tmp_path))
    assert bus.of(Verdict)[0].outcome == "rejected" and bus.of(Command) == []


def test_meta_json_es_valido(tmp_path):
    msg = event(tmp_path)
    assert json.loads((Path(msg.path) / "meta.json").read_text())["captured_at"]
