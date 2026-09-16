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
