# Agent Harness 101

一个最小、可测试的 agent harness 实现,覆盖六大运行时层,外加安全与成本两个横切面:

- **上下文管理**(`context_compaction/`)
- **工具管理**(`tool_registry/`)
- **执行环境**(`sandbox/`)
- **状态与记忆**(`goal_persistence/`、`hippocampus/`)
- **验证与评估**(`goal_loop/`、`eval_harness/`)
- **观测与审计**(`observability/`)
- **安全**(`safety/`)与**成本控制**(`cost_control/`)

提炼自 Codex goal 功能,并与 *Agent Harness 101* 课程对齐。

## 亮点特性

- **双层目标系统** —— `goal_persistence` 让目标持久化(SQLite 行、空闲自启动、
  anti-drift 引导、断点续跑、预算自动切换);`goal_loop` 让它*跑起来*(解析
  `goal.md`、maker/checker 分离、机器验证、停止条件)。
- **生成器/评估器分离** —— maker 自报"做完了"永远不算完成;只有独立 checker 的
  判定加机器验证过的验收标准才能结束。
- **组合的运行时** —— `GoalLoopRunner` 把验证命令交给 fail-closed
  的 `sandbox`、把事件写进 append-only 的 `observability` trace、把每一轮记进
  `hippocampus` 长期记忆。
- **Fail-closed 执行** —— 未配置的沙箱返回 `SANDBOX_UNAVAILABLE` 拒绝执行,绝不裸奔;
  命令有白名单,且以 `shell=False` 运行。
- **80% 上下文压缩** —— 上下文越过窗口 80% 时,被标记的内容原样保留,其余归档并摘要。
- **海马体长期记忆** —— 任务轨迹 → 重要内容索引 → 本地缓存 → 学习/遗忘/纠正 →
  回放/回溯。
- **安全与成本横切面** —— `safety/` 提供 RBAC + 高风险人机协同(HITL)+ 注入标记;
  `cost_control/` 提供令牌桶限流 + 工具结果缓存。
- **用数字说话** —— `examples/measure_efficiency.py` 产出真实测量值
  (回合数、压缩比、回放延迟、沙箱开销),记录在 `doc/02_goal_loop/efficiency.md`。

## 模块

| 模块 | 职责 | 来源 |
|---|---|---|
| `goal_persistence/` | 持久化状态、空闲自启动、anti-drift 引导、续跑、预算自动切换 | Codex goal 功能 |
| `goal_loop/` | `goal.md` 解析、maker/checker 分离、机器验证、循环状态、停止条件 | `learn-harness-engineering` 第 13 讲 / 项目 07 |
| `context_compaction/` | 80% 截断、标记内容原样保留、其余归档 + 摘要 | 学习指南 ① |
| `hippocampus/` | 任务轨迹、重要内容索引、本地缓存、学习/遗忘、回放 | 学习指南 ④ |
| `tool_registry/` | 注册工具、权限标签、最小权限、schema 校验 | 学习指南 ② |
| `sandbox/` | Fail-closed 白名单执行器(非 OS 级沙箱) | 学习指南 ③ |
| `eval_harness/` | 评测集 + 确定性 ExactJudge + LLMJudge(fail-closed,超时/异常/垃圾回复判 FAIL) | 学习指南 ⑤ |
| `observability/` | Append-only trace 日志 + 字节级回放 | 学习指南 ⑥ |
| `safety/` | RBAC 角色、高风险 HITL、prompt 注入标记 | 学习指南 M6 |
| `cost_control/` | 令牌桶限流 + 工具结果缓存 | 学习指南 M5.7 |

`goal_loop` 组合持久化层而非重写它:`GoalLoopRunner` 驱动 `GoalRuntime` 做持久化目标,
并把 blocked/complete 审计委托给它。其它层同样独立、小且可测,各自带可运行 demo。

## 状态机

```text
Active → { Paused, Blocked, UsageLimited, BudgetLimited, Complete }
```

`Complete` 和 `BudgetLimited` 是终态。非法迁移会被拒绝。

## 安装

```bash
uv venv
.venv\Scripts\activate  # Windows
uv pip install -e ".[dev]"
```

## 运行测试

```bash
python3 -m pytest -q                 # 全量测试（217 passed，另 56 opt-in 真 LLM）
scripts/check.sh                     # 四闸：format + lint + test + coverage
```

当前 **217 个测试全绿，覆盖率 97.18%**（`fail_under=92` 闸门，见 `pyproject.toml` 的
`[tool.coverage]`）。覆盖 happy path、fail-closed、红队对抗、全系统 E2E 四类场景；另有 56 条 opt-in 真 LLM 四维评测（`RUN_REAL_LLM=1` 时跑，见下文「真 LLM 深度评测」）。
未覆盖的 ~2.82% 是防御性校验 / 跳过分支 / 恢复终态 goal 的 resume 分支，不是死代码。

## 真 LLM 基线

用真实模型跑通一次 harness（`examples/llm_goal_loop.py`）：

