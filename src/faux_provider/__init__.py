"""Deterministic faux provider for testing the goal loop against a scripted LLM.

Replaces exactly one boundary — what the LLM says — and leaves the loop state
machine, verifier, sandbox, trace, and hippocampus running for real.
"""

from faux_provider.maker import FauxMaker
from faux_provider.provider import (
    FauxProvider,
    FauxProviderExhausted,
    FauxResponseFactory,
    FauxResponseStep,
)

__all__ = [
    "FauxMaker",
    "FauxProvider",
    "FauxProviderExhausted",
    "FauxResponseFactory",
    "FauxResponseStep",
]
