# Plan: ANPR FIM-UNI con inferencia en AWS

## Contexto

El sistema hoy está partido en tres piezas que no se conectan entre sí:

- **`backend/`** — API Flask + MySQL en Aiven. Funciona, pero sin autenticación y con dos capas de acceso a BD contradictorias.
- **`web/`** — Dashboard Next.js 14. Solo dos vistas activas; el login es un `setTimeout`.
- **`mqtt-camara-main/`** — Pipeline de visión (YOLO11m + PaddleOCR) que corre en una PC Windows.

Y le falta **la mitad del sistema**, verificado por grep sobre el repo:

| Pieza | Estado |
|---|---|
| Quien publica el disparo en `app/rx` | **No existe** → `mqtt+camara.py` nunca se ejecuta |
| Quien escucha el veredicto en `app/tx` | **No existe** → el backend publica al vacío |
| Control del motor (GPIO, relés) | **No existe** → cero líneas de código |
| Finales de carrera / fotocelda | **No existen** en hardware |

Hoy el portón lo abre una persona girando la perilla del UX-52. Esa persona cumple tres funciones: decidir cuándo arrancar, ver cuándo llegó al tope y parar, y ver si hay alguien en medio.

**Decisión nueva:** mover toda la IA a AWS. La Raspberry Pi y la cámara quedan solo como captura + actuador; la web, las bases de datos y el modelo viven en la nube.

**Resultado buscado:** vehículo llega → Pi captura → nube detecta y decide → Pi abre el portón, en menos de 4 segundos, sin que nadie toque la perilla.

---

## 1. Opinión sobre el cambio

**Estoy de acuerdo, con una condición de seguridad no negociable.**

### Por qué es buena idea

1. **Elimina el problema técnico más difícil.** Con inferencia en la nube usas el `best.pt` que ya entrenaste, a 640px, sin tocarlo. Si el modelo corriera en la Pi 5 en CPU habría que reentrenar a `yolo11n`, cuantizar a int8, exportar a NCNN y adelgazar PaddleOCR — semanas de trabajo con pérdida de precisión.
2. **Un solo lugar donde actualizar el modelo.** Reentrenas, reconstruyes la imagen, y listo. Sin actualizaciones de ML en campo.
3. **La inferencia es baratísima a este volumen.** ~500 eventos/día × 1.5s = **4 horas de cómputo al mes**. En Lambda son ~$4/mes. Pagar un servidor encendido 730 horas para usar 4 es 99% desperdicio.
4. **La Pi se vuelve trivial y reemplazable.** Si se quema, la repones en una hora con una imagen de disco. Nada de modelos ni pesos en el equipo de campo.
5. **La BD queda junto a la inferencia**, sin el salto de red actual hacia Aiven.

### El costo real: el portón pasa a depender de internet

Esto es el centro del intercambio y hay que asumirlo con los ojos abiertos. Con inferencia en la nube, **si se cae el enlace la Pi no puede ni leer la placa** — no solo no puede consultar la lista blanca. Así que el modo degradado no puede ser "automático con caché local": solo puede ser **operación manual**.

Consecuencia concreta para el plan: hay que **conservar un control manual** (botón con llave en el gabinete, o la perilla actual) y documentarlo como el procedimiento oficial de contingencia. No es opcional.

Latencia esperada, con presupuesto de 4s:

| Etapa | Tiempo |
|---|---|
| Captura de ráfaga (10 frames) | 1.0–2.0 s |
| Subida de ~600 KB | 0.2–1.0 s |
| Inferencia (Lambda tibia, 2-3 frames) | 0.5–1.5 s |
| Consulta BD + respuesta | 0.1 s |
| Cierre de relé y arranque del motor | 0.2 s |
| **Total** | **~2–4 s** |

