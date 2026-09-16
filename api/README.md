# F2 — API + Base de datos

FastAPI + SQLAlchemy async + Alembic. Reemplaza a `legacy/backend/` (Flask).

Implementa **exactamente** `contracts/openapi.yaml`. Ver también `contracts/db-schema.md`.

## Cómo correrlo

```bash
uv venv && uv pip install -e ".[dev]"
cp .env.example .env
.venv/bin/alembic upgrade head
.venv/bin/python scripts/seed.py --email tu@uni.pe --name "Tu Nombre"   # admin inicial
.venv/bin/uvicorn app.main:app --reload --port 8000
```

- API: http://localhost:8000
- Docs interactivos: http://localhost:8000/docs

Por defecto usa **SQLite**, así que arranca sin instalar ningún motor de base de
datos. Para MySQL, cambia `DATABASE_URL` a `mysql+aiomysql://user:pass@host:3306/anpr`.

> El `seed.py` existe porque `POST /users` exige rol administrativo: con la base
> vacía nadie podría crear al primer administrador.

| Comando | Qué hace |
|---|---|
| `pytest` | 67 tests |
| `ruff check app tests scripts` | Lint |
| `python scripts/check_contract.py` | Verifica que la API coincide con el contrato |
| `alembic revision --autogenerate -m "..."` | Nueva migración |

> **Nota del entorno:** esta máquina tiene ROS en `PYTHONPATH`, y sus plugins de
> pytest rompen la colección de tests. Usa `PYTHONPATH= pytest`.

## Despliegue en AWS Lambda

`app/lambda_handler.py` expone la app con Mangum detrás de CloudFront. Guía completa
en `infra/README.md`. Ajustes que solo se activan en AWS (vacíos en local):

| Variable | Efecto |
|---|---|
| `SSM_PREFIX` | Carga los secretos desde SSM Parameter Store al arrancar |
| `DB_SSL_CA` | TLS hacia la base de datos con la CA de Aiven |
| `DB_NULLPOOL` | Sin pool: evita reutilizar conexiones entre invocaciones |
| `ORIGIN_VERIFY_SECRET` | Rechaza con 403 lo que no llegue desde CloudFront |
| `INFER_FUNCTION_NAME` | Usa el Lambda de inferencia en vez del stub |

Respuestas nuevas de `POST /v1/detections`: **413** si la ráfaga supera 4 MB (el
límite de invocación síncrona de Lambda es 6 MB y los frames van en base64), y
**503** si la inferencia falla, para que la Pi reintente sin abrir.

## Estructura

```
app/
├── core/       config.py (pydantic-settings), security.py (Argon2 + JWT), deps.py
├── db/         models.py, session.py
├── schemas/    common.py (placas, cursores, UTC), user, auth, event
├── services/   authorization.py (regla de acceso), plate_reader.py (costura con F4)
└── routers/    auth, users, cars, events, detections
```

## Decisiones

**Autenticación.** Access token de 15 min por cabecera; refresh de 14 días en
cookie `HttpOnly` con path `/auth`. El access token nunca toca `localStorage`
en el cliente, así que un XSS no puede robar la sesión. Argon2id para las
contraseñas, con rehash automático si suben los parámetros.

**Sin MQTT.** `POST /v1/detections` devuelve el veredicto en la misma respuesta
HTTP. La Pi que detecta es la misma que abre, así que un broker intermedio solo
añadiría un componente más que puede fallar en el camino crítico.

**Idempotencia.** `event_uuid` es único: un reenvío por timeout no registra ni
abre dos veces.

**Fechas siempre en UTC con sufijo `Z`.** Sin la `Z`, `new Date(iso)` en el
navegador interpreta la fecha como hora local y el dashboard mostraría las
detecciones desplazadas.

**La inferencia no vive aquí.** `services/plate_reader.py` define la interfaz
con F4; `StubPlateReader` permite probar todo el flujo sin torch ni paddleocr.

## Deuda del legacy que queda resuelta

| Problema | Ahora |
|---|---|
| Sin autenticación: un POST anónimo a `/list/cars` abría la puerta | JWT + `Depends` en todo salvo `/health` y `/auth/login` |
| Dos capas de BD contradictorias (`connect.py` vs `db.py`) | Una sesión async inyectada |
| `create_user` no insertaba `role`: todos quedaban `student` | Se guarda, con test que lo fija |
| Alta en dos pasos con "rollback best-effort" en un catch vacío | `POST /users` transaccional |
| `schema.sql` empezaba con `DROP TABLE` de las 4 tablas | Alembic |
| `- timedelta(hours=5)` a mano | UTC en BD, `Z` al serializar |
| `GET /v1/event` devolvía la tabla entera | Paginación keyset + filtros en SQL |
| Excepciones tragadas sin loguear | Handler global con `logging.exception` |
| Placas comparadas como texto crudo | Normalización en Pydantic, en un solo sitio |
| Baja de usuario no revocaba acceso | `resolve_plate` exige propietario activo |

## Estado

- [x] Modelos, migraciones Alembic y esquema del contrato
- [x] Auth JWT + Argon2, roles y guardia en todos los routers
- [x] Users, cars, events, detections con paginación por cursor
- [x] 49 tests, lint limpio, rutas verificadas contra el contrato
- [ ] Hito **I1**: conectar F1 a esta API (`VITE_USE_MOCKS=false`)
- [ ] Empaquetado Lambda + Mangum (F3)
- [ ] Sustituir `StubPlateReader` por el cliente real (F4)
