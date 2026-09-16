# mqqt.py
import os, json, socket, time
from flask import Blueprint
from paho.mqtt import client as mqtt

MQTT_ENABLED = os.environ.get("MQTT_ENABLED", "1") not in ("0", "false", "False")
MQTT_HOST = os.environ.get("MQTT_HOST", "10.95.239.139")
MQTT_PORT = int(os.environ.get("MQTT_PORT", "1883"))
MQTT_USER = os.environ.get("MQTT_USER") or None
MQTT_PASS = os.environ.get("MQTT_PASS") or None
TOPIC_TX  = os.environ.get("TOPIC_TO_PI", "app/tx")

bp = Blueprint("mqqt", __name__, url_prefix="/mqqt")

_mqttc = None
_connected = False

def _make_client():
    c = mqtt.Client(client_id=f"flask-{socket.gethostname()}")
    if MQTT_USER:
        c.username_pw_set(MQTT_USER, MQTT_PASS)

    def _on_connect(client, userdata, flags, rc, *extra):
        global _connected
        _connected = (rc == 0)
        print(f"[MQTT] on_connect rc={rc} connected={_connected}")

    def _on_disconnect(client, userdata, rc, *extra):
        global _connected
        _connected = False
        print(f"[MQTT] on_disconnect rc={rc}")

    c.on_connect = _on_connect
    c.on_disconnect = _on_disconnect
    return c

def _start_loop_and_connect_async(c):
    # No lanza excepción; el loop manejará reconexiones
    c.loop_start()
    try:
        c.connect_async(MQTT_HOST, MQTT_PORT, keepalive=60)
        print(f"[MQTT] connect_async to {MQTT_HOST}:{MQTT_PORT}")
    except Exception as e:
        # Nunca tumbar la app por esto
        print(f"[MQTT] connect_async error: {e}")

def _ensure_client():
    global _mqttc
    if not MQTT_ENABLED:
        return None
    if _mqttc is not None:
        return _mqttc
    c = _make_client()
    _start_loop_and_connect_async(c)
    _mqttc = c
    return _mqttc

@bp.record_once
def _setup(_state):
    # Arranca el cliente en background sin bloquear el servidor.
    _ensure_client()

def publish_authorization(plate: str, authorized: bool, topic_override: str = None):
    if not plate:
        return False, "Plate is required."
    if not MQTT_ENABLED:
        return True, {"topic": "(disabled)", "payload": {"plate": plate, "authorization": {"authorized": bool(authorized)}}, "note": "MQTT disabled"}
    client = _ensure_client()
    if client is None:
        return False, "MQTT disabled"

    topic = TOPIC_TX
    payload = {"plate": plate, "authorization":  bool(authorized)}

    # Intento de publish aunque no esté conectado; Paho cola con loop activo
    try:
        r = client.publish(topic, json.dumps(payload), qos=1)
        # No bloquear: opcionalmente podrías chequear estado:
        # r.wait_for_publish(timeout=1.0)
        # print(topic)
        return True, {"topic": topic, "payload": payload}
    except Exception as e:
        print(f"[MQTT] publish error: {e}")
        return False, str(e)
