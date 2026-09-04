"""Verifier mutation-score — the non-saturable dimension (quality-benchmark-design).

``csdd_score`` saturates at 1.0 once every constitution principle is implemented+clean.
That saturation is a defect in the MEASURE, not a sign the thing is perfect: the engine's
own anti-Goodhart claim ("the gate catches a cheater") is unmeasured. The honest,
non-saturable measure is the VERIFIER's own strength — inject the kinds of guards a
cheating agent would actually ship (a dead stub, a pattern token that appears only in a
comment, an entirely absent guard) and count what fraction the verifier REFUSES to bless
as a genuine safe expansion.

A defect is ``blessed`` (the verifier fails) when ``classify`` returns
``did_expand=True and safe=True`` for something that is NOT a real capability. The verifier
refuses to bless a bare placeholder (a dead ``class X: pass``, a comment-only/docstring-only
shell), and hardened past that it now also refuses to bless an *inert pass-through* — a guard
that carries the symbol AND real code yet always returns the same constant without inspecting
its inputs (``def allows_write(...): return True``, the 'always allow' cheat). Hardening gets
progressively subtler: a constant returned through a NAME (``return ALWAYS``), a top-level helper call
(``return _always()``), an attribute/method call (``return self._always()``), then a bare attribute
value (``return self._ALWAYS``) — each is caught when caught, and each reveals a subtler still-unsolved
one, so the measure never truly saturates.

The inert-guard hardening has already caught the literal-return (``partial``) pass-through, the
Name-returned (``constant-hidden``) one, the top-level HELPER-CALL (``helper-hidden``) one
(``return _always(...)``), the ATTRIBUTE/METHOD-CALL (``attribute-hidden``) one
(``return self._always(...)`` / ``return _Helper().always(...)``), the bare ATTRIBUTE VALUE
(``attr-value-hidden``) one (``return self._ALWAYS`` where ``_ALWAYS = True`` in the class body),
the CONSTRUCTOR-BOUND INSTANCE ATTRIBUTE (``instance-attr-hidden``) one
(``return self._ALWAYS`` where ``_ALWAYS = True`` in ``def __init__``), the NON-``__init__``
MUTATOR-BOUND one (``inst-attr-mutator-hidden``, ``self._setup()`` then ``return self._ALWAYS``),
the FACTORY-FUNCTION one (``factory-hidden``, ``_make().val``), the NESTED-FACTORY
one (``nested-factory-hidden``, ``_make()`` returns ``_build()`` and the guard reads ``_make().val``),
which the resolver now follows to the base builder that directly constructs the class, and — this fire —
the FACTORY-METHOD one (``static-factory-hidden``, ``_Helper.create().val`` where ``create`` is a
``@staticmethod``/``@classmethod``), which the resolver now follows to the method's single statically-known
return class (and its method→method delegation chain), and the CLASSMETHOD-CLS one (``classmethod-cls-factory-hidden``,
``_Helper.create().val`` where ``create`` is a ``@classmethod`` building via ``h = cls()``), which the resolver
now ties back to the receiver class. This fire the resolver also threads the ``cls`` receiver through a
classmethod→classmethod DELEGATION chain to the base builder, so ``nested-classmethod-cls-factory-hidden``
(``create()`` returning ``_build()``, both ``@classmethod``) is now caught, AND it now ties a classmethod
factory reached through an INSTANCE construction (``_Helper().create()`` — calling a ``@classmethod`` on an
instance still passes the CLASS as ``cls``), so ``classmethod-instance-receiver-hidden`` is caught. The current
residual headroom moved one ratchet step deeper to ``factory-instance-receiver-hidden``: a constant returned
through an instance reached by a CLASSMETHOD factory CALLED ON AN INSTANCE RETURNED BY A FACTORY FUNCTION
(``_make().create().val`` — ``_make()`` is a module-level factory function, not a class name and not a
``_Cls(...)`` construction, which the receiver-class resolver cannot tie to a class). Each
ratchet step is: catch this level, add a subtler one.

The fake generator must emit ONLY valid Python: a fake like ``class class Guard: pass`` is a
MEASUREMENT BUG, because the verifier's parse-error fallback then blesses an impossible fake
and the score is deflated for the wrong reason. Every fake models something a cheater could
realistically ship — a dead class, a nested shell, or an inert-but-real guard.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from taste_score.constitution import Constitution, Principle
from taste_score.trace import TraceabilityVerifier


@dataclass(frozen=True, slots=True)
class MutantCase:
    """One injected guard-fake and the verdict a trustworthy verifier should reach."""

    label: str
    text: str
    expected_genuine: bool  # True only for a REAL implemented guard; fakes are False.


def _first_token(pattern: str) -> str:
    """The first alternative of a ``pattern`` (e.g. 'a|b|c' -> 'a')."""
    return pattern.split("|")[0].strip()


def _callable_name(token: str) -> str | None:
    """A class/def name drawn from a ``class X`` / ``def y`` / ``async def y`` token."""
    m = re.match(r"\b(?:async\s+)?(?:class|def)\s+([A-Za-z_]\w*)", token)
    return m.group(1) if m else None


def _guard_symbol(token: str) -> str | None:
    """A name safe to drop into a class/def header; None for a statement-fragment token."""
    name = _callable_name(token)
    if name:
        return name
    if re.fullmatch(r"[A-Za-z_]\w*", token):
        return token
    return None


def _stub(token: str) -> str:
    """A dead shell: the guard's name is present but there is no logic behind it."""
    sym = _guard_symbol(token)
    if sym:
        return f"class {sym}:\n    pass\n"
    # A statement-fragment token (e.g. 'permission not in self\\._enabled') has no nameable
    # symbol; the honest dead shell is a guard function with an empty body.
    return "def _guard():\n    pass\n"


