"""Versioned security constitution (CSDD spec).

A constitution is the explicit, hash-addressable form of the safety boundary S.
Each principle maps to a REAL file under ``src/`` (its ``anchor``) plus the
``pattern`` that must be present and the ``violations`` sentinel that must NOT be
present. The digest is a stable content hash so the gate can pin the ruler.

Authoring rule: no invented security domains. Every ``anchor`` must resolve to a
real source file that actually contains ``pattern`` (see the meta-test).
"""

from __future__ import annotations

import hashlib
import tomllib
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class Principle:
    id: str
    boundary: str
    cwe: str
    level: str  # MUST / SHOULD / MAY
    constraint: str
    anchor: str
    pattern: str
    violations: str
    rationale: str


@dataclass(frozen=True, slots=True)
class Constitution:
    version: str
    principles: tuple[Principle, ...]

    def digest(self) -> str:
        """Stable content hash — the 'ruler' signature the gate pins."""
        payload = (self.version, *[p.id for p in sorted(self.principles, key=lambda p: p.id)])
        return hashlib.sha256(repr(payload).encode("utf-8")).hexdigest()


DEFAULT_CONSTITUTION = Path(__file__).resolve().parent / "constitution.toml"


def load_constitution(path: Path) -> Constitution:
    with path.open("rb") as f:
        data = tomllib.load(f)
    return _from_payload(data)


def _from_payload(data: dict) -> Constitution:
    return Constitution(
        version=str(data["version"]),
        principles=tuple(
            Principle(**{k: str(v) for k, v in p.items()}) for p in data["principles"]
        ),
    )
