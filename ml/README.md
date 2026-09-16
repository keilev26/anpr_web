# F4 — Modelo e inferencia

Detección y lectura de placas. El modelo **no corre en la Raspberry**: vive en un
Lambda de AWS (ver `PLAN_AWS.md`).

> **Hay pendientes manuales que bloquean cerrar F4** — etiquetar placas y tomar
> fotos reales desde la puerta. Ver [Pendientes](#pendientes) al final.

## Qué hay aquí

```
src/anpr_ml/
├── plate_text.py    Post-procesado del OCR. Sin dependencias pesadas.
├── pipeline.py      Orquestación frames -> placa. Detector y OCR son Protocols.
├── coco.py          Conversión COCO->YOLO y comprobación de fugas. Pura.
├── crops.py         Planificación de recortes de vista de puerta. Pura.
├── ocr_settings.py  Configuración de PaddleOCR: única fuente de verdad. Pura.
├── onnx_engine.py   Implementaciones reales (onnxruntime, cv2, paddleocr).
└── handler.py       Entrypoint del Lambda.

scripts/
├── measure_plate_px.py   MIDE PRIMERO ESTO (ver abajo)
├── coco_to_yolo.py       Export COCO de Roboflow -> YOLO, fusionando clases
├── make_gate_view.py     Recortes de "vista de puerta" con cajas recalculadas
├── preview_labels.py     Dibuja las etiquetas para revisarlas a ojo
├── baseline.py           Línea base de best.pt + decisión de reentrenar
├── train.py              Fine-tuning con comprobación de fugas
├── detect_plates.py      Prueba visual 1/2: YOLO detecta y recorta (entorno 3.14)
├── ocr_visual.py         Prueba visual 2/2: OCR + fichas para revisar (entorno 3.12)
├── export_onnx.py        best.pt -> ONNX, con mAP antes y después
└── benchmark.py          Precisión real sobre imágenes etiquetadas
```

La separación importa: `plate_text.py` y `pipeline.py` **no importan nada pesado**,
así que los 192 tests corren en 0,1 s sin torch ni paddle instalados.

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
| `pytest` | 192 tests: post-procesado, consenso, conversión COCO, recortes y config OCR |
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

## Dataset: Peru Plate Numbers (Roboflow)

> *Peru Plate Numbers*, grupo-6-placas, Roboflow Universe, versión 3 (2023-11-09).
> https://universe.roboflow.com/grupo-6-placas/peru-plate-numbers ·
> Licencia **CC BY 4.0**, que obliga a citar la fuente.

Descargado a mano en `ml/roboflow_images/` (2 GB, ignorado por git). Después:

```bash
uv pip install -e ".[dev,data]"
python scripts/coco_to_yolo.py      # -> datasets/peru-plates   (15 MB: enlaces + etiquetas)
python scripts/make_gate_view.py    # -> datasets/peru-gate-view (140 MB de recortes)
python scripts/preview_labels.py --data datasets/peru-gate-view --split test -n 10
```

### Lo que hay que saber de estos datos

| | |
|---|---|
| Splits | train 1470 img / 2919 cajas · valid 138 / 257 · test **32** / 63 |
| Fugas | Ninguna: 0 fotos originales compartidas entre splits, ni con los recortes |
| Aumentado | Solo en train, 3 copias por foto |
| Perspectiva | Casi todas desde un puente peatonal, mirando hacia abajo |
| Placa (real) | mediana 131 px de ancho en la foto; **~21 px** tras reducir a 640 |

**Clases fusionadas.** El export trae `Placa` (2412 cajas) y `placa` (507) como
categorías distintas: dos anotadores con distinta mayúscula. `coco_to_yolo.py`
las une en una sola clase `placa`.

**Tamaño real distinto del declarado.** El JSON dice 1536×2048 pero los archivos
miden 3000×4000 (22 miden 6000×8000). Es un reescalado uniforme, así que las cajas
normalizadas son correctas; se verificó en las 1640 imágenes y a ojo en las
previsualizaciones.

**Placas sin etiquetar.** Algunas placas lejanas visibles no están anotadas.
Detectarlas cuenta como falso positivo: la precisión medida queda algo por debajo
de la real.

**Test pequeño.** Con 32 imágenes una sola mueve el mAP varios puntos. La línea
base usa valid+test juntos (170 imágenes, que `best.pt` nunca vio).

### Vista de puerta

A 640 px la placa mediana mide ~21 px: son fotos de calle con varios autos lejos.
`make_gate_view.py` recorta alrededor de cada placa para que ocupe 80-200 px en un
cuadro horizontal de 640×480, parecido al de una cámara de acceso, y **recalcula
las cajas** (recortar a mano en un editor las dejaría desalineadas sin ningún error).

Salvaguardas, porque **un recorte simula el encuadre, no la resolución**: solo
placas de ≥40 px nativos y ampliación máxima 2×. Aun así hay recortes borrosos:
sirven para *detectar* (una cámara real también da cuadros borrosos), no para
medir *lectura*. Y **no responden si la Sony alcanza**: eso requiere fotos desde la
puerta, con las que habrá que ajustar `--plate-px`.

Resultado: 2310 / 213 / 51 recortes, conservando los splits.

### Medir y, si hace falta, reentrenar

Requiere GPU funcionando y ~2,5 GB para torch con CUDA:

```bash
UV_NO_CACHE=1 uv pip install -e ".[train]"   # --no-cache: no duplicar el wheel
python scripts/baseline.py                    # -> metrics/baseline_best_pt.json + decisión
python scripts/train.py --name peru_v1        # solo si baseline dice REENTRENAR
python scripts/export_onnx.py --model runs/train/peru_v1/weights/best.pt \
       --data datasets/peru-plates/eval/valtest.yaml
```

**Criterio fijado antes de medir:** reentrenar si mAP@50 < 0,90 en valid+test a
640, o si en vista de puerta cae más de 5 puntos. `train.py` aborta si detecta
alguna foto de evaluación en train, y avisa si autobatch elige batch < 4 (4 GB de
VRAM), en cuyo caso conviene `--base yolo11s.pt`.

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

**3. Configuración del OCR.** El `ocr_config.yaml` del legacy tenía rutas absolutas
de Windows de otra persona (`C:\Users\Alexis\.paddlex\...`), que no cargan en
Linux, y activaba cuatro modelos de preprocesado de **documentos**, inútiles
sobre el recorte de una placa. Se reescribió como YAML, pero **PaddleOCR 3.7 lo
aplicaba a medias**: apagaba el preprocesado, pero ignoraba los nombres de modelo
y cargaba sus predeterminados, cosa que solo se vio en el log. Ahora la
configuración vive en `src/anpr_ml/ocr_settings.py`, por parámetros del
constructor, compartida por producción y pruebas.

## Añadido: desambiguación por posición

Una placa peruana tiene estructura conocida: `LLD-DDD`. El post-procesado la
aprovecha para resolver confusiones típicas del OCR según **dónde** aparecen:
en las tres últimas posiciones una `O` solo puede ser un `0`.

```
CUB-6O4  ->  CUB-604   (1 corrección)
CUB-GO4  ->  CUB-604   (2 correcciones)
12E274   ->  NO LEGIBLE
```

**La primera posición ya no se corrige.** Antes se convertían dígitos en letras
(`1→I`, `0→O`). En la prueba visual, sus 4 aplicaciones reales fueron **todas
erróneas**: el OCR leía `1` en placas que empiezan por `T` con la barra superior
tapada por el marco, y la corrección fabricaba placas inexistentes con aspecto
válido (`I2E-274` en lugar de `T2E-274`). Una placa inventada es peor que "no
legible". Si alguna vez se prueba `1→T`, debe medirse con un benchmark etiquetado.

Con dos salvaguardas, porque esto gobierna una puerta y **una placa inventada
que coincida por azar con la lista blanca abriría al vehículo equivocado**:

- **Máximo 2 correcciones.** A partir de tres, la placa es más invención nuestra
  que lectura del OCR.
- **El prefijo debe tener al menos una letra real.** Sin esta regla, `123456` se
  "corregía" a `I23-456`. Seis dígitos seguidos significan que el OCR estaba
  mirando otra cosa.

Y ante dos lecturas válidas, `best_plate` prefiere **la que no necesitó
corrección**, aunque tenga menos confianza: una corrección es una conjetura.

## Línea base de `best.pt` (2026-09-16)

`metrics/baseline_best_pt.json`. La clase 0 es la placa; la 1 es vehículo (se
identificó midiendo IoU contra las etiquetas, porque el modelo las llama `'0'` y `'2'`).

| Conjunto | mAP@50 | P | R |
|---|---|---|---|
| valid+test a 640 | 0,555 | 0,76 | 0,54 |
| valid+test a 1280 | 0,844 | 0,88 | 0,80 |
| **Vista de puerta a 640** | **0,954** | **0,97** | **0,92** |

El salto de 640 a 1280 (+29 puntos) dice que el problema es el tamaño de la placa,
no el modelo. **Decisión: no reentrenar por ahora**; la vista de puerta ya supera
0,90 y la pregunta pendiente es la resolución real de la cámara.

La evaluación va **sin `single_cls`**: con él, las cajas de vehículo cuentan como
placas falsas (mAP@50 0,223 en vez de 0,555), porque `val()` no aplica el filtro `classes`.

## Prueba visual de lectura (2026-09-16)

Sobre los 51 recortes de test de vista de puerta, con `PP-OCRv6_medium` en CPU
(~180 ms por placa). Fichas en `runs/ocr_visual/fichas/`.

| Estado | Casos |
|---|---|
| Válida | 38 (70%) |
| No legible | 13 (24%) |
| Sin detección | 3 (6%) |

**"Válida" no es "correcta".** De 10 válidas revisadas a ojo, 2 estaban mal
leídas con aspecto perfecto: `DPD-127` → `OPO-127` y `T5Q-640` → `T50-640`, esta
última con confianza 0,91. Ningún umbral de confianza las filtra, y ocurren en
posiciones que admiten letra o dígito, donde la corrección posicional no puede
ayudar. De ahí el consenso entre fotogramas.

Para medir la tasa real de acierto falta el paso 6: etiquetar ~30 imágenes con
su placa y ejecutar `benchmark.py`.

## Consenso entre fotogramas

`PlatePipeline(min_agreement=2)`: la misma placa debe leerse en **al menos 2
fotogramas distintos** de la ráfaga. El mismo error rara vez se repite idéntico.

- Un fotograma vota una sola vez (dos recortes de la misma foto no son consenso).
- Corta en cuanto hay consenso, para no salirse del presupuesto de latencia.
- **Si llegan menos fotogramas que `min_agreement`, no se relaja**: se rechaza con
  `reason="frames_insuficientes"`. La Pi debe enviar al menos 3.
- Sin placa aceptada, `reason` y `votes` dicen por qué: `sin_lectura` (nada
  legible) o `sin_consenso` (lecturas dispersas).
- `benchmark.py` usa `min_agreement=1` a propósito: evalúa un fotograma por imagen.

## Despliegue en Lambda

**x86_64, no ARM64.** `paddlepaddle` no publica paquetes aarch64 en PyPI.
**Python 3.12**: `paddlepaddle` no tiene paquetes para 3.14. Por eso hay dos
entornos locales en `/data/anpr/venvs/`: `ml-train` (3.14, torch) y `ml-ocr` (3.12, paddle).

### Simulación de Lambda

En Lambda solo `/tmp` es escribible. Se reprodujo en local con caché, home,
carpeta de trabajo y modelos en solo lectura, y encontró un fallo antes de AWS:
**PaddleX crea `<caché>/temp` y `<caché>/locks` al importarse**. Configuración
que funciona (y la que usa el `Dockerfile`):

- `PADDLE_PDX_CACHE_HOME=/tmp/paddlex`
- Modelos horneados, pasados por `OCR_MODELS_DIR` (evita la lógica de descarga)
- `PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK=True`
- Carga de los dos modelos: ~1,1 s; ocupan 134 MB.

El `Dockerfile` **aún no se ha construido**: queda para F3, con `docker build` y
el Lambda Runtime Interface Emulator.

## Estado

- [x] Post-procesado del OCR, con los dos bugs del legacy corregidos
- [x] Corrección posicional solo en la zona de dígitos (la de la 1.ª posición se quitó)
- [x] Consenso entre fotogramas
- [x] Configuración de OCR verificada en el log y en simulación de Lambda
- [x] Dataset peruano convertido a YOLO, clases fusionadas, sin fugas
- [x] Vista de puerta generada y verificada a ojo
- [x] Línea base de `best.pt` — decisión: no reentrenar por ahora
- [x] Prueba visual de lectura
- [ ] **Benchmark de lectura etiquetado** — ver Pendientes 1
- [ ] **Medición de píxeles con fotos reales de la cámara Sony** — ver Pendientes 2
- [ ] Exportar a ONNX y medir mAP — ver Pendientes 4
- [ ] Construir la imagen y probarla con el emulador de Lambda — ver Pendientes 5

## Pendientes

Actualizado el 2026-09-16. Los dos primeros requieren trabajo manual y son las
mediciones que más pueden cambiar las decisiones siguientes.

### 1. Benchmark de lectura con placas etiquetadas — lo hace una persona

**Por qué:** la prueba visual dio 38/51 "válidas", pero de 10 revisadas a ojo 2
estaban mal leídas. Sin etiquetas no se conoce la tasa real de acierto ni, sobre
todo, la de **placas mal leídas**, que es la métrica que importa para la puerta.

**Cómo:**
1. Elegir ~30 recortes de `datasets/peru-gate-view/test/images/` donde la placa
   se lea a simple vista (y algunos difíciles: de noche, borrosos, en ángulo).
2. Copiarlos a una carpeta nueva renombrados con su placa real:
   `CUB-604_01.jpg`, `DPD-127_01.jpg`…
3. Exportar el modelo a ONNX (pendiente 4), instalar ONNX Runtime en el entorno
   de OCR (no lo trae) y ejecutar:
   ```bash
   UV_CACHE_DIR=/data/cache/uv VIRTUAL_ENV=/data/anpr/venvs/ml-ocr uv pip install onnxruntime
   PADDLE_PDX_CACHE_HOME=/data/cache/paddlex \
   /data/anpr/venvs/ml-ocr/bin/python scripts/benchmark.py --images <carpeta> --model models/best.onnx
   ```

**Decide:** si la tasa de mal leídas es aceptable, o si hay que subir
`MIN_AGREEMENT`, cambiar de modelo OCR o reentrenar.

### 2. Fotos reales desde la cámara Sony — lo hace una persona, en la puerta

**Por qué:** la línea base mostró que el tamaño de la placa lo decide todo
(0,555 a 640 frente a 0,954 en vista de puerta). Los recortes simulan el
encuadre, **no la resolución de la Sony**, y el legacy pedía un liveview reducido
(`startLiveviewWithSize(["M"])`).

**Cómo:**
1. Montar la cámara **en su posición definitiva**, con el liveview que se va a usar.
2. Capturar 20-30 fotos con autos detenidos donde paran de verdad. De día y de noche.
3. Ejecutar:
   ```bash
   /data/anpr/venvs/ml-train/bin/python scripts/measure_plate_px.py --images <carpeta> --model ../legacy/mqtt-camara-main/best.pt
   ```

**Decide:** si la mediana queda por debajo de ~60-80 px, el cuello de botella es
**la cámara** y ningún trabajo de modelo lo arregla. Si queda por encima, ajustar
`make_gate_view.py --plate-px` al rango real y repetir la línea base.

### 3. Formatos de placa distintos al de auto particular

El dataset incluye motos, que el post-procesado rechaza. Ver
`contracts/plate-format.md`: decidir si entran motos por la Puerta 2.

### 4. Exportar `best.pt` a ONNX

```bash
/data/anpr/venvs/ml-train/bin/python scripts/export_onnx.py \
    --model ../legacy/mqtt-camara-main/best.pt --data datasets/peru-plates/eval/valtest.yaml
```

Comprobar que el mAP del ONNX no cae respecto a la línea base (0,555 a 640).
Necesario para el benchmark y para la imagen de Lambda.

### 5. Construir y probar la imagen de Lambda — con F3

1. Mover el almacenamiento de Docker a `/data` antes de construir: la imagen
   pesa varios GB y la partición de Ubuntu tiene ~6,7 GB libres.
2. Preparar `models/best.onnx` (pendiente 4) y `models/paddle/` con los dos
   modelos de `src/anpr_ml/ocr_settings.py`, copiados de
   `/data/cache/paddlex/official_models/`.
3. `docker build` y probar con el Lambda Runtime Interface Emulator, enviando
   una ráfaga de 3 fotogramas.

### 6. Reentrenar — solo si los pendientes 1 o 2 lo justifican

`scripts/train.py` está listo. Hoy no se reentrena porque la vista de puerta ya
supera 0,90. Antes de lanzarlo, reducir las fotos de calle a 1280 px de lado
mayor: bajaría el entrenamiento de ~4-6 h a ~2 h en la RTX 3050.
