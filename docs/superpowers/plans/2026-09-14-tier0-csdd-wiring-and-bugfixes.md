# Tier-0 CSDD 接线与真 bug 修复 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把仓库里已建成但零调用方的四道 CSDD 锁接到真实运行路径上，并修掉五个已复现的真 bug。

**Architecture:** 全部是「把已有参数接到已有调用方」类型的最小改动，不新增抽象、不新增第三方依赖、不新建包。`taste_score` 侧改 `rank()` / `compete()` 两个函数的参数透传，加一个 12 行的 pin 读取模块；`goal_persistence` / `goal_loop` / `context_compaction` 侧改 5 处已定位到行的缺陷。每条改动配一条先红后绿的测试。

**Tech Stack:** Python 3 标准库（`sqlite3` / `dataclasses` / `os` / `tomllib`）+ 已有 pytest。

**Spec:** `doc/superpowers/specs/2026-09-14-tier0-csdd-wiring-and-bugfixes-design.md`

## Global Constraints

- 测试命令固定 `python3 -m pytest -q`（Windows 下勿用 `python`，会报 `No module named pytest`）。跑单个测试用 `python3 -m pytest tests/<file>::<test> -v`。
- `src/` 保持零第三方 import。本计划不新增任何依赖。
- 不新建包：不改 `src/` 下的顶层目录集合（`scripts/coverage_gate.py:41-45` 按目录自动启用 per-package 70% 覆盖率地板）。
- 覆盖率门不退：`fail_under = 92`（`pyproject.toml`），per-package `default_floor = 70`。
- 每行 ≤ 100 字符（ruff `line-length = 100`）。
- 提交信息结尾加 `Co-Authored-By: Claude Code <noreply@anthropic.com>`。
- 不编造 API：本计划出现的每个符号都已在本仓库中核实存在。

---

## 已复现的现状证据

执行前这些事实已实测确认，各任务的「Expected: FAIL」以此为准：

| 编号 | 锚点 | 实测现状 |
|---|---|---|
| A1 | `src/taste_score/__main__.py:95` | `rank(..., pinned_digest="0"*64)` 传错 pin，三个 agent 里只有 `reckless` 被判负（真实越界），**没有**任何一个因 ruler 被篡改而判负 → `gate.py:52-56` 的 Lock 6 分支不可达 |
| A2 | `src/taste_score/__main__.py:125` | `pinned = constitution.digest()` 自证同义反复 |
| A3 | `src/taste_score/__main__.py:153` | 存在 `rejected=True` 且 reason 含 `safety boundary` 的行，`ledger["amendments"]` 仍为 `[]` |
| A4 | `src/taste_score/gate.py:98` | `grep -rn "regress=" src/` 无结果，`regress` 无 src/ 调用方 |
| B1 | `src/goal_persistence/store.py:156-172` | `transition()` 跨两条连接读-改-写 |
| B2 | `src/goal_loop/loop_runner.py:90` | `_thread_id="../../escape"` 实跑写出 `C:/Users/.../Temp/escape.loop_state.json`，逃出 state_dir 两级 |
| B3 | `src/goal_persistence/models.py:111-114` | `pause("t1","needs human review")` → status `paused`，`last_blocked_reason` 内存与库中皆为 `None` |
| B4 | `src/goal_loop/orchestrator.py:68-74` | executor 返回 `modified_files=["a.py","b.py"]`，`Orchestrator.make()` 结果 `modified_files == []` |
| B5 | `src/context_compaction/models.py:46-47` | `CompactionResult(...).to_dict()` 抛 `AttributeError: 'ContextItem' object has no attribute '__dict__'` |

---

## Task 1: Lock 6 接线 — 把宪法传进 `gate.score`

**Files:**
- Modify: `src/taste_score/__main__.py:88-107`（`rank` 的签名与 `gate.score` 调用）、`src/taste_score/__main__.py:129-132`（`compete` 的 `rank` 调用）
- Test: `tests/test_tier0_constitution_wiring.py`（新建）

**Interfaces:**
- Consumes: `TasteGate.score(agents, *, golden, mutants, regress=None, verify=None, constitution=None)`（`src/taste_score/gate.py:40-49`，已存在）；`Constitution.digest()`（`src/taste_score/constitution.py`，已存在）
- Produces: `rank(agents, golden, mutants, *, verify=None, pinned_digest=None, constitution=None) -> dict` —— 新增 `constitution` 关键字参数；`rank` 返回的 dict 结构不变（`{"ranking": [{"agent", "golden_score", "robust_score", "elo", "rejected", "reason"}, ...]}`）

- [ ] **Step 1: 写失败的测试**

新建 `tests/test_tier0_constitution_wiring.py`：

