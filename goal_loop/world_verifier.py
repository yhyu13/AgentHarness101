from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass(frozen=True, slots=True)
class WorldCheck:
    """One independent artifact assertion: a path plus exactly one expectation.

    ``expected`` asserts byte-identical content (utf-8), ``contains`` asserts a
    keyword is present. Exactly one of the two must be set.
    """

    path: str | Path
    expected: Optional[str] = None
    contains: Optional[str] = None

    def __post_init__(self) -> None:
        if (self.expected is None) == (self.contains is None):
            raise ValueError(
                "WorldCheck needs exactly one of 'expected' (byte-identical) "
                "or 'contains' (keyword)"
            )


@dataclass(frozen=True, slots=True)
class WorldVerificationResult:
    """Structured world evidence: what was actually observed vs what was expected.

    On failure, ``what`` / ``why`` / ``fix`` carry agent-oriented repair guidance
    (learn-harness ``lecture-10:103-111``) so a downstream agent can correct itself
    instead of guessing.
    """

    path: str
    ok: bool
    observed: str
    expected: str
    what: str = ""
    why: str = ""
    fix: str = ""


class WorldVerifier:
    """Re-read artifacts from disk and assert their content.

    This is the machine-side independent evidence channel: it trusts only the bytes
    on disk, never the maker's or checker's self-report (deepseek ``testing.md:27-29``).
    """

    def __init__(self, checks: list[WorldCheck] | None = None) -> None:
        self._checks = list(checks or [])

    def verify(
        self,
        path: str | Path,
        *,
        expected: Optional[str] = None,
        contains: Optional[str] = None,
    ) -> WorldVerificationResult:
        """Assert a single artifact's content, returning observed vs expected."""
        return _check(WorldCheck(path=path, expected=expected, contains=contains))

    def verify_all(self) -> WorldVerificationResult:
        """Run every configured check; fail-closed on the first failure."""
        for check in self._checks:
            result = _check(check)
            if not result.ok:
                return result
        return WorldVerificationResult(path="", ok=True, observed="", expected="")


def _check(check: WorldCheck) -> WorldVerificationResult:
    path = Path(check.path)
    if not path.exists():
        expectation = (
            f"byte-identical to {check.expected!r}"
            if check.expected is not None
            else f"contains {check.contains!r}"
        )
        return WorldVerificationResult(
            path=str(path),
            ok=False,
            observed="<missing>",
            expected=expectation,
            what=f"artifact {path} is missing",
            why="the file does not exist on disk, so the world does not match the report",
            fix=f"write {path} with content {expectation}",
        )

    data = path.read_bytes()

    if check.expected is not None:
        ok = data == check.expected.encode("utf-8")
        observed = data.decode("utf-8", errors="replace")
        expected = check.expected
        what = f"artifact {path} content mismatch"
        why = "byte-identical check failed: bytes on disk differ from the expected content"
        fix = f"rewrite {path} so its content is exactly {check.expected!r}"
    else:
        text = data.decode("utf-8", errors="replace")
        keyword = check.contains
        ok = keyword in text
        observed = text
        expected = f"contains {keyword!r}"
        what = f"artifact {path} is missing the keyword {keyword!r}"
        why = "keyword check failed: the expected token is absent from the file on disk"
        fix = f"rewrite {path} so it contains {keyword!r}"

    if ok:
        return WorldVerificationResult(
            path=str(path), ok=True, observed=observed, expected=expected
        )
    return WorldVerificationResult(
        path=str(path),
        ok=False,
        observed=observed,
        expected=expected,
        what=what,
        why=why,
        fix=fix,
    )
