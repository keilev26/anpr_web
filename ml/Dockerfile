# Imagen del Lambda de inferencia (F4).
#
# x86_64 y no ARM64: paddlepaddle no publica paquetes aarch64 en PyPI (3.3.1 solo
# trae x86_64). A este volumen la diferencia de precio es ~0,80 USD/mes.
# Python 3.12: paddlepaddle no tiene paquetes para 3.14.
#
# ESTADO: la configuración de OCR está verificada en un entorno que simula el
# sistema de archivos de Lambda (ml/README.md, "Simulación de Lambda"), pero esta
# imagen AÚN NO SE HA CONSTRUIDO. Validar con `docker build` + Lambda Runtime
# Interface Emulator antes de desplegar (tarea de F3).
FROM public.ecr.aws/lambda/python:3.12

RUN pip install --no-cache-dir \
      paddlepaddle==3.3.1 \
      paddleocr==3.7.0 \
      onnxruntime==1.30.0 \
 # paddleocr arrastra opencv-contrib-python, la variante con interfaz gráfica,
 # que necesita libGL. Se sustituye por la headless de la MISMA versión: dos
 # paquetes que proveen `cv2` en el mismo entorno se pisan.
 && pip uninstall -y opencv-contrib-python \
 && pip install --no-cache-dir opencv-contrib-python-headless==4.10.0.84

COPY src/anpr_ml ${LAMBDA_TASK_ROOT}/anpr_ml

# Modelos HORNEADOS en la imagen, nunca descargados en runtime: descargar en la
# primera invocación alargaría el cold start y ataría el arranque a la red.
#   models/best.onnx      -> scripts/export_onnx.py
#   models/paddle/<modelo> -> copiar de $PADDLE_PDX_CACHE_HOME/official_models/
#                            los dos de anpr_ml/ocr_settings.py
COPY models/best.onnx ${LAMBDA_TASK_ROOT}/models/
COPY models/paddle ${LAMBDA_TASK_ROOT}/models/paddle

ENV MODEL_PATH=${LAMBDA_TASK_ROOT}/models/best.onnx \
    # Rutas locales: PaddleOCR no pasa por la descarga de modelos oficiales.
    OCR_MODELS_DIR=${LAMBDA_TASK_ROOT}/models/paddle \
    # En Lambda solo /tmp es escribible, y PaddleX crea <caché>/temp y
    # <caché>/locks al importarse. Con la caché fuera de /tmp falla al arrancar
    # (reproducido en la simulación: PermissionError en .../temp).
    PADDLE_PDX_CACHE_HOME=/tmp/paddlex \
    PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK=True \
    HOME=/tmp \
    CONF_THRESHOLD=0.30 \
    MIN_AGREEMENT=2

CMD ["anpr_ml.handler.lambda_handler"]
