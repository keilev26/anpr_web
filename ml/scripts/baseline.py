"""
Paso 2: línea base de `best.pt` SIN tocarlo.

    python scripts/baseline.py

Mide mAP sobre valid+test del dataset peruano (170 imágenes que el modelo nunca
vio), a 640 y 1280, por familia de fotos, y sobre la vista de puerta. Aplica el
criterio de reentrenamiento fijado ANTES de medir, para no mover la portería
después de ver los números.

Requiere torch + ultralytics:  UV_NO_CACHE=1 uv pip install -e ".[train]"
"""

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

ML_ROOT = Path(__file__).resolve().parents[1]
DATA = ML_ROOT / "datasets"

# Criterio de reentrenamiento. Fijado antes de medir; no cambiarlo tras ver resultados.
MIN_MAP50 = 0.90
MAX_GATE_DROP = 0.05

EVALS = [
    # (nombre, yaml, imgsz, nota)
    ("valtest_640", DATA / "peru-plates/eval/valtest.yaml", 640, "principal"),
    (
        "valtest_1280",
        DATA / "peru-plates/eval/valtest.yaml",
        1280,
        "cuánto se pierde por placas diminutas a 640",
    ),
    ("test_640", DATA / "peru-plates/eval/test.yaml", 640, "solo 32 imágenes: poco fiable"),
    (
        "foto_placa_640",
        DATA / "peru-plates/eval/valtest_foto_placa.yaml",
        640,
        "familia Foto-Placa",
    ),
    (
        "fecha_640",
        DATA / "peru-plates/eval/valtest_fecha.yaml",
        640,
        "familia por fecha (tarde/noche)",
    ),
    ("gate_view_640", DATA / "peru-gate-view/valtest.yaml", 640, "recortes de vista de puerta"),
]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--model", type=Path, default=ML_ROOT.parent / "legacy/mqtt-camara-main/best.pt"
    )
    ap.add_argument("--device", default="0", help="'0' para GPU, 'cpu' para CPU")
    ap.add_argument(
        "--plate-class",
        type=int,
        default=0,
        help="Índice de la clase placa. best.pt nombra sus clases '0' y '2', así que no "
        "se puede deducir del nombre. Se identificó midiendo IoU contra las etiquetas de "
        "valid: la clase 0 encuentra el 89%% de las placas; la 1 (vehículo), el 0%%.",
    )
    ap.add_argument("--out", type=Path, default=ML_ROOT / "metrics" / "baseline_best_pt.json")
    args = ap.parse_args()

    try:
        import torch
        from ultralytics import YOLO
    except ImportError:
        print('Falta el stack:  UV_NO_CACHE=1 uv pip install -e ".[train]"', file=sys.stderr)
        return 1

    if args.device != "cpu" and not torch.cuda.is_available():
        print(
            "CUDA no disponible. Arregla el driver (paso 0c) o usa --device cpu.", file=sys.stderr
        )
        return 1

    model = YOLO(str(args.model))
    names = dict(model.names)
    print(f"Clases del modelo: {names}")

    idx = args.plate_class
    if idx != 0:
        # Las etiquetas del dataset son clase 0 y val() empareja por índice de clase.
        # Evaluar otra clase exigiría reetiquetar; no se soporta.
        print("La evaluación solo es válida si la clase placa es la 0.", file=sys.stderr)
        return 2

    # Informativo: qué otras clases dispara el modelo. Se registra en el informe
    # porque el pipeline de inferencia debe filtrar a la clase placa.
    muestra = sorted((DATA / "peru-plates/valid/images").iterdir())[:20]
    disparos = Counter()
    for r in model.predict(
        [str(p) for p in muestra], imgsz=640, device=args.device, verbose=False, stream=True
    ):
        disparos.update(int(c) for c in r.boxes.cls.tolist())
    otras = {names[c]: n for c, n in disparos.items() if c != idx}
    print(f"Detecciones por clase en 20 imágenes: { {names[c]: n for c, n in disparos.items()} }")
    if otras:
        print(
            f"El modelo también detecta otras clases: {otras}. No afectan a la "
            "métrica, que se calcula solo para la clase placa."
        )

    resultados = {}
    for nombre, yaml, imgsz, nota in EVALS:
        print(f"\n{nombre}  ({nota})")
        # SIN single_cls, a propósito. best.pt tiene una segunda clase (vehículo) y
        # val() no aplica el filtro `classes`: con single_cls sus cajas contarían como
        # placas falsas. Medido en valid+test: mAP@50 0,555 sin él frente a 0,223 con él.
        # Sin él se evalúa por clase, y las etiquetas solo tienen la clase 0.
        m = model.val(
            data=str(yaml),
            imgsz=imgsz,
            batch=8 if imgsz <= 640 else 2,
            device=args.device,
            plots=False,
            verbose=False,
            project=str(ML_ROOT / "runs/baseline"),
            name=nombre,
            exist_ok=True,
        )
        resultados[nombre] = {
            "imgsz": imgsz,
            "nota": nota,
            "map50": round(float(m.box.map50), 4),
            "map50_95": round(float(m.box.map), 4),
            "precision": round(float(m.box.mp), 4),
            "recall": round(float(m.box.mr), 4),
        }
        r = resultados[nombre]
        print(
            f"  mAP@50={r['map50']}  mAP@50-95={r['map50_95']}  P={r['precision']}  R={r['recall']}"
        )

    principal = resultados["valtest_640"]["map50"]
    caida = principal - resultados["gate_view_640"]["map50"]
    motivos = []
    if principal < MIN_MAP50:
        motivos.append(f"mAP@50 {principal} < {MIN_MAP50} en valid+test a 640")
    if caida > MAX_GATE_DROP:
        motivos.append(f"cae {caida:.3f} en vista de puerta (> {MAX_GATE_DROP})")

    informe = {
        "modelo": str(args.model),
        "clases_modelo": names,
        "clase_placa": idx,
        "detecciones_otras_clases_en_muestra": otras,
        "device": args.device,
        "criterio": {"min_map50": MIN_MAP50, "max_caida_vista_puerta": MAX_GATE_DROP},
        "resultados": resultados,
        "reentrenar": bool(motivos),
        "motivos": motivos,
        "advertencias": [
            "Hay placas visibles sin etiquetar en el dataset: detectarlas cuenta como "
            "falso positivo, así que la precisión está algo subestimada.",
            "test_640 tiene 32 imágenes: usar valtest_640 como referencia.",
        ],
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(informe, indent=2, ensure_ascii=False), encoding="utf-8")

    print(
        "\nDECISIÓN:",
        "REENTRENAR — " + "; ".join(motivos) if motivos else "no hace falta reentrenar",
    )
    print(f"Informe en {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
