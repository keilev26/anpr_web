#!/usr/bin/env bash
# Conecta la Wi-Fi de esta laptop a la Sony HDR-AS100V, sin escribir la contraseña
# en la terminal ni en el repo.
#
#   edge/tools/connect_camera_wifi.sh            # conectar
#   edge/tools/connect_camera_wifi.sh --back      # volver a la red de siempre
#
# Lee de $ANPR_SECRETS/sony_camera.env (permisos 600, fuera del repo):
#   SONY_WIFI_SSID="DIRECT-FyH4:HDR-AS100V"
#   SONY_WIFI_PASSWORD="..."
#
# Mientras la laptop esté en esta red, se queda SIN internet (es una red aislada
# que crea la propia cámara): no puede unirse a tu router.
set -euo pipefail
DIR="${ANPR_SECRETS:-/data/anpr/secrets}"
ENV_FILE="$DIR/sony_camera.env"
IFACE="${WIFI_IFACE:-wlp2s0}"
# Nombre de tu red habitual, para volver con --back. Ajustar si usas otra.
HOME_WIFI="${ANPR_HOME_WIFI:-Caleb 5G}"

if [[ "${1:-}" == "--back" ]]; then
    nmcli connection up "$HOME_WIFI"
    exit 0
fi

[[ -s "$ENV_FILE" ]] || { echo "Falta $ENV_FILE con SONY_WIFI_SSID y SONY_WIFI_PASSWORD" >&2; exit 1; }
# shellcheck disable=SC1090
source "$ENV_FILE"
: "${SONY_WIFI_SSID:?}" "${SONY_WIFI_PASSWORD:?}"

# El perfil guardado con una contraseña vieja (de intentos anteriores) bloquea
# la conexión nueva: se borra y se vuelve a crear con la contraseña actual.
nmcli connection delete "$SONY_WIFI_SSID" >/dev/null 2>&1 || true
nmcli dev wifi rescan ifname "$IFACE" >/dev/null 2>&1 || true
sleep 2

echo "Conectando a $SONY_WIFI_SSID (se pierde internet mientras dure)…"
nmcli dev wifi connect "$SONY_WIFI_SSID" password "$SONY_WIFI_PASSWORD" ifname "$IFACE"

ip -4 addr show "$IFACE" | grep -q "192.168.122" \
    && echo "Conectado: la cámara responde en http://192.168.122.1:10000/sony/camera" \
    || { echo "No se obtuvo IP de la cámara (192.168.122.x). Reintentar." >&2; exit 1; }
