# F4 — Modelo e inferencia

Detección y lectura de placas. El modelo **no corre en la Raspberry**: vive en un
Lambda de AWS (ver `PLAN_AWS.md`).

## Qué hay aquí

```
src/anpr_ml/
├── plate_text.py    Post-procesado del OCR. Sin dependencias pesadas.
├── pipeline.py      Orquestación frames -> placa. Detector y OCR son Protocols.
├── onnx_engine.py   Implementaciones reales (onnxruntime, cv2, paddleocr).
└── handler.py       Entrypoint del Lambda.

scripts/
├── measure_plate_px.py   MIDE PRIMERO ESTO (ver abajo)
├── export_onnx.py        best.pt -> ONNX, con mAP antes y después
└── benchmark.py          Precisión real sobre imágenes etiquetadas
```

La separación importa: `plate_text.py` y `pipeline.py` **no importan nada pesado**,
así que los 41 tests corren en 0,02 s sin torch ni paddle instalados.

## Empieza por medir, no por optimizar

```bash
uv pip install -e ".[train]"
python scripts/measure_plate_px.py --images ./muestras --model best.pt
```

Toma unas fotos **desde la posición real de la cámara, a la distancia real del
portón**, y pásaselas. Si la placa mide menos de ~60 px de ancho, el cuello de
botella es **óptico**: ningún reentrenamiento, cuantización ni cambio de OCR lo
arregla, y la decisión pasa a ser de cámara.

Recuerda que el legacy pedía `startLiveviewWithSize(["M"])`, un preview reducido,
y alimentaba YOLO a 640 px. Esta medición dice si eso alcanza. **Es la pregunta
más barata de responder y la que más puede cambiar el plan.**

## Comandos

| Comando | Qué hace |
|---|---|
| `pytest` | 41 tests del post-procesado y el pipeline |
| `ruff check src tests scripts` | Lint |
| `scripts/measure_plate_px.py` | Ancho de placa en píxeles + veredicto de cámara |
| `scripts/export_onnx.py` | Export a ONNX midiendo mAP antes y después |
| `scripts/benchmark.py` | Tasa de detección, lectura correcta y mal leída |

> `pytest` y `ruff` solo necesitan `.[dev]`. Los scripts necesitan `.[train]`
> o `.[runtime]`, que son ~2-3 GB.
>
> **Nota del entorno:** esta máquina tiene ROS en `PYTHONPATH` y rompe pytest.
> Usa `PYTHONPATH= pytest`.

## El modelo

De `legacy/mqtt-camara-main/best.pt`, según sus propios metadatos:

| | |
|---|---|
| Arquitectura | YOLO11m, desde los pesos `yolo11m.pt` |
| Entrenado | 19-sep-2025, Ultralytics 8.3.202 |
| Dataset | `/content/license-plate-1/data.yaml` (Colab, estilo Roboflow) |
| Épocas | 15 · batch 16 · imgsz 640 · lr0 0.01 |
| Clases | 2 (el pipeline usa la 0) |
| Licencia | **AGPL-3.0** (Ultralytics) — importa si esto se despliega como servicio |

**No existe ninguna métrica de este modelo.** 15 épocas puede ser suficiente o
no; sin `model.val()` nadie lo sabe. Medirlo es el primer paso de cualquier
mejora.

## Correcciones frente al pipeline del legacy

`legacy/mqtt-camara-main/mqtt+camara.py` perdía lecturas correctas por dos
motivos, ambos corregidos y con test:

**1. El filtro de 7 caracteres.** `wl = re.compile(r'^.{7}$')` exigía
exactamente 7. Si el OCR leía `ABC123` sin guion, **descartaba una placa
correcta**. Ahora se normaliza a 6 alfanuméricos y se reinserta el guion.

**2. El respaldo muerto.** `run_ocr_logic` devolvía `candidates[0]` cuando nada
coincidía, pero quien la llamaba revalidaba con el patrón, así que ese respaldo
**siempre se descartaba**. Peor que inútil: ocultaba los fallos del OCR, y sin
ellos no hay forma de medir la precisión. Ahora se devuelven en
`failed_readings`.

**3. `ocr_config.yaml` reescrito.** Tenía rutas absolutas de Windows de otra
persona (`C:\Users\Alexis\.paddlex\...`), que no cargan en Linux, y activaba
cuatro modelos de preprocesado de **documentos** —orientación de página,
desdoblado UVDoc, orientación de línea— inútiles sobre el recorte de una placa
y que engordan el cold start.

## Añadido: desambiguación por posición

Una placa peruana tiene estructura conocida: `LLD-DDD`. El post-procesado la
aprovecha para resolver confusiones típicas del OCR según **dónde** aparecen:
en las tres últimas posiciones una `O` solo puede ser un `0`; en la primera, un
`0` solo puede ser una `O`.

```
CUB-6O4  ->  CUB-604   (1 corrección)
CUB-GO4  ->  CUB-604   (2 correcciones)
0UB-604  ->  OUB-604   (1 corrección)
```

Con dos salvaguardas, porque esto gobierna una puerta y **una placa inventada
que coincida por azar con la lista blanca abriría al vehículo equivocado**:

- **Máximo 2 correcciones.** A partir de tres, la placa es más invención nuestra
  que lectura del OCR.
- **El prefijo debe tener al menos una letra real.** Sin esta regla, `123456` se
  "corregía" a `I23-456`. Seis dígitos seguidos significan que el OCR estaba
  mirando otra cosa.

Y ante dos lecturas válidas, `best_plate` prefiere **la que no necesitó
corrección**, aunque tenga menos confianza: una corrección es una conjetura.

## Estado

- [x] Post-procesado del OCR, con los dos bugs del legacy corregidos
- [x] Desambiguación posicional con salvaguardas
- [x] Pipeline con Protocols, probable sin el stack pesado (41 tests)
- [x] Motor ONNX, handler de Lambda y Dockerfile ARM64
- [x] `ocr_config.yaml` sin rutas de Windows y sin los 4 modelos de documento
- [x] Scripts de medición, export y benchmark
- [ ] **Ejecutar la medición de píxeles** — necesita fotos desde la cámara real
- [ ] **Exportar a ONNX y medir mAP** — necesita ~3 GB de disco libre
- [ ] Benchmark de precisión — necesita imágenes etiquetadas
- [ ] Construir y desplegar la imagen (con F3)

## Lo que bloquea terminar F4

1. **Fotos de placas desde la posición real de la cámara.** Sin ellas no hay
   medición de píxeles ni benchmark. Es lo único que no puede resolverse
   escribiendo código.
2. **Espacio en disco.** El stack de export son ~2-3 GB y la máquina está al 95%.
3. **El `data.yaml` del dataset** de Colab, para poder medir mAP con `model.val()`.
