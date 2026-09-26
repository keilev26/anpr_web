# Contrato B — Bus interno de la Pi

Mosquitto en `localhost`. No sale a internet; el bridge a AWS IoT Core es solo
para telemetría y salud (`anpr-health`).

```
gate/trigger       {"event_id", "source": "loop"|"manual", "ts"}
gate/frames_ready  {"event_id", "path", "count", "captured_at"}
gate/command       {"event_id", "action": "open", "ttl_s", "issued_at"}
gate/state         {"state": "unknown"|"homing"|"closed"|"opening"|"open"|"closing"
                             |"fault"|"manual", "position_known": bool, "ts"}   retenido
gate/fault         {"code", "detail", "ts"}
gate/verdict       {"event_id", "outcome": "open"|"deny"|"unreadable"|"rejected"
                             |"unavailable"|"late", "plate", "http_status", "latency_ms", "ts"}
svc/<servicio>/status  {"service", "status": "online"|"offline"}      retenido + Last Will
camera/status      {"online", "fps", "last_frame_age_s", "ts"}         retenido
health/summary     {"ok", "problems", "services", "gate_state", "cloud", "ts"}   retenido
```

Implementación: `edge/src/anpr_edge/common/messages.py` (un modelo pydantic por tópico).

## Reglas del bus

- **Todo mensaje se valida** al recibirlo: campos desconocidos, tipos erróneos o fechas
  sin zona horaria se descartan y se registran. Nunca llegan a la lógica.
- **QoS 1 y sesión limpia**: tras una reconexión no se reciben mensajes viejos. Un
  disparo o una orden atrasados no deben ejecutarse; quien espera respuesta usa su plazo.
- **`gate/command` nunca se retiene**; `gate/state` y `svc/*/status` sí, para que quien
  se conecte conozca el estado actual.
- **Last Will**: si un servicio muere, el broker publica `offline` en su nombre.
- **`sim/gpio/in/<SEÑAL>` y `sim/gpio/out/<SEÑAL>`**: solo en la laptop, para el GPIO
  simulado. En la Pi la ACL de Mosquitto los deniega.
- **ACL** (`edge/deploy/mosquitto/anpr.acl`): cada servicio entra con su usuario y solo
  puede publicar sus tópicos. `gate/command` solo lo publica `uplink`; `gate/state`
  solo `gate`; nadie puede escribir el estado de otro servicio.

## Quién publica y quién escucha

| Tópico | Publica | Escucha |
|---|---|---|
| `gate/trigger` | `anpr-trigger` | `anpr-capture` |
| `gate/frames_ready` | `anpr-capture` | `anpr-uplink` |
| `gate/command` | `anpr-uplink` | `anpr-gate` |
| `gate/state` | `anpr-gate` | `anpr-health`, `anpr-uplink` |
| `gate/fault` | cualquiera | `anpr-health` |
| `gate/verdict` | `anpr-uplink` | `anpr-trigger` (reintento si ilegible), `anpr-health` |
| `svc/<servicio>/status` | cada servicio (y el broker, como Last Will) | `anpr-health` |
| `camera/status` | `anpr-capture` | `anpr-health` |
| `health/summary` | `anpr-health` | diagnóstico (`mosquitto_sub`) |

**`anpr-gate` es el único suscriptor de `gate/command` y el único que toca GPIO.**
No tiene acceso a internet. Recibe órdenes del bus local y las valida contra su
propia máquina de estados antes de mover nada.
