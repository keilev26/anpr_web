#!/usr/bin/env bash
# Ejecuta un comando con DATABASE_URL y DB_SSL_CA de Aiven, leídos de archivos
# locales y sin imprimirlos:
#   infra/scripts/with_aiven.sh api/.venv/bin/alembic upgrade head
#
# Espera, con permisos restringidos:
#   $AIVEN_SECRETS/aiven.env      AIVEN_URI=mysql://avnadmin:...@host:puerto/defaultdb?ssl-mode=REQUIRED
#   $AIVEN_SECRETS/aiven-ca.pem   certificado de CA descargado de Aiven
set -euo pipefail
DIR="${AIVEN_SECRETS:-/data/anpr/secrets}"

DATABASE_URL="$(python3 - "$DIR/aiven.env" <<'PY'
import re, sys
from urllib.parse import urlsplit, urlunsplit
m = re.search(r"^AIVEN_URI=(.+)$", open(sys.argv[1]).read(), re.M)
if not m:
    sys.exit("aiven.env no contiene AIVEN_URI=")
u = urlsplit(m.group(1).strip().strip("'\""))
# ?ssl-mode=REQUIRED es de los clientes de MySQL; aiomysql no lo entiende.
# El TLS lo configura la API con DB_SSL_CA.
print(urlunsplit(("mysql+aiomysql", u.netloc, u.path, "", "")))
PY
)"
DB_SSL_CA="$(cat "$DIR/aiven-ca.pem")"
export DATABASE_URL DB_SSL_CA
# PYTHONPATH vacío: esta máquina tiene ROS en PYTHONPATH y rompe pytest/alembic.
export PYTHONPATH=
exec "$@"
