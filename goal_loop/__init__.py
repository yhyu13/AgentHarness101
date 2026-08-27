"""Goal loop harness: a self-running, durable, verifiable loop on top of
``goal_persistence``.

This package ports the ``/goal`` loop from ``learn-harness-engineering`` (Lecture 13 /
Project 07): a goal, a maker, an independent checker, machine verification, durable loop
state, and explicit stop conditions.
"""

from goal_loop.loop_runner import GoalLoopRunner
from goal_loop.models import (
    AcceptanceCriterion,
    CheckerOutput,
    FinalResult,
    GoalSpec,
    Issue,
    LoopState,
    MakerOutput,
    RoundRecord,
    Scope,
    Severity,
    StopCondition,
    VerificationResult,
    Verdict,
)
from goal_loop.roles import Checker, EchoMaker, Maker, StaticChecker
from goal_loop.verifier import CommandVerifier

__all__ = [
    "GoalLoopRunner",
    "AcceptanceCriterion",
    "CheckerOutput",
    "FinalResult",
    "GoalSpec",
    "Issue",
    "LoopState",
    "MakerOutput",
    "RoundRecord",
    "Scope",
    "Severity",
    "StopCondition",
    "VerificationResult",
    "Verdict",
    "Checker",
    "EchoMaker",
    "Maker",
    "StaticChecker",
    "CommandVerifier",
]
