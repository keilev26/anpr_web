#!/usr/bin/env bash
# Construye el SPA contra la API real y lo publica en S3 + CloudFront.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
TF="${TERRAFORM:-/data/tools/bin/terraform}"
export TF_DATA_DIR="${TF_DATA_DIR:-/data/anpr/infra/.terraform}"

cd "$ROOT/infra/terraform"
BUCKET="$("$TF" output -raw web_bucket)"
DIST="$("$TF" output -raw cloudfront_distribution_id)"
URL="$("$TF" output -raw url)"

echo "==> Build de producción (sin mocks: /api va a la misma distribución)"
cd "$ROOT/web"
VITE_USE_MOCKS=false npm run build

echo "==> Subiendo a s3://$BUCKET"
# Los assets llevan hash en el nombre: se pueden cachear un año.
aws s3 sync dist/assets "s3://$BUCKET/assets" --delete \
  --cache-control "public,max-age=31536000,immutable"
# index.html no: si se cachea, los usuarios siguen viendo la versión vieja.
aws s3 sync dist "s3://$BUCKET" --delete --exclude "assets/*" \
  --cache-control "no-cache"

echo "==> Invalidando index.html (las primeras 1000 rutas al mes son gratuitas)"
aws cloudfront create-invalidation --distribution-id "$DIST" --paths "/index.html" >/dev/null
echo "Listo: $URL"
