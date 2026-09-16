"""
Configuración de PaddleOCR. ÚNICA fuente de verdad para producción
(`onnx_engine.PaddleOcr`) y para las pruebas (`scripts/ocr_visual.py`).

Sustituye a `ocr_config.yaml`, que PaddleOCR 3.7 aplicaba solo a medias: sí
apagaba el preprocesado de documentos, pero ignoraba los nombres de modelo y
cargaba sus predeterminados. Aquí todo va por parámetros del constructor, que
se comprobaron en el código instalado (paddleocr 3.7.0) y en el log de carga.

Sin dependencias: se importa desde entornos que no tienen paddle instalado.
"""

from __future__ import annotations

# Los modelos con los que se hizo la prueba visual del 2026-09-16. Cambiarlos
# exige repetir la prueba: los resultados no se trasladan de un modelo a otro.
DET_MODEL = "PP-OCRv6_medium_det"
REC_MODEL = "PP-OCRv6_medium_rec"


def paddleocr_kwargs(models_dir: str | None = None) -> dict:
    """
    Parámetros para `PaddleOCR(**paddleocr_kwargs(...))`.

    `models_dir`: carpeta con `<DET_MODEL>/` y `<REC_MODEL>/` ya descargados.
    Obligatorio en Lambda: con rutas locales PaddleOCR no pasa por la lógica de
    descarga de modelos oficiales, que crea un fichero de bloqueo y fallaría en
    un sistema de archivos de solo lectura. Sin él, descarga a
    `PADDLE_PDX_CACHE_HOME`, que es lo cómodo en desarrollo.
    """
    kwargs = {
        # Preprocesado pensado para escanear documentos: inútil sobre el
        # recorte de una placa y solo alarga el arranque.
        "use_doc_orientation_classify": False,
        "use_doc_unwarping": False,
        "use_textline_orientation": False,
        "text_detection_model_name": DET_MODEL,
        "text_recognition_model_name": REC_MODEL,
        # oneDNN (aceleración de Paddle en CPU) falla con estos modelos en
        # paddlepaddle 3.3.1: "ConvertPirAttribute2RuntimeAttribute not support
        # [pir::ArrayAttribute<pir::DoubleAttribute>]".
        "enable_mkldnn": False,
    }
    if models_dir:
        kwargs["text_detection_model_dir"] = f"{models_dir}/{DET_MODEL}"
        kwargs["text_recognition_model_dir"] = f"{models_dir}/{REC_MODEL}"
    return kwargs
