"""
Conversión de anotaciones COCO (export de Roboflow) a formato YOLO.

Lógica pura, sin dependencias: se prueba en `tests/test_coco.py`.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field

CLASS_ID = 0
CLASS_NAME = "placa"

_TIMESTAMP = re.compile(r"^\d{8}_\d{6}")


def source_stem(file_name: str) -> str:
    """
    Nombre de la foto ORIGINAL, sin el sufijo que añade Roboflow.

    Roboflow exporta `Foto-Placa-107-_jpg.rf.<hash>.jpg`, y las copias aumentadas
    de una misma foto comparten todo lo anterior a `.rf.`. Es la clave para
    detectar fugas: la misma foto en train y en test inflaría las métricas.
    """
    return file_name.split(".rf.")[0]


def find_leakage(train_names: list[str], eval_names: list[str]) -> set[str]:
    """
    Fotos originales que aparecen a la vez en entrenamiento y evaluación.

    Compara por `source_stem`, así detecta también los recortes de vista de
    puerta (`<original>.rf.<hash>__c0.jpg`) y las copias aumentadas de Roboflow.
    Cualquier resultado no vacío invalida las métricas: el modelo estaría siendo
    evaluado con fotos que ya vio.
    """
    return {source_stem(n) for n in train_names} & {source_stem(n) for n in eval_names}


def photo_family(file_name: str) -> str:
    """El dataset mezcla dos orígenes de foto; se evalúan por separado."""
    stem = source_stem(file_name)
    if stem.startswith("Foto-Placa"):
        return "foto_placa"
    if _TIMESTAMP.match(stem):
        return "fecha"
    return "otro"


def coco_bbox_to_yolo(
    bbox: list[float], img_w: int, img_h: int
) -> tuple[float, float, float, float] | None:
    """
    COCO `[x, y, w, h]` en píxeles, esquina superior izquierda
    →  YOLO `(cx, cy, w, h)` normalizado a [0, 1].

    Recorta al borde de la imagen: el aumentado de Roboflow rota las fotos ±25°
    y algunas cajas quedan sobresaliendo. Devuelve None si tras recortar la caja
    no tiene área (no se puede entrenar con ella).
    """
    x, y, w, h = bbox
    x1 = max(0.0, min(float(img_w), x))
    y1 = max(0.0, min(float(img_h), y))
    x2 = max(0.0, min(float(img_w), x + w))
    y2 = max(0.0, min(float(img_h), y + h))

    cw, ch = x2 - x1, y2 - y1
    if cw <= 0 or ch <= 0:
        return None

    return (
        (x1 + cw / 2) / img_w,
        (y1 + ch / 2) / img_h,
        cw / img_w,
        ch / img_h,
    )


def yolo_line(box: tuple[float, float, float, float]) -> str:
    cx, cy, w, h = box
    return f"{CLASS_ID} {cx:.6f} {cy:.6f} {w:.6f} {h:.6f}"


@dataclass
class ConvertedSplit:
    labels: dict[str, list[str]] = field(default_factory=dict)
    """file_name -> líneas YOLO. Incluye imágenes sin cajas (lista vacía)."""

    merged_from: Counter = field(default_factory=Counter)
    """Cuántas cajas venían de cada nombre de categoría antes de fusionar."""

    dropped_degenerate: int = 0
    widths_px: list[float] = field(default_factory=list)
    """Ancho de cada placa en píxeles de la imagen REAL (ver `real_sizes`)."""

    widths_long_side: list[float] = field(default_factory=list)
    """Ancho de placa como fracción del lado MAYOR de la imagen. Multiplicado por
    `imgsz` da los píxeles que ve realmente el modelo tras redimensionar."""


def convert_split(
    coco: dict, real_sizes: dict[str, tuple[int, int]] | None = None
) -> ConvertedSplit:
    """
    Convierte un `_annotations.coco.json` completo.

    **Todas las categorías se fusionan en la clase 0.** El dataset trae `Placa`
    y `placa` como categorías distintas (dos anotadores con distinta mayúscula)
    más un `plates` vacío. Mantenerlas separadas obligaría al modelo a aprender
    una diferencia que no existe.
    """
    names = {c["id"]: c["name"] for c in coco.get("categories", [])}
    images = {img["id"]: img for img in coco.get("images", [])}

    out = ConvertedSplit()
    for img in images.values():
        out.labels.setdefault(img["file_name"], [])

    for ann in coco.get("annotations", []):
        img = images.get(ann["image_id"])
        if img is None:
            continue
        out.merged_from[names.get(ann["category_id"], f"id={ann['category_id']}")] += 1

        box = coco_bbox_to_yolo(ann["bbox"], img["width"], img["height"])
        if box is None:
            out.dropped_degenerate += 1
            continue
        out.labels[img["file_name"]].append(yolo_line(box))
        real_w, real_h = (real_sizes or {}).get(img["file_name"], (img["width"], img["height"]))
        out.widths_px.append(box[2] * real_w)
        out.widths_long_side.append(box[2] * real_w / max(real_w, real_h))

    return out
