#!/usr/bin/env bash
# Construye infra/build/api.zip: la API (F2) + dependencias para Lambda python3.12 x86_64.
#
# Las dependencias se listan aquí y no se toman del pyproject porque el pyproject
# incluye cosas que en Lambda sobran (uvicorn, alembic, aiosqlite). Para que la lista
# no quede desalineada sin que nadie lo note, el script IMPORTA el paquete con un
# Python 3.12 real y ejecuta una petición completa a través de Mangum antes de comprimir.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
BUILD="$ROOT/infra/build"
PKG="$BUILD/api"
export UV_CACHE_DIR="${UV_CACHE_DIR:-/data/cache/uv}"

DEPS=(
  "fastapi>=0.115"
  "sqlalchemy[asyncio]>=2.0.36"
  "pydantic[email]>=2.10"
  "pydantic-settings>=2.7"
  "pyjwt>=2.10"
  "argon2-cffi>=23.1"
  "python-multipart>=0.0.20"
  "aiomysql>=0.2"
  "mangum>=0.19"
  # boto3 NO: ya viene en el runtime de Lambda.
)

rm -rf "$PKG" "$BUILD/api.zip"
mkdir -p "$PKG"

echo "==> Dependencias para python3.12 / manylinux x86_64"
uv pip install --quiet --target "$PKG" \
  --python-version 3.12 --python-platform x86_64-manylinux_2_28 \
  --only-binary :all: "${DEPS[@]}"

echo "==> Código de la API"
cp -r "$ROOT/api/app" "$PKG/app"
find "$PKG" -name "__pycache__" -type d -prune -exec rm -rf {} +

echo "==> Prueba de humo con Python 3.12 (importa todo y atiende /api/health)"
PY312="$(command -v python3.12 || true)"
if [[ -z "$PY312" ]]; then
  echo "   AVISO: no hay python3.12 local; se omite la prueba de humo" >&2
else
  (cd "$PKG" && env -i PATH=/usr/bin:/bin PYTHONPATH="$PKG" \
     DATABASE_URL="mysql+aiomysql://u:p@127.0.0.1:1/x" \
     SECRET_KEY="clave-de-prueba-de-humo-no-usar" DEV_MODE=false DB_NULLPOOL=true \
     "$PY312" - <<'PY'
import json
from app.lambda_handler import handler

class Ctx:
    aws_request_id = "humo"

def evento(path):
    return {"version": "2.0", "routeKey": "$default", "rawPath": path, "rawQueryString": "",
            "headers": {"host": "x.lambda-url.us-east-1.on.aws"},
            "requestContext": {"http": {"method": "GET", "path": path, "protocol": "HTTP/1.1",
                                        "sourceIp": "1.1.1.1", "userAgent": "humo"},
                               "domainName": "x", "requestId": "r", "stage": "$default",
                               "accountId": "anonymous", "apiId": "x", "time": "", "timeEpoch": 0},
            "isBase64Encoded": False}

r = handler(evento("/api/health"), Ctx())
body = json.loads(r["body"])
# Sin base de datos real responde "degraded": lo que se prueba es que todo importa y enruta.
assert r["statusCode"] == 200 and body["db"] is False, r
r = handler(evento("/api/no-existe"), Ctx())
assert r["statusCode"] == 404, r
print("   OK: importa en 3.12, Mangum enruta /api/* y la API responde")
PY
  )
fi

echo "==> Comprimiendo"
(cd "$PKG" && python3 - <<'PY'
import os, zipfile
with zipfile.ZipFile("../api.zip", "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
    for root, _, files in os.walk("."):
        for f in files:
            p = os.path.join(root, f)
            z.write(p, os.path.relpath(p, "."))
PY
)
du -h "$BUILD/api.zip" | awk '{print "   api.zip: " $1 " (límite de Lambda: 50 MB comprimido)"}'
