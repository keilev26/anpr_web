# Imagen del Lambda de inferencia (F4), para arquitectura ARM64.
#
# Usa onnxruntime en vez de torch+ultralytics: la imagen pasa de varios GB a
# unos cientos de MB, y eso reduce directamente el cold start, que es el mayor
# riesgo de latencia del camino crítico.
FROM public.ecr.aws/lambda/python:3.12-arm64

# Dependencias del sistema que necesita opencv-python-headless
RUN dnf install -y mesa-libGL && dnf clean all

COPY pyproject.toml ${LAMBDA_TASK_ROOT}/
RUN pip install --no-cache-dir \
      onnxruntime==1.20.1 \
      numpy==2.2.1 \
      opencv-python-headless==4.10.0.84 \
      paddleocr==2.9.1

COPY src/anpr_ml ${LAMBDA_TASK_ROOT}/anpr_ml
COPY ocr_config.yaml ${LAMBDA_TASK_ROOT}/

# Los modelos van HORNEADOS en la imagen, no se descargan en runtime:
# descargarlos en la primera invocación añadiría segundos al cold start y
# ataría el arranque a que una red externa responda.
COPY models/best.onnx ${LAMBDA_TASK_ROOT}/models/
COPY models/paddle ${LAMBDA_TASK_ROOT}/models/paddle

ENV MODEL_PATH=${LAMBDA_TASK_ROOT}/models/best.onnx \
    OCR_CONFIG=${LAMBDA_TASK_ROOT}/ocr_config.yaml \
    PADDLE_HOME=${LAMBDA_TASK_ROOT}/models/paddle \
    CONF_THRESHOLD=0.30

CMD ["anpr_ml.handler.lambda_handler"]