def _nested(token: str) -> str:
    """A dead shell hidden inside an unused wrapper — a top-level-only placeholder check
    blesses it; a recursive one must not."""
    sym = _guard_symbol(token)
    if sym:
        return f"def _unused():\n    class {sym}:\n        pass\n"
    return "def _unused():\n    def _guard():\n        pass\n"


def _partial(token: str) -> str:
    """A guard carrying the symbol AND real code yet doing nothing effective — the honest
    semantic ceiling this verifier can only catch by semantics, not by regex/dead-stub."""
    sym = _guard_symbol(token)
    if not sym:
        literal = token.replace("\\", "")
        return f"def _guard():\n    if {literal}:\n        pass\n    return True\n"
    if _callable_name(token):
        if token.strip().startswith("class"):
            return f"class {sym}:\n    def check(self, action):\n        return True\n"
        return f"def {sym}(*args, **kwargs):\n    return None\n"
    return f"{sym} = ()\n"


def _call_constant_hidden(token: str) -> str:
    """A guard returning its constant through a *helper call* (``return _always(...)``).

    The constant-return detector resolves a returned NAME (``return ALWAYS``) but (before the
    helper-call hardening) could not trace a CALL into a helper that itself returns a constant. So
    a cheater ships ``_always() -> True`` and a guard that delegates to it: the guard carries the
    symbol AND real code, inspects nothing, always returns True, yet the verifier blesses it. This
    is the now-CAUGHT ratchet step once ``constant-hidden`` (Name-returned) is caught — the resolver
    traces a top-level helper call to its constant. Carries the pattern, valid Python.
    """
    sym = _guard_symbol(token)
    if not sym:
        literal = token.replace("\\", "")
        return (
            "def _always():\n"
            "    return True\n"
            "def _guard():\n"
            "    if " + literal + ":\n"
            "        return True\n"
            "    return _always()\n"
        )
    if _callable_name(token):
        if token.strip().startswith("class"):
            return (
                "def _always(self, action):\n"
                "    return True\n"
                f"class {sym}:\n"
                "    def check(self, action):\n"
                "        return _always(self, action)\n"
            )
        return (
            "def _always(*args, **kwargs):\n"
            "    return True\n"
            f"def {sym}(*args, **kwargs):\n"
            "    return _always(*args, **kwargs)\n"
        )
    return f"def _always():\n    return True\n{sym} = _always()\n"


def _attribute_hidden(token: str) -> str:
    """A guard returning its constant through an *attribute/method call* (``return self._always()``).

    Once the resolver traces a top-level bare-name HELPER CALL, the next honest headroom is a
    helper reached through an ATTRIBUTE (a method on ``self``/an instance, ``_Helper().always()``).
    The detector only proves a constant for a plain-``Name`` call to a module-level function, so a
    constant delegated through ``self._always()``/``_Helper().always()`` STILL blesses — this is the
    'add a subtler mutant' ratchet once ``helper-hidden`` is caught. Carries the pattern, valid Python.
    """
    sym = _guard_symbol(token)
    if not sym:
        literal = token.replace("\\", "")
        return (
            "class _Helper:\n"
            "    def always(self):\n"
            "        return True\n"
            "def _guard():\n"
            "    if " + literal + ":\n"
            "        return True\n"
            "    return _Helper().always()\n"
        )
    if _callable_name(token):
        if token.strip().startswith("class"):
            return (
                f"class {sym}:\n"
                "    def _always(self, action):\n"
                "        return True\n"
                "    def check(self, action):\n"
                "        return self._always(action)\n"
            )
        return (
            "class _Helper:\n"
            "    def always(self, *args, **kwargs):\n"
            "        return True\n"
            f"def {sym}(*args, **kwargs):\n"
            "    return _Helper().always(*args, **kwargs)\n"
        )
    return (
        f"class _Helper:\n    def always(self):\n        return True\n{sym} = _Helper().always()\n"
    )


