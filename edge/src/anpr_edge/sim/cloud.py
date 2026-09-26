"""
Nube falsa: `POST /v1/detections` con el mismo contrato que la API real, y escenarios
que la real no puede producir a voluntad (caída, lentitud, placa ilegible).

    anpr-sim-cloud --port 8001 --mode open
    curl -X POST localhost:8001/_scenario -H 'content-type: application/json' \\
         -d '{"mode": "unavailable", "delay_s": 0}'

Modos: open (placa autorizada), deny, unreadable (422), unavailable (503), hang (no
responde nunca: provoca timeouts). `delay_s` simula una red o una inferencia lenta.
"""

import argparse
import asyncio
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, File, Form, Header, HTTPException, Request, UploadFile
from pydantic import BaseModel

Mode = Literal["open", "deny", "unreadable", "unavailable", "hang"]


class Scenario(BaseModel):
    mode: Mode = "open"
    delay_s: float = 0.0
    plate: str = "CUB-604"


def create_app(scenario: Scenario | None = None, device_key: str | None = None) -> FastAPI:
    app = FastAPI(title="Nube simulada")
    app.state.scenario = scenario or Scenario()
    app.state.events: list[dict] = []
    verdicts: dict[str, dict] = {}

    @app.get("/health")
    async def health() -> dict:
        return {"status": "ok", "db": True}

    @app.post("/_scenario")
    async def set_scenario(s: Scenario) -> Scenario:
        app.state.scenario = s
        return s

    @app.get("/_events")
    async def events() -> list[dict]:
        return app.state.events

    @app.post("/v1/detections")
    async def detections(
        request: Request,
        gate_id: str = Form(...),
        event_id: str = Form(...),
        captured_at: str = Form(...),
        late: bool = Form(False),
        frames: list[UploadFile] = File(...),
        x_device_key: str | None = Header(None),
    ) -> dict:
        s: Scenario = app.state.scenario
        if device_key and x_device_key != device_key:
            raise HTTPException(401, "Clave de dispositivo inválida")
        sizes = [len(await f.read()) for f in frames]
        app.state.events.append(
            {
                "event_id": event_id,
                "late": late,
                "frames": len(sizes),
                "bytes": sum(sizes),
                "mode": s.mode,
            }
        )
        if s.delay_s:
            await asyncio.sleep(s.delay_s)
        if event_id in verdicts:
            return verdicts[event_id]  # idempotente, como la API real
        if s.mode == "hang":
            await asyncio.sleep(3600)
        if s.mode == "unavailable":
            raise HTTPException(503, "Inferencia no disponible, reintentar")
        if s.mode == "unreadable":
            raise HTTPException(422, "Ninguna placa legible en la ráfaga")
        authorized = s.mode == "open"
        verdict = {
            "event_id": event_id,
            "plate": s.plate,
            "confidence": 0.93,
            "authorized": authorized,
            "user": {"name": "Simulado", "role": "teacher"} if authorized else None,
            "command": {"action": "open" if authorized else "deny", "ttl_s": 10},
            "latency_ms": int(s.delay_s * 1000),
        }
        verdicts[event_id] = verdict
        return verdict

    return app


def main() -> None:
    import uvicorn

    ap = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8001)
    ap.add_argument("--mode", default="open")
    ap.add_argument("--delay-s", type=float, default=0.0)
    ap.add_argument("--device-key-file", help="Si se da, exige X-Device-Key")
    args = ap.parse_args()
    key = Path(args.device_key_file).read_text().strip() if args.device_key_file else None
    app = create_app(Scenario(mode=args.mode, delay_s=args.delay_s), key)
    uvicorn.run(app, host=args.host, port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