Aceptable para una pluma o un portón corredizo. El riesgo es el **cold start de Lambda** (+10-20s con una imagen de 3GB): se mitiga con un ping cada 5 minutos desde EventBridge, que cuesta centavos y mantiene una instancia tibia. Con un solo portón la concurrencia es 1, así que el truco funciona.

### La condición no negociable

**La seguridad del portón debe ser de hardware, no de software.** Finales de carrera, fotocelda y parada de emergencia van **cableados en serie con la bobina del contactor del motor**, no leídos por GPIO.

El software solo puede *pedir* que el portón se mueva; el hardware debe poder *negarlo*. Así, un cuelgue de la Pi, una caída de internet, un bug en el Lambda o un mensaje corrupto **nunca** pueden hacer que el portón cierre sobre una persona ni que el motor se fuerce contra el tope. Este punto es independiente de dónde corra la IA y es el más importante de todo el documento.

---

## 2. Arquitectura objetivo

```
  PUERTA 2 (campo)                          AWS (us-east-1)
┌───────────────────────────┐
│ Sensor de presencia       │
│   (lazo inductivo/IR)     │
│         │                 │
│         ▼                 │
│ ┌───────────────────────┐ │   1. POST ráfaga (~600 KB)
│ │ Raspberry Pi          │ │──────────────────────────►┌──────────────────┐
│ │                       │ │      HTTPS + mTLS         │ API Gateway      │
│ │ anpr-trigger          │ │                           │   HTTP API       │
│ │ anpr-capture ◄── Sony │ │                           └────────┬─────────┘
│ │ anpr-uplink           │ │                                    ▼
│ │ anpr-gate  ───────┐   │ │                           ┌──────────────────┐
│ │ anpr-health       │   │ │   2. {plate, conf,        │ Lambda infer     │
│ └───────────────────┼───┘ │      authorized}          │  YOLO11m ONNX    │
│                     │     │◄──────────────────────────│  + PaddleOCR     │
│         ┌───────────▼───┐ │                           │  (contenedor ARM)│
│         │ 2 relés opto  │ │                           └───┬──────────┬───┘
│         │ (FWD / REV)   │ │                               │          │
│         └───────┬───────┘ │                          ┌────▼────┐  ┌──▼────┐
│                 │         │                          │ RDS     │  │  S3   │
│  ┌──────────────▼──────┐  │                          │ MySQL   │  │frames │
│  │ CADENA DE SEGURIDAD │  │                          └────┬────┘  └───────┘
│  │ (hardwired, serie)  │  │                               │
│  │  E-stop → fotocelda │  │                          ┌────▼─────────────┐
│  │  → finales carrera  │  │                          │ FastAPI (Lambda  │
│  └──────────┬──────────┘  │                          │  + Mangum)       │
│             ▼             │                          └────┬─────────────┘
│      Contactor → UX-52    │                               │
│             → Motor 220V  │                          ┌────▼─────────────┐
└───────────────────────────┘                          │ React SPA        │
                                                       │ S3 + CloudFront  │
                                                       └──────────────────┘
        (MQTT sale del camino crítico: el veredicto viene en la respuesta HTTP)
```

**Decisión clave:** los frames **no** van por MQTT. AWS IoT Core tiene un límite de 128 KB por mensaje y una ráfaga de 10 frames lo excede. Van por HTTPS a API Gateway, que además permite respuesta síncrona. IoT Core se reserva para telemetría y salud del dispositivo, donde sí aporta (certificados por dispositivo, MQTTS, gestión de flota) y cuesta ~$0.10/mes.

---

## 3. Costo mensual en AWS

Supuestos declarados (corregir si no aplican):

- **500 eventos/día ≈ 15.000/mes**
- 10 frames por evento, ~60 KB cada uno → 600 KB/evento → **9 GB/mes de subida**
- Se procesan 2-3 frames por evento en promedio (corta al primer match)
- Región **us-east-1**; `sa-east-1` (São Paulo) cuesta 30-50% más
- Single-AZ, sin alta disponibilidad
- Precios de lista, sin Savings Plans ni créditos

