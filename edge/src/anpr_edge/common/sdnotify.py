"""
Protocolo sd_notify de systemd, sin dependencias.

Con `WatchdogSec=` en la unidad, el servicio debe enviar `WATCHDOG=1` más a menudo
que ese plazo; si deja de hacerlo (bucle colgado, deadlock), systemd lo mata y lo
reinicia. Fuera de systemd (laptop, tests) no hay NOTIFY_SOCKET y no hace nada.
"""

import os
import socket


def notify(state: str) -> bool:
    addr = os.environ.get("NOTIFY_SOCKET")
    if not addr:
        return False
    if addr.startswith("@"):  # socket abstracto de Linux
        addr = "\0" + addr[1:]
    with socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM) as s:
        s.connect(addr)
        s.sendall(state.encode())
    return True


def ready() -> bool:
    return notify("READY=1")


def watchdog() -> bool:
    return notify("WATCHDOG=1")


def stopping() -> bool:
    return notify("STOPPING=1")
