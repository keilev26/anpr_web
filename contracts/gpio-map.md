# Contrato C — GPIO (costura F5 ↔ F6)

| Señal | Dir | Tipo | Nota |
|---|---|---|---|
| `RELAY_FWD` | OUT | Activo alto | Hacia FWD/0V del UX-52 |
| `RELAY_REV` | OUT | Activo alto | Hacia REV/0V del UX-52 |
| `LED_STATUS` | OUT | — | Estado visible en gabinete |
| `LIMIT_OPEN` | IN | **NC**, pull-up | Abierto = portón en tope |
| `LIMIT_CLOSED` | IN | **NC**, pull-up | |
| `PHOTOCELL_OK` | IN | **NC**, pull-up | Bajo = vía libre |
| `ESTOP_OK` | IN | **NC**, pull-up | Bajo = no hay emergencia |
| `PRESENCE` | IN | Pull-up | Sensor de disparo |
| `MANUAL_BTN` | IN | Pull-up | Contingencia sin red |
| `MODE_AUTO` | IN | Pull-up | Selector MANUAL/AUTO. Bajo = AUTO; cortado = manual (la Pi no acciona) |

> Números de pin BCM: **pendientes**, se fijan al cerrar el diseño del gabinete (F6).

## Por qué todas las entradas de seguridad son NC

Normalmente cerrado significa que un **cable cortado o un sensor desconectado se lee
como "no seguro"** y el portón no se mueve. Con lógica normalmente abierta, el mismo
fallo se leería como "todo bien": un fallo silencioso que solo se descubre cuando
el portón cierra sobre algo.

## La condición no negociable

Estas entradas las lee la Pi para **decidir y reportar**. Pero además, en hardware,
cada una corta el motor por su cuenta — **no todas en el mismo sitio**:

- **`ESTOP_OK` es la única universal**: va en serie con la **bobina del contactor
  principal**, que alimenta todo el UX-52. Corta cualquier sentido, siempre.
- **`LIMIT_OPEN` corta solo el sentido de abrir** (en serie con el relé que activa
  `FWD`). **`LIMIT_CLOSED` y `PHOTOCELL_OK` cortan solo el sentido de cerrar** (en
  serie con el relé que activa `REV`).

**Por qué no van los cuatro en el contactor principal, como se pensó al inicio:**
si el final de carrera de "abierta" cortara *todo* el UX-52, la pluma quedaría
trabada ahí — sin alimentación, tampoco podría cerrar después, porque el brazo
sigue físicamente en esa posición. Cada final debe bloquear solo *su propio*
sentido para que el contrario siga disponible. Igual con la fotocelda: su trabajo
es impedir que la pluma **baje** sobre algo, no impedir que suba — bloquear abrir
dejaría el brazo a medio camino sobre un obstáculo en vez de alejarse de él.
Diagrama completo (con lo ya confirmado en la bornera real del UX-52):
[`hardware/cableado_ux52.html`](https://claude.ai/artifact/KUy8W9JECVxAuHkCrrCqXq).

**El software solo puede *pedir* movimiento; el hardware debe poder *negarlo*.**

Así, un cuelgue de la Pi, una caída de internet o un bug en el Lambda nunca pueden
cerrar el portón sobre una persona ni forzar el motor contra el tope.

Criterio de aceptación: **con la Pi apagada y el cable de red desconectado**,
pulsar la emergencia debe detener cualquier movimiento; con la pluma cerrando,
interrumpir la fotocelda o alcanzar el final de carrera correspondiente debe
detenerla. Si no lo hacen, el cableado está mal y no se pone en producción.

## Reglas que `anpr-gate` hace cumplir en software (además del hardware)

- FWD y REV nunca energizados a la vez; pausa de 0.5 s al invertir.
- Timeout de marcha = tiempo real de recorrido + 20%. Si no llega el final de
  carrera, corta y marca falla.
- Rechaza órdenes nuevas mientras hay movimiento en curso.
- Al arrancar asume posición desconocida y hace ciclo de referencia hacia "cerrado".
- Idempotencia por `event_id`.
- Si `anpr-gate` termina por cualquier motivo (incluido `kill -9`), systemd ejecuta
  `anpr-gate-safe-off` (`ExecStopPost=`), que pone ambos relés a 0.
- En MANUAL (`MODE_AUTO` alto) no acciona nada. Salir de una falla exige pasar por MANUAL.

Implementación: `edge/src/anpr_edge/gate/machine.py`. Números BCM propuestos en
`edge/deploy/edge.toml.example`, a confirmar con F6.
- Cierre automático de la pluma: tras abrir, espera a que `PHOTOCELL_OK` se interrumpa
  y se libere (el vehículo pasó) o un tiempo máximo. **Nunca ordena cerrar con la
  fotocelda interrumpida.**