### Escenario recomendado — serverless

| Servicio | Configuración | USD/mes |
|---|---|---|
| Lambda inferencia | contenedor ARM 10 GB, 15k × 1.5s | 4.05 |
| Lambda FastAPI (CRUD) | 512 MB, ~50k req | 0.30 |
| API Gateway HTTP API | ~65k requests | 0.07 |
| ECR | imagen ~3 GB | 0.30 |
| RDS MySQL | db.t4g.micro, 20 GB gp3, Single-AZ | 14.00 |
| S3 (frames + SPA) | ~5 GB promedio año 1 + PUTs | 0.60 |
| CloudFront + S3 (React SPA) | tráfico bajo, dentro de capa gratuita | 0.00 |
| AWS IoT Core | 1 dispositivo, telemetría | 0.10 |
| Route 53 | 1 hosted zone | 0.50 |
| CloudWatch Logs | ~5 GB | 2.00 |
| Secrets Manager | 2 secretos | 0.80 |
| Transferencia de datos | **ingress gratis**, egress <100 GB gratis | 0.00 |
| **Total** | | **≈ $23 / mes** |

**Por qué Lambda a 10 GB de memoria:** en Lambda la CPU escala con la memoria. A 10 GB obtienes ~6 vCPU y YOLO11m baja a ~0.4s por frame. Subir de 3 GB a 10 GB solo cuesta ~$2.80/mes más y **triplica la velocidad**. A este volumen la memoria es el acelerador más barato que existe.

**GPU no hace falta.** SageMaker o instancias `g4dn` para 4 horas de cómputo al mes serían un desperdicio de dos órdenes de magnitud.

### Alternativa — todo en una EC2

Si prefieres un solo servidor con Docker Compose (MySQL + FastAPI + inferencia + web):

| Servicio | Configuración | USD/mes |
|---|---|---|
| EC2 t4g.large (ARM) | 2 vCPU, 8 GB, 24/7 | 49.06 |
| EBS gp3 | 30 GB | 2.40 |
| IPv4 pública | $0.005/h | 3.65 |
| S3 + Route 53 + CloudWatch | | 2.10 |
| **Total** | | **≈ $57 / mes** |

Más caro y con más mantenimiento, pero latencia predecible sin cold starts y más fácil de depurar. Con un Compute Savings Plan de 1 año baja a ~$40.

### Sensibilidad al volumen

Los costos fijos dominan: el volumen casi no mueve la aguja.

| Eventos/día | Lambda | Total/mes |
|---|---|---|
| 200 | $1.65 | ≈ $21 |
| 500 | $4.05 | ≈ $23 |
| 1.000 | $8.10 | ≈ $28 |
| 5.000 | $40.50 | ≈ $60 |

A 5.000/día conviene revisar: aparece la necesidad de RDS Proxy (~$22/mes) por agotamiento de conexiones desde Lambda.

### Costos de hardware, una sola vez

| Ítem | USD aprox. |
|---|---|
| Raspberry Pi 5 4 GB + fuente 27W + disipador activo | 90 |
| SSD NVMe 128 GB + HAT M.2 (no usar microSD) | 45 |
| UPS / batería de respaldo para la Pi | 40 |
| 2× relés opto-aislados o contactores con enclavamiento mecánico | 35 |
| 2× finales de carrera IP67 con palanca de rodillo | 20 |
| Par de fotoceldas de seguridad IP65 | 40 |
| Parada de emergencia NC tipo hongo | 15 |
| Sensor de presencia (lazo inductivo o barrera IR) | 60 |
| Gabinete IP65 con riel DIN, fuente 24V, bornes, fusibles | 70 |
| Supresor RC / varistor para la carga inductiva | 10 |
| **Total** | **≈ $425** |

---

## 4. Qué Raspberry usar

