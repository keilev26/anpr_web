import json
import logging
import uuid
from datetime import UTC, datetime, timedelta

import pytest

from anpr_edge.common.bus import Bus
from anpr_edge.common.config import EdgeConfig, MqttConfig, load_config, read_secret
from anpr_edge.common.gpio import (
    MemoryGpio,
    at_closed_limit,
    at_open_limit,
    auto_mode,
    estop_ok,
    photocell_clear,
    presence,
)
from anpr_edge.common.log import JsonFormatter
from anpr_edge.common.messages import (
    Command,
    InvalidMessage,
    ServiceStatus,
    Trigger,
    decode,
)
from anpr_edge.common.service import Service

NOW = datetime(2026, 9, 26, 12, 0, tzinfo=UTC)
ID = str(uuid.uuid4()).encode()


# ---------- configuración ----------


def test_config_valida(tmp_path):
    p = tmp_path / "edge.toml"
    p.write_text('[capture]\nframes = 4\n[gpio]\nbackend = "sim"\n')
    cfg = load_config(p)
    assert cfg.capture.frames == 4 and cfg.gpio.backend == "sim"


def test_config_con_clave_mal_escrita_falla(tmp_path):
    p = tmp_path / "edge.toml"
    p.write_text("[capture]\nframez = 4\n")
    with pytest.raises(ValueError):
        load_config(p)


def test_config_menos_de_tres_frames_falla(tmp_path):
    """El consenso de la nube necesita margen: el contrato pide al menos 3."""
    p = tmp_path / "edge.toml"
    p.write_text("[capture]\nframes = 2\n")
    with pytest.raises(ValueError):
        load_config(p)


