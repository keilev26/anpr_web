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


def crop_window(box: Box, img_w: int, img_h: int) -> tuple[int, int, int, int]:
    """
    Región que se recorta alrededor de una placa antes de pasarla al OCR.

    Añade un margen proporcional a la altura: los bordes de la placa ayudan al OCR
    a segmentar los caracteres. Vive aquí, sin dependencias, para que producción
    (`OnnxCropper`) y las pruebas (`scripts/detect_plates.py`) recorten igual.
    """
    m = max(2, box.height // 10)
    return (
        max(0, box.x1 - m),
        max(0, box.y1 - m),
        min(img_w, box.x2 + m),
        min(img_h, box.y2 + m),
    )


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
    """Mayor confianza del detector entre los fotogramas que coincidieron."""

    ocr_confidence: float | None = None
    corrections: list[str] = field(default_factory=list)

    votes: dict[str, int] = field(default_factory=dict)
    """Cuántos fotogramas leyeron cada placa válida. Se registra también cuando no
    hay consenso: dice si falló por lecturas dispersas o por no leer nada."""

    reason: str | None = None
    """None si hay placa. Si no: `sin_lectura`, `sin_consenso` o `frames_insuficientes`."""

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
        min_agreement: int = 2,
    ) -> None:
        """
        `min_agreement`: fotogramas distintos que deben leer la MISMA placa para
        aceptarla.

        Por qué 2 y no 1: en la prueba visual del 2026-09-16 hubo lecturas erróneas
        con aspecto perfectamente válido y confianza alta (`T5Q-640` leída como
        `T50-640` con 0,91). Ningún umbral de confianza las filtra, pero es muy
        improbable que el mismo error se repita idéntico en dos fotogramas.
        """
        if min_agreement < 1:
            raise ValueError("min_agreement debe ser al menos 1")
        self._detector = detector
        self._ocr = ocr
        self._cropper = cropper
        self._min_conf = min_box_confidence
        self._min_agreement = min_agreement

    def run(self, frames: list[Image]) -> DetectionResult:
        """
        Procesa la ráfaga hasta que una placa reúne `min_agreement` votos.

        Corta en cuanto hay consenso, sin procesar el resto: con 10 fotogramas y
        ~0,4 s por inferencia, procesarlos todos se saldría del presupuesto de 4 s.

        Si llegan menos fotogramas que `min_agreement`, la placa no se acepta.
        Relajar el requisito en ese caso debilitaría la seguridad en silencio.
        """
        started = time.perf_counter()
        result = DetectionResult()
        votes: dict[str, int] = {}
        evidence: dict[str, dict] = {}

        def finish() -> DetectionResult:
            result.votes = dict(votes)
            result.elapsed_ms = int((time.perf_counter() - started) * 1000)
            return result

        for frame in frames:
            result.frames_processed += 1

            boxes = [b for b in self._detector.detect(frame) if b.confidence >= self._min_conf]
            result.boxes_found += len(boxes)

            # La caja más ancha primero: a igualdad de todo, la placa más
            # grande es la del vehículo más cercano y la más legible.
            for box in sorted(boxes, key=lambda b: b.width, reverse=True):
                crop = self._cropper.crop(frame, box)
                readings = self._ocr.read(crop)
                cand: PlateCandidate | None = best_plate(readings) if readings else None

                if cand is None or not cand.valid:
                    if cand is not None and cand.raw:
                        result.failed_readings.append(cand.raw)
                    # Recordar el mayor ancho visto, aunque no se leyera: si todas
                    # las lecturas fallan, este número dice si la culpa es óptica.
                    if result.plate_px_width is None or box.width > result.plate_px_width:
                        result.plate_px_width = box.width
                    continue

                plate = cand.plate
                votes[plate] = votes.get(plate, 0) + 1
                ev = evidence.setdefault(
                    plate, {"conf": 0.0, "ocr": 0.0, "corrections": [], "width": 0}
                )
                ev["conf"] = max(ev["conf"], box.confidence)
                ev["ocr"] = max(ev["ocr"], max(c for _, c in readings))
                ev["corrections"] = ev["corrections"] or cand.corrections
                ev["width"] = max(ev["width"], box.width)

                if votes[plate] >= self._min_agreement:
                    result.plate = plate
                    result.confidence = ev["conf"]
                    result.ocr_confidence = ev["ocr"]
                    result.corrections = ev["corrections"]
                    result.plate_px_width = ev["width"]
                    return finish()

                # Un fotograma vota UNA vez: dos recortes de la misma foto leyendo
                # la misma placa son la misma evidencia contada dos veces.
                break

        if len(frames) < self._min_agreement:
            result.reason = "frames_insuficientes"
        elif votes:
            result.reason = "sin_consenso"
        else:
            result.reason = "sin_lectura"
        return finish()
