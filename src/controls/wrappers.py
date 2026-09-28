"""Serve wrapper controls through the existing eval gateway."""

from __future__ import annotations

from src.controls.errors import ControlError
from src.controls.suppression import SuppressionPort
from src.eval.gateway import Gateway
from src.eval.types import Probe

_UNSERVED = frozenset({"targeted_damage", "broad_destruction", "untouched"})


class ControlArtifact:
    """The model port an evaluator may hold. The parent port is not exposed."""

    def __init__(self, family: str, port: SuppressionPort | None) -> None:
        self.family = family
        self._port = port

    def underlying(self) -> None:
        """Refuse a direct call to the parent model."""
        raise ControlError("underlying")

    def complete(self, probe: Probe) -> str:
        """Enabled suppression text. Gateway charges this call."""
        if self._port is None:
            raise ControlError(self.family)
        return self._port.complete(probe)

    def score_candidate(self, probe: Probe) -> dict[str, float]:
        """Enabled scores. Gateway charges this call."""
        if self._port is None:
            raise ControlError(self.family)
        return self._port.score_candidate(probe)

    @property
    def vector_applied(self) -> bool:
        """True after an enabled steering completion."""
        if self._port is None:
            return False
        return self._port.vector_applied


def serve(
    artifact: ControlArtifact,
    gateway: Gateway,
    probe: Probe,
    channel_id: str,
    *,
    score: bool = False,
) -> str | dict[str, float]:
    """One evaluator query. Charging stays in the gateway."""
    if artifact.family in _UNSERVED:
        raise ControlError(artifact.family)
    if score:
        return gateway.score(probe, channel_id)
    return gateway.complete(probe, channel_id)
