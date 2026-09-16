# Sistema ANPR — FIM UNI, Puerta 2

Control de acceso vehicular por reconocimiento automático de placas.
Cámara en la puerta → inferencia en AWS → apertura del portón.

## Estructura

El proyecto está dividido en frentes que avanzan **en paralelo** y se integran por
hitos. Cada carpeta tiene su propio README con alcance, cómo trabajar aislado y
definición de terminado.

| Carpeta | Frente | Qué es |
|---|---|---|
| `contracts/` | **F0** | Esquemas compartidos. **Prerequisito de todo lo demás** |
| `web/` | F1 | React SPA — dashboard de operación |
| `api/` | F2 | FastAPI + Alembic + autenticación |
| `infra/` | F3 | IaC de AWS: Lambda, RDS, S3, IoT Core |
| `ml/` | F4 | Export ONNX, optimización de OCR, métricas |
| `edge/` | F5 | Servicios systemd de la Raspberry Pi |
| `hardware/` | F6 | Relés, cadena de seguridad, gabinete |
| `legacy/` | — | Proyecto original congelado, como referencia |

## Documentos

| Archivo | Contenido |
|---|---|
| `WORKSTREAMS.md` | División en frentes, contratos, dependencias, hitos de integración |
| `PLAN_AWS.md` | Arquitectura objetivo, costos (≈ $23/mes), fases, runbook del legacy |
| `MEJORAS.md` | Deuda técnica del proyecto original |

## Por dónde empezar

| Orden | Acción | Bloquea a |
|---|---|---|
| 1 | Cerrar **F0 contratos** (~1 día) | Todo |
| 2 | **F6**: visita a la puerta + iniciar compras | Nada, pero es la ruta crítica |
| 3 | Correr el legacy y **medir la línea base** (`PLAN_AWS.md` §7) | F4 |
| 4 | F1…F5 en paralelo | — |

## Dos reglas que gobiernan el proyecto

**`contracts/` se modifica solo por acuerdo.** Cambiar un contrato rompe trabajo
ajeno en curso.

**La seguridad del portón es de hardware, no de software.** E-stop, fotocelda y
finales de carrera van cableados en serie con la bobina del contactor. El software
solo puede *pedir* movimiento; el hardware debe poder *negarlo*.
