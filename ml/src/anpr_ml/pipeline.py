"""
Orquestación: ráfaga de frames -> placa.

El detector y el OCR son Protocols, no implementaciones concretas. Así el
pipeline se prueba entero sin torch ni paddle, y F3 puede sustituir el motor
ONNX sin tocar esta lógica.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Protocol

from anpr_ml.plate_text import PlateCandidate, best_plate

Image = object  # np.ndarray en runtime; sin tipar aquí para no depender de numpy


@dataclass(slots=True, frozen=True)
class Box:
    x1: int
    y1: int
    x2: int
    y2: int
    confidence: float

    @property
    def width(self) -> int:
        return self.x2 - self.x1

    @property
    def height(self) -> int:
        return self.y2 - self.y1


class Detector(Protocol):
    def detect(self, image: Image) -> list[Box]: ...


class OcrEngine(Protocol):
    """Devuelve las lecturas de un recorte, como (texto, confianza)."""

    def read(self, crop: Image) -> list[tuple[str, float]]: ...


class Cropper(Protocol):
    def crop(self, image: Image, box: Box) -> Image: ...


@dataclass(slots=True)
class DetectionResult:
    plate: str | None = None
    confidence: float | None = None
    """Confianza del detector para el recorte que produjo la placa."""

    ocr_confidence: float | None = None
    corrections: list[str] = field(default_factory=list)

    frames_processed: int = 0
    boxes_found: int = 0
    plate_px_width: int | None = None
    """
    Ancho en píxeles de la placa detectada.

    Es la métrica que decide si la cámara sirve: por debajo de ~60-80 px
    ningún modelo lee de forma fiable, y el problema es óptico, no de software.
    """

    failed_readings: list[str] = field(default_factory=list)
    """Lecturas descartadas, tal cual las devolvió el OCR. Sin esto no se
    puede medir la tasa real de acierto ni saber por qué falla."""

    elapsed_ms: int = 0

    @property
    def ok(self) -> bool:
        return self.plate is not None


# Por debajo de este ancho, avisar: el cuello de botella es la cámara.
MIN_USABLE_PLATE_PX = 60


class PlatePipeline:
    def __init__(
        self,
        detector: Detector,
        ocr: OcrEngine,
        cropper: Cropper,
        *,
        min_box_confidence: float = 0.30,
    ) -> None:
        self._detector = detector
        self._ocr = ocr
        self._cropper = cropper
        self._min_conf = min_box_confidence

    def run(self, frames: list[Image]) -> DetectionResult:
        """
        Procesa la ráfaga y CORTA en la primera placa válida.

        Esto es lo que mantiene la latencia dentro del presupuesto de 4 s: con
        10 frames y ~0.4 s por inferencia, procesarlos todos se saldría del
        presupuesto. En la práctica basta un buen frame.
        """
        started = time.perf_counter()
        result = DetectionResult()

        for frame in frames:
            result.frames_processed += 1

            boxes = [b for b in self._detector.detect(frame) if b.confidence >= self._min_conf]
            result.boxes_found += len(boxes)

            # La caja más ancha primero: a igualdad de todo, la placa más
            # grande es la del vehículo más cercano y la más legible.
            for box in sorted(boxes, key=lambda b: b.width, reverse=True):
                crop = self._cropper.crop(frame, box)
                readings = self._ocr.read(crop)
                if not readings:
                    continue

                cand: PlateCandidate | None = best_plate(readings)
                if cand is None:
                    continue

                if cand.valid:
                    result.plate = cand.plate
                    result.confidence = box.confidence
                    result.ocr_confidence = max(c for _, c in readings)
                    result.corrections = cand.corrections
                    result.plate_px_width = box.width
                    result.elapsed_ms = int((time.perf_counter() - started) * 1000)
                    return result

                if cand.raw:
                    result.failed_readings.append(cand.raw)
                # Recordar el mayor ancho visto, aunque no se leyera: si todas
                # las lecturas fallan, este número dice si la culpa es óptica.
                if result.plate_px_width is None or box.width > result.plate_px_width:
                    result.plate_px_width = box.width

        result.elapsed_ms = int((time.perf_counter() - started) * 1000)
        return result
