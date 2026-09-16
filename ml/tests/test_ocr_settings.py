from anpr_ml.ocr_settings import DET_MODEL, REC_MODEL, paddleocr_kwargs


def test_apaga_el_preprocesado_de_documentos():
    kw = paddleocr_kwargs()
    assert kw["use_doc_orientation_classify"] is False
    assert kw["use_doc_unwarping"] is False
    assert kw["use_textline_orientation"] is False


def test_desactiva_onednn():
    """oneDNN rompe la inferencia con estos modelos en paddlepaddle 3.3.1."""
    assert paddleocr_kwargs()["enable_mkldnn"] is False


def test_fija_los_modelos_probados():
    kw = paddleocr_kwargs()
    assert kw["text_detection_model_name"] == DET_MODEL
    assert kw["text_recognition_model_name"] == REC_MODEL


def test_sin_models_dir_no_fija_rutas():
    kw = paddleocr_kwargs()
    assert "text_detection_model_dir" not in kw


def test_con_models_dir_usa_rutas_locales():
    """En Lambda: evita la lógica de descarga, que escribe un bloqueo en disco."""
    kw = paddleocr_kwargs("/var/task/models/paddle")
    assert kw["text_detection_model_dir"] == f"/var/task/models/paddle/{DET_MODEL}"
    assert kw["text_recognition_model_dir"] == f"/var/task/models/paddle/{REC_MODEL}"
