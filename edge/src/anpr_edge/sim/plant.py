"""
Simulador de la pluma y del carril, para la laptop.

Lee los relés que publican los servicios en `sim/gpio/out/...` y publica las
entradas en `sim/gpio/in/...`, como si fueran los sensores reales. Reproduce también
el CABLEADO de seguridad: aunque la Pi mande un relé, el brazo no sube pasado el
tope, no baja con la fotocelda interrumpida y no se mueve con la emergencia pulsada.

    anpr-sim-plant                 # el simulador (dejarlo corriendo)
    anpr-sim-plant car             # llega un auto
    anpr-sim-plant estop on|off    # parada de emergencia
    anpr-sim-plant mode manual|auto
    anpr-sim-plant block|unblock   # algo bajo la pluma
    anpr-sim-plant press           # botón manual

Estado en `sim/plant/state` (retenido): ángulo, autos que pasaron y los errores que
el hardware real habría sufrido (dos relés a la vez, empujar contra el tope).
"""

import argparse
import json
import logging
import time

import paho.mqtt.client as mqtt
from paho.mqtt.enums import CallbackAPIVersion

log = logging.getLogger("anpr-sim-plant")
CMD_TOPIC = "sim/cmd"
STATE_TOPIC = "sim/plant/state"


class Plant:
    def __init__(self, travel_s: float = 6.0, open_relay: str = "RELAY_FWD") -> None:
        self.travel_s = travel_s
        self.open_relay = open_relay
        self.close_relay = "RELAY_REV" if open_relay == "RELAY_FWD" else "RELAY_FWD"
        self.angle = 0.0  # 0 = cerrada (horizontal), 90 = abierta
        self.relays = {"RELAY_FWD": False, "RELAY_REV": False}
        self.estop = False
        self.auto = True
        self.blocked = False  # algo bajo la pluma, además del auto
        self.button_until = 0.0
        self.car: dict | None = None
        self.cars_passed = 0
        self.cars_gave_up = 0
        self.shorts = 0  # FWD y REV a la vez
        self.pushing_s = 0.0  # tiempo con el motor mandado contra el tope

    # ---------- física y cableado ----------

    def step(self, dt: float, now: float) -> None:
        opening = self.relays[self.open_relay] and self.auto
        closing = self.relays[self.close_relay] and self.auto
        if opening and closing:
            self.shorts += 1
            log.error("CORTO: los dos relés activos a la vez")
            opening = closing = False
        speed = 90.0 / self.travel_s * dt
        if not self.estop:
            if opening:
                if self.angle >= 90:
                    self.pushing_s += dt  # en la realidad lo corta el final de carrera
                self.angle = min(90.0, self.angle + speed)
            elif closing and not self.photocell_blocked:
                if self.angle <= 0:
                    self.pushing_s += dt
                self.angle = max(0.0, self.angle - speed)
        self._car(now)

    @property
    def photocell_blocked(self) -> bool:
        return self.blocked or (self.car is not None and self.car["phase"] == "crossing")

    def inputs(self, now: float) -> dict[str, int]:
        """Niveles crudos, con la lógica NC/pull-up del contrato C."""
        return {
            "LIMIT_OPEN": int(self.angle >= 90),
            "LIMIT_CLOSED": int(self.angle <= 0),
            "PHOTOCELL_OK": int(self.photocell_blocked),
            "ESTOP_OK": int(self.estop),
            "MODE_AUTO": int(not self.auto),
            "PRESENCE": int(not (self.car and self.car["phase"] == "waiting")),
            "MANUAL_BTN": int(now >= self.button_until),
        }

    # ---------- el auto ----------

    def car_arrives(self, now: float, patience_s: float = 25.0) -> None:
        if self.car is None:
            self.car = {"phase": "waiting", "since": now, "patience": patience_s}
            log.info("Llega un auto")

    def _car(self, now: float) -> None:
        c = self.car
        if c is None:
            return
        if c["phase"] == "waiting":
            if self.angle >= 90:
                c["phase"], c["since"] = "starting", now
            elif now - c["since"] > c["patience"]:
                log.info("El auto se rinde y se va")
                self.cars_gave_up += 1
                self.car = None
        elif c["phase"] == "starting" and now - c["since"] > 0.8:
            c["phase"], c["since"] = "crossing", now
        elif c["phase"] == "crossing" and now - c["since"] > 1.5:
            if self.angle < 60:
                log.error("CHOQUE: la pluma bajó sobre el auto")
            self.cars_passed += 1
            log.info("El auto pasó")
            self.car = None

    def snapshot(self) -> dict:
        return {
            "angle": round(self.angle, 1),
            "relays": self.relays,
            "estop": self.estop,
            "auto": self.auto,
            "blocked": self.blocked,
            "car": self.car["phase"] if self.car else None,
            "cars_passed": self.cars_passed,
            "cars_gave_up": self.cars_gave_up,
            "shorts": self.shorts,
            "pushing_s": round(self.pushing_s, 2),
        }

    def command(self, cmd: str, arg: str | None, now: float) -> None:
        if cmd == "car":
            self.car_arrives(now)
        elif cmd == "estop":
            self.estop = arg == "on"
        elif cmd == "mode":
            self.auto = arg == "auto"
        elif cmd == "block":
            self.blocked = True
        elif cmd == "unblock":
            self.blocked = False
        elif cmd == "press":
            self.button_until = now + 0.3
        log.info("Comando: %s %s", cmd, arg or "")


