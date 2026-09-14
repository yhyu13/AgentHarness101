"""Versioned security constitution (CSDD spec).

A constitution is the explicit, hash-addressable form of the safety boundary S.
Each principle maps to a REAL file under ``src/`` (its ``anchor``) plus the
``pattern`` that must be present, the ``violations`` sentinel that must NOT be
present, and the ``require`` properties that must be present. The digest is a stable
content hash so the gate can pin the ruler.

Authoring rule: no invented security domains. Every ``anchor`` must resolve to a
real source file that actually contains ``pattern`` AND every ``require`` (see the
meta-tests).
"""

from __future__ import annotations

import hashlib
import tomllib
from dataclasses import dataclass, fields
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
    # Positive sentinels: the fail-closed OUTCOME the anchor must still contain. `pattern`
    # proves the guard symbol is present and `violations` proves no forbidden shape was
    # ADDED, but neither can see a tamper that only DELETES (drop the deny branch, keep the
    # symbol) — absence-detection has nothing to match on. Each entry is a regex that must
    # be found in the anchor file, so the boundary is "still enforced", not just "not
    # obviously broken". Default () keeps hand-built fixtures and the pre-`require` ruler
    # working unchanged (an empty tuple requires nothing → strictly no detection lost).
    require: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class Constitution:
    version: str
    principles: tuple[Principle, ...]

    def digest(self) -> str:
        """Stable content hash of the FULL constitution — the 'ruler' signature the gate pins.

        Covers the version AND every field of every principle (boundary/cwe/level/constraint/
        anchor/pattern/violations/rationale), not just the ids. A ruler tamper that weakens a
        ``pattern`` or ``violations`` sentinel IN PLACE (same id, same version) changes the
        digest, so Lock 6 (``禁改尺子``) vetoes it — an agent cannot silently loosen the ruler
        to score itself ``safe`` on code that actually contains a violation.
        """
        principle_fields = tuple(f.name for f in fields(Principle))
        rows = [
            tuple(getattr(p, name) for name in principle_fields)
            for p in sorted(self.principles, key=lambda p: p.id)
        ]
        payload = (self.version, *rows)
        return hashlib.sha256(repr(payload).encode("utf-8")).hexdigest()


DEFAULT_CONSTITUTION = Path(__file__).resolve().parent / "constitution.toml"


def load_constitution(path: Path) -> Constitution:
    with path.open("rb") as f:
        data = tomllib.load(f)
    return _from_payload(data)


def _from_payload(data: dict) -> Constitution:
    return Constitution(
        version=str(data["version"]),
        principles=tuple(_principle(p) for p in data["principles"]),
    )


def _principle(raw: dict) -> Principle:
    """Build one principle, fail-closed on a malformed ``require``.

    ``require`` is a LIST of regexes (TOML array). Accepting a bare string would iterate it
    character by character — every single character a "requirement" — silently turning the
    positive-property check into a no-op. Refuse it loudly instead of degrading.
    """
    require = raw.get("require", ())
    if isinstance(require, str) or not isinstance(require, (list, tuple)):
        raise ValueError(
            f"{raw.get('id', '<no id>')}: `require` must be a list of regex strings, "
            f"got {type(require).__name__}"
        )
    values = {k: str(v) for k, v in raw.items() if k != "require"}
    return Principle(**values, require=tuple(str(r) for r in require))
