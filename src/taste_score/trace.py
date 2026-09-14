"""Static traceability verifier (CSDD spec + paper L7).

This is the anti-self-report resolver: instead of trusting an agent's claimed
``did_expand``/``safe``, it derives them from real evidence in ``src/``. Each
constitution principle maps to an ``anchor`` file (with a ``pattern`` that must be
present and a ``violations`` sentinel that must be absent). Deterministic, no LLM.
"""

from __future__ import annotations

import ast
import io
import re
import tokenize
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


def _docstring_spans(text: str) -> list[tuple[tuple[int, int], tuple[int, int]]]:
    """The ``(row, col)`` spans of every docstring in ``text`` (module/class/def alike)."""
    spans: list[tuple[tuple[int, int], tuple[int, int]]] = []
    for node in ast.walk(ast.parse(text)):
        body = getattr(node, "body", None)
        if not isinstance(body, list) or not body:
            continue
        first = body[0]
        if (
            isinstance(first, ast.Expr)
            and isinstance(first.value, ast.Constant)
            and isinstance(first.value.value, str)
        ):
            value = first.value
            spans.append(
                ((value.lineno, value.col_offset), (value.end_lineno, value.end_col_offset))
            )
    return spans


def _code_only(text: str) -> str:
    """``text`` with its PROSE blanked — comments and docstrings removed, line structure kept.

    Evidence (``pattern`` / ``require``) used to be matched against raw text, so a tamper that
    DELETED the guard and left its text behind in a comment or a docstring still satisfied it:
    the ruler credited a boundary that is no longer in the code. Evidence has to be code.
    Ordinary string literals are deliberately KEPT — a real ``require`` may contain one (SEC-02's
    ``risk == "high"``), so blanking every string would gut the real constitution instead of
    hardening it. Unparseable text falls back to itself, like ``_is_dead_stub``: a parser hiccup
    must never reject a real source file.
    """
    try:
        tokens = list(tokenize.generate_tokens(io.StringIO(text).readline))
        spans = [(tok.start, tok.end) for tok in tokens if tok.type == tokenize.COMMENT]
        spans += _docstring_spans(text)
    except (tokenize.TokenError, IndentationError, SyntaxError, ValueError):
        return text
    lines = text.splitlines(keepends=True)
    for (start_row, start_col), (end_row, end_col) in spans:
        for row in range(start_row, end_row + 1):
            line = lines[row - 1]
            body = line.rstrip("\r\n")  # the terminator is not part of the span
            begin = start_col if row == start_row else 0
            finish = end_col if row == end_row else len(body)
            lines[row - 1] = (
                body[:begin] + " " * max(0, finish - begin) + body[finish:] + line[len(body) :]
            )
    return "".join(lines)


def _line_starts(text: str) -> list[int]:
    """The character offset of every line's first character (``[row - 1]`` for a 1-indexed row)."""
    starts = [0]
    for line in text.splitlines(keepends=True):
        starts.append(starts[-1] + len(line))
    return starts


# The token types whose text is DATA rather than code. Python 3.12+ splits an f-string into
# ``FSTRING_START`` / ``FSTRING_MIDDLE`` / ``FSTRING_END``, so its literal runs are NOT ``STRING``
# tokens; naming them here is what closes the container a cheater's name could otherwise survive
# in. The ``getattr`` guards keep pre-3.12 interpreters working, where an f-string is a single
# ``STRING`` token and therefore already data.
_DATA_TOKEN_TYPES = frozenset(
    token_type
    for token_type in (
        tokenize.STRING,
        getattr(tokenize, "FSTRING_START", None),
        getattr(tokenize, "FSTRING_MIDDLE", None),
        getattr(tokenize, "FSTRING_END", None),
    )
    if token_type is not None
)


def _data_spans(text: str) -> list[tuple[int, int]]:
    """Character-offset spans of every DATA region of ``text``: string and f-string literals.

    These are the places where a symbol is DATA rather than code. ``_code_only`` blanks prose but
    KEEPS string literals on purpose (a real ``require`` can contain one, e.g. SEC-02's
    ``risk == "high"``), so deleting a guard and parking its name in a string (``_note =
    "allows_write"``) still satisfied the evidence: the ruler credited an implementation that is
    not in the code. The rule below is CONTAINMENT, not "no strings": a match that merely SPANS a
    literal is a decision made in code, a match that lies WHOLLY inside one is data.

    The same cheater has a second container. An f-string's literal runs tokenize as
    ``FSTRING_START`` / ``FSTRING_MIDDLE`` / ``FSTRING_END`` (Python 3.12+), not ``STRING``, so a
    name left behind in ``f"allows_write is enforced"`` used to sit outside every span and be
    credited as an implementation. ``_DATA_TOKEN_TYPES`` spans both containers; only the literal
    runs are spanned, so an f-string's EXPRESSIONS stay code — a real guard that builds a message
    from a live value is not judged data.

    Empty on unparseable text — the same fallback as ``_code_only`` / ``_is_dead_stub`` (a parser
    hiccup must never reject a real source file).
    """
    try:
        tokens = list(tokenize.generate_tokens(io.StringIO(text).readline))
    except (tokenize.TokenError, IndentationError, SyntaxError, ValueError):
        return []
    starts = _line_starts(text)
    return [
        (starts[tok.start[0] - 1] + tok.start[1], starts[tok.end[0] - 1] + tok.end[1])
        for tok in tokens
        if tok.type in _DATA_TOKEN_TYPES
    ]


