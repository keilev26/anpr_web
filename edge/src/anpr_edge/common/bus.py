"""
Cliente del bus interno (Mosquitto en localhost).

- Reconecta solo, con espera creciente, y se vuelve a suscribir al reconectar.
- Arranca aunque el broker esté caído: el servicio sigue vivo y en estado seguro.
- QoS 1 y sesión limpia: al reconectar NO se reciben mensajes viejos acumulados.
  Un disparo o una orden de hace un minuto no deben ejecutarse; quien espera una
  respuesta usa su propio plazo.
- Last Will retenido en `svc/<servicio>/status`: si el proceso muere, el broker
  publica `offline` por él y `anpr-health` se entera.
- Lo recibido se valida y se deja en `inbox`; la lógica del servicio lo consume
  desde su propio hilo, nunca desde el hilo de red de paho.
"""

import logging
import queue
import threading

import paho.mqtt.client as mqtt
from paho.mqtt.enums import CallbackAPIVersion

from anpr_edge.common.config import MqttConfig, read_secret
from anpr_edge.common.messages import InvalidMessage, Message, ServiceStatus, decode

log = logging.getLogger(__name__)


def status_topic(service: str) -> str:
    return ServiceStatus.TOPIC.format(service=service)


class Bus:
    def __init__(self, service: str, cfg: MqttConfig, client: mqtt.Client | None = None) -> None:
        self.service = service
        self.inbox: queue.Queue[Message] = queue.Queue(maxsize=1000)
        self._subs: dict[str, type[Message]] = {}
        self._connected = threading.Event()
        self._cfg = cfg

        self._client = client or mqtt.Client(
            callback_api_version=CallbackAPIVersion.VERSION2,
            client_id=f"anpr-{service}",
            clean_session=True,
            protocol=mqtt.MQTTv311,
        )
        if cfg.auth:
            password = read_secret("mqtt_password", cfg.password_dir / f"{service}.pw")
            self._client.username_pw_set(service, password)
        self._client.will_set(
            status_topic(service),
            ServiceStatus(service=service, status="offline").encode(),
            qos=1,
            retain=True,
        )
        self._client.reconnect_delay_set(min_delay=1, max_delay=30)
        self._client.on_connect = self._on_connect
        self._client.on_disconnect = self._on_disconnect
        self._client.on_message = self._on_message

    # ---------- API ----------

    @property
    def connected(self) -> bool:
        return self._connected.is_set()

    def subscribe(self, model: type[Message], topic: str | None = None) -> None:
        """`topic` admite comodines MQTT, p. ej. `svc/+/status` con ServiceStatus."""
        topic = topic or model.TOPIC
        self._subs[topic] = model
        if self.connected:
            self._client.subscribe(topic, qos=1)

    def publish(self, msg: Message, retain: bool = False, topic: str | None = None) -> bool:
        """False si no se pudo encolar (p. ej. broker caído): el llamador decide qué hacer."""
        info = self._client.publish(topic or msg.TOPIC, msg.encode(), qos=1, retain=retain)
        return info.rc == mqtt.MQTT_ERR_SUCCESS

    def start(self) -> None:
        # connect_async + loop_start: no falla si el broker aún no está; reintenta en fondo.
        self._client.connect_async(self._cfg.host, self._cfg.port, keepalive=15)
        self._client.loop_start()

    def stop(self) -> None:
        self._client.publish(
            status_topic(self.service),
            ServiceStatus(service=self.service, status="offline").encode(),
            qos=1,
            retain=True,
        )
        self._client.disconnect()
        self._client.loop_stop()

    # ---------- callbacks de paho (hilo de red) ----------

    def _on_connect(self, client, userdata, flags, reason_code, properties) -> None:
        if reason_code.is_failure:
            log.error("Conexión al broker rechazada: %s", reason_code)
            return
        self._connected.set()
        for topic in self._subs:
            client.subscribe(topic, qos=1)
        client.publish(
            status_topic(self.service),
            ServiceStatus(service=self.service, status="online").encode(),
            qos=1,
            retain=True,
        )
        log.info("Conectado al broker")

    def _on_disconnect(self, client, userdata, flags, reason_code, properties) -> None:
        self._connected.clear()
        log.warning("Desconectado del broker: %s", reason_code)

    def _on_message(self, client, userdata, msg: mqtt.MQTTMessage) -> None:
        model = self._subs.get(msg.topic)
        if model is None:
            model = next(
                (m for t, m in self._subs.items() if mqtt.topic_matches_sub(t, msg.topic)), None
            )
        if model is None:
            return
        try:
            parsed = decode(model, msg.payload)
        except InvalidMessage as e:
            log.warning("Mensaje inválido descartado", extra={"topic": msg.topic, "error": str(e)})
            return
        try:
            self.inbox.put_nowait(parsed)
        except queue.Full:
            log.error("Bandeja llena: mensaje descartado", extra={"topic": msg.topic})
