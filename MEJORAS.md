# Sistema ANPR — FIM UNI · Plan de Mejoras

> Estado analizado: rama `main`, commit `a2f5c55`.
> Stack objetivo: **API en FastAPI**, **frontend en React**.

---

## 0. Resumen del estado actual

| Componente | Hoy | Objetivo |
|---|---|---|
| API | Flask 3 + blueprints + PyMySQL crudo | FastAPI + Pydantic + SQLAlchemy/async |
| Frontend | Next.js 14 (App Router) + shadcn/ui | React (decidir: seguir en Next o Vite SPA) |
| DB | MySQL en Aiven, SQL a mano | Igual, pero con migraciones (Alembic) |
| Broker | MQTT (paho) hacia la Raspberry | Igual, con cliente async y reconexión |
| Cámara | Sony Camera Remote API (MJPEG) | Igual, proxy con manejo de sesión |
| Auth | **Inexistente** (login simulado) | JWT / sesión real con RBAC |

Bloqueadores reales de producción: **no hay autenticación**, **no hay `requirements.txt`**, **el `venv/` está commiteado** y **hay dos capas de acceso a base de datos que se contradicen**.

---

## 1. Crítico — hacer antes que nada

### 1.1 Sacar `venv/` del repositorio
2643 de los 2708 archivos versionados son del virtualenv (binarios de OpenCV/NumPy incluidos). Infla el clon, rompe la portabilidad y ya está en el historial.

```bash
git rm -r --cached venv
printf 'venv/\n.venv/\n' >> .gitignore
git commit -m "chore: dejar de versionar el virtualenv"
```
Si el tamaño del historial molesta, reescribir con `git filter-repo --path venv --invert-paths` (coordinar con quien tenga clones).

### 1.2 No hay declaración de dependencias
No existe `requirements.txt`, `pyproject.toml` ni lockfile de Python. Nadie puede reproducir el entorno. El `venv/` que sí está commiteado solo trae `requests`, `opencv-python` y `numpy` — o sea, ni siquiera es el entorno del backend (falta Flask, PyMySQL, paho-mqtt, python-dotenv).

Migrando a FastAPI, crear `pyproject.toml` con `uv` o Poetry y fijar versiones.

### 1.3 Autenticación: no existe
- `web/src/app/login/page.tsx:22` — el login es un `setTimeout` de 1 s y un `window.location.href = "/dashboard"`. Cualquiera entra escribiendo la URL.
- `backend/auth.py` está a medio hacer: usa placeholders `?` de SQLite contra una conexión MySQL, captura `db.IntegrityError` (que PyMySQL no expone así), llama a `render_template('auth/register.html')` sin carpeta `templates/`, y hace `url_for("auth.login")` apuntando a un endpoint que nunca se definió.
- **Todos** los endpoints de `/list/*` y `/v1/*` son públicos: cualquiera en la red puede dar de alta una placa autorizada y abrir la puerta.
- `SECRET_KEY='dev'` hardcodeado en `backend/__init__.py:12`.
- La tabla `login` del `schema.sql` existe pero nadie la usa.

Mínimo aceptable: JWT de acceso corto + refresh en cookie `HttpOnly`, hash Argon2/bcrypt, y dependencia `Depends(current_user)` en todos los routers salvo el healthcheck.

### 1.4 Credenciales y hosts hardcodeados
- `backend/connect.py:17` y `backend/db.py:16` — `user="avnadmin"` fijo en el código.
- `backend/db.py:17` — puerto por defecto `21752` (el de la instancia real de Aiven).
- `backend/mqqt.py:9` — `MQTT_HOST` por defecto `10.95.239.139`.
- `web/src/app/api/camera/live/route.ts:8` — IP de la cámara `192.168.122.1` en el código.

Todo a variables de entorno, con un `.env.example` versionado (hoy solo existe `web/.env.local`, correctamente ignorado, y nada equivalente para el backend).

---

## 2. Migración Flask → FastAPI

### 2.1 Estructura propuesta

