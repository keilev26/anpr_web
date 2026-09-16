"""
Paso 4: fine-tuning de best.pt con placas peruanas + vista de puerta.

    python scripts/train.py --name peru_v1

Solo tiene sentido si `scripts/baseline.py` decidió REENTRENAR.

Requiere torch + ultralytics:  UV_NO_CACHE=1 uv pip install -e ".[train]"
"""

import argparse
import json
import sys
from pathlib import Path

from anpr_ml.coco import find_leakage

ML_ROOT = Path(__file__).resolve().parents[1]
DATA = ML_ROOT / "datasets"
MIN_BATCH = 4


def _images(*dirs: Path) -> list[Path]:
    return sorted(p for d in dirs for p in d.iterdir() if p.suffix.lower() in {".jpg", ".png"})


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--name", required=True)
    ap.add_argument(
        "--base",
        type=Path,
        default=ML_ROOT.parent / "legacy/mqtt-camara-main/best.pt",
        help="Pesos de partida. Si autobatch da < 4, probar yolo11s.pt",
    )
    ap.add_argument("--no-gate-view", action="store_true")
    ap.add_argument("--epochs", type=int, default=50)
    ap.add_argument("--patience", type=int, default=15)
    ap.add_argument("--imgsz", type=int, default=640)
    ap.add_argument("--device", default="0")
    args = ap.parse_args()

    try:
        import torch
        from ultralytics import YOLO
    except ImportError:
        print('Falta el stack:  UV_NO_CACHE=1 uv pip install -e ".[train]"', file=sys.stderr)
        return 1
    if args.device != "cpu" and not torch.cuda.is_available():
        print("CUDA no disponible (paso 0c).", file=sys.stderr)
        return 1

    fuentes_train = [DATA / "peru-plates/train/images"]
    if not args.no_gate_view:
        fuentes_train.append(DATA / "peru-gate-view/train/images")
    train = _images(*fuentes_train)
    evaluacion = _images(
        DATA / "peru-plates/valid/images",
        DATA / "peru-plates/test/images",
        DATA / "peru-gate-view/valid/images",
        DATA / "peru-gate-view/test/images",
    )

    # Sin esto, un solo recorte de una foto de test en train invalida todas las métricas.
    fuga = find_leakage([p.name for p in train], [p.name for p in evaluacion])
    if fuga:
        print(
            f"ABORTADO: {len(fuga)} fotos en train y en evaluación, p.ej. {sorted(fuga)[:3]}",
            file=sys.stderr,
        )
        return 1
    print(
        f"Comprobación de fugas OK: {len(train)} imágenes de train, {len(evaluacion)} de evaluación"
    )

    lists = ML_ROOT / "runs" / "lists" / args.name
    lists.mkdir(parents=True, exist_ok=True)
    (lists / "train.txt").write_text("\n".join(map(str, train)) + "\n")
    data_yaml = lists / "data.yaml"
    data_yaml.write_text(
        f"train: {lists / 'train.txt'}\nval: {DATA / 'peru-plates/valid/images'}\n"
        "nc: 1\nnames:\n  0: placa\n"
    )

    model = YOLO(str(args.base))
    model.train(
        data=str(data_yaml),
        imgsz=args.imgsz,
        epochs=args.epochs,
        patience=args.patience,
        # 4 GB de VRAM: el batch 16 del entrenamiento original no entra.
        batch=-1,
        amp=True,
        # 7,5 GB de RAM: pocos workers y sin cachear imágenes de 3000x4000.
        workers=4,
        cache=False,
        device=args.device,
        seed=0,
        deterministic=True,
        project=str(ML_ROOT / "runs/train"),
        name=args.name,
        exist_ok=False,
    )

    trainer = model.trainer
    batch = int(trainer.batch_size)
    avisos = []
    if batch < MIN_BATCH:
        avisos.append(
            f"autobatch eligió {batch} (< {MIN_BATCH}): gradientes ruidosos. "
            "Repetir con --base yolo11s.pt"
        )
        print("AVISO:", avisos[-1])

    best = YOLO(str(trainer.best))
    nuevos = {}
    for nombre, yaml in (
        ("valtest_640", DATA / "peru-plates/eval/valtest.yaml"),
        ("gate_view_640", DATA / "peru-gate-view/valtest.yaml"),
    ):
        m = best.val(
            data=str(yaml),
            imgsz=640,
            batch=8,
            device=args.device,
            plots=False,
            verbose=False,
            project=str(ML_ROOT / "runs/eval"),
            name=f"{args.name}_{nombre}",
            exist_ok=True,
        )
        nuevos[nombre] = {
            "map50": round(float(m.box.map50), 4),
            "map50_95": round(float(m.box.map), 4),
        }

    base_file = ML_ROOT / "metrics" / "baseline_best_pt.json"
    base = json.loads(base_file.read_text())["resultados"] if base_file.exists() else {}
    comparacion = {
        k: {
            "antes": base.get(k, {}).get("map50"),
            "despues": v["map50"],
            "mejora": (v["map50"] > base[k]["map50"]) if k in base else None,
        }
        for k, v in nuevos.items()
    }

    informe = {
        "nombre": args.name,
        "base": str(args.base),
        "batch_autobatch": batch,
        "epocas_max": args.epochs,
        "epocas_realizadas": int(trainer.epoch) + 1,
        "imagenes_train": len(train),
        "vista_de_puerta": not args.no_gate_view,
        "pesos": str(trainer.best),
        "resultados": nuevos,
        "comparacion": comparacion,
        "avisos": avisos,
        "reemplaza_al_actual": all(c["mejora"] for c in comparacion.values()),
    }
    out = ML_ROOT / "metrics" / f"train_{args.name}.json"
    out.write_text(json.dumps(informe, indent=2, ensure_ascii=False), encoding="utf-8")
    for k, c in comparacion.items():
        print(f"  {k:14} antes={c['antes']}  después={c['despues']}  mejora={c['mejora']}")
    print(f"Informe en {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
