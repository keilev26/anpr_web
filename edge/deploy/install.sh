#!/usr/bin/env bash
# Instala o actualiza el edge ANPR en la Raspberry Pi 5 (Raspberry Pi OS 64-bit).
# Idempotente: se puede volver a correr para actualizar.
#
# En la laptop:
#   cd edge && uv build --wheel && uv export --no-dev --no-emit-project \
#       --format requirements-txt -o dist/requirements.txt
#   scp -r dist deploy pi@<ip>:anpr-edge/
# En la Pi:
#   sudo anpr-edge/deploy/install.sh anpr-edge/dist
#
# Después, una sola vez: copiar la clave del dispositivo a
#   /etc/anpr/secrets/device_api_key   (root:root 600)
set -euo pipefail

DIST="${1:?Uso: install.sh <carpeta con el .whl y requirements.txt>}"
DEPLOY="$(cd "$(dirname "$0")" && pwd)"
PREFIX=/opt/anpr-edge
ETC=/etc/anpr
SPOOL=/var/spool/anpr
SERVICES=(gate trigger capture uplink health)

[[ $EUID -eq 0 ]] || { echo "Correr con sudo" >&2; exit 1; }
WHEEL=$(ls "$DIST"/anpr_edge-*.whl | sort -V | tail -1)
[[ -f "$DIST/requirements.txt" ]] || { echo "Falta $DIST/requirements.txt" >&2; exit 1; }

echo "==> Paquetes del sistema"
# gpiozero y lgpio desde apt: compilados para el kernel de Raspberry Pi OS.
apt-get install -y --no-install-recommends mosquitto python3-venv python3-gpiozero python3-lgpio

echo "==> Usuarios (uno por servicio, sin shell ni home)"
getent group anpr >/dev/null || groupadd --system anpr
for s in "${SERVICES[@]}"; do
    id "anpr-$s" &>/dev/null || useradd --system --no-create-home --shell /usr/sbin/nologin \
        --gid anpr "anpr-$s"
done
# Solo los que leen o escriben pines.
for s in gate trigger health; do usermod -aG gpio "anpr-$s"; done

echo "==> Directorios"
install -d -m 750 -o root -g anpr "$ETC"
install -d -m 700 -o root -g root "$ETC/secrets" "$ETC/mqtt"
# setgid: lo que escribe capture queda en el grupo anpr y uplink puede marcarlo y borrarlo.
install -d -m 2770 -o anpr-capture -g anpr "$SPOOL"

echo "==> Entorno de Python en $PREFIX"
install -d -m 755 "$PREFIX"
[[ -x "$PREFIX/venv/bin/python" ]] || python3 -m venv --system-site-packages "$PREFIX/venv"
# --require-hashes: cada dependencia se verifica contra el hash de uv.lock.
"$PREFIX/venv/bin/pip" install --quiet --require-hashes -r "$DIST/requirements.txt"
"$PREFIX/venv/bin/pip" install --quiet --no-deps --force-reinstall "$WHEEL"

echo "==> Configuración"
if [[ ! -f "$ETC/edge.toml" ]]; then
    install -m 640 -o root -g anpr "$DEPLOY/edge.toml.example" "$ETC/edge.toml"
    echo "   Creado $ETC/edge.toml: revisar pines (F6) y tiempos de recorrido (visita)."
fi
[[ -s "$ETC/secrets/device_api_key" ]] || echo "   FALTA $ETC/secrets/device_api_key (uplink no arrancará)"

echo "==> Mosquitto: un usuario por servicio"
PASSWD=/etc/mosquitto/anpr.passwd
TMP=$(mktemp)
trap 'shred -u "$TMP" 2>/dev/null || rm -f "$TMP"' EXIT
chmod 600 "$TMP"
for s in "${SERVICES[@]}"; do
    pw="$ETC/mqtt/$s.pw"
    [[ -s "$pw" ]] || ( umask 077; head -c 32 /dev/urandom | base64 | tr -d '/+=' > "$pw" )
    printf '%s:%s\n' "$s" "$(cat "$pw")" >> "$TMP"
done
# Se hashea en un archivo temporal: la contraseña nunca pasa por la línea de comandos.
mosquitto_passwd -U "$TMP"
install -m 600 -o mosquitto -g mosquitto "$TMP" "$PASSWD"
install -m 644 "$DEPLOY/mosquitto/anpr.conf" /etc/mosquitto/conf.d/anpr.conf
install -m 600 -o mosquitto -g mosquitto "$DEPLOY/mosquitto/anpr.acl" /etc/mosquitto/anpr.acl
systemctl restart mosquitto

echo "==> journald y systemd"
install -d -m 755 /etc/systemd/journald.conf.d
install -m 644 "$DEPLOY/journald/anpr.conf" /etc/systemd/journald.conf.d/anpr.conf
systemctl restart systemd-journald
for s in "${SERVICES[@]}"; do
    install -m 644 "$DEPLOY/systemd/anpr-$s.service" /etc/systemd/system/
done
systemctl daemon-reload
for s in "${SERVICES[@]}"; do systemctl enable "anpr-$s" >/dev/null; done
# Si un servicio no arranca (p. ej. uplink sin la clave del dispositivo todavía),
# que se muestre igual el estado de los otros 4: no abortar aquí por `set -e`.
systemctl restart "${SERVICES[@]/#/anpr-}" || true

echo "==> Estado"
systemctl --no-pager --lines=0 status "${SERVICES[@]/#/anpr-}" | grep -E "●|Active:" || true
echo "Logs: journalctl -u 'anpr-*' -f -o cat"
