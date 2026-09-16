import pytest

from anpr_ml.coco import (
    CLASS_ID,
    coco_bbox_to_yolo,
    convert_split,
    find_leakage,
    photo_family,
    source_stem,
    yolo_line,
)


class TestBbox:
    def test_conversion_basica(self):
        # caja de 100x50 en (200, 100) sobre imagen 1000x500
        cx, cy, w, h = coco_bbox_to_yolo([200, 100, 100, 50], 1000, 500)
        assert cx == pytest.approx(0.25)
        assert cy == pytest.approx(0.25)
        assert w == pytest.approx(0.10)
        assert h == pytest.approx(0.10)

    def test_recorta_lo_que_sobresale(self):
        """El aumentado con rotación deja cajas fuera del borde."""
        cx, cy, w, h = coco_bbox_to_yolo([-50, -20, 100, 60], 1000, 500)
        assert w == pytest.approx(50 / 1000)
        assert h == pytest.approx(40 / 500)
        assert cx - w / 2 >= 0 and cy - h / 2 >= 0

    @pytest.mark.parametrize("bbox", [[1100, 10, 50, 50], [10, 10, 0, 20], [-100, 10, 50, 20]])
    def test_sin_area_devuelve_none(self, bbox):
        assert coco_bbox_to_yolo(bbox, 1000, 500) is None

    def test_coordenadas_siempre_en_rango(self):
        for bbox in ([0, 0, 1000, 500], [990, 490, 50, 50], [-5, -5, 20, 20]):
            box = coco_bbox_to_yolo(bbox, 1000, 500)
            assert box is not None
            assert all(0.0 <= v <= 1.0 for v in box)

    def test_linea_yolo_usa_clase_cero(self):
        assert yolo_line((0.5, 0.5, 0.1, 0.1)).startswith(f"{CLASS_ID} ")


class TestNombres:
    def test_source_stem_quita_el_sufijo_de_roboflow(self):
        assert source_stem("Foto-Placa-107-_jpg.rf.77a3ee.jpg") == "Foto-Placa-107-_jpg"

    def test_copias_aumentadas_comparten_origen(self):
        a = source_stem("Foto-Placa-1-_jpg.rf.aaa.jpg")
        b = source_stem("Foto-Placa-1-_jpg.rf.bbb.jpg")
        assert a == b

    @pytest.mark.parametrize(
        ("nombre", "familia"),
        [
            ("Foto-Placa-21-_jpg.rf.x.jpg", "foto_placa"),
            ("20231009_193016_jpg.rf.x.jpg", "fecha"),
            ("IMG_0001.rf.x.jpg", "otro"),
        ],
    )
    def test_familia(self, nombre, familia):
        assert photo_family(nombre) == familia


def _coco():
    return {
        "categories": [
            {"id": 0, "name": "plates"},
            {"id": 1, "name": "Placa"},
            {"id": 2, "name": "placa"},
        ],
        "images": [
            {"id": 1, "file_name": "a.jpg", "width": 1000, "height": 500},
            {"id": 2, "file_name": "b.jpg", "width": 1000, "height": 500},
            {"id": 3, "file_name": "vacia.jpg", "width": 1000, "height": 500},
        ],
        "annotations": [
            {"image_id": 1, "category_id": 1, "bbox": [10, 10, 100, 40]},
            {"image_id": 1, "category_id": 2, "bbox": [300, 10, 80, 30]},
            {"image_id": 2, "category_id": 2, "bbox": [10, 10, 60, 20]},
            {"image_id": 2, "category_id": 1, "bbox": [5000, 10, 60, 20]},  # fuera
        ],
    }


class TestConvertSplit:
    def test_fusiona_placa_y_placa_en_una_clase(self):
        r = convert_split(_coco())
        clases = {line.split()[0] for lines in r.labels.values() for line in lines}
        assert clases == {"0"}

    def test_deja_constancia_de_los_nombres_originales(self):
        r = convert_split(_coco())
        assert r.merged_from["Placa"] == 2
        assert r.merged_from["placa"] == 2

    def test_imagen_sin_cajas_queda_como_fondo(self):
        """YOLO usa las imágenes sin etiquetas como ejemplos negativos."""
        r = convert_split(_coco())
        assert r.labels["vacia.jpg"] == []

    def test_cuenta_cajas_descartadas(self):
        r = convert_split(_coco())
        assert r.dropped_degenerate == 1
        assert len(r.labels["b.jpg"]) == 1

    def test_registra_anchos_en_pixeles(self):
        r = convert_split(_coco())
        assert sorted(r.widths_px) == pytest.approx([60, 80, 100])

    def test_anchos_en_pixeles_de_la_imagen_real(self):
        """El JSON dice 1000x500 pero el archivo mide el doble: anchos x2."""
        reales = {"a.jpg": (2000, 1000), "b.jpg": (2000, 1000)}
        r = convert_split(_coco(), real_sizes=reales)
        assert sorted(r.widths_px) == pytest.approx([120, 160, 200])

    def test_reescalado_uniforme_no_altera_las_cajas_normalizadas(self):
        normal = convert_split(_coco())
        reescalado = convert_split(_coco(), real_sizes={"a.jpg": (2000, 1000)})
        assert normal.labels == reescalado.labels

    def test_ancho_relativo_al_lado_mayor(self):
        """Base de 'cuántos píxeles ve el modelo a imgsz=640'."""
        r = convert_split(_coco())  # imágenes 1000x500: lado mayor 1000
        assert sorted(r.widths_long_side) == pytest.approx([0.06, 0.08, 0.10])


class TestFugas:
    def test_sin_fuga(self):
        assert find_leakage(["A.rf.1.jpg"], ["B.rf.2.jpg"]) == set()

    def test_detecta_copia_aumentada(self):
        assert find_leakage(["A.rf.1.jpg"], ["A.rf.9.jpg"]) == {"A"}

    def test_detecta_recorte_de_vista_de_puerta(self):
        """Un recorte de una foto de test metido en train también es fuga."""
        assert find_leakage(["A.rf.1__c0.jpg"], ["A.rf.1.jpg"]) == {"A"}