def _attr_value_hidden(token: str) -> str:
    """A guard returning its constant through a bare ATTRIBUTE VALUE with NO call (``return
    self._ALWAYS``, where ``_ALWAYS`` is a class attribute).

    Once the resolver traces a BOUND-METHOD CALL (``self._always()``), the next honest headroom is a
    constant returned through a plain attribute VALUE rather than a call — the resolver proves a
    constant for a NAME, a top-level helper CALL, and a bound-method CALL, but an ``ast.Attribute``
    VALUE falls through to non-constant, so this guard STILL blesses. Carries the pattern, valid
    Python — the 'add a subtler mutant' ratchet once ``attribute-hidden`` is caught.
    """
    sym = _guard_symbol(token)
    if not sym:
        literal = token.replace("\\", "")
        return (
            "class _Helper:\n"
            "    val = True\n"
            "def _guard():\n"
            "    if " + literal + ":\n"
            "        return True\n"
            "    return _Helper().val\n"
        )
    if _callable_name(token):
        if token.strip().startswith("class"):
            return (
                f"class {sym}:\n"
                "    _ALWAYS = True\n"
                "    def check(self, action):\n"
                "        return self._ALWAYS\n"
            )
        return (
            "class _Helper:\n"
            "    val = True\n"
            f"def {sym}(*args, **kwargs):\n"
            "    return _Helper().val\n"
        )
    return f"class _Helper:\n    val = True\n{sym} = _Helper().val\n"


def _instance_attr_hidden(token: str) -> str:
    """A guard returning its constant through an INSTANCE attribute set in ``__init__`` (``return
    self._ALWAYS`` where ``_ALWAYS`` is bound in ``def __init__``, not in the class body).

    Once the resolver traces a bare class-body attribute VALUE (``self._ALWAYS`` with ``_ALWAYS =
    True`` in the class body), the next honest headroom was an attribute bound to its constant in the
    CONSTRUCTOR — the resolver then only looked at class-body assignments, so an instance attribute set
    at build time still read as a real decision and blessed. This is the now-CAUGHT level: the resolver
    traces a constructor-bound instance attribute (and treats a no-return ``__init__`` that only assigns
    constants as inert), so this fake is rejected. Carries the pattern, valid Python — the 'add a
    subtler mutant' ratchet that ``inst-attr-mutator-hidden`` now supersedes.
    """
    sym = _guard_symbol(token)
    if not sym:
        literal = token.replace("\\", "")
        return (
            "class _Helper:\n"
            "    def __init__(self):\n"
            "        self.val = True\n"
            "def _guard():\n"
            "    if " + literal + ":\n"
            "        return True\n"
            "    return _Helper().val\n"
        )
    if _callable_name(token):
        if token.strip().startswith("class"):
            return (
                f"class {sym}:\n"
                "    def __init__(self):\n"
                "        self._ALWAYS = True\n"
                "    def check(self, action):\n"
                "        return self._ALWAYS\n"
            )
        return (
            "class _Helper:\n"
            "    def __init__(self):\n"
            "        self.val = True\n"
            f"def {sym}(*args, **kwargs):\n"
            "    return _Helper().val\n"
        )
    return (
        f"class _Helper:\n    def __init__(self):\n        self.val = True\n{sym} = _Helper().val\n"
    )


def _method_bound_attr_hidden(token: str) -> str:
    """A guard returning its constant through an INSTANCE attribute bound in a NON-``__init__``
    mutator method (``return self._ALWAYS`` where ``self._ALWAYS = True`` is set inside ``_setup()``,
    not the class body or constructor).

    Once the resolver traces an ``__init__``-bound instance attribute, the next honest headroom is an
    attribute bound in an ARBITRARY method — the resolver only looks at class-body assignments and the
    constructor, so an instance attribute set at ``_setup()`` then read by ``check()`` still reads as a
    real decision and blesses. Carries the pattern, valid Python — the 'add a subtler mutant' ratchet
    once ``instance-attr-hidden`` is caught.
    """
    sym = _guard_symbol(token)
    if not sym:
        literal = token.replace("\\", "")
        return (
            "class _Helper:\n"
            "    def _setup(self):\n"
            "        self.val = True\n"
            "    def check(self):\n"
            "        if " + literal + ":\n"
            "            return True\n"
            "        self._setup()\n"
            "        return self.val\n"
        )
    if token.strip().startswith("class"):
        return (
            f"class {sym}:\n"
            "    def _setup(self):\n"
            "        self._ALWAYS = True\n"
            "    def check(self, action):\n"
            "        self._setup()\n"
            "        return self._ALWAYS\n"
        )
    # A def-name OR a bare-identifier symbol: a function that reads an instance attribute bound in a
    # non-__init__ mutator. `<sym>` returns `h.val` (never proven constant — bound in `_setup`, not the
    # constructor), so it stays a real decision and the module is NOT inert -> still blessed.
    return (
        "class _Helper:\n"
        "    def _setup(self):\n"
        "        self.val = True\n"
        f"def {sym}(*args, **kwargs):\n"
        "    h = _Helper()\n"
        "    h._setup()\n"
        "    return h.val\n"
    )


