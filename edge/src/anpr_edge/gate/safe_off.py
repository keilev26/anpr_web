"""
Apaga los relés de la pluma. systemd lo ejecuta con `ExecStopPost=` cada vez que
anpr-gate termina, por la razón que sea (incluido `kill -9` o un fallo de memoria).

Sin esto, un proceso muerto puede dejar un relé activado hasta que el servicio
vuelve a arrancar: en la Pi, una línea GPIO liberada puede conservar su último valor.
El final de carrera lo detendría igual por hardware; esta es la segunda capa.
"""

from anpr_edge.common.config import load_config
from anpr_edge.common.gpio import open_gpio
from anpr_edge.common.log import setup_logging
from anpr_edge.gate.service import RELAYS


def main() -> None:
    log = setup_logging("anpr-gate-safe-off")
    cfg = load_config()
    gpio = open_gpio("gate-safe-off", cfg.gpio, cfg.mqtt, outputs=RELAYS)
    gpio.close()  # todas las salidas a 0
    log.warning("Relés apagados tras detenerse anpr-gate")


if __name__ == "__main__":
    main()
