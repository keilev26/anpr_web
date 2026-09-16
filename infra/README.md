# F3 — Infraestructura AWS

Terraform para la **fase de prueba**, diseñada para costar **~$0,35/mes** con una
cuenta personal (solo capa gratuita permanente). Análisis completo en
`PLAN_AWS.md` → "Escenario de prueba — costo mínimo".

## Arquitectura

```
                 https://<id>.cloudfront.net
                            │
                  ┌─────────┴──────────┐   un solo dominio: la cookie de
                  │     CloudFront     │   sesión HttpOnly funciona
                  └───┬────────────┬───┘
            /*        │            │  /api/*  + cabecera X-Origin-Verify
      ┌───────────────▼──┐     ┌───▼──────────────────────┐
      │ S3 privado (SPA) │     │ Lambda API (Function URL)│── SSM Parameter Store
      │ + función de     │     │ FastAPI + Mangum, zip    │   (secretos)
      │   reescritura    │     └───┬──────────────┬───────┘
      └──────────────────┘         │ invoke       │ TLS
                         ┌─────────▼────────┐  ┌──▼──────────────────┐
                         │ Lambda inferencia│  │ Aiven MySQL gratuito│
                         │ imagen ECR, 10 GB│  │ (fuera de AWS)      │
                         └──────────────────┘  └─────────────────────┘
```

**Nada va dentro de una VPC**: así no hace falta un NAT Gateway, que costaría
~$33/mes, más que todo el resto del sistema.

| Recurso | Decisión | Por qué |
|---|---|---|
| Entrada | Lambda Function URL, no API Gateway | Gratis |
| Seguridad de la URL | Cabecera secreta que añade CloudFront; si falta, la API responde 403 | OAC para Function URLs obliga a firmar el hash del cuerpo en cada POST: ni el navegador ni la Pi lo hacen |
| Rutas del SPA | CloudFront Function que reescribe a `/index.html` | Las "custom error responses" convertirían también los 404 de la API en un index.html con 200 |
| Secretos | SSM Parameter Store; Terraform los crea con relleno y los ignora | Secrets Manager cuesta $0,40/secreto; y así no quedan en texto plano en el estado |
| Logs | Retención de 7 días, grupos creados por Terraform | Si los crea Lambda, la retención es infinita |
| Inferencia | x86_64, 10 GB | `paddlepaddle` no publica paquetes aarch64 |
| BD | Aiven MySQL gratuito, pool de 1 conexión con `pool_pre_ping` y reciclado a 300 s | Sin VPC. Mangum reutiliza el bucle de eventos del contenedor, así que la conexión sobrevive entre invocaciones y ahorra ~0,5 s por petición |
| Cabeceras | `Managed-SecurityHeadersPolicy` en web y API | HSTS, `X-Frame-Options`, `nosniff` y `Referrer-Policy` sin costo |
| Alarmas | `Errors` y `Throttles` de la API → SNS → `alert_email` | Gratis (10 alarmas); hay que confirmar el correo de suscripción |
| Protección | Las alertas existentes de la cuenta: **Zero-Spend** (correo desde $0,01) y **Monthly** ($10) | Un tercer presupuesto sería redundante; `create_budget` lo crea si hiciera falta |

## Herramientas locales

| Herramienta | Dónde | Estado |
|---|---|---|
| Terraform 1.16.3 | `/data/tools/bin/terraform` | Instalado; firma GPG de HashiCorp y checksum verificados |
| Proveedores de Terraform | `/data/cache/terraform-plugins` | aws 6.64.0 y random 3.9.1, firmados por HashiCorp |
| AWS CLI v2 | — | **Falta** |
| Docker | `/var/lib/docker` | **Mover a `/data`** antes de construir la imagen de inferencia |

Variables de entorno para Terraform en esta máquina (dejan todo en `/data`):

```bash
export TF_DATA_DIR=/data/anpr/infra/.terraform
export TF_PLUGIN_CACHE_DIR=/data/cache/terraform-plugins
alias terraform=/data/tools/bin/terraform
```

## Despliegue, en orden

### 0. Prerrequisitos (una vez)

1. **Credenciales de AWS.** Crear un usuario IAM para esta prueba y configurar
   `aws configure`. Nunca usar la cuenta root.
2. **AWS CLI v2.**
3. **Aiven**: crear un servicio **MySQL con plan gratuito** (1 CPU, 1 GB de RAM,
   1 GB de disco, backup diario, sin tarjeta). El plan gratuito **solo ofrece
   algunas regiones predeterminadas**: elegir la más cercana a us-east-1 (Norteamérica).
   Copiar el *Service URI* y descargar `ca.pem`.
   **Aiven apaga el servicio tras un periodo sin actividad** (avisa por correo antes);
   si la API empieza a fallar con errores de conexión, reactivarlo desde la consola.

