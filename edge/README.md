# F5 — Raspberry Pi

Servicios de campo de la **Pi 5 de 4 GB**: detectan el vehículo, toman la ráfaga con la
Sony, la suben a la nube y mueven la pluma. La Pi no ejecuta ningún modelo.

```
PRESENCE ─► anpr-trigger ─gate/trigger─► anpr-capture ─gate/frames_ready─► anpr-uplink ─HTTPS─► nube
                                          (Wi-Fi Sony)                          │
                                                                          gate/command
LIMITES, FOTOCELDA, E-STOP, MODE_AUTO, BOTÓN ─► anpr-gate ◄─────────────────────┘ ─► RELÉS
anpr-health: escucha todo, comprueba nube/disco/reloj, maneja el LED
```

## Servicios

Cinco procesos independientes, cada uno con su unidad systemd, su usuario Linux y su
usuario de Mosquitto. Se comunican solo por el bus local (`contracts/mqtt-topics.md`).

| Servicio | Hace | GPIO | Red permitida (systemd) |
|---|---|---|---|
| `anpr-trigger` | Presencia estable → disparo; reintenta si la placa salió ilegible; cola de autos | `PRESENCE` | Solo localhost |
| `anpr-capture` | Liveview continuo de la Sony; ráfaga de 5 fotos espaciadas al spool | — | localhost + `192.168.122.0/24` |
| `anpr-uplink` | POST a la nube dentro del plazo; **único que ordena abrir**; reenvíos tardíos; limpieza del spool | — | Internet |
| `anpr-gate` | **Único que acciona relés.** Máquina de estados de la pluma | Relés + 6 entradas | **Solo localhost** |
| `anpr-health` | Servicios vivos, pluma, cámara, nube, disco, temperatura, reloj; LED | `LED_STATUS` | Internet |

## Robustez

Cada regla está cubierta por tests (`tests/`) o se probó en la laptop con fallos
inyectados (ver "Pruebas de fallos").

**Seguridad de la pluma** (`src/anpr_edge/gate/machine.py`, segunda barrera tras el
cableado de F6):
- FWD y REV nunca a la vez; 0,5 s con ambos apagados antes de cualquier arranque.
- Tiempo máximo de marcha = recorrido + 20 %; si no llega al final de carrera, falla.
- Nunca baja con la fotocelda interrumpida; si se interrumpe al bajar, para y vuelve a subir.
- Cierre automático cuando el auto terminó de pasar, o tras un máximo si nadie cruzó.
- Emergencia, finales de carrera incoherentes o posición perdida → **falla**. Solo sale
  de la falla una persona, pasando el selector por MANUAL.
- En MANUAL la Pi no acciona nada. Al volver a AUTO, ciclo de referencia hacia cerrada.
- Órdenes vencidas (TTL) o repetidas (`event_id`) se descartan.
- Entradas con antirrebote asimétrico: lo peligroso se aplica al instante.
- Un cable cortado se lee como la situación peligrosa (entradas NC con pull-up).
- Si el proceso muere (incluso `kill -9`), `ExecStopPost=anpr-gate-safe-off` apaga los relés.
- Si su propia lógica falla, apaga los relés antes de nada.

**Servicios:**
- `Restart=always` sin límite de reintentos, `WatchdogSec` con `sd_notify`: un cuelgue
  reinicia el servicio. Si la lógica falla de forma persistente, el proceso termina
  para reiniciarse limpio.
- Red restringida por systemd (`IPAddressDeny`), no por convención.
- Mosquitto solo en localhost, usuario por servicio y ACL: solo `uplink` puede publicar
  `gate/command` (verificado contra el broker real).
- Mensajes validados al recibirlos; sesión limpia: no se ejecutan órdenes atrasadas.
- Spool con escrituras atómicas; secretos por `LoadCredential=`; logs JSON en journald
  con tope de tamaño.
- Nube caída o lenta: **nunca abre**; guarda el evento y lo reenvía después con
  `late=true`, solo para registro.

## Desarrollo en la laptop

El ~90 % es idéntico a la Pi. Lo que cambia va en la configuración (`config/dev.toml`
en la laptop, `/etc/anpr/edge.toml` en la Pi), nunca en el código: el GPIO se simula
por MQTT y el resto se configura en la Pi (parte 8 de `PENDIENTES.md` §3).

