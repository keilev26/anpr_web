import pytest

from anpr_ml.pipeline import Box, PlatePipeline


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


def build(det, ocr):
    return PlatePipeline(det, ocr, FakeCropper())


def test_lee_placa_valida(frames):
    r = build(FakeDetector([[caja()]]), FakeOcr([[("CUB-604", 0.95)]])).run(frames)
    assert r.ok and r.plate == "CUB-604"
    assert r.plate_px_width == 120


def test_corta_en_el_primer_acierto(frames):
    """Procesar los 10 frames se saldría del presupuesto de latencia."""
    det = FakeDetector([[caja()]])
    r = build(det, FakeOcr([[("CUB-604", 0.95)]])).run(frames)
    assert r.frames_processed == 1
    assert det.llamadas == 1


def test_sigue_buscando_si_la_lectura_falla(frames):
    det = FakeDetector([[caja()]])
    ocr = FakeOcr([[("XX", 0.4)], [("YY", 0.4)], [("CUB-604", 0.9)]])
    r = build(det, ocr).run(frames)
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
