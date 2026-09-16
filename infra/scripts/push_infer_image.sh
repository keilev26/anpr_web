#!/usr/bin/env bash
# Construye la imagen de inferencia (ml/Dockerfile) y la sube a ECR.
#   SKIP_PUSH=1 ./push_infer_image.sh v1   # solo construir, para probarla en local primero
#   ./push_infer_image.sh v1               # construir (usa la caché) y subir
set -euo pipefail

TAG="${1:?Uso: $0 <tag>, p. ej. v1}"
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
TF="${TERRAFORM:-/data/tools/bin/terraform}"
export TF_DATA_DIR="${TF_DATA_DIR:-/data/anpr/infra/.terraform}"
ML="$ROOT/ml"

# La imagen pesa varios GB. Construirla con Docker guardando en la partición de
# Ubuntu (casi llena) puede dejar el sistema sin espacio.
DOCKER_ROOT="$(docker info --format '{{.DockerRootDir}}')"
LIBRE_GB=$(df -BG --output=avail "$DOCKER_ROOT" | tail -1 | tr -dc '0-9')
if (( LIBRE_GB < 15 )); then
  echo "Docker guarda en $DOCKER_ROOT, con solo ${LIBRE_GB} GB libres." >&2
  echo "Mover el almacenamiento de Docker a /data antes de construir (ver infra/README.md)." >&2
  exit 1
fi

echo "==> Comprobando modelos horneados"
[[ -f "$ML/models/best.onnx" ]] || { echo "Falta ml/models/best.onnx (ml/README.md, pendiente 4)" >&2; exit 1; }
DET=$(grep -oP 'DET_MODEL = "\K[^"]+' "$ML/src/anpr_ml/ocr_settings.py")
REC=$(grep -oP 'REC_MODEL = "\K[^"]+' "$ML/src/anpr_ml/ocr_settings.py")
CACHE="${PADDLE_PDX_CACHE_HOME:-/data/cache/paddlex}/official_models"
mkdir -p "$ML/models/paddle"
for m in "$DET" "$REC"; do
  if [[ ! -d "$ML/models/paddle/$m" ]]; then
    [[ -d "$CACHE/$m" ]] || { echo "Falta $m en $CACHE (ejecutar ml/scripts/ocr_visual.py una vez)" >&2; exit 1; }
    cp -r "$CACHE/$m" "$ML/models/paddle/"
  fi
  echo "   ✓ $m"
done

cd "$ROOT/infra/terraform"
REPO="$("$TF" output -raw ecr_repository_url)"
REGION="$(echo "$REPO" | cut -d. -f4)"

echo "==> docker build $REPO:$TAG (linux/amd64)"
docker build --platform linux/amd64 -t "$REPO:$TAG" "$ML"

if [[ "${SKIP_PUSH:-0}" == "1" ]]; then
  echo
  echo "Construida sin subir. Probarla en local:"
  echo "  infra/scripts/test_infer_image_local.sh $REPO:$TAG"
  exit 0
fi

echo "==> Subiendo a ECR"
aws ecr get-login-password --region "$REGION" | docker login --username AWS --password-stdin "${REPO%%/*}"
docker push "$REPO:$TAG"

echo
echo "Imagen subida. Siguiente paso:"
echo "  1. En infra/terraform/terraform.tfvars:  infer_image_tag = \"$TAG\""
echo "  2. terraform apply"