**Recomendación: Pi 5 de 4 GB, no la de 8 GB.**

Con la inferencia en la nube la Pi solo captura frames, hace un POST y cierra relés. Eso cabe de sobra en 4 GB; los 8 GB serían gasto sin retorno. Una Pi 4 de 4 GB también serviría, pero la Pi 5 aporta dos cosas que sí importan en campo:

- **PCIe para NVMe.** Las microSD se degradan con escrituras continuas y son la causa número uno de fallos en Pi de producción. Arrancar desde SSD NVMe es la mejora de fiabilidad de mayor impacto.
- **Conector RTC.** Con una pila de respaldo los eventos conservan hora correcta aunque la Pi arranque sin red.

Requisitos de despliegue que no son opcionales:

- **Fuente oficial de 27 W.** La Pi 5 con NVMe cae en throttling o se reinicia con fuentes genéricas.
- **Disipador activo.** En gabinete cerrado al sol, obligatorio.
- **Watchdog de hardware habilitado** (`dtparam=watchdog=on` + `systemd` `RuntimeWatchdogSec`) para que un cuelgue se reinicie solo.
- **UPS.** Un corte a mitad de escritura corrompe el filesystem.
- **Ethernet para internet + Wi-Fi para la cámara Sony.** Mientras se conserve la AS100V, la Pi necesita las dos interfaces a la vez, con rutas fijadas por métrica para que el Wi-Fi de la cámara (`192.168.122.0/24`) no se robe la ruta por defecto. **Si en el gabinete no hay cable de red, esto es el primer blocker del despliegue.**

---

## 5. Arquitectura de servicios en la Pi

Cinco unidades systemd, con un Mosquitto local como bus interno y bridge hacia AWS IoT Core para telemetría.

| Servicio | Responsabilidad | Toca GPIO | Toca internet |
|---|---|---|---|
| `anpr-trigger` | Lee el sensor de presencia, emite `gate/trigger` | Sí (entrada) | No |
| `anpr-capture` | Toma la ráfaga de frames, la escribe en `/var/spool/anpr/` | No | No (solo LAN cámara) |
| `anpr-uplink` | Sube la ráfaga, recibe el veredicto, publica `gate/command` | No | Sí |
| `anpr-gate` | **Único** que cierra relés. Enclavamiento, timeouts, finales de carrera | Sí (salidas) | **No** |
| `anpr-health` | Heartbeat a IoT Core, watchdog, métricas | No | Sí |

**Por qué esta separación:** `anpr-gate` es el servicio crítico de seguridad. Se mantiene pequeño, auditable y **sin ninguna dependencia de red**. Recibe órdenes por el bus local y las valida contra su propia máquina de estados. Un bug en `anpr-uplink` no puede mover el motor de forma inválida.

Reglas que `anpr-gate` hace cumplir en software, **además** del enclavamiento por hardware:

- FWD y REV nunca energizados a la vez; pausa obligatoria de 0.5s al invertir.
- Timeout máximo de marcha (según el tiempo real de recorrido + 20%); si no llega el final de carrera, corta y marca falla.
- Rechaza órdenes nuevas mientras hay movimiento en curso.
- Al arrancar asume posición desconocida y hace un ciclo de referencia hacia "cerrado".
- Idempotencia por `event_id`: un veredicto reenviado no abre dos veces.

---

## 6. Fases de implementación

### Fase 0 — Hacer correr lo que ya existe (1 día)

Objetivo: ver el sistema actual funcionando end-to-end antes de cambiar nada, para tener una línea base. Detalle en la sección 7.

### Fase 1 — Fundaciones (2-3 días)

- Sacar `venv/` del repo (2.643 de 2.708 archivos versionados) y `best.pt` (40 MB) a Git LFS o S3.
- `pyproject.toml` para la API y `requirements.txt` para el pipeline de visión.
- `.env.example` versionado; una sola forma de leer configuración.
- Unificar las dos capas de BD (`backend/connect.py` y `backend/db.py`) en una sola.
- Reestructurar el repo en `api/`, `web/`, `edge/` (código de la Pi), `infra/` (IaC), `ml/` (modelo y export).

