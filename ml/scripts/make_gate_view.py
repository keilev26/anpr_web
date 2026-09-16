"""
Genera el dataset "vista de puerta" a partir de datasets/peru-plates.

Toma las fotos de calle (autos lejos, varias placas) y recorta alrededor de cada
placa elegible para obtener encuadres parecidos a los de una cámara de acceso.
Las cajas se recalculan: recortar a mano en un editor dejaría las etiquetas
apuntando a coordenadas viejas sin ningún error visible.

    python scripts/make_gate_view.py

Respeta los splits (los recortes de test solo van a test) y conserva en el
nombre la parte anterior a `.rf.`, así la comprobación de fugas sigue funcionando.

LÍMITE: simula el encuadre, NO la resolución de la cámara Sony. No responde si
la cámara real alcanza; eso requiere fotos tomadas desde la puerta.
"""

import argparse
import json
import random
import statistics as st
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

from PIL import Image

from anpr_ml.crops import CropParams, CropResult, plan_crop

ML_ROOT = Path(__file__).resolve().parents[1]
SPLITS = ("train", "valid", "test")


def _read_boxes(label: Path, w: int, h: int) -> list[tuple[float, float, float, float]]:
    boxes = []
    for line in label.read_text().splitlines():
        if not line.strip():
            continue
        _, cx, cy, bw, bh = map(float, line.split())
        boxes.append(((cx - bw / 2) * w, (cy - bh / 2) * h, (cx + bw / 2) * w, (cy + bh / 2) * h))
    return boxes


def _process(job: tuple) -> dict:
    img_path, label_path, out_img_dir, out_lbl_dir, per_image, seed, params = job
    # Semilla derivada del nombre: resultado idéntico sin importar el orden de los procesos.
    rng = random.Random(f"{seed}:{img_path.name}")
    stats = {"recortes": 0, "rechazos": Counter(), "escalas": [], "placa_px": [], "bytes": 0}

    with Image.open(img_path) as im:
        im.load()
        w, h = im.size
        boxes = _read_boxes(label_path, w, h)
        orden = list(range(len(boxes)))
        rng.shuffle(orden)

        hechos = 0
        for target in orden:
            if hechos >= per_image:
                break
            r = plan_crop(w, h, boxes, target, rng, params)
            if not isinstance(r, CropResult):
                stats["rechazos"][r] += 1
                continue

            crop = im.crop(tuple(round(v) for v in r.window)).convert("RGB")
            crop = crop.resize((params.out_w, params.out_h), Image.Resampling.LANCZOS)

            name = f"{img_path.stem}__c{hechos}"
            out = out_img_dir / f"{name}.jpg"
            crop.save(out, quality=90)
            (out_lbl_dir / f"{name}.txt").write_text(
                "".join(f"0 {cx:.6f} {cy:.6f} {bw:.6f} {bh:.6f}\n" for cx, cy, bw, bh in r.labels)
            )
            stats["recortes"] += 1
            stats["escalas"].append(r.scale)
            stats["placa_px"].append(r.plate_px_out)
            stats["bytes"] += out.stat().st_size
            hechos += 1
    return stats


def _summary(values: list[float]) -> dict:
    if len(values) < 2:
        return {}
    q = st.quantiles(values, n=10)
    return {
        "min": round(min(values), 2),
        "p10": round(q[0], 2),
        "mediana": round(st.median(values), 2),
        "p90": round(q[8], 2),
        "max": round(max(values), 2),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="Genera recortes de vista de puerta")
    ap.add_argument("--src", type=Path, default=ML_ROOT / "datasets" / "peru-plates")
    ap.add_argument("--dst", type=Path, default=ML_ROOT / "datasets" / "peru-gate-view")
    ap.add_argument(
        "--per-image",
        type=int,
        default=2,
        help="Máximo de recortes por imagen: evita sobrerrepresentar las fotos con 8 placas",
    )
    ap.add_argument(
        "--plate-px",
        default="80-200",
        help="Ancho de placa en el recorte final. Ajustar cuando haya fotos reales de la puerta",
    )
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--report", type=Path, default=ML_ROOT / "metrics" / "gate_view_report.json")
    args = ap.parse_args()

    lo, hi = (int(v) for v in args.plate_px.split("-"))
    params = CropParams(plate_px_min=lo, plate_px_max=hi)
    src, dst = args.src.resolve(), args.dst.resolve()

    report: dict = {
        "parametros": {
            "per_image": args.per_image,
            "plate_px": [lo, hi],
            "max_upscale": params.max_upscale,
            "min_native_px": params.min_native_px,
            "salida": [params.out_w, params.out_h],
            "seed": args.seed,
        },
        "splits": {},
    }

    for split in SPLITS:
        out_img, out_lbl = dst / split / "images", dst / split / "labels"
        out_img.mkdir(parents=True, exist_ok=True)
        out_lbl.mkdir(parents=True, exist_ok=True)

        imgs = sorted((src / split / "images").iterdir())
        jobs = [
            (
                p,
                src / split / "labels" / f"{p.stem}.txt",
                out_img,
                out_lbl,
                args.per_image,
                args.seed,
                params,
            )
            for p in imgs
        ]

        total = {"recortes": 0, "rechazos": Counter(), "escalas": [], "placa_px": [], "bytes": 0}
        with ProcessPoolExecutor(max_workers=args.workers) as ex:
            for s in ex.map(_process, jobs, chunksize=8):
                total["recortes"] += s["recortes"]
                total["rechazos"].update(s["rechazos"])
                total["escalas"] += s["escalas"]
                total["placa_px"] += s["placa_px"]
                total["bytes"] += s["bytes"]

        report["splits"][split] = {
            "imagenes_origen": len(imgs),
            "recortes": total["recortes"],
            "rechazos": dict(total["rechazos"]),
            "escala": _summary(total["escalas"]),
            "ampliados": sum(1 for e in total["escalas"] if e > 1),
            "ancho_placa_px": _summary(total["placa_px"]),
            "mb": round(total["bytes"] / 1e6, 1),
        }
        r = report["splits"][split]
        print(
            f"  {split:5} {r['imagenes_origen']:5} fotos -> {r['recortes']:5} recortes  "
            f"({r['mb']} MB)  ampliados {r['ampliados']}  rechazos {r['rechazos']}"
        )

    (dst / "data.yaml").write_text(
        f"path: {dst}\ntrain: train/images\nval: valid/images\ntest: test/images\n"
        "nc: 1\nnames:\n  0: placa\n",
        encoding="utf-8",
    )
    (dst / "valtest.yaml").write_text(
        f"path: {dst}\ntrain: train/images\nval:\n  - valid/images\n  - test/images\n"
        "nc: 1\nnames:\n  0: placa\n",
        encoding="utf-8",
    )

    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Dataset en {dst}\nInforme en {args.report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