```bash
cd edge
UV_CACHE_DIR=/data/cache/uv uv sync --python /usr/bin/python3.12 --extra dev --extra sim
PYTHONPATH= .venv/bin/pytest          # PYTHONPATH vacío: ROS inyecta plugins de pytest
.venv/bin/ruff check . && .venv/bin/ruff format --check .
```

**Todo junto, con simuladores** (Mosquitto en Docker, Sony, nube y pluma simuladas;
los 5 servicios como procesos que se reinician si mueren):

```bash
PYTHONPATH= .venv/bin/anpr-dev                  # --camera real / --cloud config / --cloud-mode deny
.venv/bin/anpr-sim-plant car                    # llega un auto
.venv/bin/anpr-sim-plant estop on|off           # también: mode manual|auto, block|unblock, press
curl -X POST localhost:8001/_scenario -H 'content-type: application/json' -d '{"mode":"unavailable"}'
docker exec anpr-mosquitto mosquitto_sub -t 'gate/#' -t 'health/#' -t sim/plant/state -v
```

Dependencias fijadas con hash en `uv.lock` y auditadas con `pip-audit`.

### Pruebas de fallos (2026-09-26, laptop)

| Prueba | Resultado |
|---|---|
| Auto autorizado | Disparo → 5 fotos → nube → orden → sube → el auto cruza → baja |
| Nube con 503 y nube colgada | 3 intentos, **nunca abre**, eventos pendientes para registro |
| `kill -9` de `anpr-gate` subiendo | Relés apagados en < 0,8 s; reinicia, referencia, el auto pasa |
| Reinicio de Mosquitto | Los 5 servicios se reconectan; el siguiente auto pasa |
| Emergencia subiendo | Para en seco; sigue en falla al soltarla; sale al pasar por MANUAL |
| ACL de Mosquitto | Solo `uplink` ordena abrir; sin suplantación; sin anónimos; `sim/#` bloqueado |

### Cámara Sony

La cámara crea su propia red Wi-Fi (`DIRECT-...:HDR-AS100V`) y solo se controla desde
ella, en `192.168.122.1`: no puede unirse al router. El cliente
(`src/anpr_edge/camera/sony.py`) parsea el formato de paquetes del liveview (no busca
marcadores JPEG como el legacy) y siempre cierra con `stopLiveview`.

**Sonda de la cámara real.** Conectar la laptop al Wi-Fi de la Sony. Se pierde internet
mientras tanto: correrla en otra terminal y volver luego a la red de siempre.

```bash
.venv/bin/anpr-probe-camera --record capturas/liveview.bin --save-frames 10 \
    > capturas/probe.json
```

`capturas/` está ignorada por git: puede haber placas y personas.

## Despliegue en la Pi

```bash
# Laptop
cd edge && uv build --wheel && \
  uv export --no-dev --no-emit-project --format requirements-txt -o dist/requirements.txt
scp -r dist deploy pi@<ip>:anpr-edge/
# Pi
sudo anpr-edge/deploy/install.sh anpr-edge/dist
sudo install -m 600 /dev/stdin /etc/anpr/secrets/device_api_key   # pegar la clave, Ctrl+D
```

`deploy/install.sh` crea usuarios, directorios, el entorno de Python (con
`--require-hashes`), las contraseñas de Mosquitto (sin pasarlas por la línea de
comandos), la ACL, las unidades y el límite de journald. Es idempotente.

Antes de conectar el motor, en `/etc/anpr/edge.toml`: números de pin (F6), tiempos de
recorrido medidos y qué relé sube la pluma (`open_relay`).

### Requisitos de campo

- Arranque desde **SSD NVMe**, no microSD; fuente oficial de 27 W; disipador activo.
- **Watchdog de hardware** (`dtparam=watchdog=on` y `RuntimeWatchdogSec` en systemd).
- UPS; RTC con pila; chrony.
- **Ethernet para internet + Wi-Fi para la Sony**, con la ruta por defecto por Ethernet
  para que `192.168.122.0/24` no se la robe. Sin cable de red en el gabinete, este es
  el primer bloqueo del despliegue.
- Resistencias pull-down en las entradas de los relés (F6): una línea GPIO suelta no
  debe activar un relé.