### Fase 2 — Migrar la API a FastAPI (3-5 días)

Estructura y mapa de endpoints ya definidos en `MEJORAS.md` secciones 2.1 y 2.2. Al migrar se resuelven de paso:

- Autenticación JWT real con Argon2, y `Depends(current_user)` en todo salvo healthcheck.
- Alembic en lugar de `schema.sql` (que hoy empieza con `DROP TABLE` de las cuatro tablas).
- Normalización de placas con `field_validator` (hoy el join `e.plate = l.plate` es sobre texto crudo).
- Guardar en UTC y convertir a `America/Lima` en presentación, eliminando el `- timedelta(hours=5)` de `backend/vehicle.py:57`.
- Paginación por cursor en `/events` y filtros en SQL, no en el cliente.
- Columnas nuevas en `event_detection`: `confidence`, `image_s3_key`, `camera_id`, `gate_opened`, `latency_ms`.
- Corregir que `create_user` no inserta `role` (`backend/listcrud.py:73`), por lo que todos quedan `student`.
- Endpoint transaccional único para crear usuario + placa, eliminando el "rollback best-effort" con `try/catch {}` vacío de `web/src/app/api/list_car/route.ts`.

### Fase 3 — Inferencia en AWS (4-6 días)

- Exportar `best.pt` a ONNX; validar que el mAP no se degrada (`model.val()` antes y después, guardando la métrica como línea base — hoy no existe ninguna).
- **Adelgazar PaddleOCR**: `ocr_config.yaml` trae activados `use_doc_preprocessor`, `use_doc_orientation_classify`, `use_doc_unwarping` y `use_textline_orientation` — cuatro modelos extra pensados para escanear documentos, inútiles sobre el recorte de una placa. Desactivarlos reduce la imagen y el tiempo de arranque de forma sustancial.
- **Reemplazar las rutas Windows** de `ocr_config.yaml` (`C:\Users\Alexis\.paddlex\...`, cinco rutas) por descarga a una ruta relativa dentro del contenedor.
- Contenedor Lambda ARM64 con ONNX Runtime + OCR; modelos horneados en la imagen, no descargados en runtime.
- API Gateway HTTP API con autorizador por mTLS o API key del dispositivo.
- EventBridge cada 5 min para mantener tibia la Lambda.
- Corregir dos bugs del pipeline actual al portarlo:
  - El filtro `wl = re.compile(r'^.{7}$')` exige exactamente 7 caracteres: si el OCR lee `ABC123` sin guion, **descarta una placa correcta**. Normalizar quitando guiones, validar 6 alfanuméricos y reinsertar.
  - `run_ocr_logic` devuelve `candidates[0]` como fallback, pero el llamador vuelve a validar con `PLATE_PATTERN.fullmatch`, así que **ese fallback siempre se descarta**. Usarlo para registrar lecturas fallidas y poder medir precisión real.
- Propagar `confidence` de YOLO y el score del OCR hasta la BD (hoy se descartan y el dashboard los fuerza a `0`).

### Fase 4 — Servicios de la Pi, sin motor (3-4 días)

- Las cinco unidades systemd, con `anpr-gate` en **modo simulado**: registra la orden en log y enciende un LED, sin cablear el motor.
- Captura por ráfaga en lugar de streaming: **medir primero** cuántos píxeles de ancho tiene la placa en el liveview `startLiveviewWithSize(["M"])` a la distancia real del portón. Si es menos de ~60-80 px, ninguna mejora de modelo lo va a salvar y la cámara pasa a ser prioridad.
- Cerrar la fuga de sesión de la cámara: hoy se llama `startLiveview` sin `stopLiveview` en los tres consumidores, y la cámara acaba agotando sesiones.
- Spool en disco con reintento: si la nube no responde, el evento se guarda y se reenvía.
- Aprovisionamiento con certificado de dispositivo en IoT Core.

