"""
Sony HDR-AS100V falsa, para desarrollar y probar sin la cámara.

Habla el mismo protocolo: JSON-RPC en /sony/camera y liveview con el formato de
paquetes de Sony. Sirve JPEG de una carpeta o repite una grabación real hecha con
`anpr-probe-camera --record`.

También reproduce los fallos que interesan:
- sesiones que se agotan si se llama a startLiveview sin stopLiveview (la fuga
  del legacy),
- stream que se corta tras N frames (--drop-after),
- RPC lenta (--rpc-delay).

    anpr-sim-camera --frames-dir tests/fixtures/frames
    anpr-sim-camera --replay capturas/liveview.bin
"""

import argparse
import contextlib
import json
import logging
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from anpr_edge.camera.sony import encode_packet

log = logging.getLogger("anpr-sim-camera")

APIS = [
    "getAvailableApiList",
    "startRecMode",
    "stopRecMode",
    "startLiveview",
    "startLiveviewWithSize",
    "stopLiveview",
]
LIVEVIEW_PATH = "/liveview/liveviewstream"


class CameraState:
    def __init__(
        self,
        frames: list[bytes] | None,
        replay: bytes | None,
        fps: float,
        max_sessions: int,
        drop_after: int | None,
        rpc_delay: float,
    ) -> None:
        if not frames and not replay:
            raise ValueError("Hace falta --frames-dir o --replay")
        self.frames = frames or []
        self.replay = replay
        self.fps = fps
        self.max_sessions = max_sessions
        self.drop_after = drop_after
        self.rpc_delay = rpc_delay
        self.rec_mode = False
        self.sessions = 0
        self.lock = threading.Lock()

    def rpc(self, method: str, params: list, base_url: str) -> dict:
        time.sleep(self.rpc_delay)
        with self.lock:
            if method == "getAvailableApiList":
                apis = APIS if self.rec_mode else ["getAvailableApiList", "startRecMode"]
                return {"result": [apis]}
            if method == "startRecMode":
                self.rec_mode = True
                return {"result": [0]}
            if method in ("startLiveview", "startLiveviewWithSize"):
                if not self.rec_mode:
                    return {"error": [1, "Not Available Now"]}
                if self.sessions >= self.max_sessions:
                    return {"error": [1, "Sesiones de liveview agotadas (simulado)"]}
                self.sessions += 1
                return {"result": [base_url + LIVEVIEW_PATH]}
            if method == "stopLiveview":
                self.sessions = max(0, self.sessions - 1)
                return {"result": [0]}
            if method == "stopRecMode":
                self.rec_mode = False
                return {"result": [0]}
        return {"error": [12, "No Such Method"]}


def make_handler(state: CameraState) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.0"  # el stream termina al cerrar la conexión

        def log_message(self, fmt, *args) -> None:
            log.debug(fmt, *args)

        def do_POST(self) -> None:
            if self.path != "/sony/camera":
                self.send_error(404)
                return
            body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))))
            host, port = self.server.server_address[:2]
            reply = state.rpc(
                body.get("method", ""), body.get("params", []), f"http://{host}:{port}"
            )
            reply["id"] = body.get("id")
            data = json.dumps(reply).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self) -> None:
            if self.path != LIVEVIEW_PATH or state.sessions == 0:
                self.send_error(404)
                return
            self.send_response(200)
            self.send_header("Content-Type", "image/jpeg")
            self.end_headers()
            # El cliente cierra la conexión al terminar: es lo normal, no un error.
            with contextlib.suppress(BrokenPipeError, ConnectionResetError):
                self._stream()

        def _stream(self) -> None:
            period = 1.0 / state.fps
            if state.replay is not None:
                chunk = 16 * 1024
                for i in range(0, len(state.replay), chunk):
                    self.wfile.write(state.replay[i : i + chunk])
                    time.sleep(period / 4)
                return
            start = time.monotonic()
            for seq in range(10**9):
                if state.drop_after is not None and seq >= state.drop_after:
                    return
                jpeg = state.frames[seq % len(state.frames)]
                ts = int((time.monotonic() - start) * 1000)
                self.wfile.write(encode_packet(seq, ts, jpeg, padding=seq % 4))
                self.wfile.flush()
                time.sleep(period)

    return Handler


def serve(state: CameraState, host: str = "127.0.0.1", port: int = 10000) -> ThreadingHTTPServer:
    server = ThreadingHTTPServer((host, port), make_handler(state))
    server.daemon_threads = True
    return server


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    ap.add_argument("--frames-dir", type=Path)
    ap.add_argument("--replay", type=Path, help="Grabación cruda del liveview")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=10000)
    ap.add_argument("--fps", type=float, default=15.0)
    ap.add_argument("--max-sessions", type=int, default=3)
    ap.add_argument("--drop-after", type=int, help="Cortar el stream tras N frames")
    ap.add_argument("--rpc-delay", type=float, default=0.0)
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")

    frames = None
    if args.frames_dir:
        frames = [p.read_bytes() for p in sorted(args.frames_dir.glob("*.jpg"))]
        if not frames:
            ap.error(f"No hay .jpg en {args.frames_dir}")
    state = CameraState(
        frames,
        args.replay.read_bytes() if args.replay else None,
        args.fps,
        args.max_sessions,
        args.drop_after,
        args.rpc_delay,
    )
    server = serve(state, args.host, args.port)
    log.info("Sony simulada en http://%s:%d/sony/camera", args.host, args.port)
    with contextlib.suppress(KeyboardInterrupt):
        server.serve_forever()


if __name__ == "__main__":
    main()