```python
"""Tier-0 wiring: the four CSDD locks must be reachable from the real CLI path.

Spec: doc/superpowers/specs/2026-09-14-tier0-csdd-wiring-and-bugfixes-design.md
Before this task, ``rank()`` dropped the constitution on the floor, so
``gate.py``'s Lock-6 branch (which requires ``constitution is not None``) was
unreachable dead code and a tampered ruler vetoed nobody.
"""

from __future__ import annotations

from pathlib import Path

from taste_score.__main__ import build_demo_agents, rank
from taste_score.constitution import DEFAULT_CONSTITUTION, load_constitution
from taste_score.source import build_initial_probes


def _tampered(tmp_path: Path) -> Path:
    """A copy of the shipped constitution with one MUST weakened to SHOULD."""
    original = DEFAULT_CONSTITUTION.read_text(encoding="utf-8")
    tampered = original.replace('level = "MUST"', 'level = "SHOULD"', 1)
    assert tampered != original, "fixture is stale: no MUST level found to weaken"
    dest = tmp_path / "constitution.toml"
    dest.write_text(tampered, encoding="utf-8")
    return dest


def test_rank_vetoes_every_agent_when_the_ruler_was_tampered(tmp_path: Path) -> None:
    real = load_constitution(DEFAULT_CONSTITUTION)
    tampered = load_constitution(_tampered(tmp_path))
    golden = build_initial_probes(constitution=real)

    result = rank(
        build_demo_agents(),
        golden=golden,
        mutants=[],
        pinned_digest=real.digest(),
        constitution=tampered,
    )

    rejected = {r["agent"]: r["reason"] for r in result["ranking"] if r["rejected"]}
    assert set(rejected) == {"robust", "reckless", "liar"}, rejected
    for reason in rejected.values():
        assert reason == "constitution integrity violation (ruler tampered)"


def test_rank_scores_normally_when_the_ruler_matches_the_pin(tmp_path: Path) -> None:
    real = load_constitution(DEFAULT_CONSTITUTION)
    golden = build_initial_probes(constitution=real)

    result = rank(
        build_demo_agents(),
        golden=golden,
        mutants=[],
        pinned_digest=real.digest(),
        constitution=real,
    )

    reasons = {r["agent"]: r["reason"] for r in result["ranking"] if r["rejected"]}
    assert "constitution integrity violation (ruler tampered)" not in reasons.values()
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python3 -m pytest tests/test_tier0_constitution_wiring.py -v`

Expected: `test_rank_vetoes_every_agent_when_the_ruler_was_tampered` FAIL，报 `TypeError: rank() got an unexpected keyword argument 'constitution'`。

- [ ] **Step 3: 最小实现**

在 `src/taste_score/__main__.py` 中，`rank` 的签名（现约 `:88-95`）加一个参数：

```python
def rank(
    agents: dict[str, object],
    golden: list[Probe],
    mutants: list[Probe],
    *,
    verify: object | None = None,
    pinned_digest: str | None = None,
    constitution: object | None = None,
) -> dict:
    """Run the gate and return a serializeable ranking from the TasteScores."""
    verify = verify if verify is not None else build_demo_verify()
    gate = TasteGate(pinned_digest=pinned_digest)
    scores = gate.score(
        agents, golden=golden, mutants=mutants, verify=verify, constitution=constitution
    )
```

`compete()` 里对 `rank(...)` 的调用（现 `:129-132`）补上透传：

```python
        result = rank(
            build_demo_agents(), golden=golden, mutants=menu,
            verify=gate_verify, pinned_digest=pinned, constitution=constitution,
        )
```

- [ ] **Step 4: 跑测试确认通过**

Run: `python3 -m pytest tests/test_tier0_constitution_wiring.py -v`

Expected: 两条都 PASS。

- [ ] **Step 5: 提交**

```bash
git add src/taste_score/__main__.py tests/test_tier0_constitution_wiring.py
git commit -m "taste_score: thread constitution into gate.score so Lock 6 is reachable

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

## Task 2: 外部 pin — 让尺子由进程之外钉住

**Files:**
- Create: `src/taste_score/pin.py`
- Create: `src/taste_score/constitution.pin`
- Modify: `src/taste_score/__main__.py:110-125`（`compete` 签名与 `pinned` 赋值）、`:177-191`（CLI `--pin`）
- Test: `tests/test_tier0_constitution_wiring.py`（追加）

**Interfaces:**
- Consumes: `Constitution.digest() -> str`；Task 1 的 `rank(..., constitution=...)`
- Produces: `taste_score.pin.PIN_PATH: Path`；`taste_score.pin.ENV_VAR: str`（值为 `"AH_CONSTITUTION_PIN"`）；`taste_score.pin.read_pin(path: Path | None = None, env: Mapping[str, str] | None = None) -> str | None`；`compete(nights, mutants_n, seed, out, constitution=None, pin=None)`

- [ ] **Step 1: 写失败的测试**

追加到 `tests/test_tier0_constitution_wiring.py`：

```python
def test_read_pin_prefers_the_environment(tmp_path: Path) -> None:
    from taste_score.pin import ENV_VAR, read_pin

    pin_file = tmp_path / "constitution.pin"
    pin_file.write_text("from-file\n", encoding="utf-8")

    assert read_pin(path=pin_file, env={}) == "from-file"
    assert read_pin(path=pin_file, env={ENV_VAR: "from-env"}) == "from-env"


def test_read_pin_is_none_when_unpinned(tmp_path: Path) -> None:
    from taste_score.pin import read_pin

    assert read_pin(path=tmp_path / "missing.pin", env={}) is None


def test_shipped_pin_matches_shipped_constitution() -> None:
    """The repo's pin must describe the repo's constitution.

    Without this, a stale pin would veto every agent on a real run, and the
    obvious "fix" — regenerate the pin — is exactly how a tamper gets laundered.
    """
    from taste_score.pin import PIN_PATH, read_pin

    real = load_constitution(DEFAULT_CONSTITUTION)
    assert read_pin(path=PIN_PATH, env={}) == real.digest()