```
api/
  pyproject.toml
  alembic/
  app/
    main.py               # create_app, CORS, lifespan
    core/
      config.py           # pydantic-settings
      security.py         # hashing, JWT
      deps.py             # get_db, get_current_user
    db/
      session.py          # async engine + sessionmaker
      models.py           # SQLAlchemy: User, ListCar, EventDetection
    schemas/              # Pydantic: UserIn/Out, CarIn/Out, EventIn/Out
    routers/
      auth.py             # /auth/login, /auth/refresh, /auth/me
      users.py            # /users
      cars.py             # /cars
      events.py           # /events        (ex /v1/event)
      camera.py           # /camera/live   (proxy MJPEG)
    services/
      mqtt.py             # cliente asíncrono + publish_authorization
      authorization.py    # regla de negocio placa → autorizado
```

### 2.2 Mapa de endpoints

| Flask hoy | FastAPI propuesto | Nota |
|---|---|---|
| `GET /` | `GET /health` | Devolver estado de DB y MQTT |
| `GET /users` (`routes.py`) | *eliminar* | Consulta la tabla `users`, que **no existe** (el schema define `user`). Endpoint muerto y duplicado de `/list/users`. |
| `GET/POST /list/users` | `GET/POST /users` | |
| `GET/PUT/DELETE /list/users/<id>` | `/users/{id}` | |
| `GET/POST /list/cars` | `GET/POST /cars` | |
| `GET/PUT/DELETE /list/cars/<id>` | `/cars/{id}` | |
| `GET /list/getlist` | `GET /users?include=cars` | El join actual no tiene nombre semántico |
| `GET/POST /v1/event` | `GET/POST /events` | Separar en dos handlers |
| `POST /v1/authorization` | `GET /cars/by-plate/{plate}` | Es una consulta, no debería ser POST |

### 2.3 Deudas que la migración debe resolver de paso

- **Dos capas de DB coexistiendo.** `backend/connect.py` (conexión nueva por query, `execute_query`) y `backend/db.py` (conexión por request en `flask.g`) hacen lo mismo de dos formas distintas; `routes.py` usa una y `vehicle.py`/`listcrud.py` la otra. Con FastAPI queda una sola: sesión async inyectada por `Depends`.
- **Sin pool de conexiones.** `connect.py` abre y cierra una conexión TCP+TLS a Aiven por cada query. Con `create_async_engine` y `pool_size` esto desaparece.
- **`client_flag=CLIENT.MULTI_STATEMENTS`** (`db.py:19`) está habilitado globalmente solo para poder correr `schema.sql` de un tirón. Es una superficie de inyección SQL innecesaria en todas las demás queries — se resuelve usando Alembic para el esquema.
- **Excepciones tragadas.** En `listcrud.py` casi todos los `except Exception as e` devuelven un 500 genérico y **descartan `e`** sin loguearlo. Un fallo en producción no deja rastro. Usar `logging` estructurado y un exception handler global.
- **Sin validación de entrada.** `plate` se acepta como venga: sin normalizar mayúsculas, sin quitar espacios, sin regex de formato peruano (`^[A-Z]{3}-\d{3}$`). Dos registros de la misma placa con distinto formato rompen el `UNIQUE` y el join. Pydantic con `field_validator` lo resuelve en un sitio.
- **Hack de zona horaria.** `vehicle.py:57` hace `v['datetime'] - timedelta(hours=5)` a mano. Guardar en UTC y convertir a `America/Lima` con `zoneinfo` en la capa de presentación.
- **Sin paginación.** `GET /v1/event` devuelve la tabla `event_detection` completa ordenada por id. Con meses de detecciones el dashboard se cae. Paginación por cursor (`?after_id=&limit=`) + filtros de rango de fecha y placa en SQL, no en el cliente.
- **MQTT bloqueante en un mundo async.** `mqqt.py` arranca el cliente en `@bp.record_once`; con FastAPI va en el `lifespan`, con `asyncio-mqtt`/`aiomqtt` o `paho` en su propio hilo, y publicando con `qos=1`.
- **El resultado del publish MQTT se ignora.** `vehicle.py:44-46` solo imprime un warning si falla. Si el mensaje no llega a la Raspberry, la puerta no abre y el usuario no se entera. Registrar el resultado del `publish` en la tabla de eventos (`mqtt_published BOOL`) y reintentar.
- **Archivos muertos.** `backend/models.py` y `backend/extensions.py` están vacíos; `backend/prueba.py` es un script de pruebas con `from connect import ...` (import absoluto, solo funciona ejecutándolo desde dentro de `backend/`). Borrar o mover a `scripts/`.

---

## 3. Base de datos

