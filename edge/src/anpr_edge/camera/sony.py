"""
Cliente de la Sony HDR-AS100V (Camera Remote API).

La cámara crea su propia red Wi-Fi y expone JSON-RPC en
`http://192.168.122.1:10000/sony/camera`. El liveview es un stream HTTP con el
formato de paquetes de Sony:

    cabecera común (8 B)   0xFF | tipo | secuencia (2 B) | marca de tiempo ms (4 B)
    cabecera de datos (128 B)  24 35 68 79 | tamaño (3 B) | relleno (1 B) | ...
    datos (JPEG si tipo = 0x01) + relleno

Se parsean las cabeceras y se usa el tamaño declarado. El legacy buscaba los
marcadores FFD8/FFD9 en el stream, que corta mal un JPEG que contenga una miniatura
(tiene su propio FFD9 dentro). Las imágenes no se decodifican: los bytes JPEG van
tal cual a la nube.
"""

import itertools
import logging
import struct
import time
from collections.abc import Iterable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field

import httpx

log = logging.getLogger(__name__)

START_BYTE = 0xFF
TYPE_IMAGE = 0x01
TYPE_FRAME_INFO = 0x02
START_CODE = b"\x24\x35\x68\x79"
COMMON_LEN = 8
PAYLOAD_HEADER_LEN = 128
HEADER_LEN = COMMON_LEN + PAYLOAD_HEADER_LEN
MAX_DATA = 4 * 1024 * 1024  # un frame de liveview pesa decenas de KB


class CameraError(RuntimeError):
    pass


@dataclass(frozen=True)
class LiveviewFrame:
    seq: int
    timestamp_ms: int
    jpeg: bytes
    received: float = field(default_factory=time.monotonic)


def encode_packet(
    seq: int, timestamp_ms: int, data: bytes, ptype: int = TYPE_IMAGE, padding: int = 0
) -> bytes:
    """Construye un paquete. Lo usan el simulador y los tests."""
    common = struct.pack(">BBHI", START_BYTE, ptype, seq & 0xFFFF, timestamp_ms & 0xFFFFFFFF)
    header = START_CODE + len(data).to_bytes(3, "big") + bytes([padding])
    header += bytes(PAYLOAD_HEADER_LEN - len(header))
    return common + header + data + bytes(padding)


class LiveviewParser:
    """
    Parser incremental: se le dan trozos del stream en cualquier tamaño y devuelve
    los frames completos. Si pierde la sincronía (bytes basura, stream cortado a
    mitad), busca el siguiente paquete válido en vez de fallar.
    """

    def __init__(self) -> None:
        self._buf = bytearray()
        self.resyncs = 0
        self.corrupt = 0

    def feed(self, chunk: bytes) -> list[LiveviewFrame]:
        self._buf += chunk
        frames: list[LiveviewFrame] = []
        while True:
            if len(self._buf) < HEADER_LEN:
                return frames
            if self._buf[0] != START_BYTE or self._buf[COMMON_LEN : COMMON_LEN + 4] != START_CODE:
                if not self._resync():
                    return frames
                continue

            ptype, seq, ts = struct.unpack_from(">BHI", self._buf, 1)
            size = int.from_bytes(self._buf[COMMON_LEN + 4 : COMMON_LEN + 7], "big")
            padding = self._buf[COMMON_LEN + 7]
            if size > MAX_DATA:
                self._drop_first_byte_and_resync()
                continue
            total = HEADER_LEN + size + padding
            if len(self._buf) < total:
                return frames

            region = bytes(self._buf[HEADER_LEN : HEADER_LEN + size])
            del self._buf[:total]
            if ptype != TYPE_IMAGE:
                continue  # información de enfoque, no la usamos
            data = self._extract_jpeg(region)
            if data is not None:
                frames.append(LiveviewFrame(seq, ts, data))
            else:
                self.corrupt += 1

    @staticmethod
    def _extract_jpeg(region: bytes) -> bytes | None:
        """
        El tamaño declarado por la cámara real (HDR-AS100V) incluye, tras el JPEG,
        datos de enfoque de longitud variable por foto — no son relleno de ceros, así
        que `size` por sí solo no basta para cortar. Se busca el ÚLTIMO `FFD9` dentro
        de la ventana declarada: si el JPEG trae una miniatura EXIF, su propio FFD9
        queda ANTES del real y nunca es el último, así que sigue sin cortar mal con ella.
        """
        if region[:2] != b"\xff\xd8":
            return None
        end = region.rfind(b"\xff\xd9")
        return region[: end + 2] if end != -1 else None

    def _resync(self) -> bool:
        """Descarta hasta el siguiente inicio de paquete plausible."""
        self.resyncs += 1
        pos = self._buf.find(START_CODE, COMMON_LEN + 1)
        while pos != -1:
            start = pos - COMMON_LEN
            if self._buf[start] == START_BYTE:
                del self._buf[:start]
                return True
            pos = self._buf.find(START_CODE, pos + 1)
        # Sin inicio a la vista: conservar la cola por si el código llega partido.
        keep = HEADER_LEN
        if len(self._buf) > keep:
            del self._buf[:-keep]
        return False

    def _drop_first_byte_and_resync(self) -> None:
        del self._buf[:1]
        self._resync()