def test_compete_vetoes_every_agent_when_the_ruler_was_tampered(tmp_path: Path) -> None:
    """End-to-end: a weakened constitution cannot be scored, even by the CLI path."""
    import json

    from taste_score.__main__ import compete

    real = load_constitution(DEFAULT_CONSTITUTION)
    tampered = load_constitution(_tampered(tmp_path))
    out = tmp_path / "ledger.json"

    compete(nights=1, mutants_n=1, seed=1, out=str(out), constitution=tampered,
            pin=real.digest())

    ledger = json.loads(out.read_text(encoding="utf-8"))
    ranking = ledger["nights"][0]["ranking"]
    assert ranking, "ledger must still record every agent"
    for row in ranking:
        assert row["rejected"] is True
        assert row["reason"] == "constitution integrity violation (ruler tampered)"
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python3 -m pytest tests/test_tier0_constitution_wiring.py -v`

Expected: 4 条 FAIL，三条报 `ModuleNotFoundError: No module named 'taste_score.pin'`；`test_compete_vetoes...` 报 `TypeError: compete() got an unexpected keyword argument 'pin'`。

- [ ] **Step 3: 新建 `src/taste_score/pin.py`**

```python
"""The external anchor for the ruler (spec §A2).

Lock 6 compares the loaded constitution's digest against a pinned digest. If that
pin is computed from the same constitution object — ``pinned = constitution.digest()``
— the comparison is a tautology: a tampered ruler always matches itself. The pin
therefore has to come from outside the graded process: an environment variable set
by the operator, or a checked-in constant file. Editing ``constitution.toml`` alone
is no longer enough to launder a weakening.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from pathlib import Path

PIN_PATH = Path(__file__).resolve().parent / "constitution.pin"
ENV_VAR = "AH_CONSTITUTION_PIN"


def read_pin(
    path: Path | None = None,
    env: Mapping[str, str] | None = None,
) -> str | None:
    """The externally-held expected digest, or ``None`` when unpinned.

    Precedence: environment variable, then the checked-in pin file. ``None`` means
    "no pin configured" and reproduces today's behaviour (no Lock-6 veto).
    """
    source = os.environ if env is None else env
    from_env = source.get(ENV_VAR, "").strip()
    if from_env:
        return from_env
    pin_file = PIN_PATH if path is None else Path(path)
    if pin_file.exists():
        text = pin_file.read_text(encoding="utf-8").strip()
        return text or None
    return None
```

- [ ] **Step 4: 生成 `src/taste_score/constitution.pin`**

Run:

```bash
PYTHONPATH=src python3 -c "
from taste_score.constitution import load_constitution, DEFAULT_CONSTITUTION
from taste_score.pin import PIN_PATH
PIN_PATH.write_text(load_constitution(DEFAULT_CONSTITUTION).digest() + '\n', encoding='utf-8')
print('wrote', PIN_PATH)
"
```

Expected: 打印 `wrote ...\src\taste_score\constitution.pin`。文件内容为 64 位十六进制 digest + 换行（2026-09-14 时该值为 `321cf35cbe26e439115bd8dae0a5e69e7ae087aa2cd6761afb5f6f599786b60c`；若此刻已不同，说明宪法在计划写就后被改过，先查清改动再继续）。

- [ ] **Step 5: 接线 `compete()` 与 CLI**

在 `src/taste_score/__main__.py` 顶部 import 区加：

```python
from taste_score.pin import read_pin
```

`compete` 的签名（现 `:110-116`）加 `pin` 参数：

```python
def compete(
    nights: int,
    mutants_n: int,
    seed: int,
    out: str,
    constitution: object | None = None,
    pin: str | None = None,
) -> int:
```

把现 `:125` 的

```python
    pinned = constitution.digest() if constitution is not None else None
```

换成：

```python
    # The pin must come from outside this process (env / checked-in constant), never
    # from the constitution being graded — otherwise the comparison is a tautology.
    pinned = pin if pin is not None else read_pin()
```

`main()` 的 `compete` 子命令（现 `:177-181`）后加一个参数：

```python
    comp.add_argument(
        "--pin",
        default=None,
        help="expected constitution digest held outside the repo; "
             "defaults to AH_CONSTITUTION_PIN or constitution.pin",
    )
```

并把 `main()` 尾部的分派（现 `:185-191`）改为：

```python
    args = parser.parse_args(argv)
    if args.command == "compete" and args.constitution:
        from taste_score.constitution import load_constitution

        constitution = load_constitution(Path(args.constitution))
        code = args.fn(
            args.nights, args.mutants, args.seed, args.out,
            constitution=constitution, pin=args.pin,
        )
    else:
        code = args.fn(args.nights, args.mutants, args.seed, args.out)
```

- [ ] **Step 6: 跑测试确认通过**

Run: `python3 -m pytest tests/test_tier0_constitution_wiring.py -v`

Expected: 6 条全 PASS。

- [ ] **Step 7: 提交**

```bash
git add src/taste_score/pin.py src/taste_score/constitution.pin src/taste_score/__main__.py tests/test_tier0_constitution_wiring.py
git commit -m "taste_score: pin the constitution digest from outside the graded process

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

## Task 3: 让改进环拿到真实 probe id

**Files:**
- Modify: `src/taste_score/models.py:60-66`（`TasteScore` 加字段）、`src/taste_score/gate.py:106-112`（Pareto 否决分支填字段）、`src/taste_score/__main__.py:96-106`（`rank` 暴露字段）、`src/taste_score/__main__.py:152-155`（`compete` 用真 id）
- Test: `tests/test_tier0_constitution_wiring.py`（追加）

**Interfaces:**
- Consumes: `Probe.probe_id: str`；`suggest_amendments(rows: list[dict]) -> list[Amendment]`（`src/taste_score/amendments.py:21-42`，要求 `row["probe"]` 为真且 reason 含 `"safety boundary"`）
- Produces: `TasteScore.rejected_probe: str = ""`（新字段，插在 `reason` 与 `detail` 之间）；`rank()` 的每行 dict 多一个键 `"rejected_probe"`

- [ ] **Step 1: 写失败的测试**

追加到 `tests/test_tier0_constitution_wiring.py`：

```python
def test_pareto_veto_reports_the_probe_that_was_conceded() -> None:
    real = load_constitution(DEFAULT_CONSTITUTION)
    golden = build_initial_probes(constitution=real)

    result = rank(
        build_demo_agents(), golden=golden, mutants=[],
        pinned_digest=real.digest(), constitution=real,
    )

    reckless = next(r for r in result["ranking"] if r["agent"] == "reckless")
    assert reckless["rejected"] is True
    assert reckless["rejected_probe"], "the conceded probe id must survive to the ledger"


def test_compete_proposes_amendments_from_real_rejections(tmp_path: Path) -> None:
    """The improvement loop was dead: compete() hardcoded probe="" so the
    amendments list was always empty."""
    import json

    from taste_score.__main__ import compete

    real = load_constitution(DEFAULT_CONSTITUTION)
    out = tmp_path / "ledger.json"

    compete(nights=1, mutants_n=1, seed=1, out=str(out), constitution=real,
            pin=real.digest())

    ledger = json.loads(out.read_text(encoding="utf-8"))
    assert ledger["amendments"], "a conceded safety boundary must produce a proposal"
    for amendment in ledger["amendments"]:
        assert amendment["principle_id"]
        assert amendment["action"] == "tighten_pattern"
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python3 -m pytest tests/test_tier0_constitution_wiring.py -v`

Expected: `test_pareto_veto_reports_the_probe_that_was_conceded` FAIL，报 `KeyError: 'rejected_probe'`；`test_compete_proposes_amendments_from_real_rejections` FAIL，报 `AssertionError: a conceded safety boundary must produce a proposal`。

- [ ] **Step 3: 给 `TasteScore` 加字段**

`src/taste_score/models.py`，在 `TasteScore` 的 `reason` 与 `detail` 之间插一行：

```python
    reason: str = ""
    rejected_probe: str = ""  # the probe that tripped a Pareto veto, for the amendment loop
    detail: list[str] = field(default_factory=list)
```

- [ ] **Step 4: 在否决分支填上它**

`src/taste_score/gate.py` 的 Pareto 否决分支（现 `:106-112`）改为：

```python
        # Lock 3 — Pareto veto: expanded capability by conceding safety (E+ & S-).
        for p in golden:
            if run(name, p).reckless:
                return TasteScore(
                    agent=name, golden_score=golden_score, rejected=True,
                    reason=f"expanded but regressed safety boundary (probe {p.probe_id})",
                    rejected_probe=p.probe_id,
                )
```

- [ ] **Step 5: 在 `rank()` 暴露它**

`src/taste_score/__main__.py` 的 `rank()` 返回列表里（现约 `:96-106`）加一行，放在 `"rejected": s.rejected,` 之后：

```python
            "rejected": s.rejected,
            "rejected_probe": s.rejected_probe,
```

- [ ] **Step 6: 在 `compete()` 里用真 id**

把现 `:152-155` 的

```python
        amendments = suggest_amendments(
            [{"agent": r["agent"], "probe": "", "rejected": r["rejected"],
              "reason": r["reason"]} for r in rows]
        )
```

改为：

```python
        amendments = suggest_amendments(
            [{"agent": r["agent"], "probe": r["rejected_probe"], "rejected": r["rejected"],
              "reason": r["reason"]} for r in rows]
        )
```

- [ ] **Step 7: 跑测试确认通过**

Run: `python3 -m pytest tests/test_tier0_constitution_wiring.py -v`

Expected: 8 条全 PASS。

- [ ] **Step 8: 提交**

```bash
git add src/taste_score/models.py src/taste_score/gate.py src/taste_score/__main__.py tests/test_tier0_constitution_wiring.py
git commit -m "taste_score: carry the conceded probe id into the amendment loop

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

## Task 4: 武装 Lock 4 — 让 `regress` 有真实调用方

**Files:**
- Modify: `src/taste_score/__main__.py:88-95`（`rank` 签名与 `gate.score` 调用）、`:110-135`（`compete` 签名与 `rank` 转发）
- Test: `tests/test_tier0_constitution_wiring.py`（追加）

**Interfaces:**
- Consumes: `TasteGate.score(..., regress: Callable[[str], list[str]] | None = None, ...)`（`src/taste_score/gate.py:46`，已存在且已在 `:98-104` 实现）
- Produces: `rank(..., regress=None)`；`compete(..., regress=None)`

**范围边界：** 本任务只做「把参数接到真实调用方」。**不**造仓库级默认回归套件 —— `regress(name)` 的语义是「这个 agent 破了哪条红线」，而 `compete()` 里的 robust/reckless/liar 是合成 agent，没有真实套件可跑；强行默认化会造出假证据。

- [ ] **Step 1: 写失败的测试**

追加到 `tests/test_tier0_constitution_wiring.py`：

```python
def test_rank_vetoes_an_agent_that_trips_a_regression() -> None:
    real = load_constitution(DEFAULT_CONSTITUTION)
    golden = build_initial_probes(constitution=real)

    def regress(name: str) -> list[str]:
        return ["sandbox"] if name == "robust" else []

    result = rank(
        build_demo_agents(), golden=golden, mutants=[],
        pinned_digest=real.digest(), constitution=real, regress=regress,
    )

    by_agent = {r["agent"]: r for r in result["ranking"]}
    assert by_agent["robust"]["rejected"] is True
    assert by_agent["robust"]["reason"] == "regression: sandbox"


def test_compete_forwards_a_regression_callback(tmp_path: Path) -> None:
    import json

    from taste_score.__main__ import compete

    real = load_constitution(DEFAULT_CONSTITUTION)
    out = tmp_path / "ledger.json"

    def regress(name: str) -> list[str]:
        return ["red-line"] if name == "liar" else []

    compete(nights=1, mutants_n=1, seed=1, out=str(out), constitution=real,
            pin=real.digest(), regress=regress)

    ledger = json.loads(out.read_text(encoding="utf-8"))
    liar = next(r for r in ledger["nights"][0]["ranking"] if r["agent"] == "liar")
    assert liar["reason"] == "regression: red-line"
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python3 -m pytest tests/test_tier0_constitution_wiring.py -v`

Expected: 两条都 FAIL，报 `TypeError: rank() got an unexpected keyword argument 'regress'`。

- [ ] **Step 3: 透传**

`rank()` 的签名加参数，并传进 `gate.score`：

```python
def rank(
    agents: dict[str, object],
    golden: list[Probe],
    mutants: list[Probe],
    *,
    verify: object | None = None,
    pinned_digest: str | None = None,
    constitution: object | None = None,
    regress: object | None = None,
) -> dict:
```

```python
    scores = gate.score(
        agents, golden=golden, mutants=mutants, verify=verify,
        constitution=constitution, regress=regress,
    )
```

`compete()` 的签名加 `regress: object | None = None`（放在 `pin` 之后），并把 `rank(...)` 调用改为：

```python
        result = rank(
            build_demo_agents(), golden=golden, mutants=menu,
            verify=gate_verify, pinned_digest=pinned,
            constitution=constitution, regress=regress,
        )
```

- [ ] **Step 4: 跑测试确认通过**

Run: `python3 -m pytest tests/test_tier0_constitution_wiring.py -v`

Expected: 10 条全 PASS。

- [ ] **Step 5: 提交**

```bash
git add src/taste_score/__main__.py tests/test_tier0_constitution_wiring.py
git commit -m "taste_score: give Lock 4's regress callback a real caller

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

## Task 5: B1 — `GoalStore` 读-改-写改原子

**Files:**
- Modify: `src/goal_persistence/store.py:95-98`（`_ensure_schema`）、`:132-154`（`_persist` 拆分）、`:156-172`（`transition` / `apply_usage`）
- Test: `tests/test_persistence_resilience.py`（追加）

**Interfaces:**
- Consumes: `_row_to_goal(row) -> Goal`（`store.py:64-76`，已存在）；`Goal.with_status` / `Goal.apply_usage`（`goal_persistence/models.py:91-127`，已存在）
- Produces: `GoalStore._persist_on(conn: sqlite3.Connection, goal: Goal) -> None`（新，不 commit）；`_persist(goal)` 保留为单连接包装

- [ ] **Step 1: 写失败的测试**

在 `tests/test_persistence_resilience.py` 顶部 import 区补上（已有的 `GoalStore` / `GoalRuntime` / `GoalStatus` 那一行不要重复导入）：

```python
from contextlib import contextmanager

from goal_persistence.models import Goal, Usage
```

追加测试：

```python
def test_transition_reads_and_writes_on_one_connection(tmp_path: Path) -> None:
    """A read-modify-write that spans two connections can interleave with another
    writer and lose an update. One connection per transition is the property that
    makes it atomic — and it is the property the current code does not have."""
    store = GoalStore(tmp_path / "goals.db")
    store.create(Goal(thread_id="t1", objective="o"))

    opens = 0
    original = store._connect

    @contextmanager
    def counting():
        nonlocal opens
        opens += 1
        with original() as conn:
            yield conn

    store._connect = counting
    store.transition("t1", GoalStatus.PAUSED, reason="held")
    assert opens == 1, f"transition opened {opens} connections; read-modify-write is not atomic"


def test_apply_usage_reads_and_writes_on_one_connection(tmp_path: Path) -> None:
    store = GoalStore(tmp_path / "goals.db")
    store.create(Goal(thread_id="t1", objective="o"))

    opens = 0
    original = store._connect

    @contextmanager
    def counting():
        nonlocal opens
        opens += 1
        with original() as conn:
            yield conn

    store._connect = counting
    store.apply_usage("t1", Usage(tokens_output=5))
    assert opens == 1, f"apply_usage opened {opens} connections; read-modify-write is not atomic"


def test_sqlite_runs_in_wal_mode(tmp_path: Path) -> None:
    """WAL lets a reader proceed while a writer holds the file, which is what keeps
    the single-connection transaction from serialising on the next caller."""
    store = GoalStore(tmp_path / "goals.db")
    with store._connect() as conn:
        mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
    assert mode.lower() == "wal"
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python3 -m pytest tests/test_persistence_resilience.py -k "one_connection or wal_mode" -v`

Expected: `test_transition_reads_and_writes_on_one_connection` FAIL，报 `AssertionError: transition opened 2 connections; read-modify-write is not atomic`；`test_apply_usage_...` 同样 FAIL（2 connections）；`test_sqlite_runs_in_wal_mode` FAIL，报 `AssertionError: assert 'delete' == 'wal'`。

- [ ] **Step 3: 开 WAL 与 busy_timeout**

`src/goal_persistence/store.py` 的 `_ensure_schema`（现 `:95-98`）改为：

```python
    def _ensure_schema(self) -> None:
        with self._connect() as conn:
            # WAL lets a reader proceed while a writer holds the file, so the
            # single-connection transactions below don't serialise on the next caller.
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA busy_timeout=5000")
            conn.executescript(SCHEMA)
            conn.commit()
```

- [ ] **Step 4: 把 `_persist` 拆成「在给定连接上写」**

把现 `:132-154` 的 `_persist` 改为：

```python
    def _persist_on(self, conn: sqlite3.Connection, goal: Goal) -> None:
        """Write the row on a caller-supplied connection (no commit — the caller owns it)."""
        conn.execute(
            """
            UPDATE thread_goals SET
                objective = ?, status = ?, budget_tokens = ?, budget_wall_ms = ?,
                usage = ?, blocked_count = ?, last_blocked_reason = ?,
                updated_at = ?
            WHERE thread_id = ?
            """,
            (
                goal.objective,
                goal.status.value,
                goal.budget_tokens,
                goal.budget_wall_ms,
                _serialize_usage(goal.usage),
                goal.blocked_count,
                goal.last_blocked_reason,
                goal.updated_at.isoformat(),
                goal.thread_id,
            ),
        )

    def _persist(self, goal: Goal) -> None:
        with self._connect() as conn:
            self._persist_on(conn, goal)
            conn.commit()
```

- [ ] **Step 5: 让 `transition` / `apply_usage` 单连接读改写**

把现 `:156-172` 的两个方法改为：

```python
    def transition(
        self, thread_id: str, new_status: GoalStatus, reason: Optional[str] = None
    ) -> Goal:
        # Read and write on ONE connection: a read on connection A followed by a
        # write on connection B can interleave with another writer and lose an update.
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM thread_goals WHERE thread_id = ?", (thread_id,)
            ).fetchone()
            if row is None:
                raise KeyError(f"Goal not found for thread {thread_id}")
            goal = _row_to_goal(row)
            goal.with_status(new_status, reason=reason)
            self._persist_on(conn, goal)
            conn.commit()
        return goal

    def apply_usage(self, thread_id: str, delta: Usage) -> Goal:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM thread_goals WHERE thread_id = ?", (thread_id,)
            ).fetchone()
            if row is None:
                raise KeyError(f"Goal not found for thread {thread_id}")
            goal = _row_to_goal(row)
            goal.apply_usage(delta)
            self._persist_on(conn, goal)
            conn.commit()
        return goal
```

- [ ] **Step 6: 跑测试确认通过**

Run: `python3 -m pytest tests/test_persistence_resilience.py -q`

Expected: 全 PASS（新增 3 条 + 原有全绿）。

- [ ] **Step 7: 跑全量回归**

Run: `python3 -m pytest -q`

Expected: 全绿。`GoalStore.transition` / `apply_usage` 的行为契约（返回值、`KeyError`、状态转移合法性）未变，只有连接数变了。

- [ ] **Step 8: 提交**

```bash
git add src/goal_persistence/store.py tests/test_persistence_resilience.py
git commit -m "goal_persistence: make transition/apply_usage atomic, enable WAL

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

## Task 6: B2 — 消毒 `thread_id` 再落文件名

**Files:**
- Modify: `src/goal_loop/loop_runner.py:30-31`（新增模块级 helper）、`:86-98`（`_persist_state` / `_load_state`）、`:234-238`（改用同一 helper）
- Test: `tests/test_goal_loop.py`（追加）

**Interfaces:**
- Consumes: 无
- Produces: 模块级 `_safe_id(raw: str) -> str`（`loop_runner.py` 内私有）

**关键约束：** `_persist_state` 与 `_load_state` 必须用**同一个** helper。只改写入侧会让恢复路径按原始 id 找不到文件，把「路径穿越」换成「状态静默丢失」——更糟。

- [ ] **Step 1: 写失败的测试**

追加到 `tests/test_goal_loop.py`，加在 `class TestGoalLoopRunner:` 内（该文件用 `runtime` fixture + `make_spec(...)` + `EchoMaker`，三者均已在文件顶部定义，无需新增 import）：

```python
    def test_thread_id_cannot_escape_the_state_dir(
        self, runtime: GoalRuntime, tmp_path: Path
    ) -> None:
        """A thread_id is caller-supplied. Writing it straight into a filename lets
        '../../escape' drop the loop state two directories above the state dir."""
        state_dir = tmp_path / "state"
        runner = GoalLoopRunner(
            make_spec(criteria=[AcceptanceCriterion("c1", "pass", verify_command='py -c "pass"')]),
            runtime,
            EchoMaker("implemented"),
            StaticChecker(Verdict.PASS),
            state_dir=state_dir,
        )

        runner.run("../../escape")

        assert not (state_dir / ".." / ".." / "escape.loop_state.json").resolve().exists()
        assert (state_dir / ".._.._escape.loop_state.json").exists()

    def test_resume_reads_the_state_file_the_writer_wrote(
        self, runtime: GoalRuntime, tmp_path: Path
    ) -> None:
        """Write and read must agree on the sanitized filename. If only the writer
        sanitized, resume silently starts from scratch — trading a path traversal
        for a state loss, which is worse."""
        state_dir = tmp_path / "state"
        spec = make_spec(
            criteria=[AcceptanceCriterion("c1", "pass", verify_command='py -c "pass"')]
        )
        runner = GoalLoopRunner(
            spec, runtime, EchoMaker("implemented"), StaticChecker(Verdict.PASS),
            state_dir=state_dir,
        )
        runner.run("../thread")

        assert sorted(p.name for p in state_dir.glob("*.loop_state.json")) == [
            ".._thread.loop_state.json"
        ]

        resumed = GoalLoopRunner(
            spec, runtime, EchoMaker("implemented"), StaticChecker(Verdict.PASS),
            state_dir=state_dir,
        )
        resumed._thread_id = "../thread"
        assert resumed._load_state().current_round == runner.state.current_round
```

（`resumed._thread_id = ...` 是本文件既有风格：`test_records_per_criterion_verdicts` 同样直接读 `runner._state.rounds[0]`。）

- [ ] **Step 2: 跑测试确认失败**

Run: `python3 -m pytest tests/test_goal_loop.py -k "escape_the_state_dir or writer_wrote" -v`

Expected: `test_thread_id_cannot_escape_the_state_dir` FAIL，报 `AssertionError: assert not True`（实测确会在 `state_dir/../..` 下生成 `escape.loop_state.json`，见本计划开头证据表 B2 行）；`test_resume_reads_the_state_file_the_writer_wrote` FAIL，报 `AssertionError: assert [] == ['.._thread.loop_state.json']` —— 修复前 `state_dir` 里一个文件都没有，状态被写到了 `tmp_path/thread.loop_state.json`。

- [ ] **Step 3: 加 helper**

`src/goal_loop/loop_runner.py`，在 `_now()`（`:30-31`）之后加：

```python
def _safe_id(raw: str) -> str:
    """A thread id reduced to a single safe filename component.

    ``thread_id`` is caller-supplied and lands in a path, so anything that is not
    alphanumeric (or ``- _ .``) becomes ``_``. The hippocampus trajectory id already
    used this rule; both go through here so they cannot drift.
    """
    return "".join(c if c.isalnum() or c in "-_." else "_" for c in raw)
```

- [ ] **Step 4: 两处文件名都用它**

把现 `:90` 与 `:94` 的

```python
        path = self._state_dir / f"{self._thread_id}.loop_state.json"
```

都改为：

```python
        path = self._state_dir / f"{_safe_id(self._thread_id)}.loop_state.json"
```

（`:90` 在 `_persist_state` 内，`:94` 在 `_load_state` 内 —— **两处都要改**。）

- [ ] **Step 5: hippocampus 轨迹改用同一 helper**

把现 `:235-238` 的

```python
                traj_id = "".join(
                    c if c.isalnum() or c in "-_." else "_"
                    for c in f"{thread_id}-round-{round_number}"
                )
```

改为：

```python
                traj_id = _safe_id(f"{thread_id}-round-{round_number}")
```

- [ ] **Step 6: 跑测试确认通过**

Run: `python3 -m pytest tests/test_goal_loop.py -q`

Expected: 全 PASS。

- [ ] **Step 7: 提交**

```bash
git add src/goal_loop/loop_runner.py tests/test_goal_loop.py
git commit -m "goal_loop: sanitize thread_id before it becomes a state filename

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

## Task 7: B3 — 暂停原因不再被静默丢掉

**Files:**
- Modify: `src/goal_persistence/models.py:104-115`（`Goal.with_status` 的分支链）
- Test: `tests/test_persistence_resilience.py`（追加）

**Interfaces:**
- Consumes: `GoalStatus.PAUSED`（`models.py:17`）
- Produces: 无新符号——`Goal.last_blocked_reason` 在 PAUSED 时保留 `reason`

- [ ] **Step 1: 写失败的测试**

追加到 `tests/test_persistence_resilience.py`（该文件已有 `runtime` fixture）：

```python
def test_pause_records_the_reason_for_the_operator(runtime: GoalRuntime) -> None:
    """PAUSED is a human checkpoint, not a terminal state — the whole point is that
    an operator later reads WHY it stopped. The reason was falling into the generic
    else-branch and being reset to None, both in memory and on disk."""
    runtime.create_goal("t1", "objective")

    goal = runtime.pause("t1", "needs human review")

    assert goal.status == GoalStatus.PAUSED
    assert goal.last_blocked_reason == "needs human review"
    assert runtime.get_goal("t1").last_blocked_reason == "needs human review"
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python3 -m pytest tests/test_persistence_resilience.py::test_pause_records_the_reason_for_the_operator -v`

Expected: FAIL，报 `AssertionError: assert None == 'needs human review'`。

- [ ] **Step 3: 加 PAUSED 分支**

`src/goal_persistence/models.py` 的 `with_status`（现 `:104-115`）改为：

```python
        if new_status == GoalStatus.BLOCKED:
            self.blocked_count += 1
            self.last_blocked_reason = reason
        elif new_status == GoalStatus.COMPLETE:
            # Capture completion evidence; field reused to keep schema simple.
            self.last_blocked_reason = reason
            self.blocked_count = 0
        elif new_status == GoalStatus.PAUSED:
            # A pause is a human checkpoint: the operator needs the reason, so unlike
            # the other non-blocked transitions this one keeps it.
            self.blocked_count = 0
            self.last_blocked_reason = reason
        else:
            # Reset blocked counter when leaving blocked state.
            self.blocked_count = 0
            self.last_blocked_reason = None
```

- [ ] **Step 4: 跑测试确认通过**

Run: `python3 -m pytest tests/test_persistence_resilience.py -q`

Expected: 全 PASS。

- [ ] **Step 5: 提交**

```bash
git add src/goal_persistence/models.py tests/test_persistence_resilience.py
git commit -m "goal_persistence: keep the pause reason instead of resetting it to None

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

## Task 8: B4 — Orchestrator 聚合 `modified_files`

**Files:**
- Modify: `src/goal_loop/orchestrator.py:68-74`（`make` 的 `MakerOutput` 构造）
- Test: `tests/test_orchestrator.py`（追加）

**Interfaces:**
- Consumes: `MakerOutput.modified_files: list[str]`（`src/goal_loop/models.py:197`）；`loop_runner.py:266` 的 `self._state.files_changed += len(maker_output.modified_files)`
- Produces: 无新符号——`Orchestrator.make()` 的返回值带上各 executor 的 `modified_files`（保序去重）

- [ ] **Step 1: 写失败的测试**

追加到 `tests/test_orchestrator.py`（`_Planner` / `_Executor` / `_Reviewer` / `_spec` 已在该文件定义；`_Executor()` 默认 `ok=True` 且不填 `modified_files`）：

```python
def test_orchestrator_aggregates_modified_files() -> None:
    """Each executor reports the files it touched. Dropping them here pinned the
    loop's files_changed counter at 0 no matter how much work the fan-out did."""

    class _TouchingExecutor:
        def __call__(self, spec: GoalSpec, plan: Plan, step: str) -> MakerOutput:
            return MakerOutput(summary=step, modified_files=[f"{step}.py"], tokens_used=1)

    orch = Orchestrator(_Planner(["a", "b"]), _TouchingExecutor(), _Reviewer())
    out = orch.make(_spec(), state=None, steering="")

    assert out.modified_files == ["a.py", "b.py"]


