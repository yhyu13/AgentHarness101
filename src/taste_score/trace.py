"""Static traceability verifier (CSDD spec + paper L7).

This is the anti-self-report resolver: instead of trusting an agent's claimed
``did_expand``/``safe``, it derives them from real evidence in ``src/``. Each
constitution principle maps to an ``anchor`` file (with a ``pattern`` that must be
present and a ``violations`` sentinel that must be absent). Deterministic, no LLM.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

from taste_score.constitution import Constitution, Principle
from taste_score.models import Probe, ProbeRun


# Sentinel for "a helper could NOT be proven to always return one constant". Distinct from any
# real value, so `is not` identity works and no constant literal can collide with it.
_NON_CONSTANT: object = object()


def _body_is_placeholder(body: list[ast.stmt]) -> bool:
    """True iff a def/class body is only a docstring/``pass``/``...`` — no real logic.

    Recursive: a statement that is itself a nested def/class whose body is a placeholder is
    itself a placeholder. This is what lets the verifier refuse a dead shell hidden inside an
    unused wrapper (``def _unused(): class Guard: pass``), which a top-level-only check would
    miss.
    """
    stmts = list(body)
    if (
        stmts
        and isinstance(stmts[0], ast.Expr)
        and isinstance(stmts[0].value, ast.Constant)
        and isinstance(stmts[0].value.value, str)
    ):
        stmts = stmts[1:]  # drop the docstring
    return all(_stmt_is_placeholder(s) for s in stmts)


def _stmt_is_placeholder(s: ast.stmt) -> bool:
    """True iff a top-level statement implements nothing: a shell def/class, a bare
    ``pass``, a docstring/``...``, or an import (imports alone are not a guard)."""
    if isinstance(s, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
        return _body_is_placeholder(s.body)
    if isinstance(s, ast.Pass):
        return True
    if isinstance(s, ast.Expr) and isinstance(s.value, ast.Constant):
        return True  # module docstring / ellipsis
    if isinstance(s, (ast.Import, ast.ImportFrom)):
        return True
    return False


def _is_dead_stub(text: str) -> bool:
    """True iff a module is only a placeholder shell: a dead ``class X: pass``, a bare
    docstring, or a comment-only/empty module. A guard symbol can be *present* yet carry no
    logic — the naive regex counts that as an expansion, the hardened verifier must not.
    Returns False on unparseable input so a real (valid) source file is never rejected."""
    try:
        tree = ast.parse(text)
    except (SyntaxError, ValueError, TypeError):
        return False
    if not tree.body:
        return True  # empty / comment-only module -> no guard implemented
    return all(_stmt_is_placeholder(s) for s in tree.body)


def _find_method(
    class_def: ast.ClassDef, name: str
) -> ast.FunctionDef | ast.AsyncFunctionDef | None:
    """The method ``name`` defined directly on ``class_def``, or ``None``."""
    for stmt in class_def.body:
        if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)) and stmt.name == name:
            return stmt
    return None


def _resolve_callable_constant(
    fn: ast.FunctionDef | ast.AsyncFunctionDef,
    env: dict[str, object],
    helpers: dict[str, object],
    sources: dict[str, ast.FunctionDef | ast.AsyncFunctionDef],
    resolving: frozenset[str],
    classes: dict[str, ast.ClassDef],
    current_class: ast.ClassDef | None,
    key: str,
) -> object:
    """The single constant value a function/method always-returns, or ``_NON_CONSTANT``.

    A callable is pure-constant iff it has at least one ``return`` and EVERY return resolves to the
    same constant (which may itself flow through another pure-constant callable or a constant NAME).
    A callable that returns a non-constant (a decision on state) or is in a recursion cycle is
    ``_NON_CONSTANT``. ``key`` is the identity used for cycle-detection; ``current_class`` is the
    class a method is defined on (so a ``self._helper()`` call inside it can be traced)."""
    if fn is None:
        return _NON_CONSTANT
    if key in resolving:
        return _NON_CONSTANT  # recursion cycle -> cannot prove a constant
    resolving = resolving | {key}
    returns = _collect_returns_of(fn)
    if not returns:
        return _NON_CONSTANT
    seen = []
    for r in returns:
        ok, k = _resolve_literal_key(
            r.value, env, helpers, sources, resolving, classes, current_class
        )
        if not ok:
            return _NON_CONSTANT
        seen.append(repr(k))
    if len(set(seen)) != 1:
        return _NON_CONSTANT
    ok, val = _resolve_literal_key(
        returns[0].value, env, helpers, sources, resolving, classes, current_class
    )
    return val if ok else _NON_CONSTANT


def _resolve_module_function_value(
    name: str,
    env: dict[str, object],
    helpers: dict[str, object] | None,
    sources: dict[str, ast.FunctionDef | ast.AsyncFunctionDef],
    resolving: frozenset[str],
    classes: dict[str, ast.ClassDef],
    current_class: ast.ClassDef | None,
) -> object:
    """The single constant a module-level helper always-returns, memoised in ``helpers``, or
    ``_NON_CONSTANT`` if the name is not a top-level function or its value is not a constant."""
    if helpers is not None and name in helpers:
        return helpers[name]
    fn = sources.get(name)
    if fn is None:
        return _NON_CONSTANT
    val = _resolve_callable_constant(
        fn, env, helpers, sources, resolving, classes, current_class, name
    )
    if helpers is not None:
        helpers[name] = val
    return val


def _resolve_method_constant(
    class_def: ast.ClassDef,
    method_name: str,
    env: dict[str, object],
    helpers: dict[str, object] | None,
    sources: dict[str, ast.FunctionDef | ast.AsyncFunctionDef],
    resolving: frozenset[str],
    classes: dict[str, ast.ClassDef],
    current_class: ast.ClassDef | None,
) -> object:
    """The single constant a bound method always-returns, or ``_NON_CONSTANT``.

    ``class_def`` is the class the method is looked up on; ``current_class`` is the class we are
    currently resolving *inside* (so a ``self._helper()`` call in the method's body resolves too)."""
    method = _find_method(class_def, method_name)
    if method is None:
        return _NON_CONSTANT
    key = f"method:{class_def.name}:{method_name}"
    val = _resolve_callable_constant(
        method, env, helpers, sources, resolving, classes, class_def, key
    )
    if helpers is not None:
        helpers[key] = val
    return val


def _resolve_attribute_constant(
    func: ast.Attribute,
    env: dict[str, object],
    helpers: dict[str, object] | None,
    sources: dict[str, ast.FunctionDef | ast.AsyncFunctionDef],
    resolving: frozenset[str],
    classes: dict[str, ast.ClassDef],
    current_class: ast.ClassDef | None,
) -> object:
    """The single constant a bound-method CALL returns, or ``_NON_CONSTANT``.

    Traces ``self._method(...)`` (a method on the enclosing class being analysed) and
    ``_Helper()._method(...)`` (a method on a module-level class). Only a call to a method that
    provably always returns ONE constant resolves; a method that decides on its inputs (returns a
    non-constant) stays ``_NON_CONSTANT`` so a real guard that delegates to a deciding helper is
    never over-rejected. A bare attribute VALUE (``self._ALWAYS``, no call) is NOT resolved here —
    that is the next ratchet headroom."""
    attr = func.attr
    val = func.value
    if isinstance(val, ast.Name) and val.id == "self" and current_class is not None:
        return _resolve_method_constant(
            current_class, attr, env, helpers, sources, resolving, classes, current_class
        )
    if isinstance(val, ast.Call) and isinstance(val.func, ast.Name) and val.func.id in classes:
        return _resolve_method_constant(
            classes[val.func.id], attr, env, helpers, sources, resolving, classes, current_class
        )
    return _NON_CONSTANT


def _resolve_literal_key(
    node: ast.AST,
    env: dict[str, object],
    helpers: dict[str, object] | None = None,
    sources: dict[str, ast.FunctionDef | ast.AsyncFunctionDef] | None = None,
    resolving: frozenset[str] = frozenset(),
    classes: dict[str, ast.ClassDef] | None = None,
    current_class: ast.ClassDef | None = None,
) -> tuple[bool, object]:
    """``(is_constant, key)`` for ``node`` — a hashable identity so two constant literals compare
    equal iff structurally identical.

    Distinguishes ``True`` from ``1``, keeps both branches of a whitelist constant (``True`` and
    ``False``) distinct, and — the hardening over a bare literal check — resolves a NAME through
    the module-constant ``env`` (``return ALWAYS`` where ``ALWAYS = True``) so a constant decision
    hidden behind a name is no longer read as state-dependent. Hardened further: resolves a
    TOP-LEVEL HELPER CALL (``return _always(...)``) when the helper provably always returns one
    constant, so a constant hidden behind a helper call is likewise caught. Hardened further still:
    resolves a BOUND-METHOD CALL (``return self._always(...)`` / ``return _Helper().always(...)``)
    when the called method always returns one constant, so a constant hidden behind an
    attribute/method call is caught too. ``(False, None)`` means non-constant (a real decision on
    state), which the inert detector treats as a genuine guard. ``sources`` maps top-level function
    names to their def; ``helpers`` is the memoised callable→constant cache; ``resolving`` guards
    recursion cycles; ``classes`` maps module-level class names to their def; ``current_class`` is
    the class being analysed (so ``self._method`` resolves on it). Only a plain-``Name`` call to a
    top-level helper or a bound-method/``_Helper().method`` call is traced — a bare attribute VALUE
    (``self._ALWAYS``) and a name not in ``sources`` fall back to non-constant, so a real guard
    that delegates to a *deciding* helper is never over-rejected."""
    if isinstance(node, ast.Constant):
        return True, node.value
    if isinstance(node, ast.Name):
        if node.id in env:
            return True, env[node.id]
        return False, None
    if isinstance(node, ast.Call):
        if isinstance(node.func, ast.Name) and sources and node.func.id in sources:
            val = _resolve_module_function_value(
                node.func.id, env, helpers, sources, resolving, classes or {}, current_class
            )
            if val is not _NON_CONSTANT:
                return True, val
        if isinstance(node.func, ast.Attribute) and classes:
            val = _resolve_attribute_constant(
                node.func, env, helpers, sources, resolving, classes, current_class
            )
            if val is not _NON_CONSTANT:
                return True, val
        return False, None
    if isinstance(node, (ast.Tuple, ast.List, ast.Set)):
        keys = []
        for e in node.elts:
            ok, k = _resolve_literal_key(
                e, env, helpers, sources, resolving, classes, current_class
            )
            if not ok:
                return False, None
            keys.append(k)
        return True, tuple(keys)
    if isinstance(node, ast.Dict):
        pairs = []
        for k, v in zip(node.keys, node.values):
            if k is None:
                return False, None
            ok_k, kk = _resolve_literal_key(
                k, env, helpers, sources, resolving, classes, current_class
            )
            ok_v, kv = _resolve_literal_key(
                v, env, helpers, sources, resolving, classes, current_class
            )
            if not ok_k or not ok_v:
                return False, None
            pairs.append((kk, kv))
        return True, tuple(pairs)
    return False, None


def _module_callable_sources(tree: ast.Module) -> dict[str, ast.FunctionDef | ast.AsyncFunctionDef]:
    """Map of top-level function/async names -> def. Only these (a bare-name call to a module-level
    helper) are traced by the inert detector; a method or attribute call is not."""

    out: dict[str, ast.FunctionDef | ast.AsyncFunctionDef] = {}
    for stmt in tree.body:
        if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)):
            out[stmt.name] = stmt
    return out


