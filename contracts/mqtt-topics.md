# Contrato B — Bus interno de la Pi

Mosquitto en `localhost`. No sale a internet; el bridge a AWS IoT Core es solo
para telemetría y salud (`anpr-health`).

```
gate/trigger       {"event_id", "source": "loop"|"manual", "ts"}
gate/frames_ready  {"event_id", "path", "count"}
gate/command       {"event_id", "action": "open", "ttl_s", "issued_at"}
gate/state         {"state": "closed"|"opening"|"open"|"closing"|"fault",
                    "position_known": bool}
gate/fault         {"code", "detail", "ts"}
```

## Quién publica y quién escucha

| Tópico | Publica | Escucha |
|---|---|---|
| `gate/trigger` | `anpr-trigger` | `anpr-capture` |
| `gate/frames_ready` | `anpr-capture` | `anpr-uplink` |
| `gate/command` | `anpr-uplink` | `anpr-gate` |
| `gate/state` | `anpr-gate` | `anpr-health`, `anpr-uplink` |
| `gate/fault` | cualquiera | `anpr-health` |

**`anpr-gate` es el único suscriptor de `gate/command` y el único que toca GPIO.**
No tiene acceso a internet. Recibe órdenes del bus local y las valida contra su
propia máquina de estados antes de mover nada.