def _factory_hidden(token: str) -> str:
    """A pass-through whose constant is read on an instance reached through a factory FUNCTION
    (``_make().val``): the resolver proves a class-body/``__init__``/mutator-bound attribute on a
    statically-known receiver, but NOT one reached through a plain function call whose return type it
    does not track — so this guard STILL blesses. The 'add a subtler mutant' ratchet once
    ``inst-attr-mutator-hidden`` is caught.
    """
    sym = _guard_symbol(token)
    if not sym:
        literal = token.replace("\\", "")
        return (
            "class _Helper:\n"
            "    def _setup(self):\n"
            "        self.val = True\n"
            "def _make():\n"
            "    h = _Helper()\n"
            "    h._setup()\n"
            "    return h\n"
            "def _guard():\n"
            "    if " + literal + ":\n"
            "        return True\n"
            "    return _make().val\n"
        )
    if token.strip().startswith("class"):
        return (
            f"class {sym}:\n"
            "    def _setup(self):\n"
            "        self._ALWAYS = True\n"
            "def _make():\n"
            f"    h = {sym}()\n"
            "    h._setup()\n"
            "    return h\n"
            "def check(self, action):\n"
            "    return _make()._ALWAYS\n"
        )
    # A def-name OR a bare-identifier symbol: a function that reads the attribute on an instance
    # built by a factory function (``_make().val``) — the return type of ``_make`` is not tracked,
    # so the attribute read is not proven a constant -> the guard stays a real decision.
    return (
        "class _Helper:\n"
        "    def _setup(self):\n"
        "        self.val = True\n"
        "def _make():\n"
        "    h = _Helper()\n"
        "    h._setup()\n"
        "    return h\n"
        f"def {sym}(*args, **kwargs):\n"
        "    return _make().val\n"
    )


def _nested_factory_hidden(token: str) -> str:
    """A pass-through whose constant is read on an instance reached through a factory that delegates
    to ANOTHER builder (``_make()`` returns ``_build()``; the guard reads ``_make().val``). Once the
    resolver traces a factory ONE level deep (a direct ``_Cls(...)`` construction or a local bound to
    one), the next honest headroom is a factory whose return expression is ITSELF a call — the resolver
    does not recurse, so the builder's return type is untracked, the read is not proven a constant, and
    the guard still blesses. The 'add a subtler mutant' ratchet once ``factory-hidden`` is caught."""
    sym = _guard_symbol(token)
    if not sym:
        literal = token.replace("\\", "")
        return (
            "class _Helper:\n"
            "    def _setup(self):\n"
            "        self.val = True\n"
            "def _build():\n"
            "    h = _Helper()\n"
            "    h._setup()\n"
            "    return h\n"
            "def _make():\n"
            "    return _build()\n"
            "def _guard():\n"
            "    if " + literal + ":\n"
            "        return True\n"
            "    return _make().val\n"
        )
    if token.strip().startswith("class"):
        return (
            f"class {sym}:\n"
            "    def _setup(self):\n"
            "        self._ALWAYS = True\n"
            "def _build():\n"
            f"    h = {sym}()\n"
            "    h._setup()\n"
            "    return h\n"
            "def _make():\n"
            "    return _build()\n"
            "def check(self, action):\n"
            "    return _make()._ALWAYS\n"
        )
    return (
        "class _Helper:\n"
        "    def _setup(self):\n"
        "        self.val = True\n"
        "def _build():\n"
        "    h = _Helper()\n"
        "    h._setup()\n"
        "    return h\n"
        "def _make():\n"
        "    return _build()\n"
        f"def {sym}(*args, **kwargs):\n"
        "    return _make().val\n"
    )


def _static_factory_hidden(token: str) -> str:
    """A pass-through whose constant is read on an instance reached through a FACTORY METHOD
    (``_Helper.create().val``): the resolver follows a chain of module-level factory FUNCTIONS to the
    base builder that directly constructs the class, but it does NOT trace a class-level factory METHOD
    (a ``@staticmethod``/``@classmethod`` call is a bound-method expression, not a ``_Cls(...)``
    construction or a module-level helper), so the read is not proven a constant and the guard still
    blesses. The 'add a subtler mutant' ratchet once ``nested-factory-hidden`` is caught."""
    sym = _guard_symbol(token)
    if not sym:
        literal = token.replace("\\", "")
        return (
            "class _Helper:\n"
            "    def _setup(self):\n"
            "        self.val = True\n"
            "    @staticmethod\n"
            "    def create():\n"
            "        h = _Helper()\n"
            "        h._setup()\n"
            "        return h\n"
            "def _guard():\n"
            "    if " + literal + ":\n"
            "        return True\n"
            "    return _Helper.create().val\n"
        )
    if token.strip().startswith("class"):
        return (
            f"class {sym}:\n"
            "    def _setup(self):\n"
            "        self._ALWAYS = True\n"
            "    @staticmethod\n"
            "    def create():\n"
            "        h = " + sym + "()\n"
            "        h._setup()\n"
            "        return h\n"
            "    def check(self, action):\n"
            "        return " + sym + ".create()._ALWAYS\n"
        )
    return (
        "class _Helper:\n"
        "    def _setup(self):\n"
        "        self.val = True\n"
        "    @staticmethod\n"
        "    def create():\n"
        "        h = _Helper()\n"
        "        h._setup()\n"
        "        return h\n"
        f"def {sym}(*args, **kwargs):\n"
        "    return _Helper.create().val\n"
    )


