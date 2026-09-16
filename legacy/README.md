# Legacy

Proyecto original, **congelado**. Se conserva como referencia mientras los frentes
nuevos lo reemplazan pieza por pieza.

| Carpeta | Qué es | Lo reemplaza |
|---|---|---|
| `backend/` | API Flask + PyMySQL | `api/` (F2) |
| `web/` | Dashboard Next.js 14 + shadcn/ui | `web/` (F1) |
| `mqtt-camara-main/` | Pipeline YOLO11m + PaddleOCR (corría en PC Windows) | `ml/` (F4) + `edge/` (F5) |
| `main2.py` | Script de diagnóstico del liveview Sony | `edge/` (F5) |
| `venv/` | Virtualenv que estaba versionado (2643 archivos) | — |

`venv/` ya **no está rastreado** por git. Puede borrarse sin consecuencias.

## Qué falta en este código

Verificado por grep sobre el repo:

- Nadie publica el disparo en `app/rx` → `mqtt+camara.py` **nunca se ejecuta**
- Nadie escucha el veredicto en `app/tx` → el backend publica al vacío
- **Cero código** de GPIO, relés o control de motor

## Antes de borrarlo

`PLAN_AWS.md` §7 tiene el runbook para hacerlo correr y **medir la línea base**.
Hoy no existe ninguna métrica de qué tan bien lee el sistema; sin ella, F4 no puede
demostrar que sus cambios mejoraron algo.
