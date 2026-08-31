"""Adapter that turns a ``FauxProvider`` into a ``goal_loop`` ``Maker``."""

from __future__ import annotations

from faux_provider.provider import FauxProvider
from goal_loop.models import GoalSpec, LoopState, MakerOutput


class FauxMaker:
    """A maker whose LLM replies are scripted by a ``FauxProvider``.

    Each call forwards the runner's anti-drift ``steering`` prompt to the provider
    and converts the scripted reply into a ``MakerOutput``. ``tokens_used`` is
    estimated from the reply length (input is deliberately not double-counted); it
    is not a real tokenizer count.
    """

    def __init__(
        self,
        provider: FauxProvider,
        *,
        modified_files: list[str] | None = None,
    ) -> None:
        self.provider = provider
        self._modified_files = list(modified_files or [])

    def __call__(self, spec: GoalSpec, state: LoopState, steering: str) -> MakerOutput:
        response = self.provider.generate(steering, context=steering, state=state)
        return MakerOutput(
            summary=response,
            modified_files=list(self._modified_files),
            tokens_used=len(response),
        )
