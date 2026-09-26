import logging
import threading
import time
import uuid
from datetime import timedelta
from pathlib import Path

from anpr_edge.camera.sony import LiveviewFrame, SonyCamera
from anpr_edge.capture.service import (
    CameraWorker,
    CaptureService,
    FrameBuffer,
    trim_to_size,
)
from anpr_edge.common import spool
from anpr_edge.common.config import CameraConfig, CaptureConfig
from anpr_edge.common.messages import CameraStatus, Fault, FramesReady, Trigger, utcnow
from anpr_edge.sim.camera import CameraState, serve

JPEGS = [p.read_bytes() for p in sorted((Path(__file__).parent / "fixtures/frames").glob("*.jpg"))]
LOG = logging.getLogger("t")


def make(bus, tmp_path, **kw):
    cfg = CaptureConfig(spool_dir=tmp_path, frames=5, spacing_ms=150, timeout_s=3.0, **kw)
    buf = FrameBuffer(2.0)
    return CaptureService(cfg, buf, bus, LOG), buf


def feed(buf: FrameBuffer, start: float, seconds: float, fps: float = 15, seq0: int = 0) -> None:
    n = int(seconds * fps)
    for k in range(n):
        buf.add(LiveviewFrame(seq0 + k, k, JPEGS[k % 3], received=start + k / fps))


def trigger(age_s: float = 0.0) -> Trigger:
    return Trigger(event_id=uuid.uuid4(), source="loop", ts=utcnow() - timedelta(seconds=age_s))


def test_rafaga_espaciada_al_spool(bus, tmp_path):
    svc, buf = make(bus, tmp_path)
    t = trigger()
    svc.on_message(t)
    start = svc.bursts[t.event_id].started
    feed(buf, start + 0.01, 1.2)
    svc.on_tick(start + 1.3)
    ready = bus.of(FramesReady)
    assert len(ready) == 1 and ready[0].count == 5 and ready[0].event_id == t.event_id
    event_dir = spool.resolve_event(tmp_path, ready[0].path)
    meta = spool.read_meta(event_dir)
    seqs = meta["seqs"]
    assert all(b - a >= 2 for a, b in zip(seqs, seqs[1:], strict=False)), "fotos espaciadas"
    assert len(spool.read_frames(event_dir)) == 5


def test_solo_usa_frames_posteriores_al_disparo(bus, tmp_path):
    svc, buf = make(bus, tmp_path)
    feed(buf, time.monotonic() - 1.5, 1.0, seq0=0)  # frames viejos
    t = trigger()
    svc.on_message(t)
    start = svc.bursts[t.event_id].started
    feed(buf, start + 0.01, 1.2, seq0=1000)
    svc.on_tick(start + 1.3)
    meta = spool.read_meta(spool.resolve_event(tmp_path, bus.of(FramesReady)[0].path))
    assert min(meta["seqs"]) >= 1000


def test_disparo_viejo_se_ignora(bus, tmp_path):
    svc, _ = make(bus, tmp_path)
    svc.on_message(trigger(age_s=10))
    assert svc.bursts == {}


def test_disparo_duplicado_una_sola_rafaga(bus, tmp_path):
    svc, _ = make(bus, tmp_path)
    t = trigger()
    svc.on_message(t)
    svc.on_message(t)
    assert len(svc.bursts) == 1


def test_camara_caida_publica_falla(bus, tmp_path):
    svc, buf = make(bus, tmp_path)
    t = trigger()
    svc.on_message(t)
    start = svc.bursts[t.event_id].started
    feed(buf, start + 0.01, 0.1)  # 1 frame
    svc.on_tick(start + 3.5)
    assert bus.of(FramesReady) == []
    assert bus.of(Fault)[0].code == "camera_unavailable"


def test_con_pocos_frames_pero_al_menos_tres_se_envia(bus, tmp_path):
    svc, buf = make(bus, tmp_path)
    t = trigger()
    svc.on_message(t)
    start = svc.bursts[t.event_id].started
    feed(buf, start + 0.01, 0.5, fps=6)  # 3 frames
    svc.on_tick(start + 3.5)
    assert bus.of(FramesReady)[0].count == 3


def test_recorte_por_tamano_nunca_baja_de_tres():
    frames = [b"x" * 1000] * 6
    assert len(trim_to_size(frames, 3500)) == 3
    assert len(trim_to_size(frames, 10**6)) == 6
    assert len(trim_to_size(frames, 10)) == 3  # el llamador detecta que no cabe


def test_estado_de_la_camara(bus, tmp_path):
    svc, buf = make(bus, tmp_path)
    now = time.monotonic()
    feed(buf, now - 1, 1)
    svc.on_tick(now)
    st = bus.of(CameraStatus)[-1]
    assert st.online and st.fps and 13 < st.fps < 17


def test_worker_reconecta_y_cierra_sesiones(tmp_path):
    """La Sony corta el stream cada 10 frames: el worker cierra y vuelve a abrir."""
    state = CameraState(JPEGS, None, fps=50, max_sessions=1, drop_after=10, rpc_delay=0)
    server = serve(state, port=0)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    host, port = server.server_address[:2]
    cam = SonyCamera(f"http://{host}:{port}/sony/camera", timeout_s=2)
    buf = FrameBuffer(10.0)
    worker = CameraWorker(cam, CameraConfig(stale_after_s=1.0), buf, LOG)
    worker.start()
    time.sleep(4.5)
    worker.stop()
    worker.join(timeout=5)
    server.shutdown()
    seqs = [f.seq for f in buf.after(0)]
    # Con max_sessions=1, reconectar solo es posible si cada sesión se cerró.
    assert seqs.count(0) >= 2, "debió reconectar al menos una vez"
    assert state.sessions == 0