### Fase 5 — Actuador y seguridad (4-5 días, requiere electricista)

Esta fase **no empieza** hasta haber verificado el cableado real del UX-52 en sitio.

1. Verificar la bornera: `AC-L`/`AC-N` (220V), `U1`/`U2` (devanado + condensador), azules (tacómetro), `0V`/`FWD`/`REV` (dirección).
2. Instalar finales de carrera de apertura y cierre, fotocelda, y parada de emergencia.
3. **Cablear la cadena de seguridad en serie con la bobina del contactor**: E-stop → fotocelda → final de carrera correspondiente. Software fuera de esa cadena.
4. Relés opto-aislados desde GPIO hacia `FWD`/`REV` contra `0V`, con enclavamiento mecánico para que sea físicamente imposible energizar ambos.
5. Supresor RC/varistor sobre los contactos por la carga inductiva.
6. Conservar el control manual (perilla o botón con llave) como contingencia documentada.
7. Pruebas: recorrido completo en ambos sentidos, corte por fotocelda a mitad de cierre, corte de red a mitad de recorrido, corte de internet, reinicio de la Pi en movimiento.

### Fase 6 — Frontend React y operación (3-4 días)

- React SPA en S3 + CloudFront (más barato y simple que Next.js SSR, y alineado con tu preferencia por React).
- TanStack Query en lugar de `fetch` en `useEffect` con `loading`/`error` a mano en cada página.
- Guardia de rutas real; hoy el login es un `setTimeout` de 1s (`web/src/app/login/page.tsx:22`).
- Borrar las ~1.100 líneas de páginas huérfanas con datos mock (`dashboard/{statistics,database,users,settings,stream}`), comentadas en el sidebar.
- Vista de evento con la foto desde S3 por URL prefirmada y la confianza de lectura.
- Alertas: fotocelda activada, timeout de motor, Pi sin heartbeat, tasa de lectura fallida por encima de umbral.

---

## 7. Cómo ejecutar lo que existe hoy

Cuatro blockers antes de que algo funcione. El orden importa: valida sin cámara ni modelo primero.

### Blockers

1. **No hay `requirements.txt`.** Nada declara Flask, PyMySQL, paho-mqtt ni python-dotenv.
2. **No hay `.env` para el backend.** Se necesitan `DATABASE_URL` *y* `HOST`/`PORT`/`DB_NAME`/`PASSWORD` porque los dos módulos leen distinto.
3. **`ocr_config.yaml` apunta a `C:\Users\Alexis\...`** — no carga en Linux.
4. **Nadie publica `entro` en `app/rx`**, así que `mqtt+camara.py` se queda esperando para siempre.

### Paso 1 — Backend solo

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install flask pymysql cryptography python-dotenv paho-mqtt requests
# crear .env con las credenciales de Aiven (ver blocker 2)
MQTT_ENABLED=0 flask --app backend check-db     # debe listar las tablas
MQTT_ENABLED=0 flask --app backend run --port 5000
```

⚠️ **No ejecutar `flask --app backend init-db`** contra la base real: borra las cuatro tablas.

### Paso 2 — Validar el flujo completo sin cámara ni IA

```bash
curl -X POST localhost:5000/v1/event \
  -H 'Content-Type: application/json' -d '{"plate":"CUB-604"}'
```

Debe responder `201` con `{"authorization":{"authorized":true|false}}`. Esto ejercita API + BD + lógica de autorización de una sola vez.

### Paso 3 — Dashboard

```bash
cd web && npm install && npm run dev   # http://localhost:3000
```

`BACKEND_URL=http://localhost:5000` ya está en `web/.env.local`. El evento del paso 2 debe aparecer en *Registros ANPR*.

