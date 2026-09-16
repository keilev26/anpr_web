"""
Exporta best.pt a ONNX y comprueba que no se degrada.

Por qué ONNX: el contenedor Lambda usa onnxruntime en vez de torch+ultralytics.
La imagen baja de varios GB a unos cientos de MB, y eso reduce directamente el
cold start, que es el mayor riesgo de latencia del camino crítico.

Exportar sin medir es un acto de fe: este script guarda el mAP ANTES y DESPUÉS.

    python scripts/export_onnx.py --model best.pt --data /ruta/data.yaml

Requiere: uv pip install -e ".[train]"
"""

import argparse
import json
import sys
from pathlib import Path


def main() -> int:
    ap = argparse.ArgumentParser(description="Exporta el modelo a ONNX")
    ap.add_argument("--model", default="best.pt", type=Path)
    ap.add_argument("--data", type=Path, default=None,
                    help="data.yaml del dataset, para medir mAP. Sin él solo exporta.")
    ap.add_argument("--imgsz", type=int, default=640)
    ap.add_argument("--opset", type=int, default=17)
    ap.add_argument("--out", type=Path, default=Path("metrics.json"))
    args = ap.parse_args()

    try:
        from ultralytics import YOLO
    except ImportError:
        print('Falta el stack de visión:  uv pip install -e ".[train]"', file=sys.stderr)
        return 1

    metrics: dict = {"model": str(args.model), "imgsz": args.imgsz, "opset": args.opset}

    model = YOLO(str(args.model))
    print(f"Modelo: {args.model}  clases={model.names}")

    if args.data:
        print("\nMidiendo el modelo original (línea base)…")
        base = model.val(data=str(args.data), imgsz=args.imgsz, verbose=False)
        metrics["pytorch"] = {
            "map50": float(base.box.map50),
            "map50_95": float(base.box.map),
        }
        print(f"  mAP@50    = {base.box.map50:.4f}")
        print(f"  mAP@50-95 = {base.box.map:.4f}")
    else:
        print("\nSin --data: no se puede medir mAP. Exportando a ciegas.")

    print("\nExportando a ONNX…")
    ruta = model.export(format="onnx", imgsz=args.imgsz, opset=args.opset, simplify=True)
    print(f"  {ruta}")
    metrics["onnx_path"] = str(ruta)

    if args.data:
        print("\nMidiendo el ONNX exportado…")
        onnx_model = YOLO(str(ruta))
        post = onnx_model.val(data=str(args.data), imgsz=args.imgsz, verbose=False)
        metrics["onnx"] = {
            "map50": float(post.box.map50),
            "map50_95": float(post.box.map),
        }
        caida = metrics["pytorch"]["map50"] - metrics["onnx"]["map50"]
        metrics["map50_delta"] = caida
        print(f"  mAP@50    = {post.box.map50:.4f}   (delta {caida:+.4f})")

        # Una caída de más de 1 punto no es ruido de cuantización.
        if caida > 0.01:
            print("\n  AVISO: el ONNX perdió más de 1 punto de mAP@50.")
            print("  Revisa opset e imgsz antes de desplegarlo.")

    args.out.write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    print(f"\nMétricas guardadas en {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
