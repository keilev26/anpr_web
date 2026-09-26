"""
anpr-capture: mantiene el liveview de la Sony y convierte cada disparo en una ráfaga.

Un hilo lee el liveview de forma continua y guarda los últimos segundos en memoria.
Así, al llegar un disparo, las fotos se toman al instante, sin esperar el ~1 s que
tarda la cámara en arrancar el liveview.

Si la cámara deja de enviar frames, el hilo cierra la sesión (`stopLiveview`, la
fuga del legacy) y reconecta con espera creciente. El servicio nunca muere por la
cámara: publica `camera/status` y `anpr-health` lo ve.
"""

import logging
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from uuid import UUID

from anpr_edge.camera.sony import CameraError, LiveviewFrame, LiveviewParser, SonyCamera
from anpr_edge.common import spool
from anpr_edge.common.bus import Bus
from anpr_edge.common.config import CameraConfig, CaptureConfig, EdgeConfig
from anpr_edge.common.messages import CameraStatus, Fault, FramesReady, Message, Trigger, utcnow
from anpr_edge.common.service import Service

MIN_FRAMES = 3  # contrato A
STATUS_EVERY_S = 5.0


class FrameBuffer:
    """Frames recientes, con acceso seguro entre el hilo de la cámara y el principal."""

    def __init__(self, max_age_s: float) -> None:
        self.max_age_s = max_age_s
        self._frames: deque[LiveviewFrame] = deque()
        self._lock = threading.Lock()

    def add(self, frame: LiveviewFrame) -> None:
        with self._lock:
            self._frames.append(frame)
            while self._frames and frame.received - self._frames[0].received > self.max_age_s:
                self._frames.popleft()

    def after(self, t: float) -> list[LiveviewFrame]:
        with self._lock:
            return [f for f in self._frames if f.received > t]

    def last_received(self) -> float | None:
        with self._lock:
            return self._frames[-1].received if self._frames else None

    def fps(self) -> float | None:
        with self._lock:
            if len(self._frames) < 2:
                return None
            span = self._frames[-1].received - self._frames[0].received
            return round((len(self._frames) - 1) / span, 1) if span > 0 else None


class CameraWorker(threading.Thread):
    def __init__(
        self, cam: SonyCamera, cfg: CameraConfig, buffer: FrameBuffer, log: logging.Logger
    ) -> None:
        super().__init__(name="camara", daemon=True)
        self.cam, self.cfg, self.buffer, self.log = cam, cfg, buffer, log
        self._halt = threading.Event()

    def stop(self) -> None:
        self._halt.set()

    def run(self) -> None:
        backoff = 1.0
        while not self._halt.is_set():
            got_frames = self._session()
            if got_frames:
                backoff = 1.0
            self._halt.wait(backoff)
            backoff = min(backoff * 2, 10.0)

    def _session(self) -> bool:
        """Una sesión de liveview, de principio a fin. Devuelve si llegó algún frame."""
        opened, got = False, False
        try:
            url = self.cam.start_liveview(self.cfg.liveview_size)
            opened = True
            self.log.info("Liveview iniciado")
            parser = LiveviewParser()
            last = time.monotonic()
            with self.cam.stream(url, read_timeout_s=self.cfg.stale_after_s) as chunks:
                for chunk in chunks:
                    for frame in parser.feed(chunk):
                        self.buffer.add(frame)
                        last, got = frame.received, True
                    if self._halt.is_set():
                        return got
                    # Llegan bytes pero no frames válidos: también es una cámara colgada.
                    if time.monotonic() - last > self.cfg.stale_after_s:
                        raise CameraError("sin frames válidos")
            raise CameraError("el stream terminó")
        except CameraError as e:
            self.log.warning("Cámara: %s; reconectando", e)
        except Exception:
            self.log.exception("Error inesperado leyendo la cámara")
        finally:
            if opened:
                self.cam.stop_liveview()
        return got


@dataclass
class Burst:
    event_id: UUID
    started: float
    picked: list[LiveviewFrame] = field(default_factory=list)


def trim_to_size(frames: list[bytes], max_bytes: int) -> list[bytes]:
    """Quita fotos del final hasta caber; nunca por debajo del mínimo del contrato."""
    frames = list(frames)
    while len(frames) > MIN_FRAMES and sum(map(len, frames)) > max_bytes:
        frames.pop()
    return frames


