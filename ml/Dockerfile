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

# Librerías de sistema que la imagen base de Lambda (Amazon Linux 2023) no trae,
# reproducido con el emulador de Lambda:
# - libgomp: libpaddle.so (compilado en C++) la necesita (OpenMP). Sin ella falla
#   al importar paddle con "libgomp.so.1: cannot open shared object file".
# - mesa-libGL, libXext, libSM, libXrender, glib2: las pide `opencv-contrib-python`
#   (la variante con interfaz gráfica que trae `paddleocr`). Se probó cambiarla
#   por la headless para no instalar esto, pero `paddlex` exige en tiempo de
#   ejecución el paquete `opencv-contrib-python` **por su nombre exacto**
#   (`paddlex.utils.deps.require_extra`); con la headless falla con
#   "A dependency error occurred during pipeline creation" aunque `cv2` funcione
#   igual. Más simple instalar estas 5 librerías que pelear con esa validación.
RUN dnf install -y libgomp mesa-libGL libXext libSM libXrender glib2 && dnf clean all

RUN pip install --no-cache-dir \
      paddlepaddle==3.3.1 \
      paddleocr==3.7.0 \
      onnxruntime==1.30.0

COPY src/anpr_ml ${LAMBDA_TASK_ROOT}/anpr_ml

# Modelos HORNEADOS en la imagen, nunca descargados en runtime: descargar en la
# primera invocación alargaría el cold start y ataría el arranque a la red.
#   models/best.onnx      -> scripts/export_onnx.py
#   models/paddle/<modelo> -> copiar de $PADDLE_PDX_CACHE_HOME/official_models/
#                            los dos de anpr_ml/ocr_settings.py
COPY models/best.onnx ${LAMBDA_TASK_ROOT}/models/
COPY models/paddle ${LAMBDA_TASK_ROOT}/models/paddle

# Sin esto, Paddle ve los CPUs del servidor físico completo (no los que le
# tocan en el sandbox de Lambda) y lanza demasiados hilos: se cuelga sin error
# ni consumir memoria (reproducido en AWS: 60 s de "Status: timeout" con solo
# 463 MB usados, sin siquiera terminar de cargar el modelo). Problema conocido
# de OpenBLAS/OpenMP en contenedores con cuota de CPU, no con CPUs fijos.
ENV OMP_NUM_THREADS=1 \
    OPENBLAS_NUM_THREADS=1 \
    MKL_NUM_THREADS=1 \
    NUMEXPR_NUM_THREADS=1 \
    # Paddle no siempre respeta OMP_NUM_THREADS para su propia librería
    # matemática interna (MKL/OpenBLAS compilados dentro de libpaddle.so):
    # tiene su propia bandera, por convención FLAGS_*.
    FLAGS_cpu_math_library_num_threads=1 \
    # Bug conocido de Paddle: su asignador de memoria por defecto ("auto_growth")
    # puede quedarse esperando indefinidamente bajo ciertas restricciones del
    # sistema (documentado para GPU; se prueba aquí porque el síntoma es
    # idéntico: colgado sin error, memoria reportada baja y estable). La
    # estrategia simple no tiene ese bucle.
    FLAGS_allocator_strategy=naive_best_fit

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
