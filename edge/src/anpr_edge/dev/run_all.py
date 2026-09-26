"""
Todo el edge en la laptop, con simuladores. Hace de systemd: arranca cada servicio
como proceso independiente y lo reinicia si muere.

    anpr-dev                           # Mosquitto en Docker + simuladores + 5 servicios
    anpr-dev --broker local            # Mosquitto ya instalado en la laptop
    anpr-dev --camera real             # la Sony real (laptop en su Wi-Fi)
    anpr-dev --cloud config            # la API de config/dev.toml en vez de la nube falsa

En otra terminal:
    anpr-sim-plant car                 # llega un auto
    mosquitto_sub -t 'gate/#' -t 'health/#' -t 'sim/plant/state' -v
"""

import argparse
import os
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path

SERVICES = ["gate", "trigger", "capture", "uplink", "health"]
EDGE = Path(__file__).resolve().parents[3]
MOSQUITTO_IMAGE = "eclipse-mosquitto:2"
COLORS = ["31", "32", "33", "34", "35", "36", "91", "92", "93", "94"]


class Child:
    def __init__(
        self,
        name: str,
        cmd: list[str],
        env: dict,
        color: str,
        restart: bool,
        stop_post: list[str] | None = None,
    ) -> None:
        self.name, self.cmd, self.env, self.color, self.restart = name, cmd, env, color, restart
        self.stop_post = stop_post  # como ExecStopPost= de systemd: corre al terminar
        self.proc: subprocess.Popen | None = None
        self.restarts = 0

    def start(self) -> None:
        self.proc = subprocess.Popen(
            self.cmd,
            env=self.env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        threading.Thread(target=self._pump, daemon=True).start()

    def _pump(self) -> None:
        assert self.proc and self.proc.stdout
        for line in self.proc.stdout:
            sys.stdout.write(f"\033[{self.color}m{self.name:>8}\033[0m | {line}")
            sys.stdout.flush()

    def stop(self) -> None:
        if self.proc and self.proc.poll() is None:
            self.proc.send_signal(signal.SIGTERM)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    ap.add_argument("--config", type=Path, default=EDGE / "config" / "dev.toml")
    ap.add_argument("--broker", choices=["docker", "local"], default="docker")
    ap.add_argument("--camera", choices=["sim", "real"], default="sim")
    ap.add_argument("--cloud", choices=["sim", "config"], default="sim")
    ap.add_argument("--cloud-mode", default="open")
    args = ap.parse_args()

    env = os.environ | {
        "ANPR_EDGE_CONFIG": str(args.config),
        "PYTHONPATH": "",
        "PYTHONUNBUFFERED": "1",
    }
    py = sys.executable
    colors = iter(COLORS)
    children: list[Child] = []

    if args.broker == "docker":
        subprocess.run(["docker", "rm", "-f", "anpr-mosquitto"], capture_output=True)
        children.append(
            Child(
                "mqtt",
                [
                    "docker",
                    "run",
                    "--rm",
                    "--name",
                    "anpr-mosquitto",
                    "-p",
                    "127.0.0.1:1883:1883",
                    MOSQUITTO_IMAGE,
                    "mosquitto",
                    "-c",
                    "/mosquitto-no-auth.conf",
                ],
                env,
                next(colors),
                restart=False,
            )
        )
    if args.camera == "sim":
        children.append(
            Child(
                "camara",
                [
                    py,
                    "-m",
                    "anpr_edge.sim.camera",
                    "--frames-dir",
                    str(EDGE / "tests" / "fixtures" / "frames"),
                ],
                env,
                next(colors),
                restart=True,
            )
        )
    if args.cloud == "sim":
        children.append(
            Child(
                "nube",
                [py, "-m", "anpr_edge.sim.cloud", "--mode", args.cloud_mode],
                env,
                next(colors),
                restart=True,
            )
        )
    children.append(
        Child("planta", [py, "-m", "anpr_edge.sim.plant"], env, next(colors), restart=True)
    )
    for name in SERVICES:
        post = [py, "-m", "anpr_edge.gate.safe_off"] if name == "gate" else None
        children.append(
            Child(
                name,
                [py, "-m", f"anpr_edge.{name}"],
                env,
                next(colors),
                restart=True,
                stop_post=post,
            )
        )

    for child in children:
        child.start()
        if child.name == "mqtt":
            time.sleep(1.5)  # que el broker esté listo antes que el resto

    stopping = False

    def stop(*_):
        nonlocal stopping
        stopping = True

    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGTERM, stop)
    try:
        while not stopping:
            time.sleep(0.5)
            for c in children:
                if c.proc and c.proc.poll() is not None and c.restart and not stopping:
                    c.restarts += 1
                    print(
                        f"*** {c.name} terminó (código {c.proc.returncode}); "
                        f"reinicio n.º {c.restarts}",
                        flush=True,
                    )
                    if c.stop_post:
                        subprocess.run(c.stop_post, env=c.env, timeout=10)
                    time.sleep(1)  # como RestartSec=1 de systemd
                    c.start()
    finally:
        for c in reversed(children):
            c.stop()
        for c in children:
            if c.proc:
                try:
                    c.proc.wait(timeout=8)
                except subprocess.TimeoutExpired:
                    c.proc.kill()


if __name__ == "__main__":
    main()
