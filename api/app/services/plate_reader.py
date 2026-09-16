from typing import Protocol


class PlateReading(Protocol):
    plate: str | None
    confidence: float | None


class PlateReader(Protocol):
    """
    Interfaz con el frente de ML (F4).

    F2 no ejecuta ningún modelo: la inferencia vive en su propio Lambda. Esta
    interfaz es la costura, para que F2 sea completo y testeable sin arrastrar
    torch ni paddleocr.
    """

    async def read(self, frames: list[bytes]) -> tuple[str | None, float | None]: ...


class StubPlateReader:
    """
    Implementación de relleno para desarrollo y pruebas.

    No lee nada: devuelve la placa que se le inyecte. F4 la sustituye por el
    cliente real del Lambda de inferencia.
    """

    def __init__(self, plate: str | None = None, confidence: float | None = None) -> None:
        self._plate = plate
        self._confidence = confidence

    async def read(self, frames: list[bytes]) -> tuple[str | None, float | None]:
        if not frames:
            return None, None
        return self._plate, self._confidence
