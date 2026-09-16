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

## Datos pendientes de verificar en sitio

1. **Cómo se invierte el giro hoy** — ¿hay interruptor FWD/REV cableado?
2. **Foto de la bornera del UX-52 instalado** — la serigrafía varía entre clones
3. **Potencia y tipo del motor** (W; monofásico con condensador de arranque)
4. **Tiempo de recorrido completo** en segundos → define el timeout de marcha
5. **Tipo de portón**: pluma, corredizo o batiente

## BOM estimado

Ver `PLAN_AWS.md` §3, "Costos de hardware": ≈ $425.