def _module_constants(tree: ast.Module) -> dict[str, object]:
    """Module-level names bound to a constant literal (or constant tuple/dict), resolved top-down
    so ``ALWAYS = True; X = ALWAYS`` works. This is what lets the inert detector trace a guard that
    returns its decision through a NAME (``return ALWAYS``) instead of a literal."""
    env: dict[str, object] = {}
    for stmt in tree.body:
        if (
            isinstance(stmt, ast.Assign)
            and len(stmt.targets) == 1
            and isinstance(stmt.targets[0], ast.Name)
        ):
            ok, key = _resolve_literal_key(stmt.value, env)
            if ok:
                env[stmt.targets[0].id] = key
    return env


def _collect_returns(stmt: ast.stmt, out: list[ast.Return]) -> None:
    """Collect every ``return`` in ``stmt``, descending through control flow but NOT into a
    nested function/class/lambda (a guard's own returns are what decide inertness, not a
    helper's)."""
    if isinstance(stmt, ast.Return):
        out.append(stmt)
    elif isinstance(stmt, (ast.If, ast.While, ast.For)):
        for s in stmt.body:
            _collect_returns(s, out)
        for s in stmt.orelse:
            _collect_returns(s, out)
    elif isinstance(stmt, ast.With):
        for s in stmt.body:
            _collect_returns(s, out)
    elif isinstance(stmt, ast.Try):
        for s in stmt.body:
            _collect_returns(s, out)
        for handler in stmt.handlers:
            for s in handler.body:
                _collect_returns(s, out)
        for s in stmt.orelse:
            _collect_returns(s, out)
        for s in stmt.finalbody:
            _collect_returns(s, out)
    elif isinstance(stmt, ast.Match):
        for case in stmt.cases:
            for s in case.body:
                _collect_returns(s, out)


