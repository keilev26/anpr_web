# Contrato D — Modelo de datos

**La migración Alembic inicial de `api/` es el contrato.** Este documento explica
las decisiones; el esquema ejecutable vive en `api/alembic/`.

## Cambios frente al esquema legacy (`legacy/backend/schema.sql`)

| Cambio | Motivo |
|---|---|
| `event_detection.confidence` | Hoy el frontend la fuerza a `0`; YOLO y el OCR sí la calculan |
| `event_detection.image_s3_key` | Hoy siempre `null`; permite ver la foto de la detección |
| `event_detection.camera_id` | Soporte multi-puerta |
| `event_detection.gate_opened` | Distinguir "autorizado" de "el portón realmente abrió" |
| `event_detection.latency_ms` | Medir el presupuesto de 4 s en producción |
| `user.password_hash`, `is_active` | Unificar con la tabla `login`, que hoy existe huérfana |
| `created_at` / `created_by` | Auditoría: quién autorizó qué placa |
| Índice `(plate, datetime)` | Consultas por rango de fecha |
| Tabla `login_attempt` (nueva) | Bloqueo temporal por correo tras intentos fallidos; en BD porque Lambda no comparte memoria entre contenedores |

## Decisiones que se conservan

**`event_detection.plate` sigue siendo texto sin FK a `list_car`.** Es deliberado:
hay que poder registrar placas **no** autorizadas, que por definición no están en
la lista blanca.

**`list_car.plate` sigue siendo `UNIQUE`.** Una placa no puede pertenecer a dos personas.

## Normalización de placas

Se aplica en la capa Pydantic, **antes** de tocar la BD, en un solo sitio:

- Mayúsculas, sin espacios
- Formato canónico `^[A-Z][A-Z0-9]{2}-\d{3}$`
- Reinsertar el guion si el OCR lo omitió

El join `event_detection.plate = list_car.plate` es sobre texto: sin esto, un espacio
o una minúscula hace que una placa autorizada aparezca como denegada.
