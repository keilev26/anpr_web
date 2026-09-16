import pytest

from anpr_ml.pipeline import Box, PlatePipeline, crop_window


class FakeDetector:
    def __init__(self, por_frame):
        self.por_frame = por_frame
        self.llamadas = 0

    def detect(self, image):
        boxes = self.por_frame[min(self.llamadas, len(self.por_frame) - 1)]
        self.llamadas += 1
        return boxes


class FakeOcr:
    def __init__(self, lecturas):
        self.lecturas = lecturas
        self.llamadas = 0

    def read(self, crop):
        r = self.lecturas[min(self.llamadas, len(self.lecturas) - 1)]
        self.llamadas += 1
        return r


class FakeCropper:
    def crop(self, image, box):
        return f"crop-{box.x1}"


def caja(w=120, conf=0.9, x1=0):
    return Box(x1=x1, y1=0, x2=x1 + w, y2=40, confidence=conf)


@pytest.fixture
def frames():
    return ["f1", "f2", "f3"]


def build(det, ocr, min_agreement=2):
    return PlatePipeline(det, ocr, FakeCropper(), min_agreement=min_agreement)


def test_lee_placa_valida(frames):
    r = build(FakeDetector([[caja()]]), FakeOcr([[("CUB-604", 0.95)]])).run(frames)
    assert r.ok and r.plate == "CUB-604"
    assert r.plate_px_width == 120


def test_corta_al_alcanzar_consenso(frames):
    """Procesar los 10 frames se saldría del presupuesto de latencia."""
    det = FakeDetector([[caja()]])
    r = build(det, FakeOcr([[("CUB-604", 0.95)]])).run(frames)
    assert r.ok and r.frames_processed == 2
    assert det.llamadas == 2
    assert r.votes == {"CUB-604": 2}


def test_con_min_agreement_1_corta_en_el_primer_acierto(frames):
    det = FakeDetector([[caja()]])
    r = build(det, FakeOcr([[("CUB-604", 0.95)]]), min_agreement=1).run(frames)
    assert r.ok and r.frames_processed == 1


def test_sigue_buscando_si_la_lectura_falla(frames):
    det = FakeDetector([[caja()]])
    ocr = FakeOcr([[("XX", 0.4)], [("YY", 0.4)], [("CUB-604", 0.9)]])
    r = build(det, ocr, min_agreement=1).run(frames)
    assert r.ok and r.frames_processed == 3


def test_descarta_cajas_bajo_el_umbral(frames):
    r = build(FakeDetector([[caja(conf=0.10)]]), FakeOcr([[("CUB-604", 0.9)]])).run(frames)
    assert not r.ok
    assert r.boxes_found == 0


def test_prueba_primero_la_caja_mas_ancha(frames):
    """La placa más grande es la del vehículo más cercano, y la más legible."""
    det = FakeDetector([[caja(w=50, x1=0), caja(w=200, x1=300)]])
    ocr = FakeOcr([[("CUB-604", 0.9)]])
    r = build(det, ocr).run(frames)
    assert r.plate_px_width == 200


def test_registra_las_lecturas_fallidas(frames):
    """Sin esto no se puede medir la tasa real de acierto."""
    ocr = FakeOcr([[("ZZ", 0.4)], [("QQ", 0.4)], [("WW", 0.4)]])
    r = build(FakeDetector([[caja()]]), ocr).run(frames)
    assert not r.ok
    assert r.failed_readings == ["ZZ", "QQ", "WW"]


def test_reporta_el_ancho_aunque_no_lea(frames):
    """Si todo falla, el ancho dice si el problema es la cámara, no el modelo."""
    ocr = FakeOcr([[("ZZ", 0.4)]])
    r = build(FakeDetector([[caja(w=35)]]), ocr).run(frames)
    assert not r.ok and r.plate_px_width == 35


def test_sin_detecciones(frames):
    r = build(FakeDetector([[]]), FakeOcr([[]])).run(frames)
    assert not r.ok and r.boxes_found == 0 and r.frames_processed == 3


def test_propaga_las_correcciones(frames):
    r = build(FakeDetector([[caja()]]), FakeOcr([[("CUB-6O4", 0.9)]])).run(frames)
    assert r.ok and r.plate == "CUB-604" and len(r.corrections) == 1


def test_crop_window_anade_margen_proporcional():
    b = Box(100, 200, 300, 260, 0.9)  # alto 60 -> margen 6
    assert crop_window(b, 1000, 1000) == (94, 194, 306, 266)


def test_crop_window_no_sale_de_la_imagen():
    b = Box(0, 0, 50, 20, 0.9)
    x1, y1, x2, y2 = crop_window(b, 52, 21)
    assert (x1, y1) == (0, 0) and x2 <= 52 and y2 <= 21


def test_crop_window_margen_minimo_en_placas_bajas():
    b = Box(10, 10, 60, 15, 0.9)  # alto 5 -> margen mínimo 2
    assert crop_window(b, 100, 100) == (8, 8, 62, 17)


class TestConsenso:
    """
    Motivo: en la prueba visual hubo lecturas erróneas con aspecto válido y alta
    confianza (T5Q-640 leída T50-640 con 0,91; DPD-127 leída OPO-127). Ningún
    umbral las filtra, pero el mismo error rara vez se repite en dos fotogramas.
    """

    def test_una_lectura_erronea_aislada_pierde_la_votacion(self):
        ocr = FakeOcr([[("OPO-127", 0.74)], [("DPD-127", 0.95)], [("DPD-127", 0.93)]])
        r = build(FakeDetector([[caja()]]), ocr).run(["f1", "f2", "f3"])
        assert r.ok and r.plate == "DPD-127"
        assert r.votes == {"OPO-127": 1, "DPD-127": 2}

    def test_lecturas_todas_distintas_no_abren(self):
        ocr = FakeOcr([[("AAA-111", 0.9)], [("BBB-222", 0.9)], [("CCC-333", 0.9)]])
        r = build(FakeDetector([[caja()]]), ocr).run(["f1", "f2", "f3"])
        assert not r.ok
        assert r.reason == "sin_consenso"
        assert r.votes == {"AAA-111": 1, "BBB-222": 1, "CCC-333": 1}

    def test_un_fotograma_no_vota_dos_veces(self):
        """Dos recortes de la misma foto son la misma evidencia, no consenso."""
        det = FakeDetector([[caja(x1=0), caja(x1=300)]])
        ocr = FakeOcr([[("CUB-604", 0.9)], [("CUB-604", 0.9)]])
        r = build(det, ocr).run(["unico"])
        assert not r.ok
        assert r.votes == {"CUB-604": 1}

    def test_menos_fotogramas_que_el_consenso_no_se_relaja(self):
        r = build(FakeDetector([[caja()]]), FakeOcr([[("CUB-604", 0.99)]])).run(["unico"])
        assert not r.ok and r.reason == "frames_insuficientes"

    def test_sin_ninguna_lectura_valida(self):
        r = build(FakeDetector([[caja()]]), FakeOcr([[("ZZ", 0.4)]])).run(["f1", "f2"])
        assert not r.ok and r.reason == "sin_lectura" and r.votes == {}

    def test_placa_con_correcciones_tambien_necesita_consenso(self):
        ocr = FakeOcr([[("CUB-6O4", 0.9)], [("XYZ-999", 0.9)]])
        r = build(FakeDetector([[caja()]]), ocr).run(["f1", "f2"])
        assert not r.ok

    def test_min_agreement_invalido(self):
        with pytest.raises(ValueError):
            PlatePipeline(FakeDetector([[]]), FakeOcr([[]]), FakeCropper(), min_agreement=0)