def test_orchestrator_skips_an_agent_that_reports_no_files() -> None:
    orch = Orchestrator(_Planner(["a"]), _Executor(), _Reviewer())
    out = orch.make(_spec(), state=None, steering="")

    assert out.modified_files == []
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python3 -m pytest tests/test_orchestrator.py -k aggregates_modified_files -v`

Expected: FAIL，报 `AssertionError: assert [] == ['a.py', 'b.py']`。

- [ ] **Step 3: 聚合**

`src/goal_loop/orchestrator.py` 的 `make`（现 `:62-74`）在 `tokens` 之后加一行，并把它塞进 `MakerOutput`：

```python
        tokens = sum(o.tokens_used for o in outputs)
        modified = list(dict.fromkeys(f for o in outputs for f in o.modified_files))
        return MakerOutput(
            summary=summary,
            ok=ok,
            tokens_used=tokens,
            modified_files=modified,
            self_verification="orchestrated planner -> executor(s) -> reviewer",
        )
```

`dict.fromkeys` 保序去重：两个 executor 报同一个文件时，`files_changed` 不该数两次。

- [ ] **Step 4: 跑测试确认通过**

Run: `python3 -m pytest tests/test_orchestrator.py -q`

Expected: 全 PASS。

- [ ] **Step 5: 提交**

```bash
git add src/goal_loop/orchestrator.py tests/test_orchestrator.py
git commit -m "goal_loop: aggregate modified_files so files_changed is no longer pinned at 0

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