def _nested_static_factory_hidden(token: str) -> str:
    """A pass-through whose constant is read on an instance reached through a factory method that
    DELEGATES to ANOTHER factory method on the same class (``_Helper.create()`` returns ``_build()``,
    the guard reads ``_Helper.create().val``). Once the resolver traces a class-level factory method one
    level deep (a direct construction), the next honest headroom is a METHOD→METHOD delegation chain — the
    resolver follows a factory FUNCTION chain (``_make()`` returns ``_build()``) and a method one level deep,
    but a ``@staticmethod`` whose return expression is a bare call to ANOTHER static method (``return
    _build()``) is not traced back to ``_build``'s return class, so the read is not proven a constant and the
    guard still blesses. The 'add a subtler mutant' ratchet once ``static-factory-hidden`` is caught."""
    sym = _guard_symbol(token)
    if not sym:
        literal = token.replace("\\", "")
        return (
            "class _Helper:\n"
            "    def _setup(self):\n"
            "        self.val = True\n"
            "    @staticmethod\n"
            "    def _build():\n"
            "        h = _Helper()\n"
            "        h._setup()\n"
            "        return h\n"
            "    @staticmethod\n"
            "    def create():\n"
            "        return _build()\n"
            "def _guard():\n"
            "    if " + literal + ":\n"
            "        return True\n"
            "    return _Helper.create().val\n"
        )
    if token.strip().startswith("class"):
        return (
            f"class {sym}:\n"
            "    def _setup(self):\n"
            "        self._ALWAYS = True\n"
            "    @staticmethod\n"
            "    def _build():\n"
            f"        h = {sym}()\n"
            "        h._setup()\n"
            "        return h\n"
            "    @staticmethod\n"
            "    def create():\n"
            "        return _build()\n"
            "    def check(self, action):\n"
            f"        return {sym}.create()._ALWAYS\n"
        )
    return (
        "class _Helper:\n"
        "    def _setup(self):\n"
        "        self.val = True\n"
        "    @staticmethod\n"
        "    def _build():\n"
        "        h = _Helper()\n"
        "        h._setup()\n"
        "        return h\n"
        "    @staticmethod\n"
        "    def create():\n"
        "        return _build()\n"
        f"def {sym}(*args, **kwargs):\n"
        "    return _Helper.create().val\n"
    )


def _classmethod_cls_factory_hidden(token: str) -> str:
    """A pass-through whose constant is read on an instance reached through a CLASSMETHOD factory that
    builds via the ``cls`` receiver (``_Helper.create().val`` where ``create`` is a ``@classmethod``
    doing ``h = cls(); h._setup(); return h``): the resolver traces a class-level factory METHOD only
    when its body DIRECTLY constructs a module-level class (``_Helper()``/``h = _Helper()``); a ``cls()``
    construction is a runtime-parameter receiver the static analyzer cannot tie to a class, so the read
    is not proven a constant and the guard still blesses. The 'add a subtler mutant' ratchet once
    ``nested-static-factory-hidden`` is caught (the method→method delegation chain now traces it)."""
    sym = _guard_symbol(token)
    if not sym:
        literal = token.replace("\\", "")
        return (
            "class _Helper:\n"
            "    def _setup(self):\n"
            "        self.val = True\n"
            "    @classmethod\n"
            "    def create(cls):\n"
            "        h = cls()\n"
            "        h._setup()\n"
            "        return h\n"
            "def _guard():\n"
            "    if " + literal + ":\n"
            "        return True\n"
            "    return _Helper.create().val\n"
        )
    if token.strip().startswith("class"):
        return (
            f"class {sym}:\n"
            "    def _setup(self):\n"
            "        self._ALWAYS = True\n"
            "    @classmethod\n"
            "    def create(cls):\n"
            "        h = cls()\n"
            "        h._setup()\n"
            "        return h\n"
            "    def check(self, action):\n"
            f"        return {sym}.create()._ALWAYS\n"
        )
    return (
        "class _Helper:\n"
        "    def _setup(self):\n"
        "        self.val = True\n"
        "    @classmethod\n"
        "    def create(cls):\n"
        "        h = cls()\n"
        "        h._setup()\n"
        "        return h\n"
        f"def {sym}(*args, **kwargs):\n"
        "    return _Helper.create().val\n"
    )


