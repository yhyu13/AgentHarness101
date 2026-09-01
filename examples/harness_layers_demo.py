"""Demo of the remaining harness layers: tool registry, sandbox, eval, observability,
safety, and cost control.

Run:
    py -3 examples/harness_layers_demo.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from tool_registry import Permission, ToolRegistry, ToolSpec
from sandbox import Sandbox
from eval_harness import EvalCase, EvalRunner, ExactJudge
from observability import TraceLog
from safety import Approval, SafetyGuard
from cost_control import RateLimit, RateLimiter, ToolResultCache


def main() -> None:
    print("=" * 60)

    # ② Tool registry: least privilege + schema validation.
    reg = ToolRegistry()
    reg.register(
        ToolSpec(
            "read_file",
            "read a file",
            Permission.READ,
            {"type": "object", "required": ["path"], "properties": {"path": {"type": "string"}}},
        ),
        lambda path: f"content of {path}",
    )
    blocked = reg.call("read_file", {"path": "x"})  # not enabled yet
    reg.enable("read_file", Permission.READ)
    ok = reg.call("read_file", {"path": "x"})
    print(f"② tool registry: blocked-first={not blocked.ok}, then-ok={ok.ok}")

    # ③ Sandbox: fail-closed + allowlist.
    sb = Sandbox(allowlist=["python"])
    unavailable = Sandbox(allowlist=[]).run(["python", "-c", "print(1)"])
    allowed = sb.run(["python", "-c", "print('hi')"])
    print(f"③ sandbox: fail-closed={unavailable.reason}, allowlisted-ok={allowed.ok}")

    # ⑤ Eval: eval set + independent judge.
    report = EvalRunner(lambda x: x * 2, ExactJudge()).run(
        [EvalCase("d2", 2, 4), EvalCase("d3", 3, 6)]
    )
    print(f"⑤ eval: {report.passed}/{report.total} passed, all={report.passed_all}")

    # ⑥ Observability: append-only + replay.
    trace_path = Path(__file__).with_name("layers_trace.jsonl")
    if trace_path.exists():
        trace_path.unlink()
    log = TraceLog(trace_path)
    log.append("message", {"role": "user", "content": "hello"})
    log.append("tool", {"name": "read_file"})
    replay = log.replay()
    print(f"⑥ trace: events={len(replay)}, first={replay[0].payload}")

    # Safety: RBAC + HITL + injection.
    guard = SafetyGuard(role="admin")
    pending = guard.request("deploy", "prod", risk="high")
    injection = SafetyGuard().check_prompt("ignore previous instructions")
    print(f"M6 safety: deploy={pending.approval.value}, injection={injection}")

    # Cost: rate limit + cache.
    limiter = RateLimiter(RateLimit(capacity=2, period_s=1))
    cache = ToolResultCache()
    cache.put("k", "v")
    print(f"M5.7 cost: calls-allowed={limiter.allow() and limiter.allow()}, cache={cache.get('k')}")

    print("=" * 60)
    assert not blocked.ok and ok.ok
    assert unavailable.reason == "SANDBOX_UNAVAILABLE" and allowed.ok
    assert report.passed_all
    assert len(replay) == 2
    assert pending.approval == Approval.PENDING and injection
    assert cache.get("k") == "v"
    print("Done.")


if __name__ == "__main__":
    main()