def _evidence(pattern: str, code: str, data: list[tuple[int, int]]) -> bool:
    """True iff ``pattern`` matches the code view somewhere that is not DATA (``_data_spans``)."""
    for match in re.finditer(pattern, code):
        if not any(start <= match.start() and match.end() <= end for start, end in data):
            return True
    return False


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
    never over-rejected. A bare attribute VALUE (``self._ALWAYS``, no call) is NOT resolved here — it is
    resolved by ``_resolve_attribute_value_constant`` (a class-body constant assignment), so this path
    only handles a method CALL."""
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


def _resolve_instance_attr_constant(
    class_def: ast.ClassDef,
    attr: str,
    env: dict[str, object],
    helpers: dict[str, object] | None,
    sources: dict[str, ast.FunctionDef | ast.AsyncFunctionDef],
    resolving: frozenset[str],
    classes: dict[str, ast.ClassDef],
    current_class: ast.ClassDef | None,
) -> object:
    """The single constant an INSTANCE attribute ``self.<attr>`` is bound to in ``__init__``, or
    ``_NON_CONSTANT``.

    A guard can carry a constant through an instance attribute set at build time
    (``self._ALWAYS = True`` in ``def __init__``) rather than in the class body — the residual
    ``instance-attr-hidden`` evasion the class-body-only resolver blesses. This resolves it, but
    conservatively: only if ``__init__`` assigns ``self.<attr>`` EXACTLY ONCE and that RHS resolves
    to a provable constant. A reassignment, a decision on an argument (``self._allowed = allowed``),
    or no ``__init__``/assignment stays ``_NON_CONSTANT`` so a real guard is never over-rejected.
    """
    init = _find_method(class_def, "__init__")
    if init is None:
        return _NON_CONSTANT
    found: ast.AST | None = None
    for stmt in init.body:
        if not isinstance(stmt, ast.Assign) or len(stmt.targets) != 1:
            continue
        target = stmt.targets[0]
        if not (
            isinstance(target, ast.Attribute)
            and target.attr == attr
            and isinstance(target.value, ast.Name)
            and target.value.id == "self"
        ):
            continue
        if found is not None:
            return _NON_CONSTANT  # reassigned -> cannot prove a single constant
        found = stmt.value
    if found is None:
        return _NON_CONSTANT
    ok, key = _resolve_literal_key(found, env, helpers, sources, resolving, classes, current_class)
    return key if ok else _NON_CONSTANT


def _instance_receiver_class(
    value: ast.AST,
    current_class: ast.ClassDef | None,
    locals_map: dict[str, ast.ClassDef],
    classes: dict[str, ast.ClassDef],
) -> ast.ClassDef | None:
    """The class an attribute-receiver expression refers to, or ``None``.

    ``self`` -> the enclosing class; a local name bound to ``_Cls(...)`` (``locals_map``); a
    ``_Cls(...)`` construction call; or a bare module-level class name ``_Mod``. ``None`` means the
    receiver could not be statically tied to a class (e.g. a factory function call), so the read is
    NOT proven a constant."""
    if isinstance(value, ast.Name) and value.id == "self" and current_class is not None:
        return current_class
    if isinstance(value, ast.Name) and value.id in locals_map:
        return locals_map[value.id]
    if (
        isinstance(value, ast.Call)
        and isinstance(value.func, ast.Name)
        and value.func.id in classes
    ):
        return classes[value.func.id]
    if isinstance(value, ast.Name) and value.id in classes:
        return classes[value.id]
    return None


def _factory_return_class(
    fn: ast.FunctionDef | ast.AsyncFunctionDef,
    classes: dict[str, ast.ClassDef],
    sources: dict[str, ast.FunctionDef | ast.AsyncFunctionDef] | None = None,
    _depth: int = 0,
    cls_class: ast.ClassDef | None = None,
    cls_name: str | None = None,
) -> ast.ClassDef | None:
    """The single class a pure-constructor factory returns, or ``None``.

    A factory that does ``h = _Cls(...); return h`` (or ``return _Cls(...)``) returns ONE statically
    known class. A factory that returns a parameter, an arbitrary expression, or different classes in
    different branches stays ``None`` so a genuinely dynamic factory is never over-resolved (which would
    let a real factory-returned guard be misjudged inert). A factory that DELEGATES to another factory
    (``return _build()``) is followed to the base builder that constructs the class. A ``@classmethod``
    factory that builds via ``cls()`` resolves to ``cls_class`` (the class it is called on). ``_depth``
    caps the (theoretical) mutual-factory recursion so an outlandish ``a()->b()->a()`` cannot hang the
    detector."""
    if _depth > 8:
        return None
    locals_map = _named_local_classes(fn, classes, cls_class, cls_name)
    returns = _collect_returns_of(fn)
    found: ast.ClassDef | None = None
    for r in returns:
        c = _return_expr_class(
            r.value, locals_map, classes, sources or {}, _depth, cls_class, cls_name
        )
        if c is None:
            return None
        if found is not None and c is not found:
            return None
        found = c
    return found


def _return_expr_class(
    expr: ast.AST,
    locals_map: dict[str, ast.ClassDef],
    classes: dict[str, ast.ClassDef],
    sources: dict[str, ast.FunctionDef | ast.AsyncFunctionDef] | None = None,
    _depth: int = 0,
    cls_class: ast.ClassDef | None = None,
    cls_name: str | None = None,
) -> ast.ClassDef | None:
    """The class an expression constructs: a direct ``_Cls(...)`` call, a local name bound to one, or —
    now — a call to a module-level FACTORY whose single statically-known return class it resolves
    (following a factory chain, so ``return _build()`` resolves to the builder's class). ``None`` means
    the expression could not be tied to a single statically-known class. ``cls_class``/``cls_name`` carry
    the ``@classmethod`` receiver (a ``cls()`` construction resolves to the class the factory is called on)."""
    if _depth > 8:
        return None
    if isinstance(expr, ast.Call) and isinstance(expr.func, ast.Name):
        if expr.func.id in classes:
            return classes[expr.func.id]
        if cls_class is not None and cls_name is not None and expr.func.id == cls_name:
            return cls_class
        if sources and expr.func.id in sources:
            return _factory_return_class(
                sources[expr.func.id], classes, sources, _depth + 1, cls_class, cls_name
            )
    if isinstance(expr, ast.Name) and expr.id in locals_map:
        return locals_map[expr.id]
    return None


def _factory_receiver(
    value: ast.AST,
    sources: dict[str, ast.FunctionDef | ast.AsyncFunctionDef],
    classes: dict[str, ast.ClassDef],
    _depth: int = 0,
) -> tuple[ast.ClassDef | None, ast.FunctionDef | ast.AsyncFunctionDef | None]:
    """``(class, base_factory_fn)`` for a ``_make().attr`` receiver, or ``(None, None)``.

    ``value`` is a call to a module-level factory FUNCTION (``_make()``) or a class-level factory METHOD
    (``_Helper.create()``). A factory may DELEGATE to another factory — a module function (``_make()``
    returns ``_build()``) or a method (``_Helper.create()`` returns ``_build()``): the resolver walks the
    chain to the BASE builder that directly constructs the class, because the mutator that binds the
    constant is called in that base builder's body, not in the delegating wrapper. A method factory is
    reached through a ``@staticmethod``/``@classmethod`` (``_Helper.create()`` is a bound-method
    expression, not a ``_Cls(...)`` construction), which the module-function-only resolver never saw.
    ``_depth`` caps mutual-factory recursion (an outlandish ``def _a(): return _b()`` cannot hang the
    detector)."""
    if _depth > 8:
        return None, None
    if not isinstance(value, ast.Call):
        return None, None
    f = value.func
    # A module-level factory FUNCTION, ``_make()``.
    if isinstance(f, ast.Name) and sources and f.id in sources:
        fn = sources[f.id]
        # A delegating factory (the return expr is itself a factory call) — recurse to the base builder first.
        for r in _collect_returns_of(fn):
            sub = _factory_receiver(r.value, sources, classes, _depth + 1)
            if sub[0] is not None:
                return sub
        # Not a delegation; this factory directly constructs the class (or is not a resolvable factory).
        cls = _factory_return_class(fn, classes, sources, _depth)
        return (cls, fn) if cls is not None else (None, None)
    # A class-level factory METHOD, ``_Helper.create()`` (staticmethod/classmethod receiver).
    if isinstance(f, ast.Attribute):
        return _class_factory_receiver(value, sources, classes, _depth)
    return None, None


def _collect_assignments(stmt: ast.stmt, out: list[tuple[list[ast.expr], ast.expr]]) -> None:
    """Collect every assignment in ``stmt`` as ``(targets, value)``, descending through control
    flow but NOT into a nested function/class (a nested scope's locals are its own)."""
    if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
        return
    if isinstance(stmt, ast.Assign):
        out.append((stmt.targets, stmt.value))
    elif isinstance(stmt, ast.AnnAssign) and stmt.value is not None:
        out.append(([stmt.target], stmt.value))
    for child in ast.iter_child_nodes(stmt):
        if isinstance(child, ast.stmt):
            _collect_assignments(child, out)


def _receiver_names(
    fn: ast.FunctionDef | ast.AsyncFunctionDef | None, receiver_name: str | None
) -> tuple[str, ...]:
    """Every LOCAL NAME that denotes the tracked receiver inside ``fn`` — canonical name first.

    A receiver can be RENAMED before it leaves the class (``create`` does ``k = cls`` then
    ``return _delegate(k)``) or between delegation hops (``j = k`` inside the helper). Following those
    names is what keeps a rename from hiding the base builder that binds the constant.

    Conservative by construction: a name counts only when EVERY assignment to it in ``fn`` is another
    tracked name, so a name that is ALSO bound from anything else (``k = cls`` in one branch,
    ``k = _spare()`` in another) is not an alias and the chain stays honestly un-resolved rather than
    guessed at. Returned as an ordered tuple (never a set) so a verdict can never depend on hash
    iteration order.
    """
    if fn is None or not receiver_name:
        return ()
    assigns: list[tuple[list[ast.expr], ast.expr]] = []
    for stmt in fn.body:
        _collect_assignments(stmt, assigns)
    values: dict[str, list[ast.expr]] = {}
    for targets, value in assigns:
        for target in targets:
            if isinstance(target, ast.Name):
                values.setdefault(target.id, []).append(value)
    names = [receiver_name]
    changed = True
    while changed:
        changed = False
        for name, bound in values.items():
            if name in names:
                continue
            if bound and all(isinstance(v, ast.Name) and v.id in names for v in bound):
                names.append(name)
                changed = True
    return tuple(names)


def _handed_receiver_param(
    call: ast.Call,
    callee: ast.FunctionDef | ast.AsyncFunctionDef,
    receiver_names: tuple[str, ...],
) -> str | None:
    """The parameter name that RECEIVES the tracked receiver at this call site, or ``None``.

    A ``@classmethod`` can hand its ``cls`` receiver to a MODULE-LEVEL helper
    (``create()`` returns ``_delegate(cls)``); inside the helper the receiver has the helper's
    parameter name (``def _delegate(k)`` -> ``return k.build()``), so that name is what a delegation
    inside the helper must be resolved against. Every POSITIONAL argument that is one of the tracked
    receiver NAMES is bound — ``_delegate(cls)`` and ``k = cls`` then ``_delegate(k)`` hand over the
    same receiver, so a rename does not break the chain (see ``_receiver_names``) — and the parameter
    must be a plain positional parameter. A hand-off whose argument is not a tracked NAME at all (the
    receiver parked on an attribute: ``cls._recv = cls`` then ``_delegate(cls._recv)``) or a keyword
    hand-off is deliberately not tracked, so that residual stays honestly un-resolved instead of being
    guessed at.
    """
    params = [*getattr(callee.args, "posonlyargs", []), *callee.args.args]
    for index, arg in enumerate(call.args):
        if isinstance(arg, ast.Name) and arg.id in receiver_names:
            return params[index].arg if index < len(params) else None
    return None


def _sibling_method_factory_receiver(
    value: ast.AST,
    class_def: ast.ClassDef,
    sources: dict[str, ast.FunctionDef | ast.AsyncFunctionDef],
    classes: dict[str, ast.ClassDef],
    _depth: int = 0,
    receiver_names: tuple[str, ...] = (),
) -> tuple[ast.ClassDef | None, ast.FunctionDef | ast.AsyncFunctionDef | None]:
    """``(class, factory_method)`` for a delegation whose return expr calls a SIBLING method of
    ``class_def`` — either a bare-Name call (``create()`` returns ``_build()``) or, when the receiver's
    names are given, an attribute call on the ``@classmethod`` receiver (``create()`` returns
    ``cls.build()``).

    ``_factory_receiver`` resolves a module-level factory FUNCTION (a bare Name in ``sources``) or an
    attribute call on a class NAME (``_Helper._build()``) — but a delegation whose return expr calls a method
    of the SAME class (neither in ``sources`` nor an attribute on a known class) falls through un-resolved,
    so the guard is blessed. This recurses into the sibling method's own factory resolution (itself following
    a delegation chain) to reach the BASE builder that directly constructs the class — the mutator that binds
    the constant lives in that base builder's body, not in the delegating wrapper. ``cls_name`` is the
    first-arg receiver name of the ``@classmethod`` whose return expr is being resolved (``cls`` in ``return
    cls.build()``): an attribute call on that name targets ``class_def`` itself. The receiver name is
    RE-DERIVED at every hop (the sibling ``@classmethod``'s own first arg, falling back to the inherited
    name), so a chain of ``cls``-receiver delegations (``create`` -> ``cls._mid()`` -> ``cls.build()``) is
    followed to the base builder rather than stopping after one hop. ``_depth`` caps mutual method-factory
    recursion (``a()`` returning ``b()`` returning ``a()`` cannot hang the detector). Returns
    ``(None, None)`` when the call is neither shape, the named method is not a method of ``class_def``, or
    the sibling is not a resolvable factory. A call to a MODULE-LEVEL HELPER that RECEIVES the tracked
    receiver as an argument (``create()`` returns ``_delegate(cls)``) is a delegation too: the helper's
    parameter bound to that argument names the receiver inside the helper, so the helper's own returns
    are resolved with that parameter as the receiver name and the base builder is still reached.
    ``receiver_names`` is every LOCAL NAME denoting the tracked receiver at this site, not just the
    canonical one (see ``_receiver_names``): a rename (``k = cls`` then ``_delegate(k)``) therefore keeps
    the chain alive, and the alias set is recomputed for the body the return expr actually lives in."""
    if _depth > 8:
        return None, None
    if not isinstance(value, ast.Call):
        return None, None
    if isinstance(value.func, ast.Name):
        method_name = value.func.id
    elif (
        receiver_names
        and isinstance(value.func, ast.Attribute)
        and isinstance(value.func.value, ast.Name)
        and value.func.value.id in receiver_names
    ):
        # A delegation through the `cls` receiver itself (`return cls.build()`): the attribute names a
        # method of the class the @classmethod was called on, i.e. `class_def`.
        method_name = value.func.attr
    else:
        return None, None
    method = _find_method(class_def, method_name)
    if method is None:
        # A delegation that HANDS THE RECEIVER TO A MODULE-LEVEL HELPER (``create()`` returns
        # ``_delegate(cls)``): the receiver leaves the class as an argument, so the attribute call made
        # inside the helper (``k.build()``) is not on a name this resolver knows and the delegation used
        # to stop here — the base builder that binds the constant was never reached and an inert
        # pass-through was blessed. Bind the helper's parameter that receives the tracked receiver, then
        # resolve the helper's OWN returns with that parameter as the receiver name, so the chain still
        # reaches the base builder. Only a module-level function written with the tracked receiver name
        # is followed (see ``_handed_receiver_param``).
        if isinstance(value.func, ast.Name) and receiver_names and sources:
            handed = sources.get(value.func.id)
            if handed is not None:
                param = _handed_receiver_param(value, handed, receiver_names)
                if param is not None:
                    for r in _collect_returns_of(handed):
                        sub = _factory_receiver(r.value, sources, classes, _depth + 1)
                        if sub[0] is None:
                            # Resolve the helper's OWN returns against the names the receiver has INSIDE
                            # the helper: a rename there (``j = k``) is still the same receiver.
                            sub = _sibling_method_factory_receiver(
                                r.value,
                                class_def,
                                sources,
                                classes,
                                _depth + 1,
                                _receiver_names(handed, param),
                            )
                        if sub[0] is not None:
                            return sub
        return None, None
    # The receiver name of THIS sibling hop: a ``@classmethod`` names its own receiver with its first arg
    # (``cls``), which is the name an attribute delegation inside its body targets. Inherit the caller's
    # name when the sibling is not a classmethod, so a ``cls``-receiver chain keeps resolving at each hop.
    inner_name = receiver_names[0] if receiver_names else None
    if _is_classmethod(method) and method.args.args:
        inner_name = method.args.args[0].arg
    for r in _collect_returns_of(method):
        sub = _factory_receiver(r.value, sources, classes, _depth + 1)
        if sub[0] is None:
            sub = _sibling_method_factory_receiver(
                r.value,
                class_def,
                sources,
                classes,
                _depth + 1,
                _receiver_names(method, inner_name),
            )
        if sub[0] is not None:
            return sub
    # Not a delegation; the sibling method directly constructs the class (or is not a resolvable factory).
    # A sibling `@classmethod` builds via `cls()` — thread the `cls` receiver through so `h = cls()` back
    # in the base builder resolves to `class_def` (the class the factory is called on).
    sib_cls_name: str | None = None
    if _is_classmethod(method) and method.args.args:
        sib_cls_name = method.args.args[0].arg
    ret_cls = _factory_return_class(method, classes, sources, _depth, class_def, sib_cls_name)
    return (class_def, method) if ret_cls is not None else (None, None)


def _is_classmethod(fn: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    """True iff a method is decorated ``@classmethod`` (its first arg is the class receiver)."""
    return any(
        (isinstance(d, ast.Name) and d.id == "classmethod")
        or (isinstance(d, ast.Attribute) and d.attr == "classmethod")
        for d in fn.decorator_list
    )


def _class_factory_receiver(
    value: ast.AST,
    sources: dict[str, ast.FunctionDef | ast.AsyncFunctionDef],
    classes: dict[str, ast.ClassDef],
    _depth: int = 0,
) -> tuple[ast.ClassDef | None, ast.FunctionDef | ast.AsyncFunctionDef | None]:
    """``(class, factory_method)`` for a class-level factory METHOD receiver (``_Helper.create()``).

    ``value`` is a call whose ``.func`` is an attribute on a bare class name (``_Helper.create()``): the
    resolver ties it to the class the method is defined on, then traces the method's single statically-known
    return class (following a method→method or method→module-function delegation chain to the BASE builder,
    so ``create()`` delegating to ``_build()`` resolves to whatever ``_build`` constructs). Returns the class
    the factory builds AND the factory method (as the enclosing context for the mutator look, since the
    mutator that binds the constant is called inside the factory method's body). ``None`` means the receiver
    could not be statically tied to a single known-return class. ``_depth`` caps mutual-factory recursion."""
    if _depth > 8:
        return None, None
    if not (isinstance(value, ast.Call) and isinstance(value.func, ast.Attribute)):
        return None, None
    recv = value.func.value
    # A class-level factory method reached through a bare class name (``_Helper.create()``) OR an
    # instance construction (``_Helper().create()`` — calling a @classmethod ON an instance still passes
    # the CLASS as ``cls``, so it builds the same receiver class). Both tie the factory method back to the
    # class it is defined on so the ``cls()`` construction can be resolved to a constant.
    if isinstance(recv, ast.Name):
        if recv.id not in classes:
            return None, None
        cls = classes[recv.id]
    elif isinstance(recv, ast.Call) and isinstance(recv.func, ast.Name) and recv.func.id in classes:
        cls = classes[recv.func.id]
    elif (
        isinstance(recv, ast.Call)
        and isinstance(recv.func, ast.Name)
        and sources
        and recv.func.id in sources
    ):
        # A classmethod factory reached through an INSTANCE returned by a FACTORY FUNCTION
        # (``_make().create()``): ``_make()`` is a module-level factory, neither a class name nor a
        # ``_Cls(...)`` construction, so the receiver-class resolver above could not tie ``create()``
        # to a class. Resolve the factory function's single statically-known return class, then tie
        # the classmethod to it. Anti-over-rejection: only a factory whose return class is provably
        # single is resolved; a factory returning a decision guard stays ``None`` (not resolved).
        cls = _factory_return_class(sources[recv.func.id], classes, sources, _depth)
        if cls is None:
            return None, None
    else:
        return None, None
    method = _find_method(cls, value.func.attr)
    if method is None:
        return None, None
    # A `@classmethod` factory's first-arg name IS the class it is called on, so both a `cls()`
    # construction and a delegation through `cls.<sibling>()` resolve back to `cls`. Computed before the
    # delegation loop so the `cls` receiver can be threaded into the sibling-delegation look.
    cls_name: str | None = None
    if _is_classmethod(method) and method.args.args:
        cls_name = method.args.args[0].arg
    # A delegating factory method (its return expr is itself a factory call, method or module fn) —
    # recurse to the base builder first, so ``create()`` returning ``_build()`` (or ``cls._build()``)
    # resolves to the builder's class.
    for r in _collect_returns_of(method):
        sub = _factory_receiver(r.value, sources, classes, _depth + 1)
        if sub[0] is None:
            # A delegation whose return expr calls a SIBLING method on the same class — a bare-Name
            # (``create()`` returns ``_build()``, both ``@staticmethod``) or an attribute on the ``cls``
            # receiver (``create()`` returns ``cls.build()``) — is neither a module-level function (the
            # module-function branch) nor an attribute call on a class name (``_Helper._build()``), so
            # ``_factory_receiver`` misses it. Recurse into the sibling method's own factory resolution
            # to reach the base builder that directly constructs the class.
            sub = _sibling_method_factory_receiver(
                r.value, cls, sources, classes, _depth + 1, _receiver_names(method, cls_name)
            )
        if sub[0] is not None:
            return sub
    # Not a delegation; this method directly constructs the class (or is not a resolvable factory).
    ret_cls = _factory_return_class(method, classes, sources, _depth, cls, cls_name)
    return (cls, method) if ret_cls is not None else (None, None)


def _is_instance_receiver(
    value: ast.AST,
    current_class: ast.ClassDef | None,
    locals_map: dict[str, ast.ClassDef],
    classes: dict[str, ast.ClassDef],
) -> bool:
    """True iff ``value`` is an instance receiver the resolver can tie to a class for the
    ``__init__``/mutator looks — ``self``, a local bound to ``_Cls(...)``, or a ``_Cls(...)`` call.
    A bare module class name ``_Mod.val`` is NOT an instance receiver (its ``val`` is a class
    attribute, resolved by the class-body path), so this stays False there."""
    if isinstance(value, ast.Name) and value.id == "self" and current_class is not None:
        return True
    if isinstance(value, ast.Name) and value.id in locals_map:
        return True
    if (
        isinstance(value, ast.Call)
        and isinstance(value.func, ast.Name)
        and value.func.id in classes
    ):
        return True
    return False


def _named_local_classes(
    fn: ast.FunctionDef | ast.AsyncFunctionDef,
    classes: dict[str, ast.ClassDef],
    cls_class: ast.ClassDef | None = None,
    cls_name: str | None = None,
) -> dict[str, ast.ClassDef]:
    """Map a local name to the class it is constructed from by a plain ``x = _Cls(...)`` assignment (or
    a ``@classmethod``'s ``x = cls()``, which resolves to ``cls_class`` — the class the factory is called
    on)."""
    out: dict[str, ast.ClassDef] = {}
    for stmt in fn.body:
        if (
            isinstance(stmt, ast.Assign)
            and len(stmt.targets) == 1
            and isinstance(stmt.targets[0], ast.Name)
            and isinstance(stmt.value, ast.Call)
            and isinstance(stmt.value.func, ast.Name)
            and (
                stmt.value.func.id in classes
                or (
                    cls_class is not None
                    and cls_name is not None
                    and stmt.value.func.id == cls_name
                )
            )
        ):
            out[stmt.targets[0].id] = (
                classes[stmt.value.func.id] if stmt.value.func.id in classes else cls_class
            )
    return out


def _iter_calls_of(stmt: ast.stmt) -> list[ast.Call]:
    """The ``ast.Call`` nodes in ``stmt`` that are DIRECT actions — not descending into a nested
    function/class/lambda body (a nested def's calls are not this function's actions)."""
    out: list[ast.Call] = []
    stack = list(ast.iter_child_nodes(stmt))
    while stack:
        node = stack.pop()
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda)):
            continue  # don't descend into nested definitions
        if isinstance(node, ast.Call):
            out.append(node)
        stack.extend(ast.iter_child_nodes(node))
    return out


def _method_binds_attr_constant(
    method: ast.FunctionDef | ast.AsyncFunctionDef,
    attr: str,
    env: dict[str, object],
    helpers: dict[str, object],
    sources: dict[str, ast.FunctionDef | ast.AsyncFunctionDef],
    classes: dict[str, ast.ClassDef],
    class_def: ast.ClassDef,
) -> object:
    """The single constant a method binds ``self.<attr>`` to EXACTLY ONCE, or ``_NON_CONSTANT``.

    A mutator (``_setup``) can set ``self._ALWAYS = True`` — the attribute the guard later reads. A
    reassignment, a binding from a non-constant RHS (an argument, a decision), or no binding keeps it
    ``_NON_CONSTANT`` so a real mutator that decides is never over-rejected. ``class_def`` is the
    method's owner, threaded as ``current_class`` so a ``self._helper()`` call in the RHS resolves too."""
    found: ast.AST | None = None
    for stmt in method.body:
        if not isinstance(stmt, ast.Assign) or len(stmt.targets) != 1:
            continue
        target = stmt.targets[0]
        if not (
            isinstance(target, ast.Attribute)
            and target.attr == attr
            and isinstance(target.value, ast.Name)
            and target.value.id == "self"
        ):
            continue
        if found is not None:
            return _NON_CONSTANT  # reassigned -> cannot prove a single constant
        found = stmt.value
    if found is None:
        return _NON_CONSTANT
    ok, key = _resolve_literal_key(found, env, helpers, sources, frozenset(), classes, class_def)
    return key if ok else _NON_CONSTANT


def _mutator_bound_attr_constant(
    enclosing_fn: ast.FunctionDef | ast.AsyncFunctionDef,
    receiver_class: ast.ClassDef,
    attr: str,
    env: dict[str, object],
    helpers: dict[str, object],
    sources: dict[str, ast.FunctionDef | ast.AsyncFunctionDef],
    classes: dict[str, ast.ClassDef],
    locals_map: dict[str, ast.ClassDef],
    current_class: ast.ClassDef | None,
) -> object:
    """The constant ``receiver.<attr>`` is bound to by a method of ``receiver_class`` that
    ``enclosing_fn`` CALLS, or ``_NON_CONSTANT``.

    The ``inst-attr-mutator-hidden`` evasion: a guard calls ``self._setup()`` (or ``h._setup()`` on a
    local instance) then reads ``self._ALWAYS`` — the value comes from a mutator, not the class body or
    ``__init__``. If the enclosing guard function calls a method of the receiver's class that binds
    ``<attr>`` to a provable single constant, the read IS that constant, so the guard is inert.
    Conservative: only a method called in the same function that binds the asked-for attribute to one
    constant proves it — a real guard that calls ``_setup`` for other side effects but reads a different,
    genuinely state-dependent attribute stays non-constant."""
    for stmt in enclosing_fn.body:
        for call in _iter_calls_of(stmt):
            if not isinstance(call.func, ast.Attribute):
                continue
            recv = _instance_receiver_class(call.func.value, current_class, locals_map, classes)
            if recv is not receiver_class:
                continue
            method = _find_method(recv, call.func.attr)
            if method is None:
                continue
            c = _method_binds_attr_constant(method, attr, env, helpers, sources, classes, recv)
            if c is not _NON_CONSTANT:
                return c
    return _NON_CONSTANT


def _resolve_attribute_value_constant(
    node: ast.Attribute,
    env: dict[str, object],
    helpers: dict[str, object] | None,
    sources: dict[str, ast.FunctionDef | ast.AsyncFunctionDef],
    resolving: frozenset[str],
    classes: dict[str, ast.ClassDef],
    current_class: ast.ClassDef | None,
    *,
    enclosing_fn: ast.FunctionDef | ast.AsyncFunctionDef | None = None,
    locals_map: dict[str, ast.ClassDef] | None = None,
) -> tuple[bool, object]:
    """``(is_constant, key)`` for a bare attribute VALUE with no call (``self._ALWAYS``,
    ``_Helper().val``, ``_Mod.val``).

    The residual inert-guard evasion: a guard returns its constant through a plain attribute READ
    rather than a literal, a NAME, a top-level helper CALL, or a bound-method CALL, so
    ``return self._ALWAYS`` (where ``_ALWAYS = True`` in the class body) always returns the same
    constant yet reads as state-dependent. Resolves it to the class-body constant assignment, then an
    ``__init__``-bound instance attribute, then — the ``inst-attr-mutator-hidden`` evasion — a mutator
    method the same function CALLS that binds ``<attr>`` to a single provable constant.

    Anti-over-rejection: only resolves when the attribute is bound to a PROVABLE constant literal we
    can statically see (class body, ``__init__``, a called mutator, or a receiver reached through a factory
    FUNCTION or a class-level factory METHOD whose single known-return class we can trace). An attribute
    carrying a real decision (a ``Compare`` like ``path in roots`` is a different node, never here), bound
    from an argument, reassigned, or reached through a factory whose return type cannot be tied to a single
    class is NOT resolved — so a real guard is never flagged. ``enclosing_fn``/``locals_map`` let the mutator
    look see which method a guard actually calls on the receiver.
    """
    attr = node.attr
    val = node.value
    locals_map = locals_map or {}
    target_class = _instance_receiver_class(val, current_class, locals_map, classes)
    enclosing = enclosing_fn
    receiver_locals = locals_map
    if target_class is None:
        # A factory-returned instance receiver (``_make().val``): trace the factory's single
        # statically-known return class, and treat the FACTORY as the enclosing context for the mutator
        # look (the mutator that binds the constant is called inside the factory body, not the guard).
        target_class, factory_fn = _factory_receiver(val, sources, classes)
        if factory_fn is not None and target_class is not None:
            enclosing = factory_fn
            # A `@classmethod` factory builds its instance via `cls()`; thread the receiver class so the
            # mutator that binds the constant (called inside the factory body) is found on `target_class`.
            cls_name: str | None = None
            if _is_classmethod(factory_fn) and factory_fn.args.args:
                cls_name = factory_fn.args.args[0].arg
            receiver_locals = _named_local_classes(factory_fn, classes, target_class, cls_name)
    if target_class is None:
        return False, None
    for stmt in target_class.body:
        if not isinstance(stmt, ast.Assign) or len(stmt.targets) != 1:
            continue
        target = stmt.targets[0]
        if not (
            (isinstance(target, ast.Name) and target.id == attr)
            or (isinstance(target, ast.Attribute) and target.attr == attr)
        ):
            continue
        ok, key = _resolve_literal_key(
            stmt.value, env, helpers, sources, resolving, classes, current_class
        )
        if ok:
            return True, key
    # Not a class-body attribute; an INSTANCE attribute bound in ``__init__`` is the same inert
    # pass-through (``self._ALWAYS = True`` in the constructor). Resolve it for an instance receiver
    # (``self`` / a local bound to ``_Cls(...)`` / a ``_Cls(...)`` call) — a bare ``_Mod.val`` class-
    # attribute read is still only a class-body lookup, so this branch never invents a constant for it.
    if _is_instance_receiver(val, current_class, locals_map, classes):
        c = _resolve_instance_attr_constant(
            target_class, attr, env, helpers, sources, resolving, classes, current_class
        )
        if c is not _NON_CONSTANT:
            return True, c
    # A mutator the SAME function calls binds ``<attr>`` to a single provable constant
    # (``self._setup()`` then ``return self._ALWAYS``) — the ``inst-attr-mutator-hidden`` evasion.
    # For a factory receiver, ``enclosing``/``receiver_locals`` are the factory's (the mutator is
    # called inside the factory body), so a factory-returned constant is caught too.
    if enclosing is not None:
        c = _mutator_bound_attr_constant(
            enclosing,
            target_class,
            attr,
            env,
            helpers,
            sources,
            classes,
            receiver_locals,
            current_class,
        )
        if c is not _NON_CONSTANT:
            return True, c
    return False, None


def _resolve_literal_key(
    node: ast.AST,
    env: dict[str, object],
    helpers: dict[str, object] | None = None,
    sources: dict[str, ast.FunctionDef | ast.AsyncFunctionDef] | None = None,
    resolving: frozenset[str] = frozenset(),
    classes: dict[str, ast.ClassDef] | None = None,
    current_class: ast.ClassDef | None = None,
    *,
    enclosing_fn: ast.FunctionDef | ast.AsyncFunctionDef | None = None,
    locals_map: dict[str, ast.ClassDef] | None = None,
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
    top-level helper, a bound-method/``_Helper().method`` call, or a bare attribute VALUE reading a
    class-body constant (``self._ALWAYS`` with ``_ALWAYS = True`` in the class body) is traced — a name
    not in ``sources`` and an attribute bound in ``__init__`` fall back to non-constant, so a real guard
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
    if isinstance(node, ast.Attribute):
        # A bare attribute VALUE (no call) that reads a provable constant from a class body
        # (``self._ALWAYS``, ``_Helper().val``) — resolves to the constant, so an inert guard that
        # always returns the same value via an attribute read is no longer read as state-dependent.
        return _resolve_attribute_value_constant(
            node,
            env,
            helpers,
            sources,
            resolving,
            classes or {},
            current_class,
            enclosing_fn=enclosing_fn,
            locals_map=locals_map,
        )
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


def _class_is_fully_inert(
    class_def: ast.ClassDef,
    env: dict[str, object],
    helpers: dict[str, object],
    sources: dict[str, ast.FunctionDef | ast.AsyncFunctionDef],
    classes: dict[str, ast.ClassDef],
    _depth: int = 0,
    _visiting: frozenset[str] = frozenset(),
) -> bool:
    """True iff every member of a class is an inert statement — a shell class whose methods only set /
    return constants and decide nothing. A real guard (a method that branches on its inputs) is NOT
    fully-inert, so a factory returning such an instance never resolves to a constant. ``_depth`` caps
    the (theoretical) self-referential-class recursion so an outlandish ``class C: def make(): return
    C()`` cannot hang the detector.

    ``_visiting`` carries the classes currently being checked so a static/class METHOD factory that lives
    *inside* the class it constructs (``class C: @staticmethod def make(): return C()``) is resolved
    coinductively: re-entering a class already assumed inert proves the factory member inert, rather than
    snapping to "not-inert" via the depth cap. A genuine state-deciding member still returns False, so the
    assumption never blesses a real guard."""
    if _depth > 8:
        return False
    if class_def.name in _visiting:
        return True  # coinductive: a self-referential factory builds an assumed-inert class
    _visiting = _visiting | {class_def.name}
    return all(
        _is_inert_statement(
            s, env, helpers, sources, classes, class_def, _depth=_depth, _visiting=_visiting
        )
        for s in class_def.body
    )


def _returns_inert_instance(
    expr: ast.AST,
    fn: ast.FunctionDef | ast.AsyncFunctionDef,
    env: dict[str, object],
    helpers: dict[str, object],
    sources: dict[str, ast.FunctionDef | ast.AsyncFunctionDef],
    classes: dict[str, ast.ClassDef],
    _depth: int = 0,
    _visiting: frozenset[str] = frozenset(),
    enclosing_class: ast.ClassDef | None = None,
) -> bool:
    """True iff ``expr`` constructs (or is a local name bound to) an instance of a FULLY-INERT class —
    a pure factory-ship of an inert shell, which contributes no real guard logic.

    ``enclosing_class`` is the class ``fn`` is a method of (``current_class`` from the parent), so a
    delegation whose return expr is a bare-Name call to a SIBLING method (``create()`` returns ``_build()``)
    is followed to the class it builds; a module-level function has ``None`` here and skips that branch.
    When ``fn`` is a ``@classmethod`` of ``enclosing_class``, its ``cls()`` construction resolves to
    ``enclosing_class`` (the class the factory is called on)."""
    cls_name: str | None = None
    if enclosing_class is not None and _is_classmethod(fn) and fn.args.args:
        cls_name = fn.args.args[0].arg
    locals_map = _named_local_classes(fn, classes, enclosing_class, cls_name)
    cls = _return_expr_class(expr, locals_map, classes, sources, 0, enclosing_class, cls_name)
    if cls is None and enclosing_class is not None:
        # A delegation whose return expr calls a SIBLING METHOD of ``enclosing_class`` — a bare-Name
        # (``create()`` returns ``_build()``, both ``@staticmethod``) or an attribute on the ``cls``
        # receiver (``create()`` returns ``cls.build()``) — is neither a module-level function nor a
        # direct class construction, so ``_return_expr_class`` misses it. Resolve it through the sibling
        # method's factory chain to the built class, then check that class's inertness.
        built, _ = _sibling_method_factory_receiver(
            expr,
            enclosing_class,
            sources,
            classes,
            receiver_names=_receiver_names(fn, cls_name),
        )
        if built is not None:
            cls = built
    if cls is None:
        return False
    return _class_is_fully_inert(
        cls, env, helpers, sources, classes, _depth=_depth + 1, _visiting=_visiting
    )


def _is_inert_function(
    fn: ast.FunctionDef | ast.AsyncFunctionDef,
    env: dict[str, object],
    helpers: dict[str, object],
    sources: dict[str, ast.FunctionDef | ast.AsyncFunctionDef],
    classes: dict[str, ast.ClassDef],
    current_class: ast.ClassDef | None,
    _depth: int = 0,
    _visiting: frozenset[str] = frozenset(),
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
    (``return self._always()``) is traced too, via ``current_class``/``classes``. A return that
    is a pure factory-ship of a FULLY-INERT class (``return _make_()`` / ``return h`` where ``h``
    is built from an inert shell) is likewise inert — otherwise a factory (which returns an
    instance, not a literal) would poison the module's inertness and let a factory-hidden cheat
    slip through.
    """
    returns = _collect_returns_of(fn)
    if not returns:
        # No explicit return (a constructor that only assigns constants, or a setter). Such a def is
        # part of an inert guard if every statement assigns only a constant (``self._ALWAYS = True``),
        # passes, imports, or is a docstring — it determines nothing. Real logic (a call, a loop, a
        # non-constant assignment like ``self._allowed = allowed``) makes it non-inert, so a real
        # setup/constructor is never flagged. Without this, a class whose ONLY non-inert-looking member
        # is ``__init__`` (implicitly returns None, so the old branch said 'not inert') would poison the
        # whole module and let the constructor-bound instance-attribute cheat slip through.
        return all(
            _is_inert_statement(
                s, env, helpers, sources, classes, current_class, _depth=_depth, _visiting=_visiting
            )
            for s in fn.body
        )
    locals_map = _named_local_classes(fn, classes)
    key: set[object] = set()
    for r in returns:
        ok, k = _resolve_literal_key(
            r.value,
            env,
            helpers,
            sources,
            frozenset(),
            classes,
            current_class,
            enclosing_fn=fn,
            locals_map=locals_map,
        )
        if not ok:
            # A pure factory-ship of an inert class is itself inert, so a factory that only builds an
            # inert shell does not un-poison the module's inertness.
            if _returns_inert_instance(
                r.value,
                fn,
                env,
                helpers,
                sources,
                classes,
                _depth=_depth,
                _visiting=_visiting,
                enclosing_class=current_class,
            ):
                key.add("inert-instance")
                continue
            return False  # a decision on state -> real guard
        key.add(repr(k))
    return len(key) == 1  # always the same constant -> constant function -> inert


def _collect_returns_of(fn: ast.FunctionDef | ast.AsyncFunctionDef) -> list[ast.Return]:
    out: list[ast.Return] = []
    for stmt in fn.body:
        _collect_returns(stmt, out)
    return out


def _is_receiver_forwarder(fn: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    """True iff a MODULE-LEVEL function carries no decision of its OWN: every ``return`` is a method
    call on one of the function's own parameters (``def _delegate(k): return k.build()``).

    A ``@classmethod`` can hand its ``cls`` receiver to such a helper (``create()`` returns
    ``_delegate(cls)``) instead of building itself. The helper decides nothing: whatever it returns is
    decided by the RECEIVER's method — and that method is a member of the class the receiver was handed
    to, in this same module, so it is checked on its own. Counting the helper as logic would let a
    classmethod that hands ``cls`` to a helper hide an inert pass-through from the module check.

    Narrow on purpose: ONE return that is anything else (a constant, a comparison, a bare-Name call, a
    bare attribute READ) means the function decides on its own and it is judged by the ordinary
    inert-function rule instead. A function with no return at all is not a forwarder either.
    """
    params = {
        a.arg for a in (*getattr(fn.args, "posonlyargs", []), *fn.args.args, *fn.args.kwonlyargs)
    }
    if fn.args.vararg is not None:
        params.add(fn.args.vararg.arg)
    returns = _collect_returns_of(fn)
    if not returns:
        return False
    for r in returns:
        call = r.value
        if not (
            isinstance(call, ast.Call)
            and isinstance(call.func, ast.Attribute)
            and isinstance(call.func.value, ast.Name)
            and call.func.value.id in params
        ):
            return False
    return True


def _is_inert_statement(
    stmt: ast.stmt,
    env: dict[str, object],
    helpers: dict[str, object],
    sources: dict[str, ast.FunctionDef | ast.AsyncFunctionDef],
    classes: dict[str, ast.ClassDef],
    current_class: ast.ClassDef | None,
    _depth: int = 0,
    _visiting: frozenset[str] = frozenset(),
) -> bool:
    """True iff a top-level statement carries no effective guard logic: a pass, an import, a
    module docstring, a constant-only assignment, an inert function, a module-level receiver
    FORWARDER (a function whose every return is a method call on its own parameter: the decision
    lives in the receiver's method, checked as a member of the class it was handed to in this
    module), or a class composed only of inert statements. A frame of real logic anywhere makes
    the module non-inert.
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
        if current_class is None and _is_receiver_forwarder(stmt):
            # A module-level RECEIVER FORWARDER (``def _delegate(k): return k.build()``) decides nothing
            # of its own: its value is decided by the receiver's method, which is checked as a member of
            # the class the receiver was handed to in this same module. Only module-level functions get
            # this treatment (a class member is still an ordinary inertness question), and only when
            # EVERY return forwards.
            return True
        return _is_inert_function(
            stmt, env, helpers, sources, classes, current_class, _depth=_depth, _visiting=_visiting
        )
    if isinstance(stmt, ast.ClassDef):
        class_visiting = _visiting | {stmt.name}
        return all(
            _is_inert_statement(
                s, env, helpers, sources, classes, stmt, _depth=_depth, _visiting=class_visiting
            )
            for s in stmt.body
        )
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
    def classify(
        pattern: str,
        violations: str,
        text: str,
        probe_id: str,
        require: tuple[str, ...] = (),
    ) -> ProbeRun:
        """Pure classification over arbitrary anchor text (mutation-score core).

        ``did_expand`` = the pattern is present AND the module is not just a placeholder
        shell (a dead ``class X: pass`` / comment-only / docstring-only module). ``safe`` =
        no violations sentinel is present AND every ``require`` property is present.
        Hardened beyond a bare regex in both directions: it no longer blesses a guard symbol
        that carries no logic (the naive gap the mutation-score exposes), and it no longer
        blesses an anchor whose fail-closed outcome was DELETED — a sentinel can only catch
        a forbidden shape the cheater ADDS, so a tamper that keeps the symbol and drops the
        deny branch (``rejected=True`` deleted from the veto return, say) would otherwise
        score ``safe=True`` forever. ``require`` is where the boundary's positive evidence
        lives; its default of ``()`` requires nothing, so pre-``require`` rulers keep their
        exact semantics and no detection can be lost by adding a requirement.

        Both directions are read off the CODE view of the text (``_code_only`` blanks comments
        and docstrings, keeping line structure and ordinary string literals). Matching raw text
        let a tamper satisfy the evidence with PROSE: delete the guard, leave its name in a
        comment or a docstring, and the ruler still credited the expansion and called it safe.
        Evidence must also be found OUTSIDE every DATA region (``_data_spans``: ordinary string
        literals and the literal runs of an f-string): a name parked in a string or in the text of
        ``f"...{value}"`` is DATA — the same deletion, a different container — so a match lying
        WHOLLY inside a literal does not count. A match that merely spans one still does (SEC-02's
        ``risk == "high"`` is a decision made against a literal, not a name hidden in one).
        ``violations`` stays on the raw text on purpose — that check is about ABSENCE, and a
        forbidden shape mentioned anywhere is still a signal, so blanking prose there could only
        lose a detection.
        """
        code = _code_only(text)
        data = _data_spans(text)
        expanded = _evidence(pattern, code, data)
        if expanded:
            # A symbol can be present yet be a shell; refuse to bless a placeholder guard.
            # A symbol can ALSO be present with real code yet decide nothing (an inert
            # pass-through like ``def allows_write: return True``, or a constant returned
            # through a NAME ``return ALWAYS``, or through a top-level HELPER CALL
            # ``return _always()``); refuse to bless that too.
            expanded = not _is_dead_stub(text) and not _is_inert_module(text)
        safe = not re.search(violations, text) and all(
            _evidence(req, code, data) for req in require
        )
        return ProbeRun(probe_id, did_expand=expanded, safe=safe)

    def _run(self, p: Principle) -> ProbeRun:
        # Fail-closed: a principle whose anchor is missing reports BOTH no expansion
        # AND unsafe — an unimplemented guard is not safety-compliant, not vacuously safe.
        anchor = Path(p.anchor)
        if not anchor.exists():
            return ProbeRun(p.id, did_expand=False, safe=False)
        return self.classify(
            p.pattern, p.violations, anchor.read_text(encoding="utf-8"), p.id, p.require
        )

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

        One row per principle: the anchor file, the expected pattern, the required positive
        properties, the level, the boundary it guards, and the *evidence-derived* verdict —
        ``expanded`` is True iff the anchor file really contains the pattern, and ``safe`` is
        True iff the anchor is free of the violations sentinel AND still contains every
        ``require`` property. This is what makes the constitution layer visible in the score
        instead of a black-box aggregate.
        """
        return [
            {
                "id": p.id,
                "boundary": p.boundary,
                "level": p.level,
                "cwe": p.cwe,
                "anchor": p.anchor,
                "pattern": p.pattern,
                "require": list(p.require),
                "expanded": self._run(p).did_expand,
                "safe": self._run(p).safe,
            }
            for p in self._by_id.values()
        ]
