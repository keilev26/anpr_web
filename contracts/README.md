# F0 — Contratos

**Prerequisito de todos los demás frentes. No es paralelo.**

Define las costuras entre frentes. Mientras estos archivos no estén cerrados, los otros
seis no pueden avanzar sin riesgo de chocar al integrar.

| Archivo | Costura que define | Frentes afectados |
|---|---|---|
| `detection-api.md` | Pi → Nube (camino crítico) | F5 ↔ F3/F4 |
| `mqtt-topics.md` | Bus interno de la Pi | F5 interno |
| `gpio-map.md` | Pi → Electrónica | F5 ↔ F6 |
| `openapi.yaml` | API → Frontend | F2 ↔ F1 |
| `db-schema.md` | Modelo de datos | F2 ↔ F4 |
| `plate-format.md` | Alcance del formato de placa | F1 ↔ F2 ↔ F4 |

## Regla

**Este directorio se modifica solo por acuerdo entre los frentes afectados.**
Cambiar un contrato rompe trabajo ajeno en curso. Todo cambio va por PR con los
dueños de los frentes de ambos lados como revisores.
