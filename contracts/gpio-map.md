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

> Números de pin BCM: **pendientes**, se fijan al cerrar el diseño del gabinete (F6).

## Por qué todas las entradas de seguridad son NC

Normalmente cerrado significa que un **cable cortado o un sensor desconectado se lee
como "no seguro"** y el portón no se mueve. Con lógica normalmente abierta, el mismo
fallo se leería como "todo bien": un fallo silencioso que solo se descubre cuando
el portón cierra sobre algo.

## La condición no negociable

Estas entradas las lee la Pi para **decidir y reportar**. Pero E-stop, fotocelda y
finales de carrera van **además cableados en serie con la bobina del contactor**.

**El software solo puede *pedir* movimiento; el hardware debe poder *negarlo*.**

Así, un cuelgue de la Pi, una caída de internet o un bug en el Lambda nunca pueden
cerrar el portón sobre una persona ni forzar el motor contra el tope.

Criterio de aceptación: **con la Pi apagada y el cable de red desconectado, la
fotocelda y los finales de carrera deben seguir deteniendo el motor.** Si no lo
hacen, el cableado está mal y no se pone en producción.

## Reglas que `anpr-gate` hace cumplir en software (además del hardware)

- FWD y REV nunca energizados a la vez; pausa de 0.5 s al invertir.
- Timeout de marcha = tiempo real de recorrido + 20%. Si no llega el final de
  carrera, corta y marca falla.
- Rechaza órdenes nuevas mientras hay movimiento en curso.
- Al arrancar asume posición desconocida y hace ciclo de referencia hacia "cerrado".
- Idempotencia por `event_id`.
