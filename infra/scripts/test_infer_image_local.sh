#!/usr/bin/env bash
# Prueba la imagen de inferencia EN LOCAL con el emulador de Lambda que trae la
# imagen base, antes de subirla. Envía una ráfaga de 3 fotogramas reales.
#   ./test_infer_image_local.sh <imagen:tag>
set -euo pipefail

IMG="${1:?Uso: $0 <imagen:tag>}"
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
TEST_DIR="$ROOT/ml/datasets/peru-gate-view/test/images"

# Solo lectura, como en Lambda: si algo intenta escribir fuera de /tmp, falla aquí.
CID=$(docker run -d --read-only --tmpfs /tmp:rw,size=1g -p 9000:8080 "$IMG")
trap 'docker rm -f "$CID" >/dev/null' EXIT
sleep 3

python3 - "$TEST_DIR" <<'PY'
import base64, json, sys, time, urllib.request
from pathlib import Path
foto = sorted(Path(sys.argv[1]).glob("*.jpg"))[0]
# La misma foto 3 veces: el consenso necesita al menos 2 lecturas iguales.
frames = [base64.b64encode(foto.read_bytes()).decode()] * 3
req = urllib.request.Request(
    "http://localhost:9000/2015-03-31/functions/function/invocations",
    data=json.dumps({"frames": frames}).encode(), method="POST")
t = time.perf_counter()
resp = json.load(urllib.request.urlopen(req, timeout=300))
print(f"{time.perf_counter() - t:.1f}s (incluye arranque en frío)")
print(json.dumps(json.loads(resp["body"]), indent=2, ensure_ascii=False))
assert resp["statusCode"] == 200, resp
PY
