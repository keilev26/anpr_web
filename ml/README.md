# F4 — Modelo e inferencia

Export, optimización y medición del pipeline de visión.

## Alcance

- Export de `best.pt` (YOLO11m) a ONNX + validación de que el mAP no se degrada
- Adelgazar PaddleOCR
- Handler de inferencia: recibe JPEG, devuelve `{plate, confidence}`
- Imagen de contenedor para Lambda ARM64, con los modelos horneados

## No incluye

- El despliegue (F3) ni la captura (F5)

## Cómo trabajar aislado

**Una carpeta de fotos de placas.** Sin nube, sin Pi, sin cámara.

## Terminado cuando

mAP medido, tasa de lectura medida, y el handler devuelve placa desde un JPEG.

## Punto de partida

`legacy/mqtt-camara-main/` — `best.pt` (YOLO11m, Ultralytics 8.3.202, dataset
`license-plate-1`, 15 épocas, imgsz 640, 2 clases) y `mqtt+camara.py`.

## Tareas concretas heredadas

**Adelgazar `ocr_config.yaml`.** Trae activados `use_doc_preprocessor`,
`use_doc_orientation_classify`, `use_doc_unwarping` y `use_textline_orientation`:
cuatro modelos extra pensados para escanear documentos, inútiles sobre el recorte
de una placa.

**Quitar las rutas Windows.** Cinco rutas `C:\Users\Alexis\.paddlex\...` que no
cargan en Linux.

**Dos bugs de lectura:**

1. El filtro `wl = re.compile(r'^.{7}$')` exige exactamente 7 caracteres: si el OCR
   lee `ABC123` sin guion, **descarta una placa correcta**.
2. `run_ocr_logic` devuelve `candidates[0]` como fallback, pero el llamador vuelve a
   validar con `PLATE_PATTERN.fullmatch`, así que **ese fallback siempre se descarta**.
   Usarlo para registrar lecturas fallidas y poder medir precisión real.

**Propagar `confidence`** de YOLO y el score del OCR hasta la BD; hoy se descartan.

## Línea base: medir antes de optimizar

Hoy **no existe ninguna métrica** del sistema. Sin línea base no se puede demostrar
que exportar a ONNX o cambiar de cámara mejoró algo. Medir primero:

- Ancho en píxeles de la placa en el crop de YOLO, a la distancia real del portón
- Tasa de detección: eventos con placa válida / disparos totales
- Tasa de lectura correcta: placas bien leídas / placas detectadas
- mAP con `model.val()`

**El dato más importante es el primero.** Si a la distancia real la placa ocupa menos
de ~60-80 px de ancho en el liveview, ninguna mejora de modelo lo va a salvar y la
cámara pasa a ser la prioridad.
