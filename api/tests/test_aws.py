"""Adaptaciones para desplegar en AWS Lambda detrás de CloudFront."""

import io
import json
import re
import uuid

import certifi
import pytest

from app.core.config import Settings, get_settings
from app.core.ssm import load_parameters_into_env
from app.db.session import engine_options
from app.main import app
from app.routers.detections import MAX_FRAMES_BYTES, get_plate_reader
from app.services.plate_reader import InferenceError, LambdaPlateReader

DEVICE = {"X-Device-Key": "clave-dispositivo-test"}


# ---------- SSM ----------


class FakeSSM:
    def __init__(self, pages):
        self.pages = pages
        self.calls = []

    def get_parameters_by_path(self, **kw):
        self.calls.append(kw)
        idx = int(kw.get("NextToken", 0))
        page = {"Parameters": self.pages[idx]}
        if idx + 1 < len(self.pages):
            page["NextToken"] = str(idx + 1)
        return page


def test_ssm_carga_todas_las_paginas_con_nombres_en_mayusculas(monkeypatch):
    for n in ("DATABASE_URL", "SECRET_KEY"):
        monkeypatch.delenv(n, raising=False)
    ssm = FakeSSM(
        [
            [{"Name": "/anpr/prueba/database_url", "Value": "mysql://x"}],
            [{"Name": "/anpr/prueba/secret_key", "Value": "s3cr3t"}],
        ]
    )
    cargados = load_parameters_into_env("/anpr/prueba", client=ssm)
    assert sorted(cargados) == ["DATABASE_URL", "SECRET_KEY"]
    assert ssm.calls[0]["WithDecryption"] is True
    import os

    assert os.environ["SECRET_KEY"] == "s3cr3t"


def test_ssm_no_sobrescribe_el_entorno_explicito(monkeypatch):
    monkeypatch.setenv("SECRET_KEY", "del-entorno")
    ssm = FakeSSM([[{"Name": "/anpr/prueba/secret_key", "Value": "de-ssm"}]])
    assert load_parameters_into_env("/anpr/prueba/", client=ssm) == []
    import os

    assert os.environ["SECRET_KEY"] == "del-entorno"


# ---------- motor de BD ----------


def _un_certificado():
    with open(certifi.where(), encoding="utf-8") as f:
        pem = f.read()
    return re.search(r"-----BEGIN CERTIFICATE-----.*?-----END CERTIFICATE-----", pem, re.S)[0]


def test_tls_con_ca_propia_para_aiven():
    opts = engine_options(Settings(db_ssl_ca=_un_certificado()))
    ctx = opts["connect_args"]["ssl"]
    assert ctx.check_hostname is True  # verifica también el nombre del host


def test_pool_pequeno_para_mysql():
    opts = engine_options(Settings(database_url="mysql+aiomysql://u:p@h/db"))
    assert opts["pool_size"] == 1
    assert opts["pool_pre_ping"] is True
    assert opts["pool_recycle"] == 300


def test_sqlite_local_sin_tls_ni_parametros_de_pool():
    opts = engine_options(Settings(database_url="sqlite+aiosqlite:///./anpr.db", db_ssl_ca=""))
    assert "connect_args" not in opts and "pool_size" not in opts


# ---------- candado de origen ----------


@pytest.fixture
def con_secreto_de_origen(monkeypatch):
    monkeypatch.setenv("ORIGIN_VERIFY_SECRET", "secreto-cloudfront")
    get_settings.cache_clear()
    yield "secreto-cloudfront"
    monkeypatch.delenv("ORIGIN_VERIFY_SECRET")
    get_settings.cache_clear()


async def test_sin_cabecera_de_cloudfront_da_403(client, con_secreto_de_origen):
    assert (await client.get("/health")).status_code == 403


async def test_cabecera_incorrecta_da_403(client, con_secreto_de_origen):
    r = await client.get("/health", headers={"X-Origin-Verify": "otro"})
    assert r.status_code == 403


async def test_cabecera_correcta_pasa(client, con_secreto_de_origen):
    r = await client.get("/health", headers={"X-Origin-Verify": con_secreto_de_origen})
    assert r.status_code == 200


async def test_sin_secreto_configurado_no_bloquea(client):
    """Desarrollo local: sin CloudFront delante."""
    assert (await client.get("/health")).status_code == 200


# ---------- cliente del Lambda de inferencia ----------