def _is_inert_function(
    fn: ast.FunctionDef | ast.AsyncFunctionDef,
    env: dict[str, object],
    helpers: dict[str, object],
    sources: dict[str, ast.FunctionDef | ast.AsyncFunctionDef],
    classes: dict[str, ast.ClassDef],
    current_class: ast.ClassDef | None,
) -> bool:
    """True iff a guard function is an inert pass-through: every ``return`` yields the SAME
    constant literal and never depends on its inputs.

    This is the 'always allow / always deny / always None' cheat — the symbol and even real
    code are present, but the guard decides nothing (``def allows_write(...): return True``).
    The key guard against over-rejection: a real whitelist that branches on its inputs and
    returns ``True`` one way and ``False`` the other yields TWO distinct constants, which is a
    real decision and is NOT flagged. A single non-constant return (``return path in roots``)
    is also never flagged. ``env`` carries the module-constant names so a constant returned
    through a NAME (``return ALWAYS``) resolves to its value and is caught. ``helpers``/
    ``sources`` let a constant returned through a top-level HELPER CALL (``return _always()``)
    be traced, and now a constant returned through a BOUND-METHOD CALL on the enclosing class
    (``return self._always()``) is traced too, via ``current_class``/``classes``.
    """
    returns = _collect_returns_of(fn)
    if not returns:
        return False  # no explicit return -> dead-stub territory, handled by _is_dead_stub
    key: set[object] = set()
    for r in returns:
        ok, k = _resolve_literal_key(
            r.value, env, helpers, sources, frozenset(), classes, current_class
        )
        if not ok:
            return False  # a decision on state -> real guard
        key.add(repr(k))
    return len(key) == 1  # always the same constant -> constant function -> inert


