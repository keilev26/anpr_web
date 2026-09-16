"""
Post-procesado del texto que devuelve el OCR.

Aquí vive la diferencia entre "el OCR leyó algo" y "tenemos una placa fiable".
El pipeline del legacy (`legacy/mqtt-camara-main/mqtt+camara.py`) perdía lecturas
correctas por dos motivos que este módulo corrige, y además no aprovechaba la
estructura conocida de una placa peruana para desambiguar.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# Mismo patrón canónico que contracts/openapi.yaml y que la API.
# Solo vehículo particular: ver contracts/plate-format.md. Al ampliar hay que
# revisar _fix_by_position(), que asume la estructura LLD-DDD para corregir.
PLATE_RE = re.compile(r"^[A-Z][A-Z0-9]{2}-\d{3}$")

_NON_ALNUM = re.compile(r"[^A-Za-z0-9]")

# Confusiones típicas de OCR en caracteres de placa.
# Se aplican SEGÚN LA POSICIÓN: una placa peruana es LLL-DDD (con el 2.º y 3.º
# admitiendo dígito), así que en las tres últimas posiciones una "O" solo puede
# ser un "0", y en la primera un "0" solo puede ser una "O".
_TO_DIGIT = str.maketrans({"O": "0", "Q": "0", "D": "0",
                           "I": "1", "L": "1", "T": "1",
                           "Z": "2", "E": "3", "A": "4",
                           "S": "5", "G": "6", "B": "8"})

_TO_LETTER = str.maketrans({"0": "O", "1": "I", "2": "Z",
                            "5": "S", "6": "G", "8": "B"})

MAX_CORRECTIONS = 2
"""
Tope de correcciones posicionales por lectura.

Cada corrección es una conjetura. A partir de tres, la "placa" es más invención
nuestra que lectura del OCR, y esto gobierna una puerta: una lectura inventada
que por casualidad coincida con la lista blanca abre al vehículo equivocado.
Mejor devolver "no legible" y que el operador lo resuelva.
"""


@dataclass(slots=True)
class PlateCandidate:
    """Resultado de interpretar una lectura del OCR."""

    raw: str
    """Lo que devolvió el OCR, sin tocar. Se conserva para poder auditar fallos."""

    plate: str | None = None
    """Placa en formato canónico, o None si no se pudo interpretar."""

    valid: bool = False
    corrections: list[str] = field(default_factory=list)
    """Correcciones posicionales aplicadas, p. ej. ['pos5: O->0']."""

    @property
    def was_corrected(self) -> bool:
        return bool(self.corrections)


def _strip(raw: str) -> str:
    return _NON_ALNUM.sub("", raw).upper()


def _fix_by_position(core: str) -> tuple[str, list[str]]:
    """
    Corrige usando la estructura conocida LLD-DDD.

    Posición 0      -> debe ser letra
    Posiciones 1-2  -> letra o dígito (se dejan como están)
    Posiciones 3-5  -> deben ser dígitos
    """
    chars = list(core)
    fixes: list[str] = []

    if chars[0].isdigit():
        nuevo = chars[0].translate(_TO_LETTER)
        if nuevo != chars[0]:
            fixes.append(f"pos1: {chars[0]}->{nuevo}")
            chars[0] = nuevo

    for i in (3, 4, 5):
        if chars[i].isalpha():
            nuevo = chars[i].translate(_TO_DIGIT)
            if nuevo != chars[i]:
                fixes.append(f"pos{i + 1}: {chars[i]}->{nuevo}")
                chars[i] = nuevo

    return "".join(chars), fixes


def parse_plate(raw: str) -> PlateCandidate:
    """
    Interpreta una lectura del OCR y devuelve siempre un PlateCandidate.

    Nunca lanza ni devuelve None a secas: una lectura fallida también es
    información, y hay que poder registrarla para medir la tasa real de acierto.

    Dos correcciones frente al pipeline del legacy:

    1. El legacy filtraba con `^.{7}$`, exigiendo exactamente 7 caracteres. Si
       el OCR leía "ABC123" sin guion (6 caracteres), DESCARTABA una placa
       correcta. Aquí se normaliza a 6 alfanuméricos y se reinserta el guion.

    2. `run_ocr_logic` devolvía `candidates[0]` como respaldo, pero quien la
       llamaba revalidaba con el patrón, así que ese respaldo SIEMPRE se
       descartaba: código muerto que además ocultaba los fallos. Aquí la lectura
       no válida se devuelve con `valid=False` y su `raw` intacto.
    """
    core = _strip(raw)

    if len(core) != 6:
        return PlateCandidate(raw=raw)

    # Si el prefijo no tiene NI UNA letra real, no estábamos leyendo una placa:
    # toda placa peruana empieza por letra, y seis dígitos seguidos suelen ser
    # otra cosa del vehículo (un teléfono rotulado, una fecha, un número de
    # unidad). Sin esta regla, "123456" se "corregiría" a "I23-456".
    if not any(c.isalpha() for c in core[:3]):
        return PlateCandidate(raw=raw)

    fixed, fixes = _fix_by_position(core)

    if len(fixes) > MAX_CORRECTIONS:
        return PlateCandidate(raw=raw, corrections=fixes)

    plate = f"{fixed[:3]}-{fixed[3:]}"
    if not PLATE_RE.match(plate):
        return PlateCandidate(raw=raw, corrections=fixes)

    return PlateCandidate(raw=raw, plate=plate, valid=True, corrections=fixes)


def best_plate(readings: list[tuple[str, float]]) -> PlateCandidate | None:
    """
    Elige la mejor lectura entre varias.

    Recibe (texto, confianza) de todos los recortes de la ráfaga. Prefiere, en
    este orden: válida sin correcciones > válida con correcciones > la de mayor
    confianza aunque no sea válida.

    Preferir la no corregida importa: una corrección posicional es una conjetura,
    y ante dos lecturas válidas conviene la que no necesitó adivinar.
    """
    if not readings:
        return None

    candidates = [(parse_plate(text), conf) for text, conf in readings]

    def rank(item: tuple[PlateCandidate, float]) -> tuple[int, int, float]:
        cand, conf = item
        return (int(cand.valid), int(not cand.was_corrected), conf)

    best, _ = max(candidates, key=rank)
    return best