- **Sin migraciones.** `schema.sql` empieza con `DROP TABLE IF EXISTS` de las cuatro tablas: ejecutar `flask init-db` en producción borra todo. Reemplazar por Alembic.
- **`event_detection.plate` es un VARCHAR suelto**, sin FK a `list_car`. El join de `/v1/event` es sobre texto. Es defendible (se quiere registrar placas *no* autorizadas, que no están en `list_car`), pero conviene documentarlo y añadir un índice compuesto `(plate, datetime)` para las consultas por rango.
- **Faltan columnas que el frontend ya espera**: `confidence` (el adaptador de `records/page.tsx:37` la fuerza a `0`) e `image` (siempre `null`). Si el pipeline ANPR calcula confianza, guardarla.
- **`user.role`** tiene ENUM `('student','teacher','administrator')`, pero `create_user` en `listcrud.py:73` **no inserta `role`** aunque el frontend lo envía → todos quedan como `student`. Bug activo.
- **`login` y `user` son tablas separadas** sin relación. Unificar: `user.password_hash` + `user.is_active`.
- Falta auditoría: quién dio de alta una placa y cuándo (`created_at`, `created_by`).

---

## 4. Frontend React

### 4.1 Decisión previa: ¿Next.js o React puro?

Lo que hay hoy **ya es React** — Next.js 14 App Router con React 19. Antes de tocar nada, elegir:

**Opción A — Quedarse en Next.js (recomendada).** Los route handlers de `web/src/app/api/*` ya funcionan como proxy hacia el backend y, sobre todo, `api/camera/live/route.ts` retransmite el MJPEG de la cámara: eso necesita un servidor. Es el menor trabajo y mantiene el streaming andando.

**Opción B — React SPA con Vite.** Más simple de razonar y de desplegar como estáticos, pero hay que mover a FastAPI las tres rutas de `app/api/` (`event`, `list_car`, `camera/live`), incluido el proxy MJPEG con `StreamingResponse`, y configurar CORS. Elegir esta solo si el despliegue estático es un requisito.

En ambos casos vale lo que sigue.

### 4.2 Problemas concretos del código actual

- **`fetch` a pelo en `useEffect`** (`records/page.tsx:51`, `users-vehicles/page.tsx:58`), con `loading`/`error` reimplementados a mano en cada página y sin revalidación. Pasar a **TanStack Query**: caché, reintentos, `refetchInterval` para los registros en vivo e invalidación tras crear/editar.
- **Bug en el proxy de `list_car`.** `PUT` y `DELETE` en `web/src/app/api/list_car/route.ts` reciben el **id de usuario** y lo usan como **id de carro**: `fetch(\`${BACKEND}/list/cars/${id}\`)`. Solo funciona mientras `user.id === list_car.id`, es decir, por casualidad. Hay que devolver el `car_id` desde el backend y usar ese.
- **Escrituras sin transacción.** El `POST` de `list_car` crea usuario, luego carro, y si el segundo falla hace un "rollback best-effort" con un `try/catch {}` vacío. Debe ser **un solo endpoint transaccional** en FastAPI (`POST /users` con el carro anidado).
- **Sin gestión de estado de sesión.** No hay `AuthContext`, ni guardia de rutas, ni middleware. Al implementar auth: `middleware.ts` (Next) o `<ProtectedRoute>` (Vite) + refresh automático del token.
- **Rutas huérfanas.** `dashboard/{statistics,database,users,settings,stream}/page.tsx` (~1100 líneas) están comentadas en el sidebar (`components/sidebar.tsx:22-29`) y llenas de datos mock. Borrarlas o terminarlas — hoy solo confunden.
- **`stream/page.tsx:24`** genera detecciones falsas con `setInterval`. Conectarlo a los eventos reales (SSE o WebSocket desde FastAPI en lugar de polling).
- **Import muerto y peligroso**: `login/page.tsx:11` importa `NextResponse` de `next/server` dentro de un componente `"use client"`.
- **Filtrado en el cliente.** `records/page.tsx:71` filtra por placa y estado sobre el array completo en memoria. Mover a query params del backend.
- **`package.json`**: el nombre sigue siendo `my-v0-project`; `@types/react` y `@types/react-dom` están en `^18` con React `^19` instalado (desajuste de tipos); hay ~25 paquetes de Radix instalados de los que se usan 8.
- **Sin manejo de reconexión en el stream.** `StreamView` marca `failed` en el primer `onError` y no reintenta nunca. Añadir backoff exponencial.
- **Fuga de sesión de la cámara.** `camera/live/route.ts` llama `startLiveview` en cada request y **nunca** llama `stopLiveview`. Tras varias recargas la cámara se queda sin sesiones. Cerrar en el `finally` del stream o mantener una única sesión compartida.
- Accesibilidad y UX: sin `aria-label` en los botones de icono, sin estados vacíos, sin confirmación al eliminar un usuario, sin toasts (`sonner` está instalado y sin usar).

