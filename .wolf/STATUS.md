# STATUS — TDD 对比 + 三目标实现

> Single source of truth for resuming work. Read this FIRST when starting a session.
> Last updated: 2026-09-01

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
- **src 布局迁移 + 100 任务路线图 + 目标 2/3（无人值守调度 + 多代理编排）**：`doc/roadmap/100_tasks.md`（100 条 P0/P1/P2 + 自我评审）；`goal_loop/scheduler.py`（`Scheduler`：`resume_all`→串行 `run_until_terminal`→晨报，skip/errored 隔离 + `run_periodic` 注入 sleep）+ `goal_loop/orchestrator.py`（`Orchestrator`：planner→executor×N→reviewer，`make`/`check` 接 loop）。全量 **140→154 passed**、覆盖率 **93.79%**，两新模块均 100%。crashed-maker 兜底核实为早已 fail-closed（`loop_runner.py:210-219`），无需新代码。
- **P1 加固（Era 33）**：`eval_harness/judge.py`（`LLMJudge` fail-closed，超时/异常/垃圾回复判 FAIL）；`cost_control/cost.py`（`Price`/`PRICING`/`estimate_cost` 按模型计价，未知模型 KeyError）+ `cost_control/ledger.py`（`TokenLedger` 持久化 input/output/calls）；`observability/trace.py`（`span` 记 `duration_ms`）；对抗补 `resume_all` 幂等 + 多 goal 状态隔离；`sandbox/path_policy.py`（`PathPolicy` 文件写白名单，`..` 穿越 fail-closed，seccomp/network 属 OS-gated）；CI `check.sh` 扩 fmt+lint+test+coverage 四闸 + `pyproject.toml` 加 ruff（line-length 100、E4/E7/E9/F）清空 34 条 lint；`doc/08_scheduler`/`doc/09_orchestrator` plan+journey 补齐；覆盖率补到 **97.18%**（目标 95%）。全量 **154→206 passed**。
- **真 LLM 深度评测套件（Era 35）**：`eval_llm/`（`client.py` 双格式适配 Anthropic/OpenAI + `report.py` 报告收集）+ `tests/test_real_llm.py`（四维 × 5 模型，`RUN_REAL_LLM=1` opt-in，单模型挂掉 graceful skip 不拖垮整批）。5 可用模型：deepseek-v4-pro/flash、grok-4.6、minimax-m3（Anthropic 格式）+ kimi-k2-turbo-preview（OpenAI 格式）；glm code 1113 无额度排除。56 条全绿（5×四维 + 探测 + 报告写盘）。抓出浅基线没暴露的真问题：thinking 模型（kimi）`reasoning_content` 消耗 `max_tokens`，小 cap 返回空 `content` → llmjudge/summarizer 提到 512。真数字见 `doc/10_real_llm_eval/report.md`（含每模型 metrics latency mean±std）。成本指标标待确认（PRICING 无真实模型 ID）。离线新增 11 测试，全量 **206→217 passed**（另 56 opt-in skipped）。
- **25 条 P0 增强全执行（本 quest）**：A 沙箱加固（PathPolicy 接线/环境 scrub/cwd/argv 绕过/HITL 绑定）、B 逐准则判定+证据+人工介入、C 目标循环韧性（in-flight 标记+崩溃恢复、重试退避、RunHistory 账本、QUARANTINED 毒目标、turn 中预算投影、重入 resume）、D 压缩（预算约束折叠、锚点保护、常驻 Do-Not-Repeat）、E 评测/成本/观测（RegressionGate 黄金对照、guard_budget、trace_cost 事件、trace 脱敏）、F 打包（src 布局 build-system、`ah` console script + `python -m agent_harness`、import-smoke/打包元数据/demo 三 meta-test、按包覆盖率闸门 `scripts/coverage_gate.py` 接入 check.sh）。全量 **217→272 passed**（另 56 opt-in skipped）、覆盖率 **95.93% ≥ 92**、按包闸门全 ≥70%、`ruff check` 清空 lint（新增 `agent_harness` 包 + `py.typed`）。
- **品味评分（taste_score，本 quest）**——多 agent 过夜竞争打分，黄金标准 `agent = LLM 头脑(C) + harness 手脚拓边(E) + 安全边界(S)`，成对帕累托判定不叠加记分，**E up & S down = 拉黑不是加分**。五道防 Goodhart 锁：成对比较 / 菜单变异 / 留出黄金组终审 / 回归否决 / judge-executor 分离+轮数预算上限，另加**自述不可信**（`did_expand`/`safe` 经 `verify` 外部证据推出，堵说谎型刷分）。探针从 `doc/roadmap/enhancements_100.md` + `tests/test_red_team.py` 合成；跑法 `PYTHONPATH=src python3 -m taste_score compete`。设计见 `doc/superpowers/specs/2026-09-02-taste-score-design.md`；已写入 CLAUDE.md/AGENTS.md。全量 **272→283 passed**（另 56 opt-in skipped）、覆盖率 **95.49% ≥ 92**、按包闸门全 ≥70%（taste_score 89.4%）、`ruff check` clean。

