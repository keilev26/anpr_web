"""
Convierte el export COCO de Roboflow a la estructura YOLO que usa Ultralytics.

    python scripts/coco_to_yolo.py

Tres decisiones:

- **Fusiona todas las categorías en una sola clase `placa`.** El dataset trae
  `Placa` y `placa` como clases distintas (dos anotadores).
- **Las imágenes se enlazan, no se copian.** Copiarlas duplicaría 2 GB con el
  disco casi lleno. Solo se escriben las etiquetas `.txt`.
- **Aborta si la misma foto original aparece en dos splits.** Inflaría las métricas.

Además genera listas de evaluación por familia de fotos, para el paso de línea base.
"""

import argparse
import json
import os
import statistics as st
import sys
from collections import Counter
from pathlib import Path

from anpr_ml.coco import CLASS_NAME, convert_split, photo_family, source_stem

SPLITS = ("train", "valid", "test")
ML_ROOT = Path(__file__).resolve().parents[1]


def _stats(values: list[float]) -> dict:
    if not values:
        return {}
    q = st.quantiles(values, n=10) if len(values) >= 2 else [values[0]] * 9
    return {
        "min": round(min(values), 1),
        "p10": round(q[0], 1),
        "mediana": round(st.median(values), 1),
        "p90": round(q[8], 1),
        "max": round(max(values), 1),
    }


