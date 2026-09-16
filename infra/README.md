# F3 — Infraestructura AWS

IaC (Terraform o CDK) para toda la nube. Región **us-east-1**.

## Alcance

| Recurso | Uso |
|---|---|
| Lambda (contenedor ARM, 10 GB) | Inferencia — camino crítico |
| Lambda (512 MB) + Mangum | API FastAPI de F2 |
| API Gateway HTTP API | Entrada, con mTLS o API key de dispositivo |
| RDS MySQL `db.t4g.micro` | Base de datos |
| S3 + CloudFront | Frames de detección y la SPA de F1 |
| ECR | Imagen de inferencia |
| AWS IoT Core | Certificados y telemetría de la Pi |
| EventBridge (5 min) | Mantener tibia la Lambda de inferencia |
| Secrets Manager | Credenciales de BD |

## No incluye

- El código de la API (F2) ni el del modelo (F4)

## Cómo trabajar aislado

Desplegar un contenedor *hello world* en lugar del Lambda real de inferencia.

## Terminado cuando

`terraform apply` levanta todo desde cero y el endpoint responde 200.

## Notas de diseño

**Los frames no van por MQTT.** AWS IoT Core limita a 128 KB por mensaje y una
ráfaga de 10 frames lo excede. Van por HTTPS a API Gateway, que además permite
respuesta síncrona.

**Lambda a 10 GB de memoria.** La CPU escala con la memoria: a 10 GB son ~6 vCPU y
YOLO11m baja a ~0.4 s/frame. Subir de 3 a 10 GB cuesta ~$2.80/mes más y triplica la
velocidad. **No usar GPU** — son 4 horas de cómputo al mes.

**Cold start** es el riesgo real (+10-20 s con imagen de 3 GB). Se mitiga con el
ping de EventBridge. Con un solo portón la concurrencia es 1.

Costos detallados en `PLAN_AWS.md` §3 (≈ $23/mes).