---

## 🚀 Next phase

**Goal:** P0 + P1 已收口（`doc/roadmap/100_tasks.md` 1–46），剩 P2（47–100）与两条待确认。

P1 已落定（Era 33）：LLM-judge、按模型计价、token 账本、trace span、CI 四闸、沙箱文件写隔离、`doc/08`/`doc/09`、覆盖率 97.18%、206 passed。

### Open decisions / 待确认
- **真 LLM 基线（P1.15–17 / 41–44）**：✅ 已跑通（2026-09-01）。修 `examples/llm_goal_loop.py` 三处（thinking block 提取、key 顺序对齐 env 三件套、token 记账 `input+output`），`deepseek/deepseek-v4-pro` 经 `llm-proxy.tapsvc.com` 跑出 **complete / 1 轮 / 185 token / 平均 6.21s**，机器 checker `answer()==42` PASS。真数字见 `doc/04_faux_provider/benchmark.md`。
- **seccomp/Landlock / network / fork 隔离（P1.18 / 20）**：Linux-only syscall 特性，Windows 降级到 `PathPolicy`（纯 pathlib 文件写隔离已落地）。要真隔离需 Linux 环境。
- **mypy 8 错误（P2.78/92）**：`src` 下 8 处类型错误（`sandbox/verifier` 的 `bytes|str`、`world_verifier` 的 `str|None in`、`models` 的 `datetime|None`、`loop_runner:184` 的 `int>=None`），多为 Optional 注解过宽，非运行时 bug（有真值守卫）。要 `py.typed`+CI 需先修。
- **P2（47–100）**：文档深水区、property-based/fuzz 测试、可观测导出、打包 wheel/Docker、生态整合、打磨重构——大部分独立可选，未启动。

---

## 📁 Active architecture

- **Stack:** Python 3.13（`python3`，**不是 `python`=2.7**）、pydantic 2.13、pytest 9.1、pytest-cov 7.1。
- **Key modules:** `goal_persistence` / `goal_loop` / `faux_provider` / `context_compaction` / `hippocampus` / `tool_registry` / `sandbox` / `eval_harness` / `observability` / `safety` / `cost_control`（共 11 个，coverage `source` 全覆盖）。
- **Patterns:** red-green（bug 修复带先红后绿的回归测试）；覆盖率闸门 `fail_under=92`（未覆盖行=死代码，不是该补测试）；verify the world（机器重读产物，不信自报）。

---

## ⚠️ External blockers (don't block coding)

- `examples/llm_goal_loop.py` 真 LLM 基线：key 在，但 model/base_url/key 三件套不一致（deepseek-v4-pro env vs MiniMax 示例假设）。对齐后重跑，否则 benchmark 标 `待确认`，不编数字。

---

## 🔧 Useful commands

```bash
python3 -m pytest -q                                # 全量测试（217 passed，另 56 opt-in skipped）
RUN_REAL_LLM=1 python3 -m pytest tests/test_real_llm.py -q  # 真 LLM 四维评测（烧真实 API，写 report.md）
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
