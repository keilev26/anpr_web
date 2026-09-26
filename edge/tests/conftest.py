import queue

import pytest


class FakeBus:
    """Bus en memoria: lo publicado queda en `published`; lo recibido se pone en `inbox`."""

    def __init__(self) -> None:
        self.inbox: queue.Queue = queue.Queue()
        self.published: list = []
        self.subscribed: list = []
        self.connected = True

    def subscribe(self, model, topic=None) -> None:
        self.subscribed.append(topic or model.TOPIC)

    def publish(self, msg, retain: bool = False, topic=None) -> bool:
        self.published.append(msg)
        return True

    def of(self, model) -> list:
        return [m for m in self.published if isinstance(m, model)]

    def start(self) -> None: ...

    def stop(self) -> None: ...


@pytest.fixture
def bus() -> FakeBus:
    return FakeBus()
