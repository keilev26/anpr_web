# F2 — API + Base de datos

FastAPI + SQLAlchemy async + Alembic. Migración de `legacy/backend/` (Flask).

## Alcance

- Routers: `auth`, `users`, `cars`, `events`, `detections`
- Autenticación JWT con Argon2 y `Depends(current_user)` en todo salvo healthcheck
- Migraciones Alembic (sustituyen a `schema.sql`, que empieza con `DROP TABLE`)
- Normalización de placas en la capa Pydantic
- **Genera `contracts/openapi.yaml`**, que consume F1

## No incluye

- Despliegue en AWS (F3) — este código corre igual en tu laptop
- El modelo de inferencia (F4); la API solo recibe la placa ya leída

## Cómo trabajar aislado

MySQL en Docker. Sin AWS.

## Terminado cuando

`pytest` verde: CRUD completo y regla de autorización correctos en local.

## Deuda que se resuelve al migrar

Detalle en `MEJORAS.md` §2.3 y `PLAN_AWS.md` Fase 2. Lo principal:

- Dos capas de BD contradictorias (`connect.py` vs `db.py`) → una sola sesión async
- `create_user` no inserta `role`: todos quedan `student`
- Hack de zona horaria `- timedelta(hours=5)` → UTC en BD, conversión en presentación
- `GET /v1/event` devuelve la tabla completa → paginación por cursor
- Excepciones tragadas sin loguear → logging estructurado
