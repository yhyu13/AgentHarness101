from __future__ import annotations

import enum
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional


class Verdict(str, enum.Enum):
    """Independent checker verdict for a round."""

    PASS = "pass"
    FAIL = "fail"
    ACCEPT_WITH_MINOR = "accept_with_minor"


class Severity(str, enum.Enum):
    """Severity of an issue reported by the checker."""

    CRITICAL = "critical"
    MEDIUM = "medium"
    MINOR = "minor"


@dataclass(frozen=True, slots=True)
class AcceptanceCriterion:
    """One machine-checkable "done" condition.

    A criterion is satisfied when its optional `verify_command` exits with code 0.
    When no command is provided, the criterion is satisfied only if the independent
    checker returns a non-FAIL verdict.
    """

    id: str
    description: str
    verify_command: Optional[str] = None


@dataclass(frozen=True, slots=True)
class Scope:
    """Advisory scope boundary for the maker.

    Human-authored intent, not a filesystem access-control layer. The runner does not
    enforce these paths; they are re-injected into the maker's steering context.
    """

    fair_game: list[str] = field(default_factory=list)
    hands_off: list[str] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class StopCondition:
    """One stopping rule for the loop.

    Kinds:
    - ``max_rounds``: stop without completing after ``value`` rounds.
    - ``budget_tokens`` / ``budget_wall_ms``: derived from the underlying
      ``goal_persistence`` goal budget; ``value`` is ignored for these kinds.

    The blocked audit is not a ``StopCondition`` because it is owned by
    ``goal_persistence``'s fixed three-strike rule, not by this spec.
    Completion is not a ``StopCondition`` either: it is the inherent success rule
    (every acceptance criterion verified + an independent non-FAIL verdict).
    """

    kind: str
    value: Optional[int] = None


@dataclass(slots=True)
class GoalSpec:
    """The whole goal description, ported from the source's ``goal-template.md``."""

    objective: str
    acceptance_criteria: list[AcceptanceCriterion]
    scope: Scope = field(default_factory=Scope)
    stop_conditions: list[StopCondition] = field(default_factory=list)
    how_to_work: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.objective.strip():
            raise ValueError("GoalSpec.objective must be non-empty")
        if not self.acceptance_criteria:
            raise ValueError("GoalSpec must have at least one acceptance criterion")

    @classmethod
    def from_markdown(cls, path: str | Path) -> "GoalSpec":
        """Parse a ``goal.md`` file into a ``GoalSpec``.

        The file must contain non-empty ``## Goal``, ``## Acceptance Criteria``, and
        ``## Stop Conditions`` sections; a missing or empty required section raises
        ``ValueError``. Acceptance criteria may carry a ``@verify <command>`` suffix to
        make them machine-checkable; without it, the independent checker decides.
        """
        return cls.from_text(Path(path).read_text(encoding="utf-8"))

    @classmethod
    def from_text(cls, text: str) -> "GoalSpec":
        sections = _split_sections(text)
        objective = _parse_objective(sections)
        criteria = _parse_criteria(sections)
        scope = _parse_scope(sections)
        stops = _parse_stop_conditions(sections)
        how_to_work = _parse_how_to_work(sections)
        return cls(
            objective=objective,
            acceptance_criteria=criteria,
            scope=scope,
            stop_conditions=stops,
            how_to_work=how_to_work,
        )


@dataclass(frozen=True, slots=True)
class VerificationResult:
    """Structured evidence from running one verification command."""

    command: str
    returncode: int
    timed_out: bool
    stdout: str
    stderr: str

    @property
    def ok(self) -> bool:
        return self.returncode == 0 and not self.timed_out

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "VerificationResult":
        return cls(
            command=data["command"],
            returncode=data["returncode"],
            timed_out=data["timed_out"],
            stdout=data["stdout"],
            stderr=data["stderr"],
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "command": self.command,
            "returncode": self.returncode,
            "timed_out": self.timed_out,
            "stdout": self.stdout,
            "stderr": self.stderr,
        }


@dataclass(frozen=True, slots=True)
class Issue:
    """A specific problem reported by the checker."""

    severity: Severity
    location: str
    description: str
    evidence: str
    suggestion: str = ""

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Issue":
        return cls(
            severity=Severity(data["severity"]),
            location=data["location"],
            description=data["description"],
            evidence=data["evidence"],
            suggestion=data.get("suggestion", ""),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "severity": self.severity.value,
            "location": self.location,
            "description": self.description,
            "evidence": self.evidence,
            "suggestion": self.suggestion,
        }


@dataclass(frozen=True, slots=True)
class MakerOutput:
    """What the maker produces and self-reports.

    ``self_verification`` is recorded for the loop state but is deliberately **not**
    trusted for the completion decision.

    ``ok`` is a machine-level signal (did the maker actually produce something?) —
    distinct from the maker's own ``self_verification`` claim. A maker that was blocked
    or crashed returns ``ok=False``; the loop must then treat the round as no-progress
    regardless of any stub checker verdict.

    ``tokens_used`` is the honest accounting delta for the maker's work this round
    (input + output). It feeds the durable budget; the loop never invents a number.
    """

    summary: str
    modified_files: list[str] = field(default_factory=list)
    self_verification: str = ""
    risks: str = ""
    tokens_used: int = 0
    ok: bool = True


