# División del proyecto en frentes independientes

Documento de coordinación. Define **qué hace cada frente, qué entrega, y cómo trabaja sin depender de los demás**.

Regla base: un frente solo puede avanzar en paralelo si conoce el **contrato** con sus vecinos y tiene un **simulador** de ellos. La sección 2 define los contratos; la columna "Cómo trabaja aislado" de cada frente define su simulador.

---

## 1. Los frentes

Propusiste 4. Los divido en 6 porque dos de ellos mezclan cosas con ritmos y perfiles distintos:

| Tu propuesta | Se divide en | Por qué |
|---|---|---|
| Servicios AWS | **F3 Infra** + **F4 ML** | Empaquetar y desplegar es DevOps; exportar el modelo y medir precisión es ML. Se estorban si van juntos. |
| (implícito en AWS) | **F2 API** | El código FastAPI corre igual en tu laptop que en Lambda. No debe esperar a que la infra exista. |

| # | Frente | Alcance | Perfil |
|---|---|---|---|
| **F0** | **Contratos** | Esquemas compartidos. **Prerequisito, no paralelo.** | Arquitectura |
| **F1** | **Web** | React SPA: dashboard, login, CRUD de usuarios y placas | Frontend |
| **F2** | **API + BD** | FastAPI, migraciones Alembic, autenticación JWT | Backend |
| **F3** | **Infra AWS** | IaC, Lambda, RDS, S3, CloudFront, IoT Core, CI/CD | DevOps |
| **F4** | **ML / Inferencia** | Export ONNX, adelgazar OCR, handler, métricas de precisión | ML |
| **F5** | **Raspberry Pi** | Servicios systemd: captura, uplink, control del portón | Sistemas |
| **F6** | **Electrónica** | Relés, cadena de seguridad, sensores, gabinete | Electricista |

---

## 2. Contratos (F0) — hacer esto PRIMERO

Es ~1 día de trabajo y es lo que desbloquea a los otros seis. Sin esto no hay paralelismo real.

### Contrato A — Pi → Nube (camino crítico)

```
POST /v1/detections          Content-Type: multipart/form-data
  gate_id      string        "puerta-2"
  event_id     uuid          idempotencia: reenviar no abre dos veces
  captured_at  ISO8601 UTC
  frames[]     1..10 JPEG

200 OK
{
  "event_id":   "uuid",
  "plate":      "CUB-604" | null,
  "confidence": 0.0-1.0,
  "authorized": true | false,
  "user":       {"name": "...", "role": "student"} | null,
  "command":    {"action": "open" | "deny", "ttl_s": 10},
  "latency_ms": 1420
}
```

Dos decisiones deliberadas:

- **`command` viene explícito**, la Pi no lo deduce de `authorized`. Si mañana un operador abre desde el dashboard, o hay una regla de horario, la lógica vive en un solo lugar.
- **`ttl_s`** — si la respuesta llega tarde (red lenta, reintento), la Pi la descarta. Sin esto, un veredicto retrasado puede abrir el portón cuando el auto ya se fue.

### Contrato B — Bus interno de la Pi (Mosquitto en localhost)

```
gate/trigger       {"event_id", "source": "loop"|"manual", "ts"}
gate/frames_ready  {"event_id", "path", "count"}
gate/command       {"event_id", "action": "open", "ttl_s", "issued_at"}
gate/state         {"state": "closed"|"opening"|"open"|"closing"|"fault",
                    "position_known": bool}
gate/fault         {"code", "detail", "ts"}
```

### Contrato C — GPIO (la costura F5 ↔ F6)

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

**Todas las entradas de seguridad son NC (normalmente cerrado).** Un cable cortado o un sensor desconectado se lee como "no seguro" y el portón no se mueve. Al revés sería un fallo silencioso.

**Recordatorio de la condición no negociable:** estas entradas las lee la Pi para *decidir y reportar*, pero E-stop, fotocelda y finales de carrera van **además cableados en serie con la bobina del contactor**. El software pide movimiento; el hardware puede negarlo aunque la Pi esté colgada.

### Contrato D — Base de datos

La migración Alembic inicial **es** el contrato. Incluye las columnas que hoy faltan y el dashboard ya espera: `confidence`, `image_s3_key`, `camera_id`, `gate_opened`, `latency_ms`.

### Contrato E — API para el frontend

El `openapi.json` que FastAPI genera solo. F1 genera su cliente TypeScript desde ahí; nadie escribe tipos a mano en dos lados.

---

## 3. Cómo trabaja cada frente aislado