def test_config_sin_archivo_falla(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_config(tmp_path / "no-existe.toml")


def test_config_de_ejemplo_es_valida():
    from pathlib import Path

    for name in ("dev.toml",):
        load_config(Path(__file__).parents[1] / "config" / name)


def test_secreto_desde_credentials_directory(tmp_path, monkeypatch):
    (tmp_path / "device_api_key").write_text("clave\n")
    monkeypatch.setenv("CREDENTIALS_DIRECTORY", str(tmp_path))
    assert read_secret("device_api_key", tmp_path / "otro") == "clave"


def test_secreto_vacio_falla(tmp_path, monkeypatch):
    monkeypatch.delenv("CREDENTIALS_DIRECTORY", raising=False)
    (tmp_path / "k").write_text("  \n")
    with pytest.raises(ValueError):
        read_secret("k", tmp_path / "k")


# ---------- mensajes ----------


def test_mensaje_ida_y_vuelta():
    t = Trigger(event_id=uuid.uuid4(), source="loop", ts=NOW)
    assert decode(Trigger, t.encode()) == t


@pytest.mark.parametrize(
    "payload",
    [
        b"no es json",
        b'{"event_id": "x", "source": "loop", "ts": "2026-09-26T12:00:00Z"}',
        b'{"event_id": "%s", "source": "otro", "ts": "2026-09-26T12:00:00Z"}' % ID,
        # sin zona horaria: ambiguo, se rechaza
        b'{"event_id": "%s", "source": "loop", "ts": "2026-09-26T12:00:00"}' % ID,
        # campo desconocido
        b'{"event_id": "%s", "source": "loop", "ts": "2026-09-26T12:00:00Z", "x": 1}' % ID,
    ],
)
def test_mensajes_invalidos_se_rechazan(payload):
    with pytest.raises(InvalidMessage):
        decode(Trigger, payload)


def test_orden_solo_puede_ser_abrir():
    bad = json.dumps(
        {
            "event_id": str(uuid.uuid4()),
            "action": "close",
            "ttl_s": 10,
            "issued_at": NOW.isoformat(),
        }
    ).encode()
    with pytest.raises(InvalidMessage):
        decode(Command, bad)


def test_orden_vencida():
    c = Command(event_id=uuid.uuid4(), action="open", ttl_s=10, issued_at=NOW)
    assert not c.expired(NOW + timedelta(seconds=9))
    assert c.expired(NOW + timedelta(seconds=11))


# ---------- GPIO ----------


def test_sin_lectura_todo_es_inseguro():
    """Pull-up + NC: un cable cortado se lee como la situación peligrosa."""
    g = MemoryGpio(
        inputs=["LIMIT_OPEN", "LIMIT_CLOSED", "PHOTOCELL_OK", "ESTOP_OK", "PRESENCE", "MODE_AUTO"]
    )
    assert at_open_limit(g) and at_closed_limit(g)  # ambos a la vez = falla de cableado
    assert not photocell_clear(g)
    assert not estop_ok(g)
    assert not presence(g)
    assert not auto_mode(g)


def test_servicio_no_puede_usar_senales_ajenas():
    g = MemoryGpio(inputs=["PRESENCE"])
    with pytest.raises(ValueError):
        g.level("LIMIT_OPEN")
    with pytest.raises(ValueError):
        g.set("RELAY_FWD", True)


def test_senal_desconocida_falla():
    with pytest.raises(ValueError):
        MemoryGpio(outputs=["RELAY_TURBO"])


def test_close_apaga_todas_las_salidas():
    g = MemoryGpio(outputs=["RELAY_FWD", "RELAY_REV"])
    g.set("RELAY_FWD", True)
    g.close()
    assert g.out == {"RELAY_FWD": False, "RELAY_REV": False}


# ---------- bus y servicio (sin broker) ----------


class FakeMqtt:
    def __init__(self):
        self.published, self.subscribed, self.will = [], [], None
        self.on_connect = self.on_disconnect = self.on_message = None

    def username_pw_set(self, *a): ...
    def will_set(self, topic, payload, qos, retain):
        self.will = (topic, payload, retain)

    def reconnect_delay_set(self, **kw): ...
    def subscribe(self, topic, qos):
        self.subscribed.append(topic)

    def publish(self, topic, payload, qos, retain=False):
        self.published.append((topic, payload, retain))

        class Info:
            rc = 0

        return Info()


class Msg:
    def __init__(self, topic, payload):
        self.topic, self.payload = topic, payload


def make_bus():
    fake = FakeMqtt()
    return Bus("prueba", MqttConfig(), client=fake), fake


def test_last_will_retenido_offline():
    _, fake = make_bus()
    topic, payload, retain = fake.will
    assert topic == "svc/prueba/status" and retain
    assert decode(ServiceStatus, payload).status == "offline"


def test_al_conectar_se_suscribe_y_anuncia_online():
    bus, fake = make_bus()
    bus.subscribe(Trigger)

    class RC:
        is_failure = False

    fake.on_connect(fake, None, None, RC(), None)
    assert "gate/trigger" in fake.subscribed
    assert any(t == "svc/prueba/status" and b'"online"' in p for t, p, _ in fake.published)


def test_mensaje_invalido_no_llega_a_la_bandeja(caplog):
    bus, fake = make_bus()
    bus.subscribe(Trigger)
    fake.on_message(fake, None, Msg("gate/trigger", b"{}"))
    assert bus.inbox.empty()
    ok = Trigger(event_id=uuid.uuid4(), source="loop", ts=NOW)
    fake.on_message(fake, None, Msg("gate/trigger", ok.encode()))
    assert bus.inbox.get_nowait() == ok


def test_excepcion_en_la_logica_no_tumba_el_servicio():
    bus, fake = make_bus()

    class Roto(Service):
        def __init__(self, *a):
            super().__init__(*a)
            self.ticks = 0

        def on_message(self, msg):
            raise RuntimeError("fallo")

        def on_tick(self, now):
            self.ticks += 1

    svc = Roto(bus, logging.getLogger("t"))
    bus.inbox.put(Trigger(event_id=uuid.uuid4(), source="loop", ts=NOW))
    svc.step()
    assert svc.ticks == 1


def test_log_json_con_campos_extra():
    rec = logging.makeLogRecord({"msg": "hola", "levelname": "INFO", "event_id": "abc"})
    entry = json.loads(JsonFormatter("anpr-x").format(rec))
    assert entry["svc"] == "anpr-x" and entry["event_id"] == "abc" and entry["msg"] == "hola"


def test_config_por_defecto_apunta_a_la_nube():
    assert EdgeConfig().uplink.api_url.startswith("https://")
