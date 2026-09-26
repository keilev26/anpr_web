"""
Acceso a los pines (contrato C, `contracts/gpio-map.md`), con backends intercambiables:

- `gpiozero`: la Pi real.
- `sim`: la laptop. Las entradas llegan por MQTT (`sim/gpio/in/<SEÑAL>`) desde el
  simulador de la pluma, y las salidas se publican en `sim/gpio/out/<SEÑAL>`.
- `memory`: tests.

Los servicios trabajan con **niveles crudos** (1 = alto) y con las funciones
semánticas de abajo, que traducen la lógica NC/pull-up del contrato. Todas las
entradas tienen pull-up: un cable cortado o un sensor desconectado se lee 1, y 1 es
siempre el valor **inseguro** (en tope, fotocelda interrumpida, emergencia, modo manual).
"""

import logging
import threading
from abc import ABC, abstractmethod
from collections.abc import Iterable

from anpr_edge.common.config import GpioConfig, MqttConfig

log = logging.getLogger(__name__)

INPUTS = frozenset(
    {
        "LIMIT_OPEN",
        "LIMIT_CLOSED",
        "PHOTOCELL_OK",
        "ESTOP_OK",
        "PRESENCE",
        "MANUAL_BTN",
        "MODE_AUTO",
    }
)
OUTPUTS = frozenset({"RELAY_FWD", "RELAY_REV", "LED_STATUS"})

# Nivel que se asume para una entrada sin lectura: el de un circuito abierto con pull-up.
OPEN_CIRCUIT = 1


class Gpio(ABC):
    """Cada servicio reclama solo las señales que usa; pedir otra es un error."""

    def __init__(self, inputs: Iterable[str] = (), outputs: Iterable[str] = ()) -> None:
        self.inputs = frozenset(inputs)
        self.outputs = frozenset(outputs)
        if unknown := (self.inputs - INPUTS) | (self.outputs - OUTPUTS):
            raise ValueError(f"Señales desconocidas: {sorted(unknown)}")

    @abstractmethod
    def level(self, name: str) -> int: ...

    @abstractmethod
    def _write(self, name: str, on: bool) -> None: ...

    def set(self, name: str, on: bool) -> None:
        if name not in self.outputs:
            raise ValueError(f"{name} no es una salida de este servicio")
        self._write(name, on)

    def close(self) -> None:
        """Todas las salidas apagadas: relés abiertos."""
        for name in self.outputs:
            self._write(name, False)

    def _check_input(self, name: str) -> None:
        if name not in self.inputs:
            raise ValueError(f"{name} no es una entrada de este servicio")


# ---------- lectura semántica ----------


def at_open_limit(g: Gpio) -> bool:
    return g.level("LIMIT_OPEN") == 1  # NC: abierto = en tope


def at_closed_limit(g: Gpio) -> bool:
    return g.level("LIMIT_CLOSED") == 1


def photocell_clear(g: Gpio) -> bool:
    return g.level("PHOTOCELL_OK") == 0  # NC: bajo = vía libre


def estop_ok(g: Gpio) -> bool:
    return g.level("ESTOP_OK") == 0  # NC: bajo = sin emergencia


def presence(g: Gpio) -> bool:
    return g.level("PRESENCE") == 0  # el sensor cierra a masa al detectar


def manual_pressed(g: Gpio) -> bool:
    return g.level("MANUAL_BTN") == 0


def auto_mode(g: Gpio) -> bool:
    return g.level("MODE_AUTO") == 0  # el selector cierra a masa en AUTO; cortado = manual


# ---------- backends ----------


class MemoryGpio(Gpio):
    def __init__(self, inputs: Iterable[str] = (), outputs: Iterable[str] = ()) -> None:
        super().__init__(inputs, outputs)
        self.levels = {n: OPEN_CIRCUIT for n in self.inputs}
        self.out = {n: False for n in self.outputs}

    def level(self, name: str) -> int:
        self._check_input(name)
        return self.levels[name]

    def _write(self, name: str, on: bool) -> None:
        self.out[name] = on


class SimGpio(Gpio):
    """Solo para la laptop. En la Pi, la ACL de Mosquitto deniega `sim/#`."""

    def __init__(self, service: str, mqtt_cfg: MqttConfig, inputs=(), outputs=()) -> None:
        import paho.mqtt.client as mqtt
        from paho.mqtt.enums import CallbackAPIVersion

        super().__init__(inputs, outputs)
        self._levels = {n: OPEN_CIRCUIT for n in self.inputs}
        self._lock = threading.Lock()
        self._client = mqtt.Client(
            callback_api_version=CallbackAPIVersion.VERSION2, client_id=f"anpr-{service}-simgpio"
        )
        self._client.on_connect = self._on_connect
        self._client.on_message = self._on_message
        self._client.connect_async(mqtt_cfg.host, mqtt_cfg.port, keepalive=15)
        self._client.loop_start()

    def _on_connect(self, client, userdata, flags, reason_code, properties) -> None:
        for name in self.inputs:
            client.subscribe(f"sim/gpio/in/{name}", qos=1)

    def _on_message(self, client, userdata, msg) -> None:
        name = msg.topic.rsplit("/", 1)[-1]
        if name in self._levels and msg.payload in (b"0", b"1"):
            with self._lock:
                self._levels[name] = int(msg.payload)

    def level(self, name: str) -> int:
        self._check_input(name)
        with self._lock:
            return self._levels[name]

    def _write(self, name: str, on: bool) -> None:
        self._client.publish(f"sim/gpio/out/{name}", b"1" if on else b"0", qos=1, retain=True)

    def close(self) -> None:
        super().close()
        self._client.disconnect()
        self._client.loop_stop()


class GpiozeroGpio(Gpio):
    """La Pi. Pines BCM desde la configuración (pendientes de F6)."""

    def __init__(self, pins: dict[str, int], inputs=(), outputs=()) -> None:
        from gpiozero import DigitalInputDevice, DigitalOutputDevice

        super().__init__(inputs, outputs)
        if missing := (self.inputs | self.outputs) - pins.keys():
            raise ValueError(f"Faltan números de pin en la configuración: {sorted(missing)}")
        self._in = {n: DigitalInputDevice(pins[n], pull_up=True) for n in self.inputs}
        # initial_value=False: al arrancar (o reiniciar tras un fallo) los relés quedan abiertos.
        self._out = {
            n: DigitalOutputDevice(pins[n], active_high=True, initial_value=False)
            for n in self.outputs
        }

    def level(self, name: str) -> int:
        self._check_input(name)
        return int(self._in[name].pin.state)  # nivel crudo, sin la inversión de gpiozero

    def _write(self, name: str, on: bool) -> None:
        self._out[name].value = on

    def close(self) -> None:
        super().close()
        for dev in (*self._in.values(), *self._out.values()):
            dev.close()


def open_gpio(service: str, cfg: GpioConfig, mqtt_cfg: MqttConfig, inputs=(), outputs=()) -> Gpio:
    if cfg.backend == "gpiozero":
        return GpiozeroGpio(cfg.pins, inputs, outputs)
    if cfg.backend == "sim":
        return SimGpio(service, mqtt_cfg, inputs, outputs)
    return MemoryGpio(inputs, outputs)