### 1. Esquema y administrador en Aiven (desde esta máquina)

Guardar la conexión en archivos locales, **nunca en el repo ni en un chat**:

```bash
mkdir -p /data/anpr/secrets && chmod 700 /data/anpr/secrets
cp ~/Descargas/ca.pem /data/anpr/secrets/aiven-ca.pem
( umask 077; echo 'AIVEN_URI=<Service URI de Aiven>' > /data/anpr/secrets/aiven.env )
```

`with_aiven.sh` lee esos archivos, adapta la URI para `aiomysql` y ejecuta el comando
sin imprimir la contraseña:

```bash
cd api
../infra/scripts/with_aiven.sh .venv/bin/alembic upgrade head
../infra/scripts/with_aiven.sh .venv/bin/python scripts/seed.py --email tu@uni.pe --name "Tu Nombre"
```

El segundo pide la contraseña del administrador de forma interactiva: ejecutarlo en
una terminal normal.

### 2. Primer apply: todo menos la inferencia

```bash
infra/scripts/build_api_zip.sh
cd infra/terraform
cp terraform.tfvars.example terraform.tfvars
terraform init
terraform plan -out=plan.bin                     # revisar ANTES de aplicar
terraform apply plan.bin
../scripts/backup_tfstate.sh                    # tras cada apply
```

Con `alert_email` en `terraform.tfvars` se crean las alarmas; AWS envía un correo
de confirmación que hay que aceptar.

**Esperado:** el presupuesto *Zero-Spend* de la cuenta va a avisar por correo cada mes,
porque la prueba cuesta ~$0,35 (almacenamiento de ECR). No indica un problema;
un aviso del de $10 sí lo indicaría.

### 3. Secretos

```bash
infra/scripts/set_secrets.sh /anpr/prueba
```

Guarda la clave del dispositivo que imprime: la necesita la Raspberry (F5).

### 4. Web

```bash
infra/scripts/deploy_web.sh
```

Abrir la URL de `terraform output url` y entrar con el administrador del paso 1.
**En este punto ya funcionan el dashboard y la API completos**; `/api/v1/detections`
responde con el stub (sin placa) hasta el paso 5.

### 5. Inferencia

1. Mover el almacenamiento de Docker a `/data` (requiere sudo):
   ```bash
   sudo systemctl stop docker
   echo '{ "data-root": "/data/docker" }' | sudo tee /etc/docker/daemon.json
   sudo rsync -aP /var/lib/docker/ /data/docker/
   sudo systemctl start docker && docker info --format '{{.DockerRootDir}}'
   ```
   Si `/etc/docker/daemon.json` ya existía, añadir la clave en lugar de sobrescribirlo.
2. Exportar el modelo: `ml/README.md`, pendiente 4, dejando el resultado en `ml/models/best.onnx`.
3. Construir, **probar en local** y solo entonces subir:
   ```bash
   SKIP_PUSH=1 infra/scripts/push_infer_image.sh v1   # solo construye
   infra/scripts/test_infer_image_local.sh <repo>:v1  # emulador de Lambda, solo lectura, ráfaga de 3
   infra/scripts/push_infer_image.sh v1               # reutiliza la caché y sube
   ```
4. `infer_image_tag = "v1"` en `terraform.tfvars` y `terraform apply`.

### 6. Probar el camino crítico

```bash
URL=$(terraform output -raw detections_endpoint)
KEY=$(aws ssm get-parameter --with-decryption --name /anpr/prueba/device_api_key --query Parameter.Value --output text)
curl -s -X POST "$URL" -H "X-Device-Key: $KEY" \
  -F gate_id=puerta-2 -F event_id=$(python3 -c 'import uuid;print(uuid.uuid4())') \
  -F captured_at=$(date -u +%FT%TZ) \
  -F frames=@foto.jpg -F frames=@foto.jpg -F frames=@foto.jpg
```

La primera petición tarda 10-20 s más por el arranque en frío (en la prueba no hay
ping de calentamiento). Tres fotogramas porque el consenso exige al menos dos
lecturas iguales.

## Borrar todo

```bash
cd infra/terraform && terraform destroy
```

El bucket y el repositorio ECR tienen `force_destroy`, así que se borran con su
contenido. **El servicio de Aiven se borra aparte**, desde su consola.

## Revisión del despliegue (2026-09-16)

Hecha contra la cuenta real con consultas de solo lectura, no contra el código.

### Verificado correcto

- **Sin deriva**: `terraform plan` no encuentra diferencias con lo desplegado.
- **Roles de Lambda mínimos**: solo logs de su propio grupo y SSM bajo `/anpr/prueba`, sin comodines.
- **Cuenta root**: MFA activo y sin claves de acceso.
- **S3**: cifrado AES256, acceso público bloqueado; acceder sin CloudFront da 403.
- **Function URL directa**: 403. **API no cacheada** por CloudFront.
- **Logs**: 78 eventos sin secretos (URL de BD, contraseñas, tokens, cookies, cabeceras
  secretas), 0 errores, retención de 7 días.