| 指标 | 值 |
|---|---|
| 模型 | `deepseek/deepseek-v4-pro`（经 `https://llm-proxy.tapsvc.com`，`ANTHROPIC_AUTH_TOKEN`） |
| 终态 | complete / 1 轮 |
| token | ~185（首次冷缓存 565，随缓存波动） |
| 墙钟 | 5.19–7.50s / 平均 6.21s |

真数字与「只 mock LLM 边界、其余跑真货」的分工见 `doc/04_faux_provider/benchmark.md`。

## 真 LLM 深度评测（opt-in）

上表只测了一条 happy path，够验证「能跑」，不够量化「多稳」。`eval_llm/` + `tests/test_real_llm.py` 把评测扩成 **四维 × 5 模型**：

- **广度**：每个 harness LLM 边界都接真模型（maker / LLMJudge / summarizer）
- **深度**：单 loop 终态（complete / blocked 三振 / budget_limited / stopped_max_rounds）
- **数字**：真实 latency mean±std、token、成本
- **红队**：真对抗模型 vs 确定性守卫（注入 / 自报 / 高风险动作）

5 个可用模型：deepseek-v4-pro/flash、grok-4.6、minimax-m3 走 Anthropic 格式，kimi-k2-turbo-preview 走 OpenAI 格式（glm 无额度排除），56 条全绿。套件默认 skip，显式 `RUN_REAL_LLM=1` 才跑；单模型挂掉 graceful skip 不拖垮整批；真数字见 `doc/10_real_llm_eval/report.md`。

## goal_loop 用法

```python
from goal_loop import GoalLoopRunner, GoalSpec
from goal_persistence import GoalRuntime, GoalStore

spec = GoalSpec.from_markdown("goal.md")  # 人类写的契约
runtime = GoalRuntime(GoalStore("goals.db"))

runner = GoalLoopRunner(
    spec,
    runtime,
    maker,      # 一个 (spec, state, steering) -> MakerOutput 的可调用对象
    checker,    # 一个独立的 (spec, output) -> CheckerOutput 可调用对象
)

status = runner.run("thread-1")
assert status.value == "complete"
```

只有当每个验收标准都被机器验证、且独立 checker 返回非 FAIL 判定时,循环才会完成。
maker 的自报永远不能结束目标。

## 持久化用法

```python
from goal_persistence import GoalRuntime, GoalStore, GoalStatus

runtime = GoalRuntime(GoalStore("goals.db"))
runtime.create_goal(
    thread_id="thread-1",
    objective="Implement a fail-closed sandbox for the agent harness",
    budget_tokens=10_000,
)

cont = runtime.maybe_continue("thread-1")
if cont:
    print(cont.steering_prompt)

acc = runtime.start_turn("thread-1")
acc.add_llm_call(input_tokens=500, cached_input_tokens=50, output_tokens=150)
runtime.notify_tool_finish("thread-1")
runtime.end_turn("thread-1")

# 只有带证据才能完成。
runtime.mark_complete("thread-1", "sandbox tests pass")
```

## 效率测量

```bash
py -3 examples/measure_efficiency.py
```

它会输出并写一份 `examples/efficiency_report.json`,详细说明见
`doc/02_goal_loop/efficiency.md`。已测得:循环 2 回合约 1.2 秒;上下文压缩
48,550 → 609 字符(98.75% 压缩,10/10 重要项保留);海马体回放约 0.6 毫秒;
沙箱开销约 5%。

## 项目布局

```text
src/                         # 11 个 harness 包（src 布局）
  goal_persistence/          # 持久化目标状态机(状态层)
  goal_loop/                 # maker/checker 验证循环 + Scheduler/Orchestrator/SelfImprover
  context_compaction/        # 上下文管理层(80% 截断压缩)
  hippocampus/               # 长期记忆层
  tool_registry/             # 工具管理层
  sandbox/                   # 执行环境层(fail-closed 白名单 + PathPolicy 文件写隔离)
  eval_harness/              # 验证与评估层(ExactJudge + LLMJudge fail-closed)
  observability/             # 观测与审计层(append-only trace + span 记 duration_ms)
  safety/                    # 安全横切面(RBAC + HITL + 注入标记)
  cost_control/              # 成本横切面(限流 + 缓存 + TokenLedger + 按模型计价)
examples/                    # 可运行 demo
tests/                       # 测试（217 + 56 opt-in 真 LLM）
scripts/check.sh             # 四闸：format + lint + test + coverage
doc/
  course/                    # TASK.md + 00-课程大纲.md(课程)
  roadmap/100_tasks.md       # 100 任务 P0/P1/P2 路线图
JOURNEY.md                   # 项目完整历程(ME/YOU 双栏,中文)
README.md / README.zh-CN.md  # 英文 / 中文说明
```

## 项目历程

完整的两栏(ME/YOU)构建历程见 [`JOURNEY.md`](JOURNEY.md):从持久化内核到六层
harness、两次外部审查、真正的组合接线,以及效率测量。
