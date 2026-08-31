# STATUS — TDD 对比 + 三目标实现

> Single source of truth for resuming work. Read this FIRST when starting a session.
> Last updated: 2026-08-30

---

## ✅ Done

- **四仓库 TDD 对比分析** → `doc/reference_harness/comparison.md`：结论是「四个仓库谈的是三个不同问题 A/B/C」，共同点只有「只 mock LLM 边界，其余跑真货」。
- **三个 plan doc（各含自我批判）** → `doc/03_tdd_testing/plan.md`、`doc/04_faux_provider/plan.md`、`doc/05_verify_world/plan.md`。
- **目标 1（red-green + 覆盖率闸门）**：`pyproject.toml` 加 `pytest-cov` + `[tool.coverage]`（`fail_under=92`、`precision=2`）；`scripts/check.sh` 单命令闸门；`AGENTS.md` 追加「测试纪律」三规则；`tests/test_coverage_gate.py` meta-test + watch-red 证明。
- **目标 2（faux provider）**：`faux_provider/`（`FauxProvider` + `FauxMaker`），13 测试，确定性 diff=0，~32.7ms/loop。
- **目标 3（verify the world）**：`goal_loop/world_verifier.py`（`WorldVerifier`）+ `loop_runner.py` 最小接线（可选参数 `world_verifier`，fail-closed），9 测试，误完成率 0/5。
- **全系统 E2E 测试** → `tests/test_system_e2e.py`：一次真实 run 串起 8 层（faux + persistence + loop + sandbox + trace + hippocampus + world_verifier + checker），happy path（complete）+ 对抗 path（假 exit-0 + 说谎 checker + 错产物 → blocked）两场景，2 passed。
- **红蓝对抗** → `tests/test_red_team.py`：红队 4 攻击（崩溃 maker/checker、注入变体 `Ignore ALL Previous Instructions`、`deploy` 风险降级）先红；蓝队修复（`loop_runner` 捕获 maker/checker 异常 fail-closed、`safety` 加 `_HIGH_RISK_ACTIONS` 内置 + 注入变体 marker）转绿。4 passed，漏洞记 `.wolf/buglog.json`。
- **全量验证**：`python3 -m pytest -q` → **116 passed**；覆盖率 **92.57% ≥ 92**。
- **收口**：`faux_provider/provider.py:121-124` 判为**行为**（`stream()` 分块语义）→ 补确定性测试（monkeypatch `time.sleep`），`faux_provider/provider.py` 覆盖率 100%；README 补 `faux_provider/`、`world_verifier.py`、`scripts/check.sh`+测试纪律 + 测试总数 79→126；JOURNEY/`doc/04_faux_provider/journey.md` 风险条目勾掉。全量 **126 passed**、覆盖率 **93.11% ≥ 92**。
- **harness skills 调研 → 自我改进闭环（目标 7）**：`doc/reference_harness/harness_skills.md` 把 `AGENTS_REPO.md` 的 100+ 仓库蒸馏成「五台阶 + 三条横切规律 + 三个新目标」；实现目标 1（§5 自我改进）`goal_loop/self_improver.py`（`SelfImprover`：run 结果→`repeat`/`avoid` 教训→下次注入 steering）+ `Hippocampus.facts()` + `GoalLoopRunner` 可选 `self_improver` 参数 fail-open。13 新测试，全量 **126→139 passed**、覆盖率 **93.33%**，`self_improver.py` 100%。

---

## 🚀 Next phase

**Goal:** 三条并行的候选（挑一条，其余留 backlog）。

1. **crashed maker 兜底决策**（遗留，本轮未动）——`run()` 是否兜底捕获 maker 异常，或维持现状（goal 停 `active`、不误判 complete）并用测试钉住。
2. **目标 2：无人值守调度（§3）**——`goal_loop/scheduler.py`：定时重臂 active goals、串行跑、收尾晨报。落点组合 `goal_persistence.resume_all` + `run_until_terminal`。
3. **目标 3：多代理编排（§4）**——`goal_loop/orchestrator.py`：编排器把 goal 拆给 N 个专职子代理（planner/executor/reviewer）。

### Open decisions
- crashed-maker 兜底本身即待定项。
- 真 LLM 基线要 key，`doc/04_faux_provider/benchmark.md` 标 `待确认`，拿 key 后补。
- 目标 2/3 各需 `doc/08_*`、`doc/09_*` plan doc（沿用 harness_skills.md 的目标拆分）。

---

## 📁 Active architecture

- **Stack:** Python 3.13（`python3`，**不是 `python`=2.7**）、pydantic 2.13、pytest 9.1、pytest-cov 7.1。
- **Key modules:** `goal_persistence` / `goal_loop` / `faux_provider` / `context_compaction` / `hippocampus` / `tool_registry` / `sandbox` / `eval_harness` / `observability` / `safety` / `cost_control`（共 11 个，coverage `source` 全覆盖）。
- **Patterns:** red-green（bug 修复带先红后绿的回归测试）；覆盖率闸门 `fail_under=92`（未覆盖行=死代码，不是该补测试）；verify the world（机器重读产物，不信自报）。

---

## ⚠️ External blockers (don't block coding)

- `examples/llm_goal_loop.py` 真 LLM 基线要 `MINIMAX_API_KEY`，无 key 时 benchmark 标 `待确认`，不编数字。

---

## 🔧 Useful commands

```bash
python3 -m pytest -q                                # 全量测试（139 passed）
python3 -m pytest --cov --cov-report=term-missing -q  # 覆盖率闸门（fail_under=92）
python3 -m pytest tests/test_faux_provider.py -q    # 单目标测试
python3 examples/system_e2e_trace.py                # 全系统 E2E 每轮对话 trace（happy + 对抗）
python3 examples/thinking_benchmark.py --rounds 5   # thinking 关/开 token+耗时对比（需 MINIMAX_API_KEY）
```

---

## 📚 References (read IF needed)

- `.wolf/cerebrum.md` — User Preferences + Do-Not-Repeat + Decision Log
- `.wolf/anatomy.md` — token-efficient file index
- `doc/reference_harness/comparison.md` — 四仓库 TDD 对比
- `doc/reference_harness/harness_skills.md` — harness skills 调研 → 三目标
- `doc/03_tdd_testing/plan.md` / `doc/04_faux_provider/plan.md` / `doc/05_verify_world/plan.md` / `doc/07_self_improve/plan.md`