### Paso 4 — Pipeline de visión, aislado

```bash
pip install ultralytics paddleocr paddlepaddle torch opencv-python
```

Antes de conectar la cámara, probar el modelo contra una foto fija:

```python
from ultralytics import YOLO
m = YOLO("mqtt-camara-main/best.pt")
r = m.predict("foto_placa.jpg", imgsz=640, conf=0.30)
print(r[0].boxes)   # ¿detecta la placa? ¿qué confianza?
```

Luego arreglar `ocr_config.yaml` (rutas relativas) y probar el OCR sobre el recorte. Esto separa "el modelo no detecta" de "la cámara no da resolución suficiente", que es la duda central.

### Paso 5 — Pipeline con cámara y disparo manual

```bash
sudo apt install mosquitto mosquitto-clients      # broker local
# en mqtt+camara.py: API_URL → http://localhost:5000/v1/event
MQTT_HOST=localhost python3 "mqtt-camara-main/mqtt+camara.py"
# en otra terminal, el disparo que hoy nadie publica:
mosquitto_pub -h localhost -t app/rx -m entro
```

Requiere que la cámara sea alcanzable en `192.168.122.1`.

### Métricas a registrar en esta fase

Son la línea base contra la cual comparar todo lo demás:

- Ancho en píxeles de la placa en el crop de YOLO, a la distancia real.
- Tasa de detección: eventos con placa válida / disparos totales.
- Tasa de lectura correcta: placas bien leídas / placas detectadas.
- Tiempo desde el disparo hasta el POST.

---

## 8. Verificación

| Nivel | Qué probar | Cómo |
|---|---|---|
| Unidad | Regla de autorización, normalización de placas, máquina de estados de `anpr-gate` | pytest |
| Integración | CRUD contra MySQL en Docker | pytest + httpx |
| Modelo | mAP antes/después de exportar a ONNX | `model.val()`, comparar contra la línea base |
| Lambda | Latencia tibia y fría, con un set de frames reales | `aws lambda invoke` + CloudWatch |
| End-to-end | Ráfaga real → veredicto → LED (modo simulado) | Pi en banco, sin motor |
| Campo | Recorrido completo ambos sentidos | Con electricista presente |
| Seguridad | Fotocelda a mitad de cierre; corte de 220V en movimiento; internet caído; `kill -9` de `anpr-gate` en movimiento | Manual, checklist firmado |
| Carga | 50 eventos en 1 minuto | k6 contra API Gateway |

**El criterio de aceptación de seguridad:** con la Pi apagada y el cable de red desconectado, la fotocelda y los finales de carrera deben seguir deteniendo el motor. Si no lo hacen, el cableado está mal y no se pone en producción.

---

## 9. Información que falta confirmar

Bloqueantes para cerrar costo y diseño:

1. **Estado de la cuenta AWS.** ¿Cuenta nueva (créditos iniciales), cuenta existente, o hay acceso institucional tipo AWS Academy por la UNI? Puede llevar el año 1 a casi cero.
2. **Internet en el gabinete de la puerta.** ¿Hay cable de red? Si solo hay celular, hay que sumar el plan de datos y revisar si 9 GB/mes de subida entran.
3. **Volumen real de vehículos por día.** Para ajustar el cálculo; los costos fijos dominan, pero define el dimensionamiento.

Bloqueantes para la Fase 5, a verificar en sitio:

4. **Cómo se invierte el giro hoy.** ¿Hay un interruptor FWD/REV cableado, o el motor gira en un solo sentido?
5. **Foto de la bornera del UX-52 instalado.** La serigrafía varía entre clones.
6. **Potencia y tipo del motor** (W; monofásico con condensador de arranque).
7. **Tiempo de recorrido completo** en segundos, que define el timeout de marcha.
8. **Tipo de portón**: pluma, corredizo o batiente.
