import random

import pytest

from anpr_ml.crops import CropParams, CropResult, plan_crop

W, H = 3000, 4000
P = CropParams()


def placa(cx=1500, cy=2000, w=130, h=60):
    return (cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2)


def plan(boxes, target=0, seed=0, params=P, size=(W, H)):
    return plan_crop(size[0], size[1], boxes, target, random.Random(seed), params)


def test_placa_tipica_produce_recorte():
    r = plan([placa()])
    assert isinstance(r, CropResult)


@pytest.mark.parametrize("seed", range(30))
def test_placa_queda_en_el_rango_de_tamano(seed):
    r = plan([placa()], seed=seed)
    assert isinstance(r, CropResult)
    assert P.plate_px_min <= r.plate_px_out <= P.plate_px_max * 1.001


@pytest.mark.parametrize("seed", range(30))
def test_nunca_amplia_mas_de_dos_veces(seed):
    r = plan([placa(w=45)], seed=seed)
    if isinstance(r, CropResult):
        assert r.scale <= P.max_upscale + 1e-9


def test_rechaza_placa_estrecha_en_origen():
    """Ampliarla la haría grande pero borrosa: no simula ninguna cámara real."""
    assert isinstance(plan([placa(w=30)]), str)


def test_rechaza_si_no_llega_al_minimo_sin_ampliar_de_mas():
    # 42 px nativos x 2 de ampliación máxima = 84: justo pasa
    assert isinstance(plan([placa(w=42)]), CropResult)
    # con ampliación máxima 1.5 no llega a 80
    assert isinstance(plan([placa(w=42)], params=CropParams(max_upscale=1.5)), str)


@pytest.mark.parametrize("seed", range(20))
def test_ventana_dentro_de_la_imagen(seed):
    # placa pegada a una esquina: la ventana debe desplazarse, no salirse
    r = plan([placa(cx=80, cy=40)], seed=seed)
    assert isinstance(r, CropResult)
    x1, y1, x2, y2 = r.window
    assert x1 >= 0 and y1 >= 0 and x2 <= W + 1e-6 and y2 <= H + 1e-6


@pytest.mark.parametrize("seed", range(20))
def test_etiquetas_normalizadas_y_placa_objetivo_presente(seed):
    r = plan([placa()], seed=seed)
    assert isinstance(r, CropResult) and len(r.labels) == 1
    cx, cy, w, h = r.labels[0]
    assert cx - w / 2 >= 0 and cx + w / 2 <= 1 + 1e-9
    assert cy - h / 2 >= 0 and cy + h / 2 <= 1 + 1e-9


def test_la_proporcion_de_salida_es_horizontal():
    r = plan([placa()])
    assert isinstance(r, CropResult)
    x1, y1, x2, y2 = r.window
    assert (x2 - x1) / (y2 - y1) == pytest.approx(P.aspect)


def test_conserva_otra_placa_completa_dentro():
    """Una cola de autos es realista; la segunda placa debe quedar etiquetada."""
    boxes = [placa(), placa(cx=1500 + 150, cy=2000 + 40)]
    r = plan(boxes, params=CropParams(plate_px_min=80, plate_px_max=81))
    assert isinstance(r, CropResult) and len(r.labels) == 2


def test_descarta_placa_lejana_fuera_del_recorte():
    boxes = [placa(), placa(cx=200, cy=300)]
    r = plan(boxes)
    assert isinstance(r, CropResult) and len(r.labels) == 1


def test_descarta_placa_cortada_por_el_borde():
    params = CropParams()
    boxes = [placa(), (0.0, 0.0, 100.0, 50.0)]
    r = plan_crop(W, H, boxes, 0, random.Random(0), params)
    assert isinstance(r, CropResult)
    wx1, wy1, wx2, wy2 = r.window
    # construir una placa que solo asome un 30% dentro de la ventana
    asomada = (wx2 - 30, 2000, wx2 + 70, 2040)
    r2 = plan_crop(W, H, [placa(), asomada], 0, random.Random(0), params)
    assert isinstance(r2, CropResult) and len(r2.labels) == 1


def test_determinista_con_la_misma_semilla():
    assert plan([placa()], seed=7) == plan([placa()], seed=7)


def test_imagen_pequena_no_rompe():
    r = plan([placa(cx=300, cy=200, w=120, h=50)], size=(640, 480))
    assert isinstance(r, (CropResult, str))
    if isinstance(r, CropResult):
        x1, y1, x2, y2 = r.window
        assert x2 <= 640 + 1e-6 and y2 <= 480 + 1e-6
