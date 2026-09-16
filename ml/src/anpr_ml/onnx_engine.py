"""
Implementaciones reales de los Protocols de `pipeline.py`.

Este módulo es el único que depende de onnxruntime, numpy, cv2 y paddleocr.
El resto de F4 (pipeline, post-procesado del texto) no importa nada de esto,
por eso se puede probar entero sin instalar el stack de visión.

No tiene tests unitarios: probarlo de verdad exige el modelo y los pesos. Se
valida con `scripts/benchmark.py` sobre imágenes reales.
"""

from __future__ import annotations

import os

import cv2
import numpy as np
import onnxruntime as ort

from anpr_ml.pipeline import Box, crop_window

# El modelo se entrenó a 640 (ver metadatos de best.pt: imgsz=640).
INPUT_SIZE = 640
NMS_IOU = 0.45
PLATE_CLASS = 0


class OnnxDetector:
    """YOLO11 exportado a ONNX, ejecutado con onnxruntime."""

    def __init__(self, model_path: str, *, threads: int | None = None) -> None:
        opts = ort.SessionOptions()
        # En Lambda la CPU escala con la memoria asignada; dejar que
        # onnxruntime use todos los núcleos disponibles.
        opts.intra_op_num_threads = threads or (os.cpu_count() or 2)
        opts.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL

        self._session = ort.InferenceSession(
            model_path, sess_options=opts, providers=["CPUExecutionProvider"]
        )
        self._input_name = self._session.get_inputs()[0].name

    @staticmethod
    def _letterbox(img: np.ndarray) -> tuple[np.ndarray, float, int, int]:
        """Redimensiona conservando la proporción y rellena. Devuelve la escala
        y los desplazamientos para poder deshacerlo sobre las cajas."""
        h, w = img.shape[:2]
        scale = min(INPUT_SIZE / h, INPUT_SIZE / w)
        nh, nw = int(round(h * scale)), int(round(w * scale))
        resized = cv2.resize(img, (nw, nh), interpolation=cv2.INTER_LINEAR)

        canvas = np.full((INPUT_SIZE, INPUT_SIZE, 3), 114, dtype=np.uint8)
        top, left = (INPUT_SIZE - nh) // 2, (INPUT_SIZE - nw) // 2
        canvas[top : top + nh, left : left + nw] = resized
        return canvas, scale, left, top

    def detect(self, image: np.ndarray) -> list[Box]:
        canvas, scale, pad_x, pad_y = self._letterbox(image)

        blob = canvas[:, :, ::-1].transpose(2, 0, 1)  # BGR->RGB, HWC->CHW
        blob = np.ascontiguousarray(blob, dtype=np.float32) / 255.0
        blob = blob[None]

        out = self._session.run(None, {self._input_name: blob})[0]

        # YOLO11 entrega (1, 4+nc, 8400): se transpone a (8400, 4+nc).
        preds = np.squeeze(out, 0).T
        scores = preds[:, 4 + PLATE_CLASS]

        keep = scores > 0.05  # filtro grueso; el umbral fino lo aplica el pipeline
        preds, scores = preds[keep], scores[keep]
        if preds.size == 0:
            return []

        cx, cy, bw, bh = preds[:, 0], preds[:, 1], preds[:, 2], preds[:, 3]
        x1 = (cx - bw / 2 - pad_x) / scale
        y1 = (cy - bh / 2 - pad_y) / scale
        x2 = (cx + bw / 2 - pad_x) / scale
        y2 = (cy + bh / 2 - pad_y) / scale

        h, w = image.shape[:2]
        x1, x2 = np.clip(x1, 0, w), np.clip(x2, 0, w)
        y1, y2 = np.clip(y1, 0, h), np.clip(y2, 0, h)

        boxes_xywh = np.stack([x1, y1, x2 - x1, y2 - y1], axis=1)
        idx = cv2.dnn.NMSBoxes(
            boxes_xywh.tolist(), scores.tolist(), score_threshold=0.05, nms_threshold=NMS_IOU
        )
        if len(idx) == 0:
            return []

        return [
            Box(int(x1[i]), int(y1[i]), int(x2[i]), int(y2[i]), float(scores[i]))
            for i in np.array(idx).flatten()
        ]


class OnnxCropper:
    def crop(self, image: np.ndarray, box: Box) -> np.ndarray:
        h, w = image.shape[:2]
        x1, y1, x2, y2 = crop_window(box, w, h)
        return image[y1:y2, x1:x2]


class PaddleOcr:
    def __init__(self, models_dir: str | None = None) -> None:
        from paddleocr import PaddleOCR

        from anpr_ml.ocr_settings import paddleocr_kwargs

        self._ocr = PaddleOCR(**paddleocr_kwargs(models_dir))

    def read(self, crop: np.ndarray) -> list[tuple[str, float]]:
        if crop.size == 0:
            return []

        out = self._ocr.predict(cv2.cvtColor(crop, cv2.COLOR_BGR2RGB))
        if not out:
            return []

        primero = out[0]
        textos = primero.get("rec_texts", []) or []
        scores = primero.get("rec_scores", []) or []

        # Emparejar texto con su score; si faltan scores, asumir 0.0 en vez de
        # inventar confianza: el post-procesado usa ese número para elegir.
        return [
            (str(t), float(scores[i]) if i < len(scores) else 0.0) for i, t in enumerate(textos)
        ]
