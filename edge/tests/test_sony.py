import threading
from pathlib import Path

import pytest

from anpr_edge.camera.sony import (
    TYPE_FRAME_INFO,
    CameraError,
    LiveviewParser,
    SonyCamera,
    encode_packet,
    jpeg_size,
)
from anpr_edge.sim.camera import CameraState, serve

FRAMES = sorted((Path(__file__).parent / "fixtures" / "frames").glob("*.jpg"))


@pytest.fixture
def jpegs() -> list[bytes]:
    return [p.read_bytes() for p in FRAMES]


def jpeg_with_thumbnail(main: bytes, thumb: bytes) -> bytes:
    """JPEG con miniatura en APP1, como los de muchas cámaras: contiene un FFD9 interno."""
    app1 = b"Exif\x00\x00" + thumb
    return main[:2] + b"\xff\xe1" + (len(app1) + 2).to_bytes(2, "big") + app1 + main[2:]


# ---------- parser ----------


def test_parsea_frames_en_trozos_de_cualquier_tamano(jpegs):
    stream = b"".join(encode_packet(i, i * 66, j, padding=i % 3) for i, j in enumerate(jpegs))
    for chunk_size in (1, 7, 136, 4096, len(stream)):
        parser = LiveviewParser()
        frames = []
        for i in range(0, len(stream), chunk_size):
            frames += parser.feed(stream[i : i + chunk_size])
        assert [f.jpeg for f in frames] == jpegs
        assert [f.seq for f in frames] == [0, 1, 2]
        assert parser.resyncs == parser.corrupt == 0


def test_jpeg_con_miniatura_no_se_corta(jpegs):
    """El legacy cortaba en el primer FFD9, que aquí es el de la miniatura."""
    full = jpeg_with_thumbnail(jpegs[0], jpegs[1][:200] + b"\xff\xd9")
    frames = LiveviewParser().feed(encode_packet(0, 0, full))
    assert len(frames) == 1 and frames[0].jpeg == full


def test_ignora_paquetes_de_informacion_de_enfoque(jpegs):
    info = encode_packet(0, 0, b"\x00" * 40, ptype=TYPE_FRAME_INFO)
    stream = info + encode_packet(1, 5, jpegs[0])
    frames = LiveviewParser().feed(stream)
    assert [f.seq for f in frames] == [1]


def test_se_resincroniza_tras_basura(jpegs):
    stream = b"basura\xff\x00" * 50 + encode_packet(7, 0, jpegs[0]) + b"\x13" * 30
    stream += encode_packet(8, 0, jpegs[1])
    parser = LiveviewParser()
    frames = parser.feed(stream)
    assert [f.seq for f in frames] == [7, 8]
    assert parser.resyncs >= 1


def test_stream_cortado_a_mitad_de_paquete_no_rompe(jpegs):
    p1, p2 = encode_packet(0, 0, jpegs[0]), encode_packet(1, 0, jpegs[1])
    parser = LiveviewParser()
    assert parser.feed(p1 + p2[: len(p2) // 2]) != []
    # Llega un paquete nuevo sin terminar el anterior (reconexión): se recupera.
    frames = parser.feed(encode_packet(2, 0, jpegs[2]) + encode_packet(3, 0, jpegs[0]))
    assert 3 in [f.seq for f in frames]


def test_datos_que_no_son_jpeg_cuentan_como_corruptos():
    parser = LiveviewParser()
    assert parser.feed(encode_packet(0, 0, b"no soy un jpeg")) == []
    assert parser.corrupt == 1


def test_resolucion_sin_decodificar(jpegs):
    assert jpeg_size(jpegs[0]) == (640, 360)


# ---------- cliente contra la Sony simulada ----------


@pytest.fixture
def sim(jpegs):
    state = CameraState(jpegs, None, fps=50, max_sessions=2, drop_after=None, rpc_delay=0)
    server = serve(state, port=0)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    host, port = server.server_address[:2]
    cam = SonyCamera(f"http://{host}:{port}/sony/camera", timeout_s=2)
    yield state, cam
    cam.close()
    server.shutdown()


def test_liveview_extremo_a_extremo(sim, jpegs):
    state, cam = sim
    url = cam.start_liveview("M")
    assert state.rec_mode, "debe activar el modo de grabación antes"
    got = []
    for f in cam.frames(url, read_timeout_s=2):
        got.append(f.jpeg)
        if len(got) == 5:
            break
    cam.stop_liveview()
    assert got[:3] == jpegs
    assert state.sessions == 0


def test_sin_stop_se_agotan_las_sesiones(sim):
    """Reproduce la fuga del legacy: por eso stop_liveview es obligatorio."""
    state, cam = sim
    cam.start_liveview()
    cam.start_liveview()
    with pytest.raises(CameraError):
        cam.start_liveview()
    cam.stop_liveview()
    cam.start_liveview()  # liberar una sesión permite volver a empezar


def test_camara_inalcanzable_da_camera_error():
    cam = SonyCamera("http://127.0.0.1:9/sony/camera", timeout_s=0.5)
    with pytest.raises(CameraError):
        cam.available_apis()


def test_no_repite_el_cambio_de_modo(sim):
    """startRecMode tarda ~1 s: solo se llama la primera vez."""
    import time

    _, cam = sim
    cam.start_liveview()
    cam.stop_liveview()
    t = time.monotonic()
    cam.start_liveview()
    assert time.monotonic() - t < 0.5
