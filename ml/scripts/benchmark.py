"""
Mide la precisión real del pipeline completo sobre imágenes etiquetadas.

Produce la línea base que hoy NO EXISTE. Sin ella no se puede afirmar que
exportar a ONNX, cambiar de cámara o reentrenar haya mejorado algo.

Espera una carpeta donde el nombre de cada archivo sea su placa real:

    muestras/
      CUB-604_01.jpg
      CUB-604_02.jpg
      V1A-882_01.jpg

    python scripts/benchmark.py --images ./muestras --model best.onnx

Requiere: uv pip install -e ".[runtime]"
"""

import argparse
import json
import sys
from collections import Counter
from pathlib import Path


def placa_esperada(p: Path) -> str:
    return p.stem.split("_")[0].upper()


def main() -> int:
    ap = argparse.ArgumentParser(description="Mide la precisión del pipeline")
    ap.add_argument("--images", required=True, type=Path)
    ap.add_argument("--model", default="best.onnx", type=Path)
    ap.add_argument(
        "--ocr-models-dir", default=None, help="Modelos de PaddleOCR locales (opcional)"
    )
    ap.add_argument("--conf", type=float, default=0.30)
    ap.add_argument("--out", type=Path, default=Path("benchmark.json"))
    args = ap.parse_args()

    try:
        import cv2

        from anpr_ml.onnx_engine import OnnxCropper, OnnxDetector, PaddleOcr
        from anpr_ml.pipeline import PlatePipeline
    except ImportError as exc:
        print(
            f'Falta el runtime de visión ({exc}):  uv pip install -e ".[runtime]"', file=sys.stderr
        )
        return 1

    fotos = sorted(
        p for p in args.images.rglob("*") if p.suffix.lower() in {".jpg", ".jpeg", ".png"}
    )
    if not fotos:
        print(f"No hay imágenes en {args.images}", file=sys.stderr)
        return 1

    pipeline = PlatePipeline(
        OnnxDetector(str(args.model)),
        PaddleOcr(args.ocr_models_dir),
        OnnxCropper(),
        min_box_confidence=args.conf,
        # Cada imagen del benchmark es un solo fotograma: con el consenso de 2 de
        # producción nunca se aceptaría nada. Esto mide la LECTURA por fotograma;
        # el consenso se evalúa aparte, sobre ráfagas reales.
        min_agreement=1,
    )

    stats = Counter()
    anchos: list[int] = []
    fallos: list[dict] = []

    for foto in fotos:
        esperada = placa_esperada(foto)
        r = pipeline.run([cv2.imread(str(foto))])

        if r.plate_px_width:
            anchos.append(r.plate_px_width)
        if r.boxes_found:
            stats["detectadas"] += 1

        if r.plate == esperada:
            stats["correctas"] += 1
            if r.corrections:
                stats["correctas_con_correccion"] += 1
        elif r.plate is not None:
            stats["mal_leidas"] += 1
            fallos.append({"archivo": foto.name, "esperada": esperada, "leida": r.plate})
        else:
            stats["no_leidas"] += 1
            fallos.append(
                {
                    "archivo": foto.name,
                    "esperada": esperada,
                    "leida": None,
                    "descartadas": r.failed_readings,
                    "ancho_px": r.plate_px_width,
                }
            )

    n = len(fotos)
    print(f"\nImágenes            : {n}")
    print(f"Placa detectada     : {stats['detectadas'] / n:.1%}")
    print(f"Leída correctamente : {stats['correctas'] / n:.1%}")
    print(f"  con corrección    : {stats['correctas_con_correccion']}")
    print(f"MAL leída           : {stats['mal_leidas'] / n:.1%}  <-- lo más grave")
    print(f"No leída            : {stats['no_leidas'] / n:.1%}")
    if anchos:
        anchos.sort()
        print(f"\nAncho de placa      : mediana {anchos[len(anchos) // 2]}px, mínimo {anchos[0]}px")

    print("\nUna placa MAL leída es peor que una no leída: la no leída deja la")
    print("puerta cerrada, la mal leída puede abrirla al vehículo equivocado.")

    args.out.write_text(
        json.dumps(
            {"total": n, "stats": dict(stats), "fallos": fallos}, indent=2, ensure_ascii=False
        ),
        encoding="utf-8",
    )
    print(f"\nDetalle en {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
