"""Arranque común: configuración, logs, bus y bucle. Cada servicio solo aporta su clase."""

import argparse
import logging
from collections.abc import Callable
from pathlib import Path

from anpr_edge.common.bus import Bus
from anpr_edge.common.config import EdgeConfig, load_config
from anpr_edge.common.log import setup_logging
from anpr_edge.common.service import Service


def run(name: str, build: Callable[[EdgeConfig, Bus, logging.Logger], Service]) -> None:
    ap = argparse.ArgumentParser(prog=f"anpr-{name}")
    ap.add_argument(
        "--config", type=Path, help="Por defecto $ANPR_EDGE_CONFIG o /etc/anpr/edge.toml"
    )
    args = ap.parse_args()
    log = setup_logging(f"anpr-{name}")
    try:
        cfg = load_config(args.config)
    except Exception:
        # Sin configuración válida no se arranca: systemd lo reintenta y health lo ve offline.
        log.exception("Configuración inválida")
        raise SystemExit(2) from None
    service = build(cfg, Bus(name, cfg.mqtt), log)
    log.info("Arrancando")
    service.run()
    log.info("Detenido")
