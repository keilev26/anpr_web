import uuid

import pytest

from app.main import app
from app.routers.detections import get_plate_reader
from app.services.plate_reader import StubPlateReader
from tests.conftest import TEST_PASSWORD

DEVICE = {"X-Device-Key": "clave-dispositivo-test"}


def _frames(n: int = 1):
    return [("frames", (f"f{i}.jpg", b"\xff\xd8\xff\xd9", "image/jpeg")) for i in range(n)]


def _form(plate_uuid: str | None = None):
    return {
        "gate_id": "puerta-2",
        "event_id": plate_uuid or str(uuid.uuid4()),
        "captured_at": "2026-09-15T14:30:00Z",
    }


@pytest.fixture
def reader_devuelve():
    def _set(plate, confidence=0.95):
        app.dependency_overrides[get_plate_reader] = lambda: StubPlateReader(plate, confidence)
    yield _set
    app.dependency_overrides.pop(get_plate_reader, None)


async def test_sin_clave_de_dispositivo_da_401(client):
    r = await client.post("/v1/detections", data=_form(), files=_frames())
    assert r.status_code == 401


async def test_placa_autorizada_manda_abrir(client, reader_devuelve):
    reader_devuelve("CUB-604")
    r = await client.post("/v1/detections", headers=DEVICE, data=_form(), files=_frames(3))
    assert r.status_code == 200
    body = r.json()
    assert body["authorized"] is True
    assert body["command"]["action"] == "open"
    assert body["command"]["ttl_s"] == 10
    assert body["user"]["email"] == "admin@uni.pe"


async def test_placa_desconocida_deniega(client, reader_devuelve):
    reader_devuelve("ZZZ-999")
    r = await client.post("/v1/detections", headers=DEVICE, data=_form(), files=_frames())
    body = r.json()
    assert body["authorized"] is False
    assert body["command"]["action"] == "deny"
    assert body["user"] is None


async def test_placa_de_usuario_inactivo_deniega(client, reader_devuelve):
    """Dar de baja a alguien debe bastar; el legacy obligaba a borrar sus placas."""
    reader_devuelve("XYZ-789")
    r = await client.post("/v1/detections", headers=DEVICE, data=_form(), files=_frames())
    assert r.json()["authorized"] is False


async def test_normaliza_lo_que_lee_el_ocr(client, reader_devuelve):
    """El OCR omite el guion: 'cub604' debe seguir autorizando."""
    reader_devuelve("cub604")
    r = await client.post("/v1/detections", headers=DEVICE, data=_form(), files=_frames())
    assert r.json()["plate"] == "CUB-604"
    assert r.json()["authorized"] is True


async def test_es_idempotente(client, reader_devuelve):
    """Un reenvío por timeout no debe registrar ni abrir dos veces."""
    reader_devuelve("CUB-604")
    same = str(uuid.uuid4())
    r1 = await client.post("/v1/detections", headers=DEVICE, data=_form(same), files=_frames())
    r2 = await client.post("/v1/detections", headers=DEVICE, data=_form(same), files=_frames())
    assert r1.status_code == r2.status_code == 200
    assert r1.json()["authorized"] == r2.json()["authorized"]

    admin = await client.post(
        "/auth/login", json={"email": "admin@uni.pe", "password": TEST_PASSWORD}
    )
    h = {"Authorization": f"Bearer {admin.json()['access_token']}"}
    eventos = (await client.get("/events", headers=h)).json()["items"]
    assert len(eventos) == 1, "el reenvío creó un evento duplicado"


async def test_sin_placa_legible_da_422(client, reader_devuelve):
    reader_devuelve(None)
    r = await client.post("/v1/detections", headers=DEVICE, data=_form(), files=_frames())
    assert r.status_code == 422


async def test_rechaza_mas_de_diez_frames(client, reader_devuelve):
    reader_devuelve("CUB-604")
    r = await client.post("/v1/detections", headers=DEVICE, data=_form(), files=_frames(11))
    assert r.status_code == 400


async def test_event_id_debe_ser_uuid(client, reader_devuelve):
    reader_devuelve("CUB-604")
    form = {**_form(), "event_id": "no-es-un-uuid"}
    r = await client.post("/v1/detections", headers=DEVICE, data=form, files=_frames())
    assert r.status_code == 400


async def test_eventos_guardan_confianza_y_latencia(client, admin_headers, reader_devuelve):
    """El legacy descartaba ambas y el dashboard las forzaba a 0 y null."""
    reader_devuelve("CUB-604", 0.937)
    await client.post("/v1/detections", headers=DEVICE, data=_form(), files=_frames())

    ev = (await client.get("/events", headers=admin_headers)).json()["items"][0]
    assert ev["confidence"] == 0.937
    assert ev["latency_ms"] is not None
    assert ev["gate_opened"] is True


async def test_filtro_de_eventos_por_autorizacion(client, admin_headers, reader_devuelve):
    reader_devuelve("CUB-604")
    await client.post("/v1/detections", headers=DEVICE, data=_form(), files=_frames())
    reader_devuelve("ZZZ-999")
    await client.post("/v1/detections", headers=DEVICE, data=_form(), files=_frames())

    solo_ok = (await client.get(
        "/events", headers=admin_headers, params={"authorized": "true"}
    )).json()["items"]
    assert len(solo_ok) == 1 and solo_ok[0]["plate"] == "CUB-604"


async def test_health_no_requiere_auth(client):
    r = await client.get("/health")
    assert r.status_code == 200 and r.json()["db"] is True


async def test_fechas_se_serializan_en_utc_con_z(client, admin_headers, reader_devuelve):
    """
    Sin la Z, `new Date(iso)` en el navegador interpreta la fecha como hora
    LOCAL y el dashboard mostraría las detecciones desplazadas.
    """
    reader_devuelve("CUB-604")
    await client.post("/v1/detections", headers=DEVICE, data=_form(), files=_frames())

    ev = (await client.get("/events", headers=admin_headers)).json()["items"][0]
    assert ev["detected_at"].endswith("Z"), ev["detected_at"]

    usuarios = (await client.get("/users", headers=admin_headers)).json()["items"]
    assert usuarios[0]["created_at"].endswith("Z"), usuarios[0]["created_at"]