def _collect_returns_of(fn: ast.FunctionDef | ast.AsyncFunctionDef) -> list[ast.Return]:
    out: list[ast.Return] = []
    for stmt in fn.body:
        _collect_returns(stmt, out)
    return out


def _is_inert_statement(
    stmt: ast.stmt,
    env: dict[str, object],
    helpers: dict[str, object],
    sources: dict[str, ast.FunctionDef | ast.AsyncFunctionDef],
    classes: dict[str, ast.ClassDef],
    current_class: ast.ClassDef | None,
) -> bool:
    """True iff a top-level statement carries no effective guard logic: a pass, an import, a
    module docstring, a constant-only assignment, an inert function, or a class composed only
    of inert statements. A frame of real logic anywhere makes the module non-inert.
    ``env`` carries the module-constant names so a constant hidden behind a NAME is traced;
    ``helpers``/``sources`` extend that to a constant hidden behind a HELPER CALL, and
    ``classes``/``current_class`` extend it to a constant hidden behind a BOUND-METHOD CALL."""
    if isinstance(stmt, ast.Pass):
        return True
    if isinstance(stmt, (ast.Import, ast.ImportFrom)):
        return True
    if isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Constant):
        return True  # module docstring / ellipsis
    if isinstance(stmt, ast.Assign):
        ok, _ = _resolve_literal_key(
            stmt.value, env, helpers, sources, frozenset(), classes, current_class
        )
        return ok
    if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)):
        return _is_inert_function(stmt, env, helpers, sources, classes, current_class)
    if isinstance(stmt, ast.ClassDef):
        return all(_is_inert_statement(s, env, helpers, sources, classes, stmt) for s in stmt.body)
    return False


