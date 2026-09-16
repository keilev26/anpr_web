"""
Recortes de "vista de puerta": convierten fotos de calle tomadas desde lejos en
encuadres parecidos a los de una cámara de acceso.

Lógica pura (sin Pillow ni numpy), probada en `tests/test_crops.py`.

Un recorte simula el ENCUADRE, no la RESOLUCIÓN. Ampliar una placa pequeña la
hace más grande pero borrosa, y un modelo entrenado con eso aprendería a leer
placas que ninguna cámara real produciría. De ahí las dos salvaguardas:
ancho nativo mínimo y ampliación máxima.
"""

from __future__ import annotations

import random
from dataclasses import dataclass

Box = tuple[float, float, float, float]  # x1, y1, x2, y2 en píxeles


@dataclass(frozen=True, slots=True)
class CropParams:
    out_w: int = 640
    aspect: float = 4 / 3
    """Ancho/alto del recorte. Horizontal, como el cuadro de una cámara."""

    plate_px_min: int = 80
    plate_px_max: int = 200
    """Ancho que debe tener la placa en el recorte final, en píxeles."""

    min_native_px: int = 40
    """Placas más estrechas en la foto original no son elegibles."""

    max_upscale: float = 2.0
    min_visibility: float = 0.6
    """Otras placas que el recorte corte: se conservan si queda visible al menos esto."""

    @property
    def out_h(self) -> int:
        return round(self.out_w / self.aspect)


DEFAULT_PARAMS = CropParams()


@dataclass(frozen=True, slots=True)
class CropResult:
    window: Box
    scale: float
    """Factor aplicado al redimensionar: >1 amplía, <1 reduce."""

    labels: list[tuple[float, float, float, float]]
    """Cajas YOLO normalizadas (cx, cy, w, h) respecto al recorte final."""

    plate_px_out: float
    """Ancho de la placa objetivo en el recorte final."""


def plan_crop(
    img_w: int,
    img_h: int,
    boxes: list[Box],
    target: int,
    rng: random.Random,
    params: CropParams = DEFAULT_PARAMS,
) -> CropResult | str:
    """
    Planifica un recorte centrado aproximadamente en `boxes[target]`.

    Devuelve un CropResult, o un str con el motivo si la placa no es elegible.
    """
    x1, y1, x2, y2 = boxes[target]
    plate_w = x2 - x1
    if plate_w < params.min_native_px:
        return "placa demasiado pequeña en la foto original"

    # Ancho de ventana para que la placa quede con el tamaño deseado.
    desired = rng.uniform(params.plate_px_min, params.plate_px_max)
    win_w = plate_w * params.out_w / desired

    # No ampliar más de max_upscale: eso inventaría nitidez.
    win_w = max(win_w, params.out_w / params.max_upscale)

    # La ventana tiene que caber en la imagen.
    win_w = min(win_w, img_w, img_h * params.aspect)
    win_h = win_w / params.aspect

    scale = params.out_w / win_w
    plate_out = plate_w * scale
    if plate_out < params.plate_px_min:
        return "no alcanza el tamaño mínimo sin ampliar de más"
    if plate_out > params.plate_px_max * 1.001:
        return "la placa no cabe en el rango ni con la ventana más grande"

    # La placa en una posición variable dentro del cuadro, no siempre al centro.
    pcx, pcy = (x1 + x2) / 2, (y1 + y2) / 2
    wx1 = pcx - win_w * rng.uniform(0.3, 0.7)
    wy1 = pcy - win_h * rng.uniform(0.35, 0.75)
    wx1 = min(max(0.0, wx1), img_w - win_w)
    wy1 = min(max(0.0, wy1), img_h - win_h)
    window = (wx1, wy1, wx1 + win_w, wy1 + win_h)

    labels = []
    for i, b in enumerate(boxes):
        kept = _clip_to_window(b, window, params.min_visibility)
        if kept is None:
            if i == target:
                return "la placa objetivo quedó cortada"
            continue
        bx1, by1, bx2, by2 = kept
        labels.append(
            (
                ((bx1 + bx2) / 2 - wx1) / win_w,
                ((by1 + by2) / 2 - wy1) / win_h,
                (bx2 - bx1) / win_w,
                (by2 - by1) / win_h,
            )
        )

    return CropResult(window=window, scale=scale, labels=labels, plate_px_out=plate_out)


def _clip_to_window(box: Box, window: Box, min_visibility: float) -> Box | None:
    x1, y1, x2, y2 = box
    wx1, wy1, wx2, wy2 = window
    ix1, iy1, ix2, iy2 = max(x1, wx1), max(y1, wy1), min(x2, wx2), min(y2, wy2)
    if ix2 <= ix1 or iy2 <= iy1:
        return None
    area = (x2 - x1) * (y2 - y1)
    if area <= 0 or (ix2 - ix1) * (iy2 - iy1) / area < min_visibility:
        return None
    return ix1, iy1, ix2, iy2
