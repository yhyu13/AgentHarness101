# Memory

> Chronological action log. Hooks and AI append to this file automatically.
> Old sessions are consolidated by the daemon weekly.

| Time | Description | File(s) | Outcome | ~tokens |
|---|---|---|---|---|
| 17:1x | 对比四 reference harness 的 TDD 做法 | doc/reference_harness/comparison.md | 三问 A/B/C + 共同点「只 mock LLM 边界」 | 高 |
| 17:1x | 写三个 plan doc（各含自我批判） | doc/03,04,05_*/plan.md | 目标1/2/3 规格落定 | 高 |
| 17:1x | 派 3 子代理并行实现（red-green + benchmark + journey） | pyproject.toml, scripts/, faux_provider/, goal_loop/world_verifier.py, tests/* | 110 passed, 覆盖 92.58% | 高 |
| 17:2x | 修 meta-test 精确列表 bug + faux_provider 进 source + .coverage 进 gitignore | tests/test_coverage_gate.py, pyproject.toml, .gitignore | 全绿 | 中 |
| 03:1x | 写全系统 E2E 测试（8 层 + 3 新组件一次 run，happy+对抗） | tests/test_system_e2e.py | 2 passed，一次通过 | 中 |
| 04:0x | 加 GoalLoopRunner.state 公开只读属性 + 逐轮 trace demo + 输出写 doc | goal_loop/loop_runner.py, examples/system_e2e_trace.py, doc/06_system_e2e/trace.md | 每轮对话可打印 | 中 |
| 04:5x | 红蓝对抗：红队 4 攻击先红，蓝队修 loop_runner fail-closed + safety HIGH_RISK/注入变体 | tests/test_red_team.py, goal_loop/loop_runner.py, safety/safety.py, .wolf/buglog.json | 4 攻击转绿，116 passed | 中 |
| 09:0x | thinking benchmark：量化测试（关=省略参数/开=adaptive/stats 均值方差）+ 脚本；无 key 真实验待确认 | tests/test_thinking_benchmark.py, examples/thinking_benchmark.py | 5 passed，121 passed 全绿 | 中 |
| 23:1x | 自我改进闭环（目标7）：harness_skills 调研蒸馏 → SelfImprover(distill/relevant_lessons/steering_context) + Hippocampus.facts() + loop_runner 可选接线 | goal_loop/self_improver.py, hippocampus/memory.py, goal_loop/loop_runner.py, tests/test_self_improver.py, doc/07_self_improve/*, doc/reference_harness/harness_skills.md | 139 passed / 覆盖 93.33% / self_improver 100% | 中 |
| 00:42 | 100 任务路线图 + P0 目标2/3（无人值守调度 Scheduler + 多代理编排 Orchestrator）：先核对 crashed-maker 早已 fail-closed，写 doc/roadmap/100_tasks.md，再 TDD 落 scheduler.py/orchestrator.py | goal_loop/scheduler.py, goal_loop/orchestrator.py, goal_loop/__init__.py, tests/test_scheduler.py, tests/test_orchestrator.py, doc/roadmap/100_tasks.md, JOURNEY.md, README.md, .wolf/STATUS.md, .wolf/cerebrum.md | 154 passed / 覆盖 93.79% / 两新模块 100% | 中 |

## Session: 2026-08-29 21:52

| Time | Action | File(s) | Outcome | ~Tokens |
|------|--------|---------|---------|--------|
| 22:05 | Synced stale Kilo hook pre-read.ts (SDD block) from template | .kilo/plugin/openwolf/pre-read.ts | identical to openwolf src | ~0 tok |

## Session: 2026-08-30 22:16

| Time | Action | File(s) | Outcome | ~Tokens |
|------|--------|---------|---------|--------|

## Session: 2026-08-30 22:17

| Time | Action | File(s) | Outcome | ~Tokens |
|------|--------|---------|---------|--------|
| 22:25 | Edited tests/test_faux_provider.py | modified test_stream_yields_reply_and_records_call() | ~334 |
| 22:26 | Edited README.md | modified LLM() | ~118 |
| 22:26 | Edited README.md | 6→11 lines | ~232 |
| 22:27 | Edited README.md | 8→11 lines | ~118 |
| 22:27 | Edited README.md | 3→7 lines | ~123 |
| 22:27 | Edited JOURNEY.md | inline fix | ~42 |
| 22:27 | Edited doc/04_faux_provider/journey.md | 2→2 lines | ~35 |
| 22:30 | Session end: 7 writes across 4 files (test_faux_provider.py, README.md, JOURNEY.md, journey.md) | 8 reads | ~11363 tok |
| 22:31 | 收口：判 provider.py:121-124 为行为（非死代码）+ 补 monkeypatch-sleep 确定性测试；README 补三模块+测试总数126+覆盖率闸门；勾掉 JOURNEY/doc 风险条目；STATUS 推进、cerebrum 记学习 | tests/test_faux_provider.py, README.md, JOURNEY.md, doc/04_faux_provider/journey.md, .wolf/STATUS.md, .wolf/cerebrum.md | 126 passed / 覆盖率 93.11 过 92 闸门 | ~4.5k |
| 22:31 | Session end: 7 writes across 4 files (test_faux_provider.py, README.md, JOURNEY.md, journey.md) | 8 reads | ~11363 tok |
| 22:32 | Session end: 7 writes across 4 files (test_faux_provider.py, README.md, JOURNEY.md, journey.md) | 8 reads | ~11363 tok |
| 22:36 | Session end: 7 writes across 4 files (test_faux_provider.py, README.md, JOURNEY.md, journey.md) | 10 reads | ~16498 tok |
| 22:47 | Session end: 7 writes across 4 files (test_faux_provider.py, README.md, JOURNEY.md, journey.md) | 11 reads | ~16639 tok |
| 22:53 | Edited CLAUDE.md | expanded (+17 lines) | ~161 |
| 22:53 | Edited AGENTS.md | expanded (+15 lines) | ~163 |
| 22:53 | Edited .claude/rules/openwolf.md | reduced (-7 lines) | ~110 |
| 22:54 | Session end: 10 writes across 7 files (test_faux_provider.py, README.md, JOURNEY.md, journey.md, CLAUDE.md) | 13 reads | ~17493 tok |

## Session: 2026-08-30 23:02

| Time | Action | File(s) | Outcome | ~Tokens |
|------|--------|---------|---------|--------|

## Session: 2026-08-30 23:02

| Time | Action | File(s) | Outcome | ~Tokens |
|------|--------|---------|---------|--------|
| 15:0X | push to origin/main: committed 86 files (world verifier, faux_provider, coverage gate, agent configs); excluded .wolf/ + node_modules | d17d7c2 | pushed a155c6a..d17d7c2 | ~400 |
| 23:08 | Created doc/reference_harness/harness_skills.md | — | ~937 |
| 23:09 | Created tests/test_self_improver.py | — | ~2094 |
| 23:10 | Created goal_loop/self_improver.py | — | ~959 |
| 23:10 | Edited hippocampus/memory.py | modified retrospective() | ~98 |
| 23:11 | Edited goal_loop/loop_runner.py | added 1 import(s) | ~42 |
| 23:11 | Edited goal_loop/loop_runner.py | 3→4 lines | ~48 |
| 23:11 | Edited goal_loop/loop_runner.py | 2→3 lines | ~37 |
| 23:11 | Edited goal_loop/loop_runner.py | 4→9 lines | ~116 |
| 23:11 | Edited goal_loop/loop_runner.py | modified _finalize() | ~174 |
| 23:11 | Edited goal_loop/__init__.py | added 1 import(s) | ~49 |
| 23:11 | Edited goal_loop/__init__.py | 4→5 lines | ~27 |
| 23:13 | Edited tests/test_self_improver.py | modified test_relevant_lessons_empty_objective_matches_nothing() | ~135 |
| 23:14 | Created doc/07_self_improve/plan.md | — | ~992 |
| 23:15 | Created doc/07_self_improve/benchmark.md | — | ~389 |
| 23:15 | Created doc/07_self_improve/journey.md | — | ~740 |
| 23:16 | Edited README.md | 1→2 lines | ~80 |
| 23:16 | Edited README.md | 1→2 lines | ~53 |
| 23:16 | Edited README.md | 4→4 lines | ~75 |
| 23:16 | Edited README.md | 2→5 lines | ~98 |
| 23:17 | Edited JOURNEY.md | expanded (+10 lines) | ~211 |
| 23:19 | Session end: 20 writes across 11 files (harness_skills.md, test_self_improver.py, self_improver.py, memory.py, loop_runner.py) | 20 reads | ~36320 tok |
| 23:21 | Session end: 20 writes across 11 files (harness_skills.md, test_self_improver.py, self_improver.py, memory.py, loop_runner.py) | 20 reads | ~36320 tok |
| 23:22 | Session end: 20 writes across 11 files (harness_skills.md, test_self_improver.py, self_improver.py, memory.py, loop_runner.py) | 20 reads | ~36320 tok |
| 23:22 | Session end: 20 writes across 11 files (harness_skills.md, test_self_improver.py, self_improver.py, memory.py, loop_runner.py) | 20 reads | ~36320 tok |
| 23:22 | Session end: 20 writes across 11 files (harness_skills.md, test_self_improver.py, self_improver.py, memory.py, loop_runner.py) | 20 reads | ~36320 tok |
| 23:23 | Session end: 20 writes across 11 files (harness_skills.md, test_self_improver.py, self_improver.py, memory.py, loop_runner.py) | 20 reads | ~36320 tok |
| 23:23 | Session end: 20 writes across 11 files (harness_skills.md, test_self_improver.py, self_improver.py, memory.py, loop_runner.py) | 20 reads | ~36320 tok |
| 23:23 | Session end: 20 writes across 11 files (harness_skills.md, test_self_improver.py, self_improver.py, memory.py, loop_runner.py) | 20 reads | ~36320 tok |
| 23:23 | Session end: 20 writes across 11 files (harness_skills.md, test_self_improver.py, self_improver.py, memory.py, loop_runner.py) | 20 reads | ~36320 tok |
| 23:24 | Session end: 20 writes across 11 files (harness_skills.md, test_self_improver.py, self_improver.py, memory.py, loop_runner.py) | 20 reads | ~36320 tok |
| 08:46 | Session end: 20 writes across 11 files (harness_skills.md, test_self_improver.py, self_improver.py, memory.py, loop_runner.py) | 20 reads | ~36320 tok |
| 08:46 | Session end: 20 writes across 11 files (harness_skills.md, test_self_improver.py, self_improver.py, memory.py, loop_runner.py) | 20 reads | ~36320 tok |
| 08:46 | Session end: 20 writes across 11 files (harness_skills.md, test_self_improver.py, self_improver.py, memory.py, loop_runner.py) | 20 reads | ~36320 tok |
| 08:47 | Session end: 20 writes across 11 files (harness_skills.md, test_self_improver.py, self_improver.py, memory.py, loop_runner.py) | 20 reads | ~36320 tok |
| 08:47 | Session end: 20 writes across 11 files (harness_skills.md, test_self_improver.py, self_improver.py, memory.py, loop_runner.py) | 20 reads | ~36320 tok |
| 08:47 | Session end: 20 writes across 11 files (harness_skills.md, test_self_improver.py, self_improver.py, memory.py, loop_runner.py) | 20 reads | ~36320 tok |
| 08:47 | Session end: 20 writes across 11 files (harness_skills.md, test_self_improver.py, self_improver.py, memory.py, loop_runner.py) | 20 reads | ~36320 tok |
| 08:47 | Session end: 20 writes across 11 files (harness_skills.md, test_self_improver.py, self_improver.py, memory.py, loop_runner.py) | 20 reads | ~36320 tok |
| 08:47 | Session end: 20 writes across 11 files (harness_skills.md, test_self_improver.py, self_improver.py, memory.py, loop_runner.py) | 20 reads | ~36320 tok |
| 08:47 | Session end: 20 writes across 11 files (harness_skills.md, test_self_improver.py, self_improver.py, memory.py, loop_runner.py) | 20 reads | ~36320 tok |

## Session: 2026-08-31 08:50

| Time | Action | File(s) | Outcome | ~Tokens |
|------|--------|---------|---------|--------|
| 10:40 | Edited CLAUDE.md | inline fix | ~42 |
| 10:40 | Edited CLAUDE.md | 3→5 lines | ~34 |
| 10:41 | Edited CLAUDE.md | 1→3 lines | ~36 |
| 10:47 | 收口：CLAUDE.md 三处 fix（补测试命令、debug 纪律优先级、round report 短路规则）+ 定位并修 .wolf/hooks/stop.js 的 buglog 对 .md 误报 | CLAUDE.md, .wolf/hooks/stop.js | 文档改定 + hook 误报修复 | 中 |
| 10:41 | Session end: 3 writes across 1 files (CLAUDE.md) | 5 reads | ~4537 tok |
| 10:42 | Session end: 3 writes across 1 files (CLAUDE.md) | 5 reads | ~4537 tok |
| 10:42 | Session end: 3 writes across 1 files (CLAUDE.md) | 5 reads | ~4537 tok |
| 10:43 | Session end: 3 writes across 1 files (CLAUDE.md) | 5 reads | ~4537 tok |
| 10:45 | Session end: 3 writes across 1 files (CLAUDE.md) | 5 reads | ~4537 tok |
| 10:45 | Session end: 3 writes across 1 files (CLAUDE.md) | 5 reads | ~4537 tok |
| 10:46 | Session end: 3 writes across 1 files (CLAUDE.md) | 5 reads | ~4537 tok |
| 10:47 | Session end: 3 writes across 1 files (CLAUDE.md) | 5 reads | ~4537 tok |
| 10:51 | Session end: 3 writes across 1 files (CLAUDE.md) | 5 reads | ~4537 tok |
| 11:08 | Session end: 3 writes across 1 files (CLAUDE.md) | 5 reads | ~4537 tok |
| 11:18 | Edited .gitignore | — | ~120 |
| 11:19 | Session end: 4 writes across 2 files (CLAUDE.md, .gitignore) | 5 reads | ~4666 tok |
| 11:38 | Edited pyproject.toml | reduced (-12 lines) | ~29 |
| 11:38 | Edited tests/test_coverage_gate.py | modified test_coverage_run_has_source_branch_omit() | ~187 |
| 11:40 | Edited tests/test_goal_loop.py | "goal_loop" → "src" | ~28 |
| 11:41 | Session end: 7 writes across 5 files (CLAUDE.md, .gitignore, pyproject.toml, test_coverage_gate.py, test_goal_loop.py) | 8 reads | ~12185 tok |
| 11:45 | Session end: 7 writes across 5 files (CLAUDE.md, .gitignore, pyproject.toml, test_coverage_gate.py, test_goal_loop.py) | 8 reads | ~12185 tok |

## Session: 2026-08-31 00:06

| Time | Action | File(s) | Outcome | ~Tokens |
|------|--------|---------|---------|--------|

## Session: 2026-08-31 00:20

| Time | Action | File(s) | Outcome | ~Tokens |
|------|--------|---------|---------|--------|
| 00:27 | Edited JOURNEY.md | expanded (+12 lines) | ~166 |
| 00:29 | Created doc/roadmap/100_tasks.md | — | ~1976 |
| 00:29 | Edited doc/roadmap/100_tasks.md | inline fix | ~37 |
| 00:29 | Edited doc/roadmap/100_tasks.md | expanded (+14 lines) | ~280 |
| 00:32 | Created tests/test_scheduler.py | — | ~1490 |
| 00:33 | Created tests/test_orchestrator.py | — | ~1119 |
| 00:33 | Created src/goal_loop/scheduler.py | — | ~1252 |
| 00:33 | Created src/goal_loop/orchestrator.py | — | ~767 |
| 00:34 | Edited src/goal_loop/__init__.py | added 2 import(s) | ~100 |
| 00:34 | Edited src/goal_loop/__init__.py | 5→9 lines | ~46 |
| 00:36 | Edited tests/test_scheduler.py | modified test_active_goals_returns_continuations() | ~98 |
| 00:39 | Edited README.md | 1→3 lines | ~116 |
| 00:39 | Edited README.md | 139 → 154 | ~20 |
| 00:39 | Edited JOURNEY.md | expanded (+12 lines) | ~235 |
| 00:40 | Session end: 14 writes across 8 files (JOURNEY.md, 100_tasks.md, test_scheduler.py, test_orchestrator.py, scheduler.py) | 15 reads | ~36227 tok |
| 00:41 | Session end: 14 writes across 8 files (JOURNEY.md, 100_tasks.md, test_scheduler.py, test_orchestrator.py, scheduler.py) | 15 reads | ~36227 tok |
| 00:41 | Session end: 14 writes across 8 files (JOURNEY.md, 100_tasks.md, test_scheduler.py, test_orchestrator.py, scheduler.py) | 15 reads | ~36227 tok |
| 00:42 | Session end: 14 writes across 8 files (JOURNEY.md, 100_tasks.md, test_scheduler.py, test_orchestrator.py, scheduler.py) | 15 reads | ~36227 tok |
| 00:44 | Edited src/eval_harness/judge.py | added 1 import(s) | ~50 |
| 00:45 | Edited src/eval_harness/judge.py | modified __init__() | ~623 |
| 00:45 | Edited src/eval_harness/__init__.py | 12→13 lines | ~84 |
| 00:45 | Edited src/cost_control/cost.py | modified estimate_cost() | ~332 |
| 00:45 | Edited src/cost_control/__init__.py | expanded (+7 lines) | ~64 |
| 00:46 | Edited src/observability/trace.py | added 2 import(s) | ~60 |
| 00:46 | Edited src/observability/trace.py | modified messages() | ~212 |
| 00:46 | Created tests/test_p1_hardening.py | — | ~801 |
| 00:47 | Created src/cost_control/ledger.py | — | ~588 |
| 00:48 | Edited src/cost_control/__init__.py | added 1 import(s) | ~82 |
| 00:48 | Edited tests/test_p1_hardening.py | 3→3 lines | ~40 |
| 00:48 | Edited tests/test_p1_hardening.py | modified test_span_appends_even_on_exception() | ~460 |
| 00:51 | Edited tests/test_adversarial_boundaries.py | modified test_goal_state_does_not_cross_contaminate() | ~438 |
| 00:52 | Edited pyproject.toml | expanded (+14 lines) | ~113 |
| 00:52 | Edited tests/test_harness.py | 2→2 lines | ~22 |
| 00:52 | Edited tests/test_adversarial_boundaries.py | 6→6 lines | ~93 |
| 00:52 | Edited tests/test_harness.py | 2→2 lines | ~24 |
| 00:53 | Edited tests/test_efficiency.py | inline fix | ~6 |
| 00:53 | Created scripts/check.sh | — | ~76 |
| 00:54 | Edited tests/test_goal_loop.py | modified test_accepts_argv_list() | ~163 |
| 00:56 | Created doc/08_scheduler/plan.md | — | ~836 |
| 00:56 | Created doc/08_scheduler/journey.md | — | ~592 |
| 00:57 | Created doc/09_orchestrator/plan.md | — | ~850 |
| 00:57 | Created doc/09_orchestrator/journey.md | — | ~583 |
| 00:58 | Edited README.md | 9→9 lines | ~112 |
| 00:58 | Edited JOURNEY.md | expanded (+8 lines) | ~396 |
| 00:59 | Created tests/test_path_policy.py | — | ~497 |
| 00:59 | Created src/sandbox/path_policy.py | — | ~375 |
| 00:59 | Edited src/sandbox/__init__.py | added 1 import(s) | ~65 |
| 01:02 | Created tests/test_guard_branches.py | — | ~2526 |
| 01:05 | Edited tests/test_p1_hardening.py | modified test_timeout_is_fail_closed() | ~234 |
| 01:07 | Edited doc/04_faux_provider/benchmark.md | 5→10 lines | ~118 |
| 01:07 | Edited examples/llm_goal_loop.py | inline fix | ~21 |
| 01:11 | Session end: 47 writes across 26 files (JOURNEY.md, 100_tasks.md, test_scheduler.py, test_orchestrator.py, scheduler.py) | 44 reads | ~78272 tok |
| 09:31 | Edited examples/llm_goal_loop.py | modified block() | ~84 |
| 09:32 | Edited examples/llm_goal_loop.py | 3→6 lines | ~118 |
| 09:34 | Edited examples/llm_goal_loop.py | 3→4 lines | ~84 |
| 09:35 | Edited doc/04_faux_provider/benchmark.md | expanded (+14 lines) | ~350 |
| 09:37 | Session end: 51 writes across 26 files (JOURNEY.md, 100_tasks.md, test_scheduler.py, test_orchestrator.py, scheduler.py) | 44 reads | ~79043 tok |
| 10:10 | Session end: 51 writes across 26 files (JOURNEY.md, 100_tasks.md, test_scheduler.py, test_orchestrator.py, scheduler.py) | 44 reads | ~79043 tok |
| 10:24 | Edited JOURNEY.md | expanded (+9 lines) | ~584 |
| 10:25 | Edited README.zh-CN.md | expanded (+15 lines) | ~180 |
| 10:25 | Edited README.zh-CN.md | 19→21 lines | ~272 |
| 10:25 | Edited README.zh-CN.md | inline fix | ~25 |
