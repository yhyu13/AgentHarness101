"""The external anchor for the ruler (spec §A2).

Lock 6 compares the loaded constitution's digest against a pinned digest. If that
pin is computed from the same constitution object — ``pinned = constitution.digest()``
— the comparison is a tautology: a tampered ruler always matches itself. The pin
therefore has to come from outside the graded process: an environment variable set
by the operator, or a checked-in constant file. Editing ``constitution.toml`` alone
is no longer enough to launder a weakening.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from pathlib import Path

PIN_PATH = Path(__file__).resolve().parent / "constitution.pin"
ENV_VAR = "AH_CONSTITUTION_PIN"


def read_pin(
    path: Path | None = None,
    env: Mapping[str, str] | None = None,
) -> str | None:
    """The externally-held expected digest, or ``None`` when unpinned.

    Precedence: environment variable, then the checked-in pin file. ``None`` means
    "no pin configured" and reproduces today's behaviour (no Lock-6 veto).
    """
    source = os.environ if env is None else env
    from_env = source.get(ENV_VAR, "").strip()
    if from_env:
        return from_env
    pin_file = PIN_PATH if path is None else Path(path)
    if pin_file.exists():
        text = pin_file.read_text(encoding="utf-8").strip()
        return text or None
    return None
