# F5 — Raspberry Pi

Servicios systemd del dispositivo de campo. **Pi 5 de 4 GB** (no la de 8: con la
inferencia en la nube, la Pi solo captura, hace un POST y cierra relés).

## Servicios

| Servicio | Responsabilidad | GPIO | Internet |
|---|---|---|---|
| `anpr-trigger` | Lee el sensor de presencia, emite `gate/trigger` | Sí (in) | No |
| `anpr-capture` | Toma la ráfaga, la escribe en `/var/spool/anpr/` | No | No |
| `anpr-uplink` | Sube la ráfaga, recibe veredicto, publica `gate/command` | No | Sí |
| `anpr-gate` | **Único** que cierra relés. Enclavamiento y timeouts | Sí (out) | **No** |
| `anpr-health` | Heartbeat a IoT Core, watchdog, métricas | No | Sí |

**Por qué esta separación:** `anpr-gate` es el servicio crítico de seguridad. Se
mantiene pequeño, auditable y **sin ninguna dependencia de red**. Un bug en
`anpr-uplink` no puede mover el motor de forma inválida.

## Desarrollo en la laptop

El ~90 % se desarrolla y prueba en la laptop: Linux, Python, systemd, Mosquitto y el
protocolo de la Sony son los mismos. Lo que cambia entre máquinas va en la
configuración (`/etc/anpr/edge.toml`; en la laptop, `config/dev.toml`), nunca en el
código. El GPIO se simula (backend `sim`); dos redes, watchdog, RTC y NVMe se
configuran ya en la Pi. Plan por partes: `PENDIENTES.md` §3.

```bash
cd edge
UV_CACHE_DIR=/data/cache/uv uv sync --python /usr/bin/python3.12 --extra dev --extra sim
PYTHONPATH= .venv/bin/pytest          # PYTHONPATH vacío: ROS inyecta plugins de pytest
.venv/bin/ruff check . && .venv/bin/ruff format --check .
```

Dependencias fijadas con hash en `uv.lock` y auditadas con `pip-audit`.

### Cámara Sony

La cámara crea su propia red Wi-Fi (`DIRECT-...:HDR-AS100V`) y solo se controla desde
ella, en `192.168.122.1`: no puede unirse al router. Cliente en
`src/anpr_edge/camera/sony.py`: parsea el formato de paquetes del liveview (no busca
marcadores JPEG como el legacy) y siempre cierra con `stopLiveview`.

**Sonda de la cámara real.** Conectar la laptop al Wi-Fi de la Sony. Se pierde internet
mientras tanto, así que conviene correrla en otra terminal y volver luego a la red de siempre:

```bash
.venv/bin/anpr-probe-camera --record capturas/liveview.bin --save-frames 10 \
    > capturas/probe.json
```

Mide el arranque del liveview, FPS, resolución y tamaño de los frames, y comprueba en
3 ciclos que no se agotan las sesiones. `capturas/` está ignorada por git: puede haber
placas y personas.

**Sony simulada** (mismo protocolo, con fallos inyectables):

```bash
.venv/bin/anpr-sim-camera --frames-dir tests/fixtures/frames   # o --replay capturas/liveview.bin
```

## No incluye

- El cableado de potencia ni los sensores (F6)
- La inferencia (F4): la Pi no ejecuta ningún modelo

## Cómo trabajar aislado

- Stub FastAPI local que devuelve veredictos enlatados, en lugar de la nube
- **Relés en modo simulado: un LED y un log**, sin tocar el motor

Así F5 y F6 validan cada uno su mitad del portón sin esperarse: el electricista
prueba potencia y seguridad con un botón; tú pruebas la lógica con un LED.

## Terminado cuando

Ráfaga → POST → veredicto → LED, sin motor conectado.

## Requisitos de despliegue en campo

- Arranque desde **SSD NVMe**, no microSD (causa nº1 de fallos en Pi de producción)
- Fuente oficial de 27 W y disipador activo
- **Watchdog de hardware** habilitado, para que un cuelgue se reinicie solo
- UPS: un corte a mitad de escritura corrompe el filesystem
- RTC con pila, para conservar hora correcta sin red
- **Ethernet para internet + Wi-Fi para la cámara Sony**, con rutas fijadas por
  métrica para que `192.168.122.0/24` no se robe la ruta por defecto.
  **Si no hay cable de red en el gabinete, este es el primer blocker del despliegue.**

## Tarea heredada

Cerrar la fuga de sesión de la cámara: hoy los tres consumidores llaman
`startLiveview` sin `stopLiveview`, y la cámara acaba agotando sesiones.