@dataclass(frozen=True, slots=True)
class CheckerOutput:
    """The independent verdict, the only completion signal the runner trusts."""

    verdict: Verdict
    issues: list[Issue] = field(default_factory=list)
    command_results: list[VerificationResult] = field(default_factory=list)
    tokens_used: int = 0


@dataclass(slots=True)
class RoundRecord:
    """One round in the loop's state log."""

    number: int
    started_at: datetime
    finished_at: Optional[datetime] = None
    maker_summary: str = ""
    checker_verdict: Optional[Verdict] = None
    issues: list[Issue] = field(default_factory=list)
    verification: list[VerificationResult] = field(default_factory=list)
    criteria_satisfied: list[str] = field(default_factory=list)
    next_round_plan: str = ""
    human_intervention: bool = False

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "RoundRecord":
        return cls(
            number=data["number"],
            started_at=_parse_dt(data["started_at"]),
            finished_at=_parse_dt(data["finished_at"]),
            maker_summary=data.get("maker_summary", ""),
            checker_verdict=(
                Verdict(data["checker_verdict"]) if data.get("checker_verdict") else None
            ),
            issues=[Issue.from_dict(i) for i in data.get("issues", [])],
            verification=[
                VerificationResult.from_dict(v) for v in data.get("verification", [])
            ],
            criteria_satisfied=list(data.get("criteria_satisfied", [])),
            next_round_plan=data.get("next_round_plan", ""),
            human_intervention=data.get("human_intervention", False),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "number": self.number,
            "started_at": _iso(self.started_at),
            "finished_at": _iso(self.finished_at),
            "maker_summary": self.maker_summary,
            "checker_verdict": (
                self.checker_verdict.value if self.checker_verdict else None
            ),
            "issues": [i.to_dict() for i in self.issues],
            "verification": [v.to_dict() for v in self.verification],
            "criteria_satisfied": list(self.criteria_satisfied),
            "next_round_plan": self.next_round_plan,
            "human_intervention": self.human_intervention,
        }


@dataclass(slots=True)
class FinalResult:
    status: str = ""
    finished_at: Optional[datetime] = None
    summary: str = ""

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "FinalResult":
        return cls(
            status=data.get("status", ""),
            finished_at=_parse_dt(data.get("finished_at")),
            summary=data.get("summary", ""),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "finished_at": _iso(self.finished_at),
            "summary": self.summary,
        }


@dataclass(slots=True)
class LoopState:
    """Durable loop progress, ported from ``loop-state-template.md``."""

    loop_name: str
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    current_round: int = 0
    status: str = "in_progress"
    rounds: list[RoundRecord] = field(default_factory=list)
    blockers: list[str] = field(default_factory=list)
    passed_rounds: int = 0
    failed_rounds: int = 0
    total_issues: int = 0
    human_interventions: int = 0
    files_changed: int = 0
    final_result: Optional[FinalResult] = None

    def record_round(self, record: RoundRecord) -> None:
        self.rounds.append(record)
        self.current_round = record.number
        self.total_issues += len(record.issues)
        if record.human_intervention:
            self.human_interventions += 1
        if record.checker_verdict in (Verdict.PASS, Verdict.ACCEPT_WITH_MINOR):
            self.passed_rounds += 1
        else:
            self.failed_rounds += 1

    def add_blocker(self, blocker: str) -> None:
        if blocker and blocker not in self.blockers:
            self.blockers.append(blocker)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "LoopState":
        state = cls(
            loop_name=data["loop_name"],
            started_at=_parse_dt(data["started_at"]),
            current_round=data.get("current_round", 0),
            status=data.get("status", "in_progress"),
        )
        state.rounds = [RoundRecord.from_dict(r) for r in data.get("rounds", [])]
        state.blockers = list(data.get("blockers", []))
        state.passed_rounds = data.get("passed_rounds", 0)
        state.failed_rounds = data.get("failed_rounds", 0)
        state.total_issues = data.get("total_issues", 0)
        state.human_interventions = data.get("human_interventions", 0)
        state.files_changed = data.get("files_changed", 0)
        if data.get("final_result"):
            state.final_result = FinalResult.from_dict(data["final_result"])
        return state

    def to_dict(self) -> dict[str, Any]:
        return {
            "loop_name": self.loop_name,
            "started_at": _iso(self.started_at),
            "current_round": self.current_round,
            "status": self.status,
            "rounds": [r.to_dict() for r in self.rounds],
            "blockers": list(self.blockers),
            "passed_rounds": self.passed_rounds,
            "failed_rounds": self.failed_rounds,
            "total_issues": self.total_issues,
            "human_interventions": self.human_interventions,
            "files_changed": self.files_changed,
            "final_result": self.final_result.to_dict() if self.final_result else None,
        }