- **TLS 1.1 rechazado** en la práctica; HTTP redirige a HTTPS.
- **Costo**: uso de la capa gratuita cercano a 0 %.

### Pendientes, por prioridad

Estado al 2026-09-16, tras aplicar las correcciones (ver **Resuelto** en la última columna).

| # | Prioridad | Hallazgo | Evidencia | Corrección |
|---|---|---|---|---|
| 1 | **Alta** | Límite de **10 ejecuciones simultáneas** de Lambda en la cuenta. La Function URL es pública y **cada petición directa invoca el Lambda aunque responda 403**: saturarla bloquearía la API y la puerta | `get-account-settings`: `ConcurrentExecutions: 10` | **Pendiente (lo solicita el usuario):** Service Quotas → AWS Lambda → *Concurrent executions* → 1000 (gratis). La alarma de `Throttles` avisa si ocurre. WAF lo mitigaría, pero cuesta ~$6/mes |
| 2 | **Alta** | **Login sin límite de intentos** (fuerza bruta). Argon2 lo frena, pero también consume las 10 ejecuciones | Sin rate limit en `/auth/login` | **Resuelto:** tabla `login_attempt`; 5 fallos seguidos bloquean el correo 15 min con 429 y `Retry-After`, exista o no el correo. Verificado en vivo |
| 3 | **Alta** | **Documentación de la API pública**: mapa completo de endpoints | `/api/docs`, `/api/redoc`, `/api/openapi.json` → 200 sin sesión | **Resuelto:** desactivada con `DEV_MODE=false`; las tres rutas dan 404 |
| 4 | Media | **Sin cabeceras de seguridad**: ni HSTS, ni `X-Frame-Options` (clickjacking), ni `X-Content-Type-Options` | `curl -I`: ninguna presente | **Resuelto:** `Managed-SecurityHeadersPolicy` en ambos comportamientos; verificado con `curl -I` |
| 5 | Media | **~0,65 s por petición abriendo conexión a Aiven**. `DB_NULLPOOL` fue una precaución innecesaria: Mangum 0.22 reutiliza el mismo event loop en el contenedor | Con BD ~1,0 s; sin BD ~0,35 s | **Resuelto:** pool de 1 conexión. En caliente ~0,55 s con BD (antes ~1,0 s); logs sin errores de bucle de eventos |
| 6 | Media | Usuario IAM con `AdministratorAccess` y clave permanente | `list-access-keys`: 1 activa | Pendiente: desactivar la clave al terminar la prueba |
| 7 | Baja | Sin alarmas: un fallo de la API pasaría inadvertido | Sin alarmas de CloudWatch | **Resuelto:** 2 alarmas + tema SNS. Falta confirmar la suscripción desde el correo |
| 8 | Baja | TLS mínimo declarado `TLSv1`; con el certificado por defecto no se puede subir | `MinimumProtocolVersion: TLSv1` | Requiere dominio propio. En la práctica ya rechaza TLS 1.1 |
| 9 | Baja | IPv6 desactivado | `IsIPV6Enabled: false` | **Resuelto:** activado; la distribución responde por IPv6 |
| 10 | Baja | Estado de Terraform con permisos 664 y sin respaldo | Contiene el secreto de origen | **Resuelto:** permisos 600 y `infra/scripts/backup_tfstate.sh` (copias en `/data/anpr/backups/terraform`, 700/600, conserva 10). Ejecutarlo tras cada apply |

## Estado

Desplegado el 2026-09-16 en la cuenta de prueba: **https://d22z1x91kqav4d.cloudfront.net**

- [x] Terraform aplicado: 24 recursos, sin VPC ni NAT
- [x] Aiven: esquema migrado y administrador creado
- [x] Secretos cargados en SSM (la clave del dispositivo está en `/data/anpr/secrets/device_api_key`)
- [x] Web publicada
- [x] Verificado en vivo: `/api/health` con BD conectada; la Function URL directa responde
      403; los errores de la API llegan como JSON y no como la web; las rutas del SPA
      sirven `index.html`; HTTP redirige a HTTPS
- [x] Correcciones de la revisión aplicadas (2026-09-16): bloqueo de login, docs ocultas,
      cabeceras de seguridad, pool de conexiones (~0,55 s en caliente, antes ~1 s),
      alarmas, IPv6 y respaldo del estado
- [ ] Confirmar la suscripción SNS de las alarmas (correo de AWS)
- [ ] Pedir el aumento de la cuota de concurrencia de Lambda (10 → 1000)
- [ ] Mover Docker a `/data`, exportar ONNX y construir la imagen de inferencia (paso 5)
- [ ] Probar el camino crítico de punta a punta (paso 6)
