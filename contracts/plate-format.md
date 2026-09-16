# Formato de placa: alcance actual y ampliación pendiente

## Decisión

**El sistema solo acepta el formato de placa de vehículo particular:**

```
^[A-Z][A-Z0-9]{2}-\d{3}$
```

Ejemplos válidos: `ABC-123`, `V1A-882`, `A11-234`.

Acordado el 2026-09-16. El patrón viene heredado de
`legacy/mqtt-camara-main/mqtt+camara.py`, donde ya se usaba, y se propagó al
contrato al formalizarlo.

## Por qué se acepta por ahora

Es el formato de los vehículos que hoy usan la Puerta 2. Ampliarlo antes de
tener casos reales sería complejidad especulativa: cada formato adicional
agranda la superficie de falsos positivos del OCR, y un falso positivo aquí
abre una puerta al vehículo equivocado.

## Qué queda FUERA, y qué pasa si aparece

Cualquier placa con otra disposición —**motos** en primer lugar, y según el
caso vehículos oficiales, de carga o de transporte público— **será rechazada
aunque el OCR la lea perfectamente**.

El síntoma en producción no es un error visible: la detección se registra como
*no legible* y la puerta simplemente no abre. Si alguien reporta "mi placa nunca
funciona", esto es lo primero que hay que descartar.

## Cómo verificar si hace falta ampliar

No es una pregunta que se responda desde el código ni con imágenes de internet:

1. ¿Qué tipos de vehículo usan la Puerta 2? ¿Entran motos?
2. Revisar placas reales en el estacionamiento y ver si todas encajan.
3. Contrastar contra la normativa vigente de SUNARP/MTC — **no dar por buenos
   los formatos de memoria**, que cambian con las sucesivas normas.

## Qué tocar al ampliar

Son cuatro sitios y **deben cambiar juntos**. El contrato manda; los otros tres
lo implementan.

| Frente | Archivo | Qué hay |
|---|---|---|
| **F0** | `contracts/openapi.yaml` | Schema `Plate`, campo `pattern` |
| **F0** | este archivo | Actualizar la decisión |
| **F2** | `api/app/schemas/common.py` | `PLATE_RE` y `normalize_plate()` |
| **F4** | `ml/src/anpr_ml/plate_text.py` | `PLATE_RE` y `_fix_by_position()` |
| **F1** | `web/src/lib/format.ts` | `PLATE_RE` y `normalizePlate()` |

Además, al ampliar hay que revisar dos cosas que hoy dependen de que el formato
sea uno solo:

**La corrección posicional de F4.** `_fix_by_position()` asume la estructura
`LLD-DDD`: sabe que las tres últimas posiciones son dígitos y por eso puede
convertir `O`→`0` con seguridad. Con varios formatos hay que decidir el formato
*antes* de corregir, o desactivar la corrección para los ambiguos.

**La regla del prefijo con letra.** `parse_plate()` rechaza lecturas cuyo
prefijo no tenga ninguna letra, para no inventar placas a partir de seis
dígitos. Si algún formato peruano empieza por dígitos, esa salvaguarda hay que
replantearla, no simplemente quitarla.

## Lo que NO cambia al ampliar

La normalización del separador. El guion está siempre en la misma posición
dentro de cada formato, así que no aporta información y puede reconstruirse.
Que el OCR devuelva `ABC123` en vez de `ABC-123` seguirá siendo tolerable: la
salida canónica siempre lleva guion.
