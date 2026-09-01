"""Filesystem write-isolation tests (P1.19).

``PathPolicy`` enforces a write allowlist at the path level: a write outside a
whitelisted root is rejected. This is the portable, cross-platform layer — real
syscall-level isolation (seccomp/Landlock, network, fork) is OS-gated and documented as
degraded on Windows, but the path check runs the same everywhere and is fully tested
here. No LLM is involved.
"""

from pathlib import Path

from sandbox import PathPolicy


class TestPathPolicy:
    def test_write_within_root_is_allowed(self, tmp_path: Path) -> None:
        policy = PathPolicy([tmp_path / "out"])
        assert policy.allows_write(tmp_path / "out" / "a.txt")
        assert policy.allows_write(tmp_path / "out" / "nested" / "b.py")

    def test_write_outside_root_is_rejected(self, tmp_path: Path) -> None:
        policy = PathPolicy([tmp_path / "out"])
        assert not policy.allows_write(tmp_path / "other" / "a.txt")

    def test_path_traversal_escape_is_rejected(self, tmp_path: Path) -> None:
        root = tmp_path / "out"
        policy = PathPolicy([root])
        # ".." escapes the allowlisted root; resolve() collapses it before the check.
        assert not policy.allows_write(root / ".." / "secret.txt")

    def test_empty_allowlist_fails_closed(self, tmp_path: Path) -> None:
        policy = PathPolicy([])
        assert not policy.allows_write(tmp_path / "anything" / "x.txt")

    def test_multiple_roots_are_union(self, tmp_path: Path) -> None:
        policy = PathPolicy([tmp_path / "a", tmp_path / "b"])
        assert policy.allows_write(tmp_path / "a" / "1.txt")
        assert policy.allows_write(tmp_path / "b" / "2.txt")
        assert not policy.allows_write(tmp_path / "c" / "3.txt")