---

## 5. Cámara y `main2.py`

- `main2.py:16` llama `rpc("startRecMode","HQ")` pero `rpc` está definido con **un solo parámetro** (`main2.py:6`). Siempre lanza `TypeError`, que el `except Exception: pass` de la línea siguiente se traga. El modo rec nunca se activa.
- El parseo de JPEG busca `\xff\xd8`/`\xff\xd9` en el buffer sin respetar el `boundary` multipart: un `\xff\xd9` dentro de los datos EXIF puede cortar un frame a la mitad.
- El buffer crece sin límite si nunca aparece un EOI válido.
- Este script duplica lo que hace `camera/live/route.ts`. Convertirlo en un módulo compartido o dejarlo explícitamente como herramienta de diagnóstico en `scripts/`.

---

## 6. Seguridad

- Sin autenticación ni autorización (ver 1.3). **La consecuencia directa: un `POST /list/cars` anónimo abre la puerta del campus.**
- Sin CORS configurado, sin rate limiting, sin CSRF.
- Sin TLS entre el frontend y la API (`BACKEND_URL` apunta a HTTP).
- MQTT en el puerto 1883 sin TLS y sin credenciales por defecto: cualquiera en la red puede publicar en `app/tx` y ordenar la apertura. Pasar a MQTTS (8883) con usuario/contraseña y ACL por tópico, y firmar el payload.
- `ssl={"ssl": {}}` en las conexiones a MySQL habilita TLS **sin verificar el certificado**. Cargar el CA de Aiven.
- Sin logging de auditoría: no queda registro de quién autorizó qué placa.
- Datos personales (nombre, teléfono, correo, placa) sin política de retención.

---

## 7. Infraestructura y calidad

- **Cero tests.** Empezar por los de mayor valor: la regla de autorización de placas y los CRUD (pytest + httpx + una MySQL de test en Docker).
- **Sin CI.** GitHub Actions: lint (ruff) + mypy + pytest + `next build` en cada PR.
- **Sin Docker.** `docker-compose.yml` con `api`, `web`, `mysql` y `mosquitto` para levantar todo con un comando y no depender de Aiven en desarrollo.
- **Sin README ni documentación de despliegue.** No hay ningún `.md` en la raíz del repo.
- **Sin observabilidad.** Ni logging estructurado, ni métricas, ni healthcheck real. Para un sistema que controla una puerta física, hace falta al menos una alerta cuando el MQTT se desconecta.
- Formateo inconsistente (mezcla de comillas, indentación variable). Añadir `ruff format` y Prettier con pre-commit.
- Erratas en nombres que conviene arreglar al migrar: `mqqt.py` → `mqtt.py`, `prueba.py` fuera del paquete.

---

## 8. Orden sugerido

| # | Tarea | Esfuerzo | Impacto |
|---|---|---|---|
| 1 | Sacar `venv/` del repo + `pyproject.toml` + `.env.example` | 1 h | Alto |
| 2 | Autenticación real (FastAPI + JWT) y proteger todos los endpoints | 2-3 d | **Crítico** |
| 3 | Migrar Flask → FastAPI con SQLAlchemy y Pydantic | 3-5 d | Alto |
| 4 | Alembic + arreglar `role`, timezone, normalización de placas | 1 d | Alto |
| 5 | Corregir el bug `car_id`/`user_id` y hacer transaccional el alta | 4 h | Alto |
| 6 | TanStack Query + guardia de rutas en el frontend | 1-2 d | Medio |
| 7 | Paginación y filtros en servidor para `/events` | 1 d | Medio |
| 8 | Docker Compose + CI + primeros tests | 2 d | Medio |
| 9 | Borrar rutas huérfanas y datos mock | 2 h | Bajo |
| 10 | MQTTS, verificación de CA en MySQL, logging de auditoría | 1-2 d | Alto (seguridad) |