def _real_sizes(src: Path, split: str, coco: dict) -> tuple[dict, Counter, list[str]]:
    """
    Lee el tamaño real de TODAS las imágenes (solo la cabecera, es rápido).

    En este export el JSON declara 1536x2048 pero los archivos miden 3000x4000.
    Un reescalado uniforme es inocuo: las cajas YOLO están normalizadas. Lo que sí
    sería grave es un cambio de PROPORCIÓN (p. ej. orientación EXIF no aplicada):
    las cajas quedarían giradas. Solo eso se trata como error.
    """
    from PIL import Image

    sizes, escalas, problemas = {}, Counter(), []
    for img in coco["images"]:
        with Image.open(src / split / img["file_name"]) as im:
            rw, rh = im.size
        sizes[img["file_name"]] = (rw, rh)
        sx, sy = rw / img["width"], rh / img["height"]
        escalas[round(sx, 4)] += 1
        if abs(sx - sy) > 1e-3:
            problemas.append(
                f"{split}/{img['file_name']}: proporción distinta "
                f"(real {rw}x{rh}, JSON {img['width']}x{img['height']})"
            )
    return sizes, escalas, problemas


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    ap.add_argument("--src", type=Path, default=ML_ROOT / "roboflow_images")
    ap.add_argument("--dst", type=Path, default=ML_ROOT / "datasets" / "peru-plates")
    ap.add_argument("--report", type=Path, default=ML_ROOT / "metrics" / "dataset_report.json")
    args = ap.parse_args()

    src, dst = args.src.resolve(), args.dst.resolve()
    report: dict = {"fuente": str(src), "clase": CLASS_NAME, "splits": {}}
    fuentes: dict[str, set[str]] = {}
    image_paths: dict[str, list[Path]] = {}
    problemas_dims: list[str] = []

    for split in SPLITS:
        ann_file = src / split / "_annotations.coco.json"
        if not ann_file.exists():
            print(f"No existe {ann_file}", file=sys.stderr)
            return 1
        coco = json.loads(ann_file.read_text(encoding="utf-8"))
        sizes, escalas, problemas = _real_sizes(src, split, coco)
        problemas_dims += problemas
        conv = convert_split(coco, real_sizes=sizes)

        img_dir = dst / split / "images"
        lbl_dir = dst / split / "labels"
        img_dir.mkdir(parents=True, exist_ok=True)
        lbl_dir.mkdir(parents=True, exist_ok=True)

        paths = []
        for file_name, lines in conv.labels.items():
            link = img_dir / file_name
            target = src / split / file_name
            if link.is_symlink() or link.exists():
                link.unlink()
            # Enlace relativo: sigue funcionando si se mueve el repo entero.
            link.symlink_to(os.path.relpath(target, img_dir))
            (lbl_dir / (Path(file_name).stem + ".txt")).write_text(
                "\n".join(lines) + ("\n" if lines else ""), encoding="utf-8"
            )
            paths.append(link)
        image_paths[split] = paths

        por_imagen = Counter(len(v) for v in conv.labels.values())
        srcs = {source_stem(f) for f in conv.labels}
        fuentes[split] = srcs
        report["splits"][split] = {
            "imagenes": len(conv.labels),
            "cajas": sum(len(v) for v in conv.labels.values()),
            "fotos_originales": len(srcs),
            "copias_por_original": round(len(conv.labels) / max(1, len(srcs)), 2),
            "categorias_fusionadas": dict(conv.merged_from),
            "cajas_descartadas_sin_area": conv.dropped_degenerate,
            "cajas_por_imagen": {str(k): v for k, v in sorted(por_imagen.items())},
            "escala_real_vs_json": {str(k): v for k, v in escalas.items()},
            "ancho_placa_px_real": _stats(conv.widths_px),
            # Lo que ve el modelo a imgsz=640, tras reducir el lado mayor a 640.
            "ancho_placa_px_a_640": _stats([f * 640 for f in conv.widths_long_side]),
            "familias": dict(Counter(photo_family(f) for f in conv.labels)),
        }

    # Fugas: la misma foto original en dos splits.
    fugas = {}
    for a, b in (("train", "valid"), ("train", "test"), ("valid", "test")):
        comunes = sorted(fuentes[a] & fuentes[b])
        fugas[f"{a}∩{b}"] = len(comunes)
        if comunes:
            print(f"FUGA: {len(comunes)} fotos en {a} y {b}, p.ej. {comunes[:3]}", file=sys.stderr)
    report["fugas"] = fugas
    report["verificacion_dimensiones"] = problemas_dims or "ok"

    # data.yaml principal
    (dst / "data.yaml").write_text(
        f"path: {dst}\n"
        "train: train/images\n"
        "val: valid/images\n"
        "test: test/images\n"
        "nc: 1\n"
        f"names:\n  0: {CLASS_NAME}\n",
        encoding="utf-8",
    )

    # Evaluación de línea base: valid+test juntos (test solo tiene 32 imágenes),
    # y por familia de fotos. Ultralytics acepta un .txt con rutas como `val`.
    lists = dst / "eval"
    lists.mkdir(exist_ok=True)
    evaluacion = image_paths["valid"] + image_paths["test"]
    grupos = {
        "valtest": evaluacion,
        "test": image_paths["test"],
        "valtest_foto_placa": [p for p in evaluacion if photo_family(p.name) == "foto_placa"],
        "valtest_fecha": [p for p in evaluacion if photo_family(p.name) == "fecha"],
    }
    for nombre, paths in grupos.items():
        (lists / f"{nombre}.txt").write_text(
            "\n".join(str(p) for p in paths) + "\n", encoding="utf-8"
        )
        (lists / f"{nombre}.yaml").write_text(
            f"path: {dst}\ntrain: {lists / nombre}.txt\nval: {lists / nombre}.txt\n"
            f"nc: 1\nnames:\n  0: {CLASS_NAME}\n",
            encoding="utf-8",
        )
    report["conjuntos_evaluacion"] = {k: len(v) for k, v in grupos.items()}

    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"Dataset YOLO en {dst}")
    for split, r in report["splits"].items():
        print(
            f"  {split:5} {r['imagenes']:5} imágenes  {r['cajas']:5} cajas  "
            f"fusionadas {r['categorias_fusionadas']}  "
            f"descartadas {r['cajas_descartadas_sin_area']}"
        )
    print(f"  fugas entre splits: {fugas}")
    print(f"  proporciones: {report['verificacion_dimensiones']}")
    for split, r in report["splits"].items():
        print(f"  {split:5} ancho de placa real {r['ancho_placa_px_real']}")
        print(f"        visto a imgsz=640    {r['ancho_placa_px_a_640']}")
    print(f"  conjuntos de evaluación: {report['conjuntos_evaluacion']}")
    print(f"Informe en {args.report}")
    return 1 if any(fugas.values()) or problemas_dims else 0


if __name__ == "__main__":
    raise SystemExit(main())
