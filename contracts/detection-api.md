# Contrato A — Pi → Nube (camino crítico)

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

## Decisiones deliberadas

**`command` viene explícito.** La Pi no deduce la acción a partir de `authorized`.
Si mañana un operador abre desde el dashboard, o hay reglas de horario o de rol,
la lógica queda en un solo lugar y la Pi no cambia.

**`ttl_s`.** Si la respuesta llega tarde (red lenta, reintento), la Pi la descarta.
Sin esto, un veredicto retrasado puede abrir el portón cuando el vehículo ya se fue.

**`event_id` como idempotencia.** Un reenvío por timeout no debe abrir dos veces.

## Errores

| Código | Significado | Qué hace la Pi |
|---|---|---|
| 400 | Ráfaga inválida | Descarta, registra fallo |
| 401 | Credencial de dispositivo inválida | Alerta, no reintenta |
| 422 | Ninguna placa legible en la ráfaga | Registra, no abre |
| 5xx / timeout | Falla de nube | Encola y reintenta; **no abre** |

## Presupuesto de latencia

| Etapa | Objetivo |
|---|---|
| Captura de ráfaga | 1.0–2.0 s |
| Subida (~600 KB) | 0.2–1.0 s |
| Inferencia (tibia) | 0.5–1.5 s |
| BD + respuesta | 0.1 s |
| **Total** | **< 4 s** |
