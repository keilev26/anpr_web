"""
Mide el ancho en píxeles de las placas detectadas.

ES LA MEDICIÓN MÁS IMPORTANTE DE F4, y conviene hacerla antes que cualquier
optimización de modelo. Si a la distancia real del portón la placa ocupa menos
de ~60-80 px de ancho, el cuello de botella es ÓPTICO: ningún reentrenamiento,
cuantización ni cambio de OCR lo arregla. La decisión pasa a ser de cámara.

Recuerda que `legacy/mqtt-camara-main/mqtt+camara.py` pedía
`startLiveviewWithSize(["M"])`, un preview reducido, y luego alimentaba YOLO a
640 px. Este script dice si eso alcanza.

    python scripts/measure_plate_px.py --images ./muestras --model best.pt

Requiere: uv pip install -e ".[train]"
"""

import argparse
import statistics
import sys
from pathlib import Path

MIN_USABLE = 60
COMODO = 100


def main() -> int:
    ap = argparse.ArgumentParser(description="Mide el ancho de placa en píxeles")
    ap.add_argument(
        "--images",
        required=True,
        type=Path,
        help="Carpeta con fotos tomadas DESDE LA POSICIÓN REAL de la cámara",
    )
    ap.add_argument("--model", default="best.pt", type=Path)
    ap.add_argument("--conf", type=float, default=0.30)
    ap.add_argument("--imgsz", type=int, default=640)
    args = ap.parse_args()

    try:
        from ultralytics import YOLO
    except ImportError:
        print('Falta el stack de visión:  uv pip install -e ".[train]"', file=sys.stderr)
        return 1

    fotos = sorted(
        p for p in args.images.rglob("*") if p.suffix.lower() in {".jpg", ".jpeg", ".png", ".bmp"}
    )
    if not fotos:
        print(f"No hay imágenes en {args.images}", file=sys.stderr)
        return 1

    model = YOLO(str(args.model))
    anchos: list[int] = []
    sin_deteccion = 0

    for foto in fotos:
        res = model.predict(str(foto), imgsz=args.imgsz, conf=args.conf, verbose=False)
        cajas = [b for r in res for b in r.boxes]
        if not cajas:
            sin_deteccion += 1
            continue
        # La más ancha: la placa del vehículo más cercano.
        anchos.append(max(int(b.xyxy[0][2] - b.xyxy[0][0]) for b in cajas))

    print(f"\nImágenes            : {len(fotos)}")
    print(f"Sin detección       : {sin_deteccion}  ({sin_deteccion / len(fotos):.0%})")
    if not anchos:
        print("\nNinguna placa detectada. Revisa el modelo, el umbral o el encuadre.")
        return 1

    anchos.sort()
    p = statistics.quantiles(anchos, n=100) if len(anchos) >= 2 else [anchos[0]] * 99
    print("\nAncho de placa (px)")
    print(f"  mínimo            : {anchos[0]}")
    print(f"  percentil 10      : {p[9]:.0f}")
    print(f"  mediana           : {statistics.median(anchos):.0f}")
    print(f"  máximo            : {anchos[-1]}")

    bajo = sum(1 for a in anchos if a < MIN_USABLE)
    print(f"\n  por debajo de {MIN_USABLE}px : {bajo}/{len(anchos)}  ({bajo / len(anchos):.0%})")

    mediana = statistics.median(anchos)
    print("\nVEREDICTO")
    if mediana < MIN_USABLE:
        print(f"  La placa mide {mediana:.0f}px de mediana, por debajo de {MIN_USABLE}.")
        print("  El problema es ÓPTICO, no del modelo. Antes de tocar nada de ML:")
        print("    - pedir un liveview mayor a la cámara, o")
        print("    - acercar/enfocar la cámara, o")
        print("    - cambiar a una cámara IP con más resolución.")
    elif mediana < COMODO:
        print(f"  {mediana:.0f}px de mediana: justo. Debería leer, pero sin margen.")
        print(f"  El {bajo / len(anchos):.0%} de los casos queda bajo el mínimo y fallará.")
    else:
        print(f"  {mediana:.0f}px de mediana: suficiente. La cámara no es el cuello de botella.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