| Frente | Simula a sus vecinos con | Terminado cuando |
|---|---|---|
| **F1 Web** | MSW o `json-server` sirviendo el `openapi.json` de F0 | Todas las vistas funcionan contra mocks; login con guardia de rutas real |
| **F2 API** | MySQL en Docker; sin AWS | `pytest` verde; CRUD y autorización correctos en local |
| **F3 Infra** | Contenedor "hello world" en vez del Lambda real | `terraform apply` levanta todo y responde un 200 |
| **F4 ML** | Una carpeta de fotos de placas. Sin nube, sin Pi | mAP medido, tasa de lectura medida, handler que recibe JPEG y devuelve placa |
| **F5 Pi** | Stub FastAPI local con veredictos enlatados; **relés en modo simulado (LED)** | Ráfaga → POST → veredicto → LED, sin tocar el motor |
| **F6 Electrónica** | Botón manual en lugar de GPIO | Portón se mueve con botón; fotocelda y finales cortan el motor **con la Pi apagada** |

El truco de F5 y F6: **cada uno prueba su mitad del portón sin el otro.** F6 valida la potencia y la seguridad con un botón; F5 valida la lógica con un LED. Se unen solo en I4.

---

## 4. Dependencias reales

```
F0 Contratos ──┬──> F1 Web ─────────────────┐
               ├──> F2 API ────────┬────────┼──> I1 ─┐
               ├──> F3 Infra ──────┤        │        │
               ├──> F4 ML ─────────┴─> I2 ──┤        ├──> I5 CAMPO
               ├──> F5 Pi ──────────────────┴─> I3 ──┤
               └──> F6 Electrónica ───────────> I4 ──┘
```

Solo hay dos dependencias duras: **todo depende de F0**, y **F4 necesita que F3 tenga ECR + Lambda** para desplegar (aunque puede desarrollar y medir precisión mucho antes).

### La ruta crítica no es la que parece

**Empieza por F6, aunque integre al final.** Es el único frente con plazos que no controlas:

1. Ir a la puerta a verificar la bornera del UX-52 (los 5 datos pendientes de `PLAN_AWS.md` §9).
2. Conseguir electricista.
3. Comprar sensores, gabinete y contactores (~$425, con demoras de importación).

Los frentes de software se recuperan con horas extra; un pedido de fotoceldas que tarda tres semanas, no. Arranca la compra y la visita técnica ya, mientras el software avanza.

---

## 5. Hitos de integración

| Hito | Une | Criterio de aceptación |
|---|---|---|
| **I1** | F1 + F2 | El dashboard muestra eventos reales desde FastAPI local, con login funcionando |
| **I2** | F4 + F3 | Se sube un JPEG al Lambda desplegado y devuelve placa + confianza en <2s tibio |
| **I3** | F5 + F3 + F4 | La Pi captura, sube, recibe veredicto y enciende el LED. **Sin motor.** |
| **I4** | F5 + F6 | El portón recorre ambos sentidos comandado por la Pi. **En banco o con el portón liberado.** |
| **I5** | Todo | Vehículo real → portón abre. Checklist de seguridad firmado. |

**I3 e I4 corren en paralelo.** Son las dos mitades del sistema de campo y no se estorban.

Checklist de seguridad de I5, que se prueba **antes** de considerar el sistema en producción:

- [ ] Fotocelda interrumpida a mitad de cierre → el motor para
- [ ] Corte de 220V en movimiento → el portón queda seguro, sin daño
- [ ] Internet caído → no abre, y el control manual sí funciona
- [ ] `kill -9` a `anpr-gate` en pleno movimiento → el motor para
- [ ] **Pi apagada y cable de red desconectado** → fotocelda y finales de carrera **siguen deteniendo el motor**
- [ ] Veredicto duplicado (mismo `event_id`) → no abre dos veces

El penúltimo es el que decide si el cableado está bien. Si falla, no se pone en producción.

---

## 6. Estructura de repositorio

```
anpr/
├── contracts/          F0  openapi.yaml, gpio-map.md, mqtt-topics.md
├── api/                F2  FastAPI + Alembic
├── web/                F1  React SPA
├── ml/                 F4  export ONNX, benchmarks, handler de inferencia
├── edge/               F5  servicios systemd de la Pi
├── infra/              F3  Terraform / CDK
├── hardware/           F6  diagramas, BOM, fotos de bornera, checklist
├── MEJORAS.md              deuda técnica de lo existente
├── PLAN_AWS.md             arquitectura objetivo y costos
└── WORKSTREAMS.md          este documento
```

Una rama por frente (`f1-web`, `f2-api`, …) que integra a `main` al cerrar cada hito. Cada frente es dueño de su carpeta; **`contracts/` se modifica solo por acuerdo**, porque tocarlo rompe a los demás.

---

## 7. Orden sugerido para arrancar

| Orden | Acción | Bloquea a |
|---|---|---|
| 1 | **F0 Contratos** (~1 día) | Todo |
| 2 | **F6**: visita a la puerta + iniciar compras | Nada, pero es la ruta crítica |
| 3 | **Fase 0 de `PLAN_AWS.md`**: hacer correr lo actual y medir la línea base | F4 (sin métricas no sabes si mejoras) |
| 4 | F1, F2, F3, F4, F5 en paralelo | — |

El paso 3 importa más de lo que parece: hoy **no existe ninguna métrica** de qué tan bien lee el sistema. Sin esa línea base, F4 no puede demostrar que exportar a ONNX o cambiar de cámara mejoró algo.