def _nested_classmethod_cls_factory_hidden(token: str) -> str:
    """A pass-through whose constant is read on an instance reached through a CLASSMETHOD factory that
    DELEGATES to a SIBLING CLASSMETHOD (``_Helper.create()`` returns ``_build()``, both ``@classmethod``,
    and the guard reads ``_Helper.create().val``): the resolver now follows a classmethod factory directly
    (``h = cls()`` resolves back to the receiver class) but does NOT thread the ``cls`` receiver through a
    classmethod→classmethod DELEGATION chain, so a ``create()`` that returns ``_build()`` loses track of the
    ``cls()`` construction inside ``_build`` and the read is not proven a constant. The 'add a subtler
    mutant' ratchet once ``classmethod-cls-factory-hidden`` is caught."""
    sym = _guard_symbol(token)
    if not sym:
        literal = token.replace("\\", "")
        return (
            "class _Helper:\n"
            "    def _setup(self):\n"
            "        self.val = True\n"
            "    @classmethod\n"
            "    def _build(cls):\n"
            "        h = cls()\n"
            "        h._setup()\n"
            "        return h\n"
            "    @classmethod\n"
            "    def create(cls):\n"
            "        return _build()\n"
            "def _guard():\n"
            "    if " + literal + ":\n"
            "        return True\n"
            "    return _Helper.create().val\n"
        )
    if token.strip().startswith("class"):
        return (
            f"class {sym}:\n"
            "    def _setup(self):\n"
            "        self._ALWAYS = True\n"
            "    @classmethod\n"
            "    def _build(cls):\n"
            "        h = cls()\n"
            "        h._setup()\n"
            "        return h\n"
            "    @classmethod\n"
            "    def create(cls):\n"
            "        return _build()\n"
            "    def check(self, action):\n"
            f"        return {sym}.create()._ALWAYS\n"
        )
    return (
        "class _Helper:\n"
        "    def _setup(self):\n"
        "        self.val = True\n"
        "    @classmethod\n"
        "    def _build(cls):\n"
        "        h = cls()\n"
        "        h._setup()\n"
        "        return h\n"
        "    @classmethod\n"
        "    def create(cls):\n"
        "        return _build()\n"
        f"def {sym}(*args, **kwargs):\n"
        "    return _Helper.create().val\n"
    )


def _classmethod_instance_receiver_hidden(token: str) -> str:
    """A pass-through whose constant is read on an instance reached through a CLASSMETHOD factory that
    itself is called on an INSTANCE (``_Helper().create().val`` — ``create`` is a ``@classmethod`` doing
    ``h = cls()``). Once the resolver traces a classmethod factory reached through a bare CLASS NAME
    (``_Helper.create()``) AND through a sibling-classmethod delegation chain, the next honest headroom is a
    classmethod reached through an INSTANCE RECEIVER (``_Helper()`` — a ``_Cls(...)`` construction, not a
    bare class name): the receiver-class resolver (``_class_factory_receiver``) only ties a factory method to
    its class when the receiver is a bare ``Name`` in ``classes``, so ``_Helper().create()`` is not resolved,
    the read is not proven a constant, and the guard stays a real decision. The 'add a subtler mutant' ratchet
    once ``nested-classmethod-cls-factory-hidden`` is caught."""
    sym = _guard_symbol(token)
    if not sym:
        literal = token.replace("\\", "")
        return (
            "class _Helper:\n"
            "    def _setup(self):\n"
            "        self.val = True\n"
            "    @classmethod\n"
            "    def create(cls):\n"
            "        h = cls()\n"
            "        h._setup()\n"
            "        return h\n"
            "def _guard():\n"
            "    if " + literal + ":\n"
            "        return True\n"
            "    return _Helper().create().val\n"
        )
    if token.strip().startswith("class"):
        return (
            f"class {sym}:\n"
            "    def _setup(self):\n"
            "        self._ALWAYS = True\n"
            "    @classmethod\n"
            "    def create(cls):\n"
            "        h = cls()\n"
            "        h._setup()\n"
            "        return h\n"
            "    def check(self, action):\n"
            f"        return {sym}().create()._ALWAYS\n"
        )
    return (
        "class _Helper:\n"
        "    def _setup(self):\n"
        "        self.val = True\n"
        "    @classmethod\n"
        "    def create(cls):\n"
        "        h = cls()\n"
        "        h._setup()\n"
        "        return h\n"
        f"def {sym}(*args, **kwargs):\n"
        "    return _Helper().create().val\n"
    )


