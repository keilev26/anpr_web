"""
Verifica que la API implementa exactamente `contracts/openapi.yaml`.

El contrato es la fuente de verdad, no el código: F1 construyó su cliente
contra él. Este script va en CI para que una ruta añadida o renombrada sin
acordarlo con F1 rompa el build, en vez de descubrirse en integración.

    python scripts/check_contract.py
"""

import sys
from pathlib import Path

import yaml

from app.main import app

METHODS = {"get", "post", "patch", "put", "delete"}
CONTRACT = Path(__file__).resolve().parents[2] / "contracts" / "openapi.yaml"


def main() -> int:
    contract = yaml.safe_load(CONTRACT.read_text(encoding="utf-8"))
    generated = app.openapi()

    problems: list[str] = []

    esperadas = set(contract["paths"])
    reales = set(generated["paths"])

    for p in sorted(esperadas - reales):
        problems.append(f"FALTA la ruta {p}")
    for p in sorted(reales - esperadas):
        problems.append(f"SOBRA la ruta {p} (no está en el contrato)")

    for p in sorted(esperadas & reales):
        mc = {m for m in contract["paths"][p] if m in METHODS}
        mg = {m for m in generated["paths"][p] if m in METHODS}
        for m in sorted(mc - mg):
            problems.append(f"FALTA {m.upper()} {p}")
        for m in sorted(mg - mc):
            problems.append(f"SOBRA {m.upper()} {p} (no está en el contrato)")

    if problems:
        print("La API no coincide con el contrato:\n", file=sys.stderr)
        for p in problems:
            print(f"  - {p}", file=sys.stderr)
        print(
            "\nSi el cambio es intencional, acuérdalo con F1 y actualiza "
            "contracts/openapi.yaml en el mismo PR.",
            file=sys.stderr,
        )
        return 1

    print(f"OK: {len(esperadas)} rutas coinciden con contracts/openapi.yaml")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
