"""
Logs en JSON por la salida estándar: systemd los guarda en journald.

Una línea por evento, con el nombre del servicio y campos extra, para filtrar con
`journalctl -u anpr-gate -o cat | jq 'select(.event_id=="...")'` y seguir un evento
por todos los servicios.
"""

import json
import logging
import sys
from datetime import UTC, datetime

_RESERVED = set(vars(logging.makeLogRecord({}))) | {"message", "asctime"}


class JsonFormatter(logging.Formatter):
    def __init__(self, service: str) -> None:
        super().__init__()
        self.service = service

    def format(self, record: logging.LogRecord) -> str:
        entry = {
            "ts": datetime.fromtimestamp(record.created, UTC).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "svc": self.service,
            "msg": record.getMessage(),
        }
        # logging.info("...", extra={"event_id": ...}) añade campos sueltos.
        entry.update({k: v for k, v in vars(record).items() if k not in _RESERVED})
        if record.exc_info:
            entry["exc"] = self.formatException(record.exc_info)
        return json.dumps(entry, ensure_ascii=False, default=str)


def setup_logging(service: str, level: int = logging.INFO) -> logging.Logger:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter(service))
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(level)
    # paho y httpx son muy verbosos en INFO.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    return logging.getLogger(service)
