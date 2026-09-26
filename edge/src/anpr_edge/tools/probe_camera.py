"""
Sonda de la Sony real: mide el liveview y graba una muestra para los tests.

Conectar antes la laptop al Wi-Fi de la cámara (red DIRECT-...:HDR-AS100V). La
laptop pierde internet mientras tanto, salvo por cable o tethering.

    anpr-probe-camera                       # 3 ciclos de 5 s
    anpr-probe-camera --record capturas/liveview.bin --save-frames 10

Mide por ciclo: cuánto tarda en arrancar el liveview y en llegar el primer frame,
FPS, resolución, tamaño de los JPEG, huecos de secuencia y paquetes corruptos.
Cierra SIEMPRE con stopLiveview y repite varios ciclos para comprobar que la cámara
no se queda sin sesiones. Las grabaciones van a `capturas/` (ignorada por git: puede
haber placas y personas).
"""

import argparse
import json
import statistics
import sys
import time
from pathlib import Path

from anpr_edge.camera.sony import CameraError, LiveviewParser, SonyCamera, jpeg_size

DEFAULT_RPC = "http://192.168.122.1:10000/sony/camera"


def probe_cycle(
    cam: SonyCamera,
    size: str,
    seconds: float,
    record: Path | None,
    record_max: int,
    save_dir: Path | None,
    save_n: int,
) -> dict:
    result: dict = {}
    t0 = time.monotonic()
    url = cam.start_liveview(size)
    result["start_liveview_s"] = round(time.monotonic() - t0, 3)
    parser = LiveviewParser()
    frames, recorded = [], bytearray()
    try:
        t1 = time.monotonic()
        with cam.stream(url, read_timeout_s=5.0) as chunks:
            for chunk in chunks:
                if record is not None and len(recorded) < record_max:
                    recorded += chunk
                frames.extend(parser.feed(chunk))
                if time.monotonic() - t1 >= seconds:
                    break
    finally:
        t2 = time.monotonic()
        cam.stop_liveview()
        result["stop_liveview_s"] = round(time.monotonic() - t2, 3)

    if not frames:
        result["error"] = "no llegó ningún frame"
        return result
    first, last = frames[0], frames[-1]
    elapsed = last.received - first.received
    sizes = [len(f.jpeg) for f in frames]
    seqs = [f.seq for f in frames]
    result |= {
        "first_frame_s": round(first.received - t1, 3),
        "frames": len(frames),
        "fps": round((len(frames) - 1) / elapsed, 1) if elapsed > 0 else None,
        "resolution": jpeg_size(first.jpeg),
        "jpeg_kb_avg": round(statistics.mean(sizes) / 1024, 1),
        "jpeg_kb_max": round(max(sizes) / 1024, 1),
        "seq_gaps": sum(1 for a, b in zip(seqs, seqs[1:], strict=False) if (b - a) % 65536 != 1),
        "resyncs": parser.resyncs,
        "corrupt": parser.corrupt,
    }
    if record is not None:
        record.parent.mkdir(parents=True, exist_ok=True)
        record.write_bytes(recorded)
        result["recorded_bytes"] = len(recorded)
    if save_dir is not None:
        save_dir.mkdir(parents=True, exist_ok=True)
        step = max(1, len(frames) // save_n)
        for i, f in enumerate(frames[::step][:save_n]):
            (save_dir / f"frame_{i:02d}.jpg").write_bytes(f.jpeg)
    return result


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    ap.add_argument("--rpc-url", default=DEFAULT_RPC)
    ap.add_argument("--size", choices=["M", "L"], default="M")
    ap.add_argument("--seconds", type=float, default=5.0)
    ap.add_argument("--cycles", type=int, default=3)
    ap.add_argument("--record", type=Path, help="Guardar el stream crudo del primer ciclo")
    ap.add_argument("--record-mb", type=float, default=5.0)
    ap.add_argument("--save-frames", type=int, default=0, help="Guardar N JPEG del primer ciclo")
    ap.add_argument("--out-dir", type=Path, default=Path("capturas"))
    args = ap.parse_args()

    cam = SonyCamera(args.rpc_url, timeout_s=10.0)
    try:
        apis = cam.available_apis()
    except CameraError as e:
        print(
            f"No responde la cámara en {args.rpc_url}: {e}\n"
            "¿Está la laptop conectada al Wi-Fi DIRECT-... de la Sony?",
            file=sys.stderr,
        )
        return 1

    report = {"rpc_url": args.rpc_url, "apis": apis, "size": args.size, "cycles": []}
    for n in range(args.cycles):
        first = n == 0
        try:
            r = probe_cycle(
                cam,
                args.size,
                args.seconds,
                args.record if first else None,
                int(args.record_mb * 1024 * 1024),
                args.out_dir / "frames" if first and args.save_frames else None,
                args.save_frames,
            )
        except CameraError as e:
            r = {"error": str(e)}
        r["cycle"] = n + 1
        report["cycles"].append(r)
        print(json.dumps(r, ensure_ascii=False), file=sys.stderr)
        time.sleep(1)
    cam.close()

    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if all("error" not in c for c in report["cycles"]) else 2


if __name__ == "__main__":
    raise SystemExit(main())