def _is_inert_module(text: str) -> bool:
    """True iff a whole module is an inert pass-through: every top-level statement is a no-op
    guard (a constant assignment, a function that always returns one constant, a class of
    such methods). A real anchor file always contains real logic somewhere, so it is never
    flagged. Returns False on unparseable input so a real source file is never rejected."""
    try:
        tree = ast.parse(text)
    except (SyntaxError, ValueError, TypeError):
        return False
    if not tree.body:
        return True  # empty/comment-only module
    env = _module_constants(tree)
    sources = _module_callable_sources(tree)
    classes: dict[str, ast.ClassDef] = {}
    for stmt in tree.body:
        if isinstance(stmt, ast.ClassDef):
            classes[stmt.name] = stmt
    helpers: dict[str, object] = {}
    return all(_is_inert_statement(s, env, helpers, sources, classes, None) for s in tree.body)


class TraceabilityVerifier:
    """Evidence-derived ``verify`` (name, probe) -> ProbeRun."""

    def __init__(self, constitution: Constitution) -> None:
        self._by_id = {p.id: p for p in constitution.principles}

    def __call__(self, name: str, probe: Probe) -> ProbeRun:
        """Make the verifier usable directly as a ``verify(name, probe)`` resolver."""
        return self.verify(name, probe)

    def verify(self, name: str, probe: Probe) -> ProbeRun | None:
        p = self._by_id.get(probe.probe_id)
        if p is None:
            # No constitutional principle for this probe -> no evidence EITHER WAY.
            # Return None so the gate keeps the agent's own run instead of reading
            # the whole menu as (False, False) and zeroing mutation robustness.
            return None
        return self._run(p)

    @staticmethod
    def classify(pattern: str, violations: str, text: str, probe_id: str) -> ProbeRun:
        """Pure classification over arbitrary anchor text (mutation-score core).

        ``did_expand`` = the pattern is present AND the module is not just a placeholder
        shell (a dead ``class X: pass`` / comment-only / docstring-only module). ``safe`` =
        no violations sentinel is present. Hardened beyond a bare regex: it no longer
        blesses a guard symbol that carries no logic, which is the naive gap the
        mutation-score is designed to expose.
        """
        expanded = bool(re.search(pattern, text))
        if expanded:
            # A symbol can be present yet be a shell; refuse to bless a placeholder guard.
            # A symbol can ALSO be present with real code yet decide nothing (an inert
            # pass-through like ``def allows_write: return True``, or a constant returned
            # through a NAME ``return ALWAYS``, or through a top-level HELPER CALL
            # ``return _always()``); refuse to bless that too.
            expanded = not _is_dead_stub(text) and not _is_inert_module(text)
        safe = not re.search(violations, text)
        return ProbeRun(probe_id, did_expand=expanded, safe=safe)

    def _run(self, p: Principle) -> ProbeRun:
        # Fail-closed: a principle whose anchor is missing reports BOTH no expansion
        # AND unsafe — an unimplemented guard is not safety-compliant, not vacuously safe.
        anchor = Path(p.anchor)
        if not anchor.exists():
            return ProbeRun(p.id, did_expand=False, safe=False)
        return self.classify(p.pattern, p.violations, anchor.read_text(encoding="utf-8"), p.id)

    def compliance(self) -> float:
        """The single-agent cumulative CSDD score.

        Fraction of principles that are BOTH implemented (the pattern is present) and
        clean (no violations sentinel). Each agent modification that installs a guard or
        removes a violation raises this toward 1.0; any violation or missing guard drops
        it to 0.0. This is the honest "did the code satisfy the constitution" number —
        not the gate's Pareto rank, which is for comparing agents.
        """
        if not self._by_id:
            return 0.0
        good = sum(1 for p in self._by_id.values() if self._run(p).safe and self._run(p).did_expand)
        return good / len(self._by_id)

    def matrix(self) -> list[dict]:
        """The compliance traceability matrix (paper L7).

        One row per principle: the anchor file, the expected pattern, the level, the
        boundary it guards, and the *evidence-derived* verdict — ``expanded`` is True iff
        the anchor file really contains the pattern, and ``safe`` is True iff the anchor
        is free of the violations sentinel. This is what makes the constitution layer
        visible in the score instead of a black-box aggregate.
        """
        return [
            {
                "id": p.id,
                "boundary": p.boundary,
                "level": p.level,
                "cwe": p.cwe,
                "anchor": p.anchor,
                "pattern": p.pattern,
                "expanded": self._run(p).did_expand,
                "safe": self._run(p).safe,
            }
            for p in self._by_id.values()
        ]
