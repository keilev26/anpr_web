import pytest
from pydantic import BaseModel, ValidationError

from app.schemas.common import Plate, normalize_plate


class Holder(BaseModel):
    plate: Plate


@pytest.mark.parametrize(
    ("entrada", "esperada"),
    [
        ("CUB-604", "CUB-604"),
        ("cub-604", "CUB-604"),
        ("cub604", "CUB-604"),       # el OCR omite el guion
        ("CUB 604", "CUB-604"),      # espacio en vez de guion
        (" cub-604 ", "CUB-604"),
        ("c u b 6 0 4", "CUB-604"),
        ("V1A-882", "V1A-882"),      # segundo carácter numérico, válido en Perú
    ],
)
def test_normaliza_variantes(entrada, esperada):
    assert Holder(plate=entrada).plate == esperada


@pytest.mark.parametrize("malo", ["", "AB-123", "ABCD-1234", "1BC-604", "ABC-12A", "@@@-999"])
def test_rechaza_invalidas(malo):
    with pytest.raises(ValidationError):
        Holder(plate=malo)


def test_normalizacion_es_idempotente():
    assert normalize_plate(normalize_plate("cub604")) == "CUB-604"
