"""
Entrypoint del Lambda de inferencia.

Alcance: SOLO visión. Recibe frames, devuelve placa y confianza. No consulta la
base de datos ni decide si se abre la puerta: eso es de F2, que llama aquí a
través de la interfaz `PlateReader` (`api/app/services/plate_reader.py`).

Mantenerlo así evita que el contenedor de visión —el pesado, el del cold start—
necesite credenciales de base de datos.

Contrato:
    entrada  {"frames": ["<jpeg en base64>", ...]}
    salida   {"plate": "CUB-604"|null, "confidence": 0.93, "ocr_confidence": 0.88,
              "corrections": [...], "votes": {"CUB-604": 2}, "reason": null,
              "plate_px_width": 142, "frames_processed": 2,
              "failed_readings": [...], "elapsed_ms": 380}
"""

from __future__ import annotations

import base64
import binascii
import json
import logging
import os
from typing import Any

from anpr_ml.pipeline import MIN_USABLE_PLATE_PX, PlatePipeline

log = logging.getLogger()
log.setLevel(os.environ.get("LOG_LEVEL", "INFO"))

MAX_FRAMES = 10

# Se construye una sola vez por contenedor y se reutiliza entre invocaciones:
# recrearlo en cada llamada volvería a cargar los modelos y arruinaría la
# latencia de todas las peticiones, no solo la primera.
_pipeline: PlatePipeline | None = None


def _build_pipeline() -> PlatePipeline:
    # Import diferido: mantiene fuera del arranque del módulo todo lo pesado.
    from anpr_ml.onnx_engine import OnnxCropper, OnnxDetector, PaddleOcr

    return PlatePipeline(
        detector=OnnxDetector(os.environ["MODEL_PATH"]),
        ocr=PaddleOcr(os.environ.get("OCR_MODELS_DIR")),
        cropper=OnnxCropper(),
        min_box_confidence=float(os.environ.get("CONF_THRESHOLD", "0.30")),
        # Fotogramas que deben leer la misma placa. Ver PlatePipeline.
        min_agreement=int(os.environ.get("MIN_AGREEMENT", "2")),
    )


def _get_pipeline() -> PlatePipeline:
    global _pipeline
    if _pipeline is None:
        _pipeline = _build_pipeline()
    return _pipeline


def _decode_frames(payload: dict[str, Any]) -> list:
    import cv2
    import numpy as np

    raw = payload.get("frames") or []
    if not isinstance(raw, list) or not 1 <= len(raw) <= MAX_FRAMES:
        raise ValueError(f"Se esperan entre 1 y {MAX_FRAMES} frames")

    frames = []
    for i, b64 in enumerate(raw):
        try:
            data = base64.b64decode(b64, validate=True)
        except (binascii.Error, TypeError) as exc:
            raise ValueError(f"frame {i}: base64 inválido") from exc

        img = cv2.imdecode(np.frombuffer(data, dtype=np.uint8), cv2.IMREAD_COLOR)
        if img is None:
            raise ValueError(f"frame {i}: no es un JPEG decodificable")
        frames.append(img)
    return frames


def lambda_handler(event: dict[str, Any], context: Any = None) -> dict[str, Any]:
    body = event.get("body", event)
    if isinstance(body, str):
        body = json.loads(body)

    try:
        frames = _decode_frames(body)
    except ValueError as exc:
        log.warning("Petición inválida: %s", exc)
        return {"statusCode": 400, "body": json.dumps({"detail": str(exc)})}

    result = _get_pipeline().run(frames)

    # La placa pequeña es la causa más común de fallo de lectura, y es un
    # problema de cámara. Dejarlo en el log evita horas depurando el modelo.
    if result.plate_px_width is not None and result.plate_px_width < MIN_USABLE_PLATE_PX:
        log.warning(
            "Placa de solo %spx de ancho (mínimo utilizable %s): el cuello de "
            "botella es la cámara, no el modelo.",
            result.plate_px_width,
            MIN_USABLE_PLATE_PX,
        )

    if not result.ok:
        log.info(
            "Sin placa aceptada (%s). frames=%s cajas=%s votos=%s descartadas=%s",
            result.reason,
            result.frames_processed,
            result.boxes_found,
            result.failed_readings,
        )

    return {
        "statusCode": 200,
        "body": json.dumps(
            {
                "plate": result.plate,
                "confidence": result.confidence,
                "ocr_confidence": result.ocr_confidence,
                "corrections": result.corrections,
                "votes": result.votes,
                "reason": result.reason,
                "plate_px_width": result.plate_px_width,
                "frames_processed": result.frames_processed,
                "boxes_found": result.boxes_found,
                "failed_readings": result.failed_readings,
                "elapsed_ms": result.elapsed_ms,
            }
        ),
    }
