"""
Prueba visual de lectura, etapa 2 de 2: PaddleOCR + post-procesado sobre los
recortes de `scripts/detect_plates.py`, y fichas para revisar a ojo.

    PADDLE_PDX_CACHE_HOME=/data/cache/paddlex \\
    /data/anpr/venvs/ml-ocr/bin/python scripts/ocr_visual.py

Cada ficha muestra la imagen con la caja, la placa ampliada, lo que leyó el OCR
tal cual y lo que el sistema haría con ello:

    verde    placa válida sin correcciones
    naranja  placa válida gracias a la corrección posicional (una conjetura)
    rojo     no legible, o sin detección

No hay texto de referencia (el dataset solo trae cajas): la verificación es
comparar a ojo la placa ampliada con el resultado.
"""

import argparse
import json
import time
from collections import Counter
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from anpr_ml.ocr_settings import DET_MODEL, REC_MODEL
from anpr_ml.plate_text import best_plate


def paddleocr_models() -> list[str]:
    return [DET_MODEL, REC_MODEL]


ML_ROOT = Path(__file__).resolve().parents[1]
VERDE, NARANJA, ROJO = (40, 170, 70), (235, 140, 20), (215, 40, 50)
CARD_W = 640
BAND_H = 120


def _font(size: int) -> ImageFont.ImageFont:
    for f in (
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ):
        if Path(f).exists():
            return ImageFont.truetype(f, size)
    return ImageFont.load_default(size=size)


def build_ocr(models_dir: str | None):
    from paddleocr import PaddleOCR

    from anpr_ml.ocr_settings import paddleocr_kwargs

    # Exactamente la misma configuración que onnx_engine.PaddleOcr en producción.
    return PaddleOCR(**paddleocr_kwargs(models_dir))


def read(ocr, crop: Path) -> list[tuple[str, float]]:
    out = ocr.predict(str(crop))
    if not out:
        return []
    r = out[0]
    textos = list(r.get("rec_texts", []) or [])
    scores = list(r.get("rec_scores", []) or [])
    return [(str(t), float(scores[i]) if i < len(scores) else 0.0) for i, t in enumerate(textos)]


def card(imagen: Path, det: dict | None, lecturas, cand) -> tuple[Image.Image, str]:
    with Image.open(imagen) as im:
        im = im.convert("RGB")
    im.thumbnail((CARD_W, CARD_W))
    lienzo = Image.new("RGB", (CARD_W, im.height + BAND_H), (18, 18, 18))
    lienzo.paste(im, (0, 0))
    d = ImageDraw.Draw(lienzo)
    f_big, f_small = _font(26), _font(17)

    if det is None:
        estado, color = "sin_deteccion", ROJO
        linea1, linea2 = "YOLO no detectó ninguna placa", "→ la puerta no abriría"
    else:
        if cand is not None and cand.valid and not cand.was_corrected:
            estado, color = "valida", VERDE
        elif cand is not None and cand.valid:
            estado, color = "corregida", NARANJA
        else:
            estado, color = "no_legible", ROJO

        escala = im.width / Image.open(imagen).width
        x1, y1, x2, y2 = (v * escala for v in det["box"])
        d.rectangle([x1, y1, x2, y2], outline=color, width=4)

        with Image.open(det["crop"]) as c:
            c = c.convert("RGB")
            c = c.resize((280, max(1, round(280 * c.height / c.width))), Image.Resampling.LANCZOS)
            d.rectangle([6, 6, 14 + c.width, 14 + c.height], fill=(255, 255, 255))
            lienzo.paste(c, (10, 10))

        crudo = "  |  ".join(f"'{t}' {s:.2f}" for t, s in lecturas) or "(nada)"
        linea1 = f"OCR: {crudo}"
        if estado == "valida":
            linea2 = f"→ {cand.plate}"
        elif estado == "corregida":
            linea2 = f"→ {cand.plate}   corregida: {', '.join(cand.corrections)}"
        else:
            linea2 = "→ NO LEGIBLE"
        linea1 += f"    det {det['conf']:.2f} · {det['ancho_px']}px"

    y0 = im.height
    d.rectangle([0, y0, CARD_W, y0 + 8], fill=color)
    d.text((12, y0 + 18), linea1[:78], font=f_small, fill=(230, 230, 230))
    d.text((12, y0 + 52), linea2[:48], font=f_big, fill=color)
    d.text((12, y0 + 92), Path(imagen).name[:70], font=_font(13), fill=(140, 140, 140))
    return lienzo, estado


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", type=Path, default=ML_ROOT / "runs/ocr_visual")
    ap.add_argument(
        "--models-dir", default=None, help="Modelos de PaddleOCR locales, como en Lambda"
    )
    ap.add_argument("--por-pagina", type=int, default=6)
    args = ap.parse_args()

    registros = json.loads((args.run / "detections.json").read_text(encoding="utf-8"))

    ocr = build_ocr(args.models_dir)

    fichas_dir = args.run / "fichas"
    fichas_dir.mkdir(parents=True, exist_ok=True)
    fichas, conteo, detalle, tiempos = [], Counter(), [], []

    for reg in registros:
        imagen = Path(reg["imagen"])
        if not reg["detecciones"]:
            ficha, estado = card(imagen, None, [], None)
            fichas.append(ficha)
            conteo[estado] += 1
            detalle.append({"imagen": imagen.name, "estado": estado})
            continue
        for det in reg["detecciones"]:
            t0 = time.perf_counter()
            lecturas = read(ocr, Path(det["crop"]))
            tiempos.append(time.perf_counter() - t0)
            cand = best_plate(lecturas)
            ficha, estado = card(imagen, det, lecturas, cand)
            fichas.append(ficha)
            conteo[estado] += 1
            detalle.append(
                {
                    "imagen": imagen.name,
                    "crop": Path(det["crop"]).name,
                    "estado": estado,
                    "ocr": lecturas,
                    "placa": cand.plate if cand else None,
                    "correcciones": cand.corrections if cand else [],
                    "ancho_px": det["ancho_px"],
                }
            )

    # Páginas de 2 columnas para revisar varias fichas de un vistazo.
    cols = 2
    paginas = []
    for i in range(0, len(fichas), args.por_pagina):
        grupo = fichas[i : i + args.por_pagina]
        alto = max(f.height for f in grupo)
        filas = (len(grupo) + cols - 1) // cols
        hoja = Image.new("RGB", (CARD_W * cols, alto * filas), (255, 255, 255))
        for j, f in enumerate(grupo):
            hoja.paste(f, ((j % cols) * CARD_W, (j // cols) * alto))
        ruta = fichas_dir / f"pagina_{len(paginas) + 1:02d}.jpg"
        hoja.save(ruta, quality=88)
        paginas.append(ruta)

    total = sum(conteo.values())
    resumen = {
        "total": total,
        "conteo": dict(conteo),
        "ocr_ms_mediana": round(sorted(tiempos)[len(tiempos) // 2] * 1000) if tiempos else None,
        "modelos": paddleocr_models(),
        "detalle": detalle,
    }
    (args.run / "ocr_resumen.json").write_text(
        json.dumps(resumen, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    for k in ("valida", "corregida", "no_legible", "sin_deteccion"):
        print(f"  {k:14} {conteo[k]:3}  ({conteo[k] / total:.0%})")
    print(f"  OCR por placa (mediana): {resumen['ocr_ms_mediana']} ms en CPU")
    print(f"Fichas: {len(paginas)} páginas en {fichas_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