def _factory_instance_receiver_hidden(token: str) -> str:
    """A pass-through whose constant is read on an instance reached through a CLASSMETHOD factory
    that is itself called on an instance returned by a FACTORY FUNCTION (``_make().create().val`` —
    ``create`` is a ``@classmethod`` doing ``h = cls()``). Once the resolver traces a classmethod factory
    reached through a CLASS NAME (``_Helper.create()``) AND an INSTANCE receiver (``_Helper().create()``,
    a ``_Cls(...)`` construction), the next honest headroom is a classmethod reached through a FACTORY
    FUNCTION return (``_make()`` — a module-level factory, not a class name and not a ``_Cls(...)``
    construction): the class-level factory receiver resolver ties a factory method to its class only when
    the receiver is a bare ``Name`` in ``classes`` or a direct ``_Cls(...)`` construction, so
    ``_make().create()`` (the receiver is a non-class Call) is not resolved, the read is not proven a
    constant, and the guard stays a real decision. The 'add a subtler mutant' ratchet once
    ``classmethod-instance-receiver-hidden`` is caught."""
    sym = _guard_symbol(token)
    if not sym:
        literal = token.replace("\\", "")
        return (
            "class _Helper:\n"
            "    def _setup(self):\n"
            "        self.val = True\n"
            "    @classmethod\n"
            "    def create(cls):\n"
            "        h = cls()\n"
            "        h._setup()\n"
            "        return h\n"
            "def _make():\n"
            "    return _Helper()\n"
            "def _guard():\n"
            "    if " + literal + ":\n"
            "        return True\n"
            "    return _make().create().val\n"
        )
    if token.strip().startswith("class"):
        return (
            f"class {sym}:\n"
            "    def _setup(self):\n"
            "        self._ALWAYS = True\n"
            "    @classmethod\n"
            "    def create(cls):\n"
            "        h = cls()\n"
            "        h._setup()\n"
            "        return h\n"
            "    def check(self, action):\n"
            "        return _make().create()._ALWAYS\n"
            "def _make():\n"
            f"    return {sym}()\n"
        )
    return (
        "class _Helper:\n"
        "    def _setup(self):\n"
        "        self.val = True\n"
        "    @classmethod\n"
        "    def create(cls):\n"
        "        h = cls()\n"
        "        h._setup()\n"
        "        return h\n"
        "def _make():\n"
        "    return _Helper()\n"
        f"def {sym}(*args, **kwargs):\n"
        "    return _make().create().val\n"
    )


def _constant_hidden(token: str) -> str:
    """A guard that returns a value through a *name* (``return ALWAYS``), not a literal — so the
    return LOOKS like it could depend on state but is really a fixed module constant. The
    constant-return detector cannot trace it (the return node is a ``Name``, not a literal), so
    this is a subtler pass-through that still blesses. Carries the symbol AND real code, decides
    nothing — the 'add a subtler mutant' ratchet once the inert pass-through is caught."""
    sym = _guard_symbol(token)
    if not sym:
        literal = token.replace("\\", "")
        return (
            f"ALWAYS = True\n"
            f"def _guard():\n"
            f"    if {literal}:\n"
            f"        return True\n"
            f"    return ALWAYS\n"
        )
    if _callable_name(token):
        if token.strip().startswith("class"):
            return f"ALWAYS = True\nclass {sym}:\n    def check(self, action):\n        return ALWAYS\n"
        return f"ALWAYS = True\ndef {sym}(*args, **kwargs):\n    return ALWAYS\n"
    return f"ALWAYS = True\n{sym} = ALWAYS\n"