def run_sim(host: str, port: int, travel_s: float, open_relay: str) -> None:
    plant = Plant(travel_s, open_relay)
    client = mqtt.Client(
        callback_api_version=CallbackAPIVersion.VERSION2, client_id="anpr-sim-plant"
    )

    def on_connect(c, userdata, flags, rc, props):
        c.subscribe("sim/gpio/out/+", qos=1)
        c.subscribe(CMD_TOPIC, qos=1)

    def on_message(c, userdata, msg):
        if msg.topic == CMD_TOPIC:
            body = json.loads(msg.payload)
            plant.command(body["cmd"], body.get("arg"), time.monotonic())
            return
        name = msg.topic.rsplit("/", 1)[-1]
        if name in plant.relays:
            plant.relays[name] = msg.payload == b"1"

    client.on_connect, client.on_message = on_connect, on_message
    client.connect_async(host, port)
    client.loop_start()
    last_inputs: dict = {}
    last_state = 0.0
    prev = time.monotonic()
    try:
        while True:
            time.sleep(0.02)
            now = time.monotonic()
            plant.step(now - prev, now)
            prev = now
            for name, level in plant.inputs(now).items():
                if last_inputs.get(name) != level:
                    client.publish(f"sim/gpio/in/{name}", str(level), qos=1, retain=True)
                    last_inputs[name] = level
            if now - last_state > 0.25:
                client.publish(STATE_TOPIC, json.dumps(plant.snapshot()), qos=0, retain=True)
                last_state = now
    except KeyboardInterrupt:
        pass
    finally:
        client.loop_stop()


def send_command(host: str, port: int, cmd: str, arg: str | None) -> None:
    import paho.mqtt.publish as publish

    publish.single(CMD_TOPIC, json.dumps({"cmd": cmd, "arg": arg}), qos=1, hostname=host, port=port)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    ap.add_argument("cmd", nargs="?", choices=["car", "estop", "mode", "block", "unblock", "press"])
    ap.add_argument("arg", nargs="?")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=1883)
    ap.add_argument("--travel-s", type=float, default=6.0)
    ap.add_argument("--open-relay", default="RELAY_FWD")
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [planta] %(message)s")
    if args.cmd:
        send_command(args.host, args.port, args.cmd, args.arg)
    else:
        run_sim(args.host, args.port, args.travel_s, args.open_relay)


if __name__ == "__main__":
    main()
