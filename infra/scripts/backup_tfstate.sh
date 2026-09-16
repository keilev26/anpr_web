#!/usr/bin/env bash
# Copia el estado de Terraform fuera del repo. Sin él, Terraform "olvida" lo que
# creó y no puede actualizarlo ni borrarlo. Contiene secretos (el de X-Origin-Verify):
# carpeta 700 y archivos 600. Conserva las 10 copias más recientes.
#
#   infra/scripts/backup_tfstate.sh        (ejecutar después de cada apply)
set -euo pipefail

STATE="$(cd "$(dirname "$0")/../terraform" && pwd)/terraform.tfstate"
DEST="${ANPR_BACKUPS:-/data/anpr/backups/terraform}"

[[ -s "$STATE" ]] || { echo "No existe $STATE" >&2; exit 1; }

umask 077
mkdir -p "$DEST"
chmod 700 "$DEST"
copia="$DEST/terraform.tfstate.$(date +%Y%m%d-%H%M%S)"
cp "$STATE" "$copia"
chmod 600 "$copia"

ls -1t "$DEST"/terraform.tfstate.* | tail -n +11 | xargs -r rm -f
echo "Copia en $copia ($(ls -1 "$DEST"/terraform.tfstate.* | wc -l) conservadas)"