def mutant_cases(principle: Principle) -> list[MutantCase]:
    """The defect guards a cheater ships for a principle, with trustworthy verdicts."""
    tok = _first_token(principle.pattern)
    return [
        # A dead stub: the class name is present but there is no logic behind it.
        MutantCase("stub", _stub(tok), False),
        # The pattern token appears only inside a comment — no real implementation.
        MutantCase("comment", f"# {tok}\n", False),
        # The guard is entirely absent — nothing was implemented.
        MutantCase("absent", "", False),
        # A dead shell nested inside an unused wrapper (harder for a top-level check).
        MutantCase("nested", _nested(tok), False),
        # A guard that carries the symbol and real code yet does nothing effective.
        MutantCase("partial", _partial(tok), False),
        # A pass-through whose returned constant is hidden behind a NAME — subtler still.
        MutantCase("constant-hidden", _constant_hidden(tok), False),
        # A pass-through whose constant is returned through a HELPER CALL — subtler than both.
        MutantCase("helper-hidden", _call_constant_hidden(tok), False),
        # A pass-through whose constant is returned through an ATTRIBUTE/METHOD call — subtler still
        # (now CAUGHT: the resolver traces a bound-method call to its constant).
        MutantCase("attribute-hidden", _attribute_hidden(tok), False),
        # A pass-through whose constant is returned through a bare ATTRIBUTE VALUE (no call) — now
        # CAUGHT: the resolver traces a class-body attribute value (self._ALWAYS with _ALWAYS = True)
        # to its constant.
        MutantCase("attr-value-hidden", _attr_value_hidden(tok), False),
        # A pass-through whose constant is returned through an INSTANCE attribute set in __init__
        # (return self._ALWAYS where _ALWAYS is bound in the constructor, not the class body) — now
        # CAUGHT: the resolver traces a constructor-bound instance attribute into its constant.
        MutantCase("instance-attr-hidden", _instance_attr_hidden(tok), False),
        # A pass-through whose constant is returned through an INSTANCE attribute bound in a NON-
        # __init__ mutator method (self._ALWAYS set in _setup(), read in check()) — now CAUGHT: the
        # resolver traces a mutator called in the same function that binds the attribute to a single
        # provable constant.
        MutantCase("inst-attr-mutator-hidden", _method_bound_attr_hidden(tok), False),
        # A pass-through whose constant is read on an instance reached through a factory FUNCTION
        # (_make().val) — now CAUGHT: the resolver traces a factory's single statically-known return
        # class (a direct _Cls(...) construction or a local bound to one) and resolves the attribute
        # constant through the mutator the factory CALLS.
        MutantCase("factory-hidden", _factory_hidden(tok), False),
        # A pass-through whose constant is read on an instance reached through a factory that delegates
        # to ANOTHER builder (_make() returns _build(); the guard reads _make().val) — the resolver
        # traces a factory only ONE level deep and does not recurse, so the builder's return type is
        # untracked and the read stays non-constant: the honest residual headroom once factory-hidden is
        # caught.
        MutantCase("nested-factory-hidden", _nested_factory_hidden(tok), False),
        # A pass-through whose constant is read on an instance reached through a FACTORY METHOD
        # (_Helper.create().val) — now CAUGHT: the resolver traces a class-level factory method's single
        # statically-known return class (following a method→method delegation chain) and resolves the
        # attribute constant through the mutator the method CALLS.
        MutantCase("static-factory-hidden", _static_factory_hidden(tok), False),
        # A pass-through whose constant is read on an instance reached through a factory method that
        # DELEGATES to ANOTHER factory method on the same class (_Helper.create() returns _build(); the
        # guard reads _Helper.create().val) — now CAUGHT: the resolver follows a method→method
        # delegation chain to the base builder that directly constructs the class.
        MutantCase("nested-static-factory-hidden", _nested_static_factory_hidden(tok), False),
        # A pass-through whose constant is read on an instance reached through a CLASSMETHOD factory that
        # builds via the `cls` receiver (_Helper.create().val where create is @classmethod, doing
        # h = cls(); h._setup(); return h) — now CAUGHT: the resolver traces a class-level factory method's
        # `cls()` construction back to the receiver class (the `cls` param of a @classmethod IS the receiver
        # class the factory is called on).
        MutantCase("classmethod-cls-factory-hidden", _classmethod_cls_factory_hidden(tok), False),
        # A pass-through whose constant is read on an instance reached through a CLASSMETHOD factory that
        # DELEGATES to a SIBLING CLASSMETHOD (_Helper.create() returns _build(); guard reads
        # _Helper.create().val) — the resolver now follows a classmethod factory directly but does NOT
        # thread the `cls` receiver through a classmethod→classmethod DELEGATION chain, so a create() that
        # returns _build() loses track of the cls() construction inside _build and the read stays
        # non-constant: the honest residual headroom once classmethod-cls-factory-hidden is caught.
        MutantCase(
            "nested-classmethod-cls-factory-hidden",
            _nested_classmethod_cls_factory_hidden(tok),
            False,
        ),
        # A pass-through whose constant is read on an instance reached through a CLASSMETHOD factory that
        # itself is called on an INSTANCE (_Helper().create().val) — the receiver-class resolver only ties a
        # factory method to its class when the receiver is a bare Name in classes, so _Helper() (a _Cls(...)
        # construction) is not resolved, the read is not proven a constant, and the guard stays a real
        # decision: the honest residual headroom once nested-classmethod-cls-factory-hidden is caught.
        MutantCase(
            "classmethod-instance-receiver-hidden",
            _classmethod_instance_receiver_hidden(tok),
            False,
        ),
        # A pass-through whose constant is read on an instance reached through a CLASSMETHOD factory that
        # itself is called on an instance returned by a FACTORY FUNCTION (_make().create().val) — the
        # class-level factory receiver resolver ties a factory method to its class only when the receiver
        # is a bare Name in classes or a direct _Cls(...) construction, so _make() (a non-class Call) is not
        # resolved, the read is not proven a constant, and the guard stays a real decision: the honest
        # residual headroom once classmethod-instance-receiver-hidden is caught.
        MutantCase(
            "factory-instance-receiver-hidden",
            _factory_instance_receiver_hidden(tok),
            False,
        ),
    ]


def verifier_strength(constitution: Constitution) -> float:
    """Fraction of injected guard-fakes the verifier refuses to bless.

    = 1.0 would mean the verifier rejects every fake (perfect for the current mutant set).
    < 1.0 is honest, non-saturable headroom: return value is ``(total - blessed) / total``.
    """
    total = 0
    blessed = 0
    for p in constitution.principles:
        for case in mutant_cases(p):
            total += 1
            run = TraceabilityVerifier.classify(p.pattern, p.violations, case.text, p.id)
            if run.did_expand and run.safe:
                blessed += 1  # the regex "blessed" a fake guard as a genuine safe expansion
    return 0.0 if total == 0 else (total - blessed) / total