class CaptureService(Service):
    def __init__(
        self,
        cfg: CaptureConfig,
        buffer: FrameBuffer,
        bus: Bus,
        log: logging.Logger,
        worker: CameraWorker | None = None,
        stale_after_s: float = 3.0,
    ) -> None:
        super().__init__(bus, log)
        self.cfg, self.buffer, self.worker = cfg, buffer, worker
        self.stale_after_s = stale_after_s
        self.bursts: dict[UUID, Burst] = {}
        self._last_status = 0.0

    def on_start(self) -> None:
        self.bus.subscribe(Trigger)
        if self.worker:
            self.worker.start()

    def on_stop(self) -> None:
        if self.worker:
            self.worker.stop()
            self.worker.join(timeout=10)  # su finally cierra la sesión de la cámara

    def on_message(self, msg: Message) -> None:
        if not isinstance(msg, Trigger):
            return
        age = (utcnow() - msg.ts).total_seconds()
        if age > self.cfg.trigger_max_age_s:
            self.log.warning(
                "Disparo viejo ignorado",
                extra={"event_id": str(msg.event_id), "age_s": round(age, 2)},
            )
            return
        if msg.event_id in self.bursts:
            return  # duplicado (QoS 1 puede entregar dos veces)
        self.bursts[msg.event_id] = Burst(msg.event_id, time.monotonic())
        self.log.info("Disparo", extra={"event_id": str(msg.event_id)})

    def on_tick(self, now: float) -> None:
        spacing = self.cfg.spacing_ms / 1000
        for burst in list(self.bursts.values()):
            since = burst.picked[-1].received if burst.picked else burst.started
            for f in self.buffer.after(since):
                if not burst.picked or f.received - burst.picked[-1].received >= spacing:
                    burst.picked.append(f)
                if len(burst.picked) == self.cfg.frames:
                    break
            if len(burst.picked) >= self.cfg.frames:
                self._finish(burst)
            elif now - burst.started > self.cfg.timeout_s:
                if len(burst.picked) >= MIN_FRAMES:
                    self._finish(burst)
                else:
                    self._fail(burst)
        if now - self._last_status >= STATUS_EVERY_S:
            self._publish_status(now)
            self._last_status = now

    def _finish(self, burst: Burst) -> None:
        del self.bursts[burst.event_id]
        frames = trim_to_size([f.jpeg for f in burst.picked], self.cfg.max_burst_bytes)
        if sum(map(len, frames)) > self.cfg.max_burst_bytes:
            self._fault("burst_too_large", f"{len(frames)} fotos superan el límite", burst)
            return
        age = time.monotonic() - burst.picked[0].received
        captured_at = datetime.now(UTC) - timedelta(seconds=age)
        path = spool.write_event(
            self.cfg.spool_dir,
            burst.event_id,
            frames,
            {
                "event_id": str(burst.event_id),
                "captured_at": captured_at.isoformat(),
                "seqs": [f.seq for f in burst.picked[: len(frames)]],
            },
        )
        self.bus.publish(
            FramesReady(
                event_id=burst.event_id, path=str(path), count=len(frames), captured_at=captured_at
            )
        )
        self.log.info(
            "Ráfaga lista", extra={"event_id": str(burst.event_id), "frames": len(frames)}
        )

    def _fail(self, burst: Burst) -> None:
        del self.bursts[burst.event_id]
        self._fault(
            "camera_unavailable", f"Solo {len(burst.picked)} fotos en {self.cfg.timeout_s} s", burst
        )

    def _fault(self, code: str, detail: str, burst: Burst) -> None:
        self.log.error(detail, extra={"event_id": str(burst.event_id), "code": code})
        self.bus.publish(
            Fault(code=code, detail=f"{detail} (evento {burst.event_id})", ts=utcnow())
        )

    def _publish_status(self, now: float) -> None:
        last = self.buffer.last_received()
        age = round(now - last, 1) if last is not None else None
        online = age is not None and age < self.stale_after_s
        self.bus.publish(
            CameraStatus(
                online=online,
                fps=self.buffer.fps() if online else None,
                last_frame_age_s=age,
                ts=utcnow(),
            ),
            retain=True,
        )


def build(cfg: EdgeConfig, bus: Bus, log: logging.Logger) -> CaptureService:
    buffer = FrameBuffer(cfg.capture.buffer_s)
    cam = SonyCamera(cfg.camera.rpc_url, cfg.camera.timeout_s)
    worker = CameraWorker(cam, cfg.camera, buffer, log)
    return CaptureService(cfg.capture, buffer, bus, log, worker, cfg.camera.stale_after_s)


def main() -> None:
    from anpr_edge.common.runner import run

    run("capture", build)