def jpeg_size(jpeg: bytes) -> tuple[int, int] | None:
    """(ancho, alto) leyendo el marcador SOF, sin decodificar la imagen."""
    i = 2
    while i + 9 < len(jpeg):
        if jpeg[i] != 0xFF:
            return None
        marker = jpeg[i + 1]
        if marker in (0xD8, 0x01) or 0xD0 <= marker <= 0xD7:
            i += 2
            continue
        length = int.from_bytes(jpeg[i + 2 : i + 4], "big")
        if 0xC0 <= marker <= 0xCF and marker not in (0xC4, 0xC8, 0xCC):
            h = int.from_bytes(jpeg[i + 5 : i + 7], "big")
            w = int.from_bytes(jpeg[i + 7 : i + 9], "big")
            return w, h
        i += 2 + length
    return None


class SonyCamera:
    def __init__(
        self, rpc_url: str, timeout_s: float = 5.0, client: httpx.Client | None = None
    ) -> None:
        self.rpc_url = rpc_url
        self.timeout_s = timeout_s
        self._client = client or httpx.Client()
        self._ids = itertools.count(1)

    def close(self) -> None:
        self._client.close()

    def call(self, method: str, params: list | None = None, version: str = "1.0") -> list:
        payload = {
            "method": method,
            "params": params or [],
            "id": next(self._ids),
            "version": version,
        }
        try:
            r = self._client.post(self.rpc_url, json=payload, timeout=self.timeout_s)
            r.raise_for_status()
            data = r.json()
        except (httpx.HTTPError, ValueError) as e:
            raise CameraError(f"{method}: {e}") from e
        if "error" in data:
            raise CameraError(f"{method}: {data['error']}")
        return data.get("result", [])

    def available_apis(self) -> list[str]:
        return self.call("getAvailableApiList")[0]

    def start_liveview(self, size: str = "M") -> str:
        """Devuelve la URL del stream. Activa el modo de grabación si la cámara lo pide."""
        apis = self.available_apis()
        # Solo si el liveview aún no está disponible: cambiar de modo cuesta ~1 s.
        if "startLiveview" not in apis and "startRecMode" in apis:
            self.call("startRecMode")
            time.sleep(1)  # la cámara tarda en cambiar de modo; sin esto falla el siguiente paso
            apis = self.available_apis()
        if "startLiveviewWithSize" in apis:
            return self.call("startLiveviewWithSize", [size])[0]
        return self.call("startLiveview")[0]

    def stop_liveview(self) -> None:
        """
        Siempre tras usar el liveview. El legacy nunca lo llamaba y la cámara acababa
        sin sesiones libres.
        """
        try:
            self.call("stopLiveview")
        except CameraError as e:
            log.warning("stopLiveview falló: %s", e)

    @contextmanager
    def stream(self, url: str, read_timeout_s: float) -> Iterator[Iterable[bytes]]:
        """Bytes crudos del liveview. Si no llega nada en `read_timeout_s`, lanza CameraError."""
        timeout = httpx.Timeout(self.timeout_s, read=read_timeout_s)
        try:
            with self._client.stream("GET", url, timeout=timeout) as r:
                r.raise_for_status()
                yield r.iter_bytes()
        except httpx.HTTPError as e:
            raise CameraError(f"liveview: {e}") from e

    def frames(self, url: str, read_timeout_s: float) -> Iterator[LiveviewFrame]:
        parser = LiveviewParser()
        with self.stream(url, read_timeout_s) as chunks:
            for chunk in chunks:
                yield from parser.feed(chunk)
