"""
Antirrebote por tiempo, con plazos distintos para cada sentido.

Para las señales de seguridad se usa asimétrico: pasar a la situación peligrosa es
inmediato (plazo 0) y volver a la segura exige que se mantenga estable. Un rebote
nunca retrasa una parada, y nunca adelanta un arranque.
"""


class Debouncer:
    def __init__(self, initial: bool, hold_on_s: float, hold_off_s: float | None = None) -> None:
        """`hold_on_s`: tiempo estable para pasar a True; `hold_off_s`: para pasar a False."""
        self.value = initial
        self.hold_on_s = hold_on_s
        self.hold_off_s = hold_on_s if hold_off_s is None else hold_off_s
        self._since: float | None = None

    def update(self, raw: bool, now: float) -> bool:
        """Devuelve True si el valor estable cambió en esta llamada."""
        if raw == self.value:
            self._since = None
            return False
        if self._since is None:
            self._since = now
        hold = self.hold_on_s if raw else self.hold_off_s
        if now - self._since >= hold:
            self.value, self._since = raw, None
            return True
        return False
