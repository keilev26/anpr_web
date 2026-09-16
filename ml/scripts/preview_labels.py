"""
Dibuja las etiquetas YOLO sobre las imágenes para revisarlas a ojo.

Es el único control que detecta etiquetas desalineadas: un error en la
conversión de coordenadas no produce ningún fallo, solo un modelo que aprende
basura durante horas de GPU.

    python scripts/preview_labels.py --data datasets/peru-plates --split train -n 12
"""

import argparse
import random
from pathlib import Path

from PIL import Image, ImageDraw

MAX_SIDE = 900  # las previsualizaciones se reducen: solo son para mirar


def draw(img_path: Path, label_path: Path, out: Path) -> int:
    with Image.open(img_path) as im:
        im = im.convert("RGB")
        w, h = im.size
        d = ImageDraw.Draw(im)
        n = 0
        lines = label_path.read_text().split("\n") if label_path.exists() else []
        grosor = max(3, w // 300)
        for line in lines:
            if not line.strip():
                continue
            _, cx, cy, bw, bh = map(float, line.split())
            x1, y1 = (cx - bw / 2) * w, (cy - bh / 2) * h
            x2, y2 = (cx + bw / 2) * w, (cy + bh / 2) * h
            d.rectangle([x1, y1, x2, y2], outline=(255, 0, 60), width=grosor)
            n += 1
        im.thumbnail((MAX_SIDE, MAX_SIDE))
        im.save(out, quality=85)
    return n


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", type=Path, required=True)
    ap.add_argument("--split", default="train")
    ap.add_argument("-n", type=int, default=12)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--match", default="", help="Filtra por texto en el nombre")
    args = ap.parse_args()

    img_dir = args.data / args.split / "images"
    lbl_dir = args.data / args.split / "labels"
    out_dir = args.data / "preview" / args.split
    out_dir.mkdir(parents=True, exist_ok=True)

    imgs = sorted(p for p in img_dir.iterdir() if args.match in p.name)
    random.Random(args.seed).shuffle(imgs)
    for p in imgs[: args.n]:
        n = draw(p, lbl_dir / (p.stem + ".txt"), out_dir / p.name)
        print(f"  {n} cajas  {out_dir / p.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
