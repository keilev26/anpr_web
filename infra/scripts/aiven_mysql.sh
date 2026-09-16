#!/usr/bin/env bash
# Abre el cliente mysql contra Aiven sin escribir la contraseña:
#   infra/scripts/aiven_mysql.sh                         # consola interactiva
#   infra/scripts/aiven_mysql.sh -e "SHOW TABLES"        # una consulta
#
# La contraseña va en un archivo temporal con permisos 600 (--defaults-extra-file),
# nunca en los argumentos: ahí se vería con `ps` y quedaría en el historial.
set -euo pipefail
DIR="${AIVEN_SECRETS:-/data/anpr/secrets}"

TMP="$(umask 077; mktemp)"
trap 'rm -f "$TMP"' EXIT

python3 - "$DIR/aiven.env" "$TMP" <<'PY'
import re, sys
from urllib.parse import urlsplit, unquote
m = re.search(r"^AIVEN_URI=(.+)$", open(sys.argv[1]).read(), re.M)
if not m:
    sys.exit("aiven.env no contiene AIVEN_URI=")
u = urlsplit(m.group(1).strip().strip("'\""))
with open(sys.argv[2], "w") as f:
    f.write("[client]\n")
    f.write(f"host={u.hostname}\nport={u.port}\nuser={unquote(u.username)}\n")
    f.write(f'password="{unquote(u.password)}"\n')
    f.write(f"database={u.path.strip('/')}\n")
PY

# VERIFY_IDENTITY: además de cifrar, comprueba que el servidor sea el de Aiven.
# Sin `exec`: exec reemplaza este shell por mysql y el `trap` que borra el archivo
# con la contraseña nunca llegaría a ejecutarse.
mysql --defaults-extra-file="$TMP" \
  --ssl-mode=VERIFY_IDENTITY --ssl-ca="$DIR/aiven-ca.pem" "$@"
