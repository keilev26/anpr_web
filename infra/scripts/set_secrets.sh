#!/usr/bin/env bash
# Carga los secretos en SSM Parameter Store. Se ejecuta una vez tras el primer apply.
#
# Los valores nunca pasan por argumentos de línea de comandos (se verían en `ps`):
# se escriben a un temporal con permisos 600 y se envían con file://.
set -euo pipefail

PREFIX="${1:-/anpr/prueba}"
command -v aws >/dev/null || { echo "Falta el AWS CLI" >&2; exit 1; }

TMP="$(umask 077; mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

put() {  # put <nombre> <archivo-con-el-valor>
  aws ssm put-parameter --overwrite --type SecureString \
    --name "$PREFIX/$1" --value "file://$2" >/dev/null
  echo "   ✓ $PREFIX/$1"
}

SECRETS="${AIVEN_SECRETS:-/data/anpr/secrets}"

echo "1/4 URL de la base de datos"
if [[ -f "$SECRETS/aiven.env" ]]; then
  echo "    leída de $SECRETS/aiven.env"
  URI="$(python3 -c "import re,sys; print(re.search(r'^AIVEN_URI=(.+)$', open(sys.argv[1]).read(), re.M).group(1).strip().strip(chr(39)+chr(34)))" "$SECRETS/aiven.env")"
else
  echo "    (Aiven -> Overview -> Service URI)"
  read -rsp "    Pegar y Enter (no se muestra): " URI; echo
fi
python3 - "$URI" "$TMP/database_url" <<'PY2'
import sys
from urllib.parse import urlsplit, urlunsplit
uri, out = sys.argv[1], sys.argv[2]
u = urlsplit(uri.strip())
if u.scheme not in ("mysql", "mysql+aiomysql"):
    sys.exit(f"Se esperaba una URL mysql://, llegó '{u.scheme}://'")
# Aiven añade ?ssl-mode=REQUIRED, que aiomysql no entiende. El TLS lo configura
# la API con el certificado de CA (db_ssl_ca), no la URL.
open(out, "w").write(urlunsplit(("mysql+aiomysql", u.netloc, u.path, "", "")))
PY2
put database_url "$TMP/database_url"

echo "2/4 Certificado de CA de Aiven"
if [[ -f "$SECRETS/aiven-ca.pem" ]]; then
  CA="$SECRETS/aiven-ca.pem"; echo "    leído de $CA"
else
  read -rp "    Ruta al ca.pem (Overview -> CA Certificate): " CA
fi
grep -q "BEGIN CERTIFICATE" "$CA" || { echo "No parece un certificado PEM" >&2; exit 1; }
put db_ssl_ca "$CA"

echo "3/4 Clave de firma JWT: se genera aleatoria"
python3 -c "import secrets; print(secrets.token_urlsafe(48), end='')" > "$TMP/secret_key"
put secret_key "$TMP/secret_key"

echo "4/4 Clave del dispositivo (X-Device-Key): se genera aleatoria"
python3 -c "import secrets; print(secrets.token_urlsafe(32), end='')" > "$TMP/device_api_key"
put device_api_key "$TMP/device_api_key"
# La clave de la Raspberry no se imprime: quedaría en el historial de la terminal
# o en cualquier registro de la sesión. Se guarda en un archivo solo legible por ti.
( umask 077; cp "$TMP/device_api_key" "$SECRETS/device_api_key" )
echo "   Clave del dispositivo guardada en $SECRETS/device_api_key (permisos 600)."
echo "   La necesitará la Raspberry (F5). También se puede leer de SSM:"
echo "   aws ssm get-parameter --with-decryption --name $PREFIX/device_api_key --query Parameter.Value --output text"
echo
echo "Los Lambda leen los secretos al arrancar: los que ya estaban calientes no los ven."
echo "Forzar un arranque nuevo:"
echo "   aws lambda update-function-configuration --function-name anpr-prueba-api --description \"secretos $(date +%F_%T)\""
