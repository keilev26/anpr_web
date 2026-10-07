"""
Prueba de humo del pipeline de producción completo (detección ONNX + PaddleOCR),
en un solo entorno Python 3.12, sin el antiguo truco de dos etapas (ya no hace
falta: PaddlePaddle sí tiene paquetes para 3.12).

    .venv/bin/python scripts/smoke_pipeline.py imagen1.jpg [imagen2.jpg ...]
"""

import argparse
import sys
import time
from pathlib import Path

import cv2

from anpr_ml.onnx_engine import OnnxCropper, OnnxDetector, PaddleOcr
from anpr_ml.pipeline import PlatePipeline

ML_ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    ap.add_argument("images", nargs="+", type=Path)
    ap.add_argument("--model", type=Path, default=ML_ROOT / "models/best.onnx")
    ap.add_argument("--min-agreement", type=int, default=1, help="1 para una sola imagen")
    args = ap.parse_args()

    print(f"Cargando detector ({args.model})…")
    t0 = time.monotonic()
    detector = OnnxDetector(str(args.model))
    print(f"  {time.monotonic() - t0:.1f}s")

    print("Cargando PaddleOCR (descarga los modelos la primera vez)…")
    t0 = time.monotonic()
    ocr = PaddleOcr()
    print(f"  {time.monotonic() - t0:.1f}s")

    pipeline = PlatePipeline(detector, ocr, OnnxCropper(), min_agreement=args.min_agreement)

    frames = []
    for p in args.images:
        img = cv2.imread(str(p))
        if img is None:
            print(f"No se pudo leer {p}", file=sys.stderr)
            return 1
        frames.append(img)

    t0 = time.monotonic()
    result = pipeline.run(frames)
    elapsed = time.monotonic() - t0

    print(f"\n{'='*50}")
    print(f"placa:            {result.plate}")
    print(f"confianza det.:   {result.confidence}")
    print(f"confianza OCR:    {result.ocr_confidence}")
    print(f"ancho de placa:   {result.plate_px_width} px")
    print(f"votos:            {result.votes}")
    print(f"razón (si None):  {result.reason}")
    print(f"lecturas fallidas:{result.failed_readings}")
    print(f"cajas encontradas:{result.boxes_found}")
    print(f"frames procesados:{result.frames_processed}")
    print(f"tiempo total:     {elapsed*1000:.0f} ms")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