def _iso(value: Optional[datetime]) -> Optional[str]:
    return value.isoformat() if value else None


def _parse_dt(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    return datetime.fromisoformat(value)


# --------------------------------------------------------------------- markdown


def _split_sections(text: str) -> dict[str, str]:
    """Split markdown into a ``{heading: body}`` map by ``## Heading`` lines."""
    sections: dict[str, str] = {}
    current: Optional[str] = None
    lines: list[str] = []

    def flush() -> None:
        if current is not None:
            sections[current] = "\n".join(lines).strip()

    for line in text.splitlines():
        m = re.match(r"^##\s+(.+?)\s*$", line)
        if m:
            flush()
            current = m.group(1).strip()
            lines = []
        elif current is not None:
            lines.append(line)
    flush()
    return sections


def _parse_objective(sections: dict[str, str]) -> str:
    body = sections.get("Goal", "").strip()
    if not body:
        raise ValueError("goal.md is missing a non-empty '## Goal' section")
    # Strip HTML comments and blank/whitespace-only lines, then join the first real
    # paragraph (which is the objective sentence).
    lines = [
        line
        for line in body.splitlines()
        if line.strip() and not line.strip().startswith("<!--")
    ]
    if not lines:
        raise ValueError("goal.md '## Goal' section has no objective text")
    return " ".join(line.strip() for line in lines)


def _parse_criteria(sections: dict[str, str]) -> list[AcceptanceCriterion]:
    body = sections.get("Acceptance Criteria", "").strip()
    if not body:
        raise ValueError(
            "goal.md is missing a non-empty '## Acceptance Criteria' section"
        )

    criteria: list[AcceptanceCriterion] = []
    # Criteria are markdown list items. A criterion line is either
    # "- [ ] <description>" or "- [ ] <description> @verify <command>".
    for line in body.splitlines():
        m = re.match(r"^\s*[-*]\s+\[[ xX]\]\s+(.+?)\s*$", line)
        if not m:
            continue
        text = m.group(1).strip()
        command: Optional[str] = None
        at_verify = re.search(r"@verify\s+(.+?)\s*$", text)
        if at_verify:
            command = at_verify.group(1).strip()
            text = text[: at_verify.start()].strip()
        if not text:
            continue
        criteria.append(
            AcceptanceCriterion(
                id=f"c{len(criteria) + 1}",
                description=text,
                verify_command=command,
            )
        )

    if not criteria:
        raise ValueError(
            "goal.md '## Acceptance Criteria' has no checklist items"
        )
    return criteria


def _parse_scope(sections: dict[str, str]) -> Scope:
    body = sections.get("Scope", "")
    fair_game: list[str] = []
    hands_off: list[str] = []
    current = None
    for line in body.splitlines():
        if re.match(r"^###\s+Fair game\s*$", line, re.IGNORECASE):
            current = fair_game
        elif re.match(r"^###\s+Hands off\s*$", line, re.IGNORECASE):
            current = hands_off
        elif current is not None:
            m = re.match(r"^\s*[-*]\s+(.+?)\s*$", line)
            if m:
                current.append(m.group(1).strip())
    return Scope(fair_game=fair_game, hands_off=hands_off)


def _parse_stop_conditions(sections: dict[str, str]) -> list[StopCondition]:
    body = sections.get("Stop Conditions", "").strip()
    if not body:
        raise ValueError(
            "goal.md is missing a non-empty '## Stop Conditions' section"
        )

    stops: list[StopCondition] = []
    for line in body.splitlines():
        m = re.match(r"^\s*[-*]\s+(.+?)\s*$", line)
        if not m:
            continue
        item = m.group(1).strip()
        lowered = item.lower()
        if "no progress" in lowered or "无进展" in item or "no progress" in item.lower():
            # Blocked audit is owned by goal_persistence's fixed three-strike rule,
            # not a StopCondition the runner can honor.
            continue
        if "max round" in lowered or "max turn" in lowered or "最大回合" in item:
            number = re.search(r"\d+", item)
            if number:
                stops.append(
                    StopCondition(kind="max_rounds", value=int(number.group(0)))
                )
        elif "budget" in lowered and "token" in lowered:
            stops.append(StopCondition(kind="budget_tokens"))
        elif "budget" in lowered and ("time" in lowered or "wall" in lowered):
            stops.append(StopCondition(kind="budget_wall_ms"))
        elif "all acceptance" in lowered or "criteria pass" in lowered:
            # Completion is the inherent success rule, not a StopCondition.
            continue

    if not stops:
        raise ValueError(
            "goal.md '## Stop Conditions' has no recognizable stop condition"
        )
    return stops


def _parse_how_to_work(sections: dict[str, str]) -> list[str]:
    body = sections.get("How to Work", "")
    steps: list[str] = []
    for line in body.splitlines():
        m = re.match(r"^\s*\d+\.\s+(.+?)\s*$", line)
        if m:
            steps.append(m.group(1).strip())
    return steps
