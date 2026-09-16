import asyncio
import base64
import json
import logging
from typing import Any, Protocol

log = logging.getLogger("anpr.plate_reader")


class PlateReading(Protocol):
    plate: str | None
    confidence: float | None


class PlateReader(Protocol):
    """
    Interfaz con el frente de ML (F4).

    F2 no ejecuta ningún modelo: la inferencia vive en su propio Lambda. Esta
    interfaz es la costura, para que F2 sea completo y testeable sin arrastrar
    torch ni paddleocr.
    """

    async def read(self, frames: list[bytes]) -> tuple[str | None, float | None]: ...


class StubPlateReader:
    """
    Implementación de relleno para desarrollo y pruebas.

    No lee nada: devuelve la placa que se le inyecte. F4 la sustituye por el
    cliente real del Lambda de inferencia.
    """

    def __init__(self, plate: str | None = None, confidence: float | None = None) -> None:
        self._plate = plate
        self._confidence = confidence

    async def read(self, frames: list[bytes]) -> tuple[str | None, float | None]:
        if not frames:
            return None, None
        return self._plate, self._confidence


class InferenceError(RuntimeError):
    """El Lambda de inferencia falló. La API responde 5xx: la Pi reintenta y no abre."""


class LambdaPlateReader:
    """
    Cliente del Lambda de inferencia (`ml/src/anpr_ml/handler.py`).

    El consenso entre fotogramas se decide allí: si no hay placa aceptada, llega
    `plate=None` con `reason` (sin_lectura / sin_consenso / frames_insuficientes),
    que se registra aquí para poder diagnosticar.
    """

    def __init__(self, function_name: str, client: Any = None) -> None:
        if client is None:
            import boto3

            client = boto3.client("lambda")
        self._fn = function_name
        self._client = client

    async def read(self, frames: list[bytes]) -> tuple[str | None, float | None]:
        payload = json.dumps({"frames": [base64.b64encode(f).decode() for f in frames]}).encode()
        # boto3 es bloqueante: fuera del bucle de eventos.
        resp = await asyncio.to_thread(self._client.invoke, FunctionName=self._fn, Payload=payload)
        raw = resp["Payload"].read()
        if resp.get("FunctionError"):
            raise InferenceError(f"Lambda de inferencia falló: {raw[:300]!r}")

        body = json.loads(raw)
        data = json.loads(body.get("body") or "{}")
        if body.get("statusCode") != 200:
            raise InferenceError(f"Inferencia respondió {body.get('statusCode')}: {data}")

        if data.get("plate") is None:
            log.info(
                "Sin placa aceptada: reason=%s votes=%s descartadas=%s",
                data.get("reason"),
                data.get("votes"),
                data.get("failed_readings"),
            )
        return data.get("plate"), data.get("confidence")