class FakeLambda:
    def __init__(self, status=200, body=None, function_error=None):
        self.status, self.body, self.function_error = status, body or {}, function_error
        self.payloads = []

    def invoke(self, FunctionName, Payload):
        self.payloads.append(json.loads(Payload))
        out = {"statusCode": self.status, "body": json.dumps(self.body)}
        resp = {"Payload": io.BytesIO(json.dumps(out).encode())}
        if self.function_error:
            resp["FunctionError"] = self.function_error
        return resp


async def test_lambda_reader_envia_frames_en_base64_y_lee_la_placa():
    fake = FakeLambda(body={"plate": "CUB-604", "confidence": 0.93})
    plate, conf = await LambdaPlateReader("anpr-infer", client=fake).read(
        [b"\xff\xd8a", b"\xff\xd8b"]
    )
    assert (plate, conf) == ("CUB-604", 0.93)
    assert len(fake.payloads[0]["frames"]) == 2


async def test_lambda_reader_sin_consenso_devuelve_none():
    fake = FakeLambda(body={"plate": None, "reason": "sin_consenso", "votes": {"A": 1, "B": 1}})
    assert await LambdaPlateReader("f", client=fake).read([b"x", b"y"]) == (None, None)


async def test_lambda_reader_error_de_funcion_lanza():
    fake = FakeLambda(function_error="Unhandled")
    with pytest.raises(InferenceError):
        await LambdaPlateReader("f", client=fake).read([b"x"])


async def test_lambda_reader_status_distinto_de_200_lanza():
    fake = FakeLambda(status=400, body={"detail": "frame 0: base64 inválido"})
    with pytest.raises(InferenceError):
        await LambdaPlateReader("f", client=fake).read([b"x"])


# ---------- endpoint de detecciones ----------


def _form():
    return {
        "gate_id": "puerta-2",
        "event_id": str(uuid.uuid4()),
        "captured_at": "2026-09-16T14:30:00Z",
    }


async def test_rafaga_demasiado_grande_da_413(client):
    trozo = MAX_FRAMES_BYTES // 3 + 1
    files = [("frames", (f"f{i}.jpg", b"\xff" * trozo, "image/jpeg")) for i in range(3)]
    r = await client.post("/v1/detections", headers=DEVICE, data=_form(), files=files)
    assert r.status_code == 413


async def test_fallo_de_inferencia_no_abre_la_puerta(client):
    """Contrato: 5xx -> la Pi reintenta y NO abre."""

    class Rompe:
        async def read(self, frames):
            raise InferenceError("caído")

    app.dependency_overrides[get_plate_reader] = lambda: Rompe()
    try:
        files = [("frames", ("f.jpg", b"\xff\xd8", "image/jpeg"))]
        r = await client.post("/v1/detections", headers=DEVICE, data=_form(), files=files)
        assert r.status_code == 503
        assert "command" not in r.text
    finally:
        app.dependency_overrides.pop(get_plate_reader, None)


# ---------- handler de Lambda ----------


class _Ctx:
    aws_request_id = "test"


def _function_url_event(method, path):
    return {
        "version": "2.0",
        "routeKey": "$default",
        "rawPath": path,
        "rawQueryString": "",
        "headers": {"host": "abc.lambda-url.us-east-1.on.aws"},
        "requestContext": {
            "http": {
                "method": method,
                "path": path,
                "protocol": "HTTP/1.1",
                "sourceIp": "1.2.3.4",
                "userAgent": "test",
            },
            "domainName": "abc.lambda-url.us-east-1.on.aws",
            "requestId": "r",
            "stage": "$default",
            "accountId": "anonymous",
            "apiId": "abc",
            "time": "16/Sep/2026:00:00:00 +0000",
            "timeEpoch": 0,
        },
        "isBase64Encoded": False,
    }


def test_handler_quita_el_prefijo_api_de_cloudfront():
    """CloudFront reenvía /api/health; FastAPI debe ver /health."""
    from app.lambda_handler import handler

    r = handler(_function_url_event("GET", "/api/health"), _Ctx())
    assert r["statusCode"] == 200
    assert json.loads(r["body"])["status"] in {"ok", "degraded"}


def test_handler_ruta_inexistente_devuelve_404_json_no_el_spa():
    from app.lambda_handler import handler

    r = handler(_function_url_event("GET", "/api/no-existe"), _Ctx())
    assert r["statusCode"] == 404


def test_documentacion_oculta_en_produccion():
    import importlib

    import app.main as main_module

    try:
        get_settings.cache_clear()
        import os

        os.environ["DEV_MODE"] = "false"
        prod = importlib.reload(main_module).app
        assert prod.docs_url is None and prod.redoc_url is None and prod.openapi_url is None
    finally:
        os.environ["DEV_MODE"] = "true"
        get_settings.cache_clear()
        importlib.reload(main_module)
