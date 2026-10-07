# F6 — Electrónica y potencia

Actuación del portón y cadena de seguridad. **Requiere electricista.**

## Situación actual

El portón lo abre una persona girando la perilla del UX-52. Esa persona cumple
**tres** funciones a la vez:

| Función que cumple la persona | Qué la reemplaza |
|---|---|
| Decide cuándo arrancar | El veredicto de la nube |
| Ve cuándo llegó al tope y para | **Finales de carrera** |
| Ve si hay alguien en medio | **Fotocelda de seguridad** |

Las dos últimas **no existen en hardware hoy**. Son obligatorias antes de automatizar:
sin final de carrera el motor se fuerza contra el tope hasta romper algo; sin
fotocelda, cierra sobre quien esté pasando. Que el motor sea potente es justamente
lo que lo hace peligroso sin esos sensores.

El UX-52 **no tiene realimentación de posición** — su entrada azul es tacómetro de
*velocidad*, no de posición.

## Alcance

- Relés opto-aislados o contactores con **enclavamiento mecánico** hacia FWD/REV
- Finales de carrera de apertura y cierre
- Fotocelda de seguridad
- Parada de emergencia NC tipo hongo
- Sensor de presencia para el disparo
- Gabinete IP65 con riel DIN, fuente 24 V, bornes, fusibles
- Supresor RC / varistor sobre los contactos (carga inductiva)
- **Conservar el control manual** como contingencia documentada

## La regla que gobierna este frente

E-stop, fotocelda y finales de carrera van **cableados en serie con la bobina del
contactor**, no solo leídos por GPIO.

**El software solo puede *pedir* movimiento; el hardware debe poder *negarlo*.**

Criterio de aceptación: **con la Pi apagada y el cable de red desconectado, la
fotocelda y los finales de carrera deben seguir deteniendo el motor.**
Si no lo hacen, no se pone en producción.

## Cómo trabajar aislado

Botón manual en lugar de GPIO. Valida potencia y seguridad sin esperar a F5.

## Terminado cuando

El portón se mueve con el botón, y fotocelda y finales de carrera cortan el motor
**con la Pi apagada**.

## Esta es la ruta crítica

Aunque integra al final, **empieza primero**: es el único frente con plazos que no
controlas (visita técnica, electricista, compra de sensores con demoras de
importación). El software se recupera con horas extra; un pedido de fotoceldas que
tarda tres semanas, no.

## Nota de F5 para el cableado

- **Resistencias pull-down** en las entradas de los módulos de relé: si un proceso
  muere y la línea GPIO queda suelta, el relé debe quedar abierto.
- El selector MANUAL/AUTO necesita un **contacto adicional hacia la Pi** (`MODE_AUTO`,
  a masa en AUTO): la Pi debe saber que no manda.
- Verificar en banco qué relé sube la pluma (`open_relay` en `/etc/anpr/edge.toml`).

## Convivencia con el mando manual

El selector FWD / STOP / REV existente **se conserva como mando manual**. Pero no se
pueden cablear los relés de la Pi en paralelo con él sin más: si el vigilante pide un
sentido y la Pi el otro, `FWD` y `REV` quedarían unidos a `0V` a la vez.

Por eso se añade un **selector MANUAL / AUTO** de varios contactos que conecta a los
bornes `FWD`/`REV` **o** el selector manual **o** los relés de la Pi, nunca ambos. Los
finales de carrera, la fotocelda y la parada de emergencia quedan **después** del
selector MANUAL / AUTO, así que protegen también el modo manual: hoy el vigilante debe
soltar la perilla a tiempo; con esto el portón se detiene solo en el tope.

## Particularidades de la pluma

- **Finales de carrera en el eje**, accionados por una leva: uno a 0° (horizontal,
  cerrada) y otro a ~90° (vertical, abierta). No en el extremo del brazo.
- **Fotocelda a lo ancho del carril, bajo la trayectoria del brazo** (~50 cm de altura):
  impide que la pluma baje sobre un auto o una persona.
- **Cierre automático** cuando el vehículo terminó de pasar: la fotocelda se interrumpe
  y se libera. Si nunca se interrumpe (el auto no avanzó), cierra tras un tiempo
  máximo. Nunca cierra con la fotocelda interrumpida.
- **El auto se detiene frente a la pluma**: la ráfaga se toma con el vehículo quieto,
  sin desenfoque por movimiento. El sensor de presencia va donde el auto se detiene.
- **Verificar en sitio:** que el brazo esté equilibrado (resorte o contrapeso) y que
  haya **desbloqueo manual** para levantarla sin energía.

## Datos pendientes de verificar en sitio

1. ~~Cómo se invierte el giro hoy~~ **Resuelto (2026-09-22):** con el selector
   FWD / STOP / REV de la caja de mando, junto a la perilla de velocidad, sin recablear
   el motor. Los relés de la Pi unirán `FWD`-`0V` o `REV`-`0V` y la perilla queda fija.
   Ver "Convivencia con el mando manual".
2. ~~Foto de la bornera del UX-52 instalado~~ **Resuelto (2026-10-07):** 9 bornes,
   etiquetados en chino y español, de izquierda a derecha:
   `AC-L` `AC-N` — alimentación 220 V (ya conectados: negro y rojo)
   `黑(Black)` `红(Red)` — devanado + condensador (ya conectados)
   `白(White)` — entrada "S", tacómetro de velocidad (ya conectado)
   `滅(Blue)` ×2 — más conexiones del devanado/condensador (ya conectados)
   **`0V` `FWD`(正转) `REV`(反转) — control de dirección, SIN NADA CONECTADO
   todavía.** Ahí van los dos relés de la Pi: uno entre `0V`-`FWD`, otro entre
   `0V`-`REV`. El propio diagrama impreso en la caja ya dibuja `K1`/`K2` como
   dos interruptores simples ahí — confirma el diseño planeado, no uno nuevo.
   El selector FWD/STOP/REV de la caja de mando (dato 1) se conecta aparte, a
   estos mismos tres bornes: el selector **MANUAL/AUTO** (ver más abajo) debe
   elegir entre ese selector y los relés de la Pi, nunca los dos a la vez.
3. ~~Potencia y tipo del motor~~ **Resuelto a medias (2026-10-07):** la etiqueta
   del propio `UX-52` dice **400 W, máx. 3 A, 220-240 V AC, 50/60 Hz** — es la
   capacidad del controlador, que debería coincidir con el motor por ser un
   juego emparejado. Falta la placa del motor en sí para confirmarlo
   (monofásico con condensador de arranque, a juzgar por los bornes `Black`/`Red`)
4. **Tiempo de recorrido completo** en segundos → define el timeout de marcha
5. ~~Tipo de portón~~ **Resuelto (2026-09-22):** **pluma** (barrera vehicular: brazo
   horizontal que gira ~90° sobre un eje lateral). Ver "Particularidades de la pluma".

## BOM estimado

Ver `PLAN_AWS.md` §3, "Costos de hardware": ≈ $425.