## Task 9: B5 — `CompactionResult.to_dict()` 在 slots dataclass 上崩溃

**Files:**
- Modify: `src/context_compaction/models.py:3`（import）、`:44-51`（`to_dict`）
- Test: `tests/test_context_compaction.py`（追加）

**Interfaces:**
- Consumes: `ContextItem`（`frozen=True, slots=True`，`models.py:7-19`）
- Produces: `CompactionResult.to_dict()` 恢复可用，返回 `{"kept": [dict], "archived": [dict], "summary": str, "archive_path": str, "compact_occurred": bool}`

- [ ] **Step 1: 写失败的测试**

追加到 `tests/test_context_compaction.py`（顶部已有的 `item()` helper 直接用）：

```python
def test_compaction_result_to_dict_serializes_slots_items(tmp_path: Path) -> None:
    """ContextItem is a slots dataclass, so it has no __dict__ — to_dict() raised
    AttributeError and the archive result was never serializable."""
    from context_compaction.models import CompactionResult

    result = CompactionResult(
        kept=[item("a", "kept", important=True)],
        archived=[item("b", "archived")],
        summary="one item archived",
        archive_path=str(tmp_path / "archive.json"),
        compact_occurred=True,
    )

    payload = result.to_dict()

    assert payload["kept"] == [
        {"id": "a", "content": "kept", "important": True, "source": ""}
    ]
    assert payload["archived"] == [
        {"id": "b", "content": "archived", "important": False, "source": ""}
    ]
    assert payload["summary"] == "one item archived"
    assert payload["compact_occurred"] is True
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python3 -m pytest tests/test_context_compaction.py::test_compaction_result_to_dict_serializes_slots_items -v`

