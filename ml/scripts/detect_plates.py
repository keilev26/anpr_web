"""
Prueba visual de lectura, etapa 1 de 2: detectar placas y guardar los recortes.

    /data/anpr/venvs/ml-train/bin/python scripts/detect_plates.py

Se separa en dos etapas porque PaddlePaddle no tiene paquetes para Python 3.14
(solo hasta 3.13) y el entorno con torch es 3.14. Así no se duplican los ~6 GB
de torch en un segundo entorno. La etapa 2 es `scripts/ocr_visual.py`.

Los recortes usan `crop_window`, la misma función que `OnnxCropper` en
producción: el OCR recibe exactamente lo que recibiría en el Lambda.
"""

import argparse
import json
import sys
from pathlib import Path

from PIL import Image

from anpr_ml.pipeline import Box, crop_window

ML_ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--images", type=Path, default=ML_ROOT / "datasets/peru-gate-view/test/images")
    ap.add_argument(
        "--model", type=Path, default=ML_ROOT.parent / "legacy/mqtt-camara-main/best.pt"
    )
    ap.add_argument("--plate-class", type=int, default=0)
    ap.add_argument("--conf", type=float, default=0.30, help="Mismo umbral que el pipeline")
    ap.add_argument("--imgsz", type=int, default=640)
    ap.add_argument("--device", default="0")
    ap.add_argument("--out", type=Path, default=ML_ROOT / "runs/ocr_visual")
    args = ap.parse_args()

    try:
        from ultralytics import YOLO
    except ImportError:
        print(
            "Ejecutar con el entorno de entrenamiento: /data/anpr/venvs/ml-train", file=sys.stderr
        )
        return 1

    crops_dir = args.out / "crops"
    crops_dir.mkdir(parents=True, exist_ok=True)
    model = YOLO(str(args.model))

    registros = []
    imagenes = sorted(p for p in args.images.iterdir() if p.suffix.lower() in {".jpg", ".png"})
    # Una imagen por llamada: con una lista, ultralytics mete todas en un mismo
    # lote y en 4 GB de VRAM no caben.
    for img_path in imagenes:
        res = model.predict(
            str(img_path),
            imgsz=args.imgsz,
            conf=args.conf,
            classes=[args.plate_class],
            device=args.device,
            verbose=False,
        )[0]
        src = Path(res.path)
        with Image.open(src) as im:
            im = im.convert("RGB")
            w, h = im.size
            dets = []
            orden = sorted(
                zip(res.boxes.xyxy.tolist(), res.boxes.conf.tolist(), strict=True),
                key=lambda bc: bc[0][2] - bc[0][0],
                reverse=True,  # la más ancha primero, como el pipeline
            )
            for k, (xyxy, conf) in enumerate(orden):
                box = Box(*(int(v) for v in xyxy), confidence=float(conf))
                ventana = crop_window(box, w, h)
                crop_path = crops_dir / f"{src.stem}__d{k}.png"
                im.crop(ventana).save(crop_path)
                dets.append(
                    {
                        "box": [box.x1, box.y1, box.x2, box.y2],
                        "conf": round(box.confidence, 3),
                        "ancho_px": box.width,
                        "crop": str(crop_path),
                    }
                )
        registros.append({"imagen": str(src), "detecciones": dets})

    salida = args.out / "detections.json"
    salida.write_text(json.dumps(registros, indent=2, ensure_ascii=False), encoding="utf-8")
    n_det = sum(len(r["detecciones"]) for r in registros)
    sin = sum(1 for r in registros if not r["detecciones"])
    print(f"{len(registros)} imágenes, {n_det} placas detectadas, {sin} sin detección")
    print(f"Recortes en {crops_dir}\nSiguiente: scripts/ocr_visual.py con el entorno ml-ocr")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