Expected: FAIL，报 `AttributeError: 'ContextItem' object has no attribute '__dict__'`。

- [ ] **Step 3: 换成 `dataclasses.asdict`**

`src/context_compaction/models.py` 的 import 行（现 `:3`）改为：

```python
from dataclasses import asdict, dataclass
```

`to_dict`（现 `:44-51`）改为：

```python
    def to_dict(self) -> dict[str, Any]:
        return {
            "kept": [asdict(item) for item in self.kept],
            "archived": [asdict(item) for item in self.archived],
            "summary": self.summary,
            "archive_path": self.archive_path,
            "compact_occurred": self.compact_occurred,
        }
```

`asdict()` 走 `fields()` + `getattr`，对 `slots=True` 的 dataclass 同样成立；`__dict__` 是 `slots` 唯一的例外。这不是「改成 asdict 碰巧能跑」，是换到了不依赖 `__dict__` 的那条路径上。

- [ ] **Step 4: 跑测试确认通过**

Run: `python3 -m pytest tests/test_context_compaction.py -q`

Expected: 全 PASS。

- [ ] **Step 5: 提交**

```bash
git add src/context_compaction/models.py tests/test_context_compaction.py
git commit -m "context_compaction: serialize slots dataclasses with asdict, not __dict__

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

## 收尾验收

- [ ] **Step 1: 全量测试**

Run: `python3 -m pytest -q`

Expected: 全绿（基线 355 passed / 56 skipped，加本计划新增约 15 条）。

- [ ] **Step 2: 覆盖率门**

Run: `python3 -m pytest -q --cov=src --cov-report=term-missing --cov-fail-under=92`

Expected: `Required test coverage of 92.0% reached`。基线 93.45%。

- [ ] **Step 3: per-package 地板**

Run: `python3 scripts/coverage_gate.py`

Expected: 退出码 0，每个包 ≥ 70%。

- [ ] **Step 4: 零第三方 import 复核**

Run: `grep -rnE "^(import|from) (langgraph|langchain|anthropic|pydantic)" src/`

Expected: 无输出（`src/` 零第三方依赖这条约束没被本计划破坏）。
