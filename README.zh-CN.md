# Agent Harness 101

一个最小、可测试的 agent harness 实现,覆盖六大运行时层,外加安全与成本两个横切面:

- **上下文管理**(`context_compaction/`)
- **工具管理**(`tool_registry/`)
- **执行环境**(`sandbox/`)
- **状态与记忆**(`goal_persistence/`、`hippocampus/`)
- **验证与评估**(`goal_loop/`、`eval_harness/`)
- **观测与审计**(`observability/`)
- **安全**(`safety/`)与**成本控制**(`cost_control/`)

源自 Codex 的 goal 功能,对应《Agent Harness 101》课程。

## 它是怎么工作的（说人话）

你写一个目标——一句目标 + 一串验收标准。harness 像个挑剔的评审那样去跑它:`maker`
负责产出,一个独立的 `checker` 回头重新读产物、逐条对照验收标准核实,而不是信 maker
嘴里的"做完了"。循环一直转,直到每条标准都被机器验证(`complete`)、maker 不再有进展
(`blocked`)、或预算用光(`budget_limited`)。

它小而快。实测:两轮跑完约 **1.2 秒**;上下文溢出后从 48,550 字压到 609 字(98.75%
压缩),10 条标记项原样保留;长期记忆回放约 **0.6 毫秒**;fail-closed 沙箱比裸
subprocess 只多 **约 5%**。完整数字见 `doc/02_goal_loop/efficiency.md`。

## 亮点特性

- **双层目标系统** —— `goal_persistence` 让目标持久化(SQLite 行、空闲自启动、
  anti-drift 引导、断点续跑、预算自动切换);`goal_loop` 让它跑起来(解析
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
- **自我改进闭环** —— 一轮跑完蒸馏成一条持久教训(`repeat`/`avoid`),下一轮把相关
  教训重新注入引导,让 harness 越跑越好,而不是重复旧错。
- **安全与成本横切面** —— `safety/` 提供 RBAC + 高风险人机协同(HITL)+ 注入标记;
  `cost_control/` 提供令牌桶限流 + 工具结果缓存。
- **用数字说话** —— `examples/measure_efficiency.py` 产出真实测量值
  (回合数、压缩比、回放延迟、沙箱开销),记录在 `doc/02_goal_loop/efficiency.md`。
- **确定性测试** —— red-green TDD,`fail_under=92` 覆盖率闸门;`faux_provider` 只替换
  "LLM 说的话"让循环真跑;`world_verifier` 重新读产物,不信 maker/checker 自报。

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
| `faux_provider/` | 确定性脚本 LLM(`FauxProvider` + `FauxMaker`):只替换"LLM 说的话" | 目标 2 |
| `goal_loop/world_verifier.py` | `WorldVerifier`:重新读产物,不信 maker/checker 自报 | 目标 3 |
| `goal_loop/self_improver.py` | `SelfImprover`:把结果蒸馏成持久教训,下轮重注入 | 目标 7 |
| `goal_loop/scheduler.py` | `Scheduler`:重臂活跃目标,逐个串行跑到终态,出晨报 | 目标 8 |
| `goal_loop/orchestrator.py` | `Orchestrator`:目标拆分给 planner/executor/reviewer 子代理 | 目标 9 |

`goal_loop` 也带 `registered_roles.py`,把 maker/checker 经过 `ToolRegistry` 权限闸门
——所以最后一个"平行玩具"缺口(循环 → 工具注册表)是靠构造闭合的,不是靠嘴说。

`goal_loop` 组合持久化层而非重写它:`GoalLoopRunner` 驱动 `GoalRuntime` 做持久化目标,
并把 blocked/complete 审计委托给它。其它层同样独立、小且可测,各自带可运行 demo。

## goal_persistence 做什么

1. **持久化状态** —— 每个 thread/context ID 一行 SQLite。
2. **空闲自启动** —— 线程空闲且目标活跃时,产出一条 continuation 引导提示。
3. **防漂移引导** —— 每次续跑都重新注入完整目标 + completion/blocked 审计契约。
4. **续跑** —— 重启时重读活跃目标,重新武装空闲循环。
5. **预算自动切换** —— token 或墙钟预算超了,在 accounting 写入里把目标翻到
   `budget_limited`。

## 状态机

```text
Active → { Paused, Blocked, UsageLimited, BudgetLimited, Complete }
```

`Complete` 和 `BudgetLimited` 是终态。非法迁移会被拒绝。

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

## 安装

```bash
uv venv
.venv\Scripts\activate  # Windows
uv pip install -e ".[dev]"
```

## 运行测试

一条命令跑完全部测试;`scripts/check.sh` 是合闸——格式、lint、测试、覆盖率四样全过才算
绿。

```bash
python3 -m pytest -q                 # 全量测试（217 passed，另 56 opt-in 真 LLM）
scripts/check.sh                     # 四闸：format + lint + test + coverage
```

当前 **217 个测试全绿，覆盖率 97.18%**（`fail_under=92` 闸门，见 `pyproject.toml` 的
`[tool.coverage]`）。覆盖 happy path、fail-closed、红队对抗、全系统 E2E 四类场景；另有 56 条 opt-in 真 LLM 四维评测（`RUN_REAL_LLM=1` 时跑，见下文「真 LLM 深度评测」）。
未覆盖的 ~2.82% 是防御性校验 / 跳过分支 / 恢复终态 goal 的 resume 分支，不是死代码。

## 真 LLM 深度评测（opt-in）

`eval_llm/` + `tests/test_real_llm.py` 用真模型跑四维（广度 / 单 loop 终态 / 真实计量 / 红队）× 5 模型（deepseek-v4-pro/flash、grok-4.6、minimax-m3、kimi-k2-turbo-preview，glm 无额度排除），56 条全绿。每个测试的上下文（为什么、干什么、预期、实测、超出预期怎么处理）如下：

| 测试（干什么） | 为什么 | 预期 | 实测 | 超出预期怎么处理 |
|---|---|---|---|---|
| 模型探测 | 5 个模型都得真跑，先定格式 | 都 Anthropic 兼容 | 4 个是；kimi 走 OpenAI；glm 无额度（code 1113） | kimi 换 OpenAI 客户端=**修复**；glm 排除=**接受** |
| thinking 模型边界（judge/summarizer） | 每个 LLM 边界接真模型 | 返回判定 / 非空摘要 | 4 模型正常；kimi 空 `content`（reasoning 吃掉 `max_tokens`） | 提取过滤 `b.type=="text"` + `max_tokens`→512=**修复** |
| token 记账 | 计量要真实 | `input - cache + output` | llm-proxy 两字段互不重叠，相减 -97 | 改 `input + output`=**修复** |
| 数字 latency | 真实延迟给 SLO | 各模型几秒 | 多数 3–6s；grok-4.6 平均 15.2s / std 17.0s | **接受**（模型特性）；结论=设超时看分布 |
| 红队 | 真对抗模型打确定性守卫 | 都到不了 complete | 注入/自报/高风险 5 模型全 blocked=符合预期 | **接受**，无 bug |

它烧真 API,所以 opt-in 默认 skip:

```bash
RUN_REAL_LLM=1 python3 -m pytest tests/test_real_llm.py -q
```

每次跑写一份每模型报告到 `doc/10_real_llm_eval/report.md`。单个模型不可达时 graceful
skip,不拖垮整批。

## goal_loop 用法

三样东西拼起来:一份目标契约(`goal.md`)、一个持久化库、两个回调——`maker` 产出、独立
`checker` 验收。交给 `GoalLoopRunner` 调 `run`,循环自己跑完并返回终态。

```python
from pathlib import Path

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

这套 API 不跑循环,只负责"记住"目标状态和 token 消耗。先建目标,空闲时拿引导提示,跑一
轮记 token,最后带证据标记完成。

```python
from goal_persistence import GoalRuntime, GoalStore, GoalStatus

runtime = GoalRuntime(GoalStore("goals.db"))

# 建一个目标。
runtime.create_goal(
    thread_id="thread-1",
    objective="Implement a fail-closed sandbox for the agent harness",
    budget_tokens=10_000,
)

# 线程空闲时,要一次续跑引导。
cont = runtime.maybe_continue("thread-1")
if cont:
    print(cont.steering_prompt)

# 跑一轮。
acc = runtime.start_turn("thread-1")
acc.add_llm_call(input_tokens=500, cached_input_tokens=50, output_tokens=150)
runtime.notify_tool_finish("thread-1")
goal = runtime.end_turn("thread-1")

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

## 测试结果

### 单元测试

```bash
.\.venv\Scripts\python.exe -m pytest tests/test_harness.py -q
```

```text
20 passed in 0.76s
```

| 测试组 | 数量 | 结果 |
|---|---|---|
| `TestStatusMachine` | 3 | passed |
| `TestPersistence` | 2 | passed |
| `TestAccounting` | 4 | passed |
| `TestIdleSelfStart` | 4 | passed |
| `TestResume` | 2 | passed |
| `TestBlockedAudit` | 2 | passed |
| `TestCompletionAudit` | 1 | passed |
| `TestLifecycleEvents` | 2 | passed |

### LLM demo

```bash
.\.venv\Scripts\python.exe examples\llm_demo.py
```

配置(`.env`):

```ini
ANTHROPIC_BASE_URL=https://llm-proxy.tapsvc.com
ANTHROPIC_MODEL=deepseek/deepseek-v4-pro
ANTHROPIC_AUTH_TOKEN=...
```

真 LLM 评测现在覆盖 5 模型 × 4 维——见上文「真 LLM 深度评测」。下面的「结果」表是早前
MiniMax 端点跑的,保留作历史记录。

结果:

| 指标 | 值 |
|---|---|
| 目标 | 写一个文档齐全的小 Python 函数,迭代算第 n 个斐波那契数,再简要说明时间/空间复杂度 |
| 模型 | `MiniMax-M3` |
| 执行轮数 | 2 |
| 最终状态 | `complete` |
| 总 token | 948 / 5,000 预算 |
| 证据 | LLM 产出了斐波那契函数 |

harness 每轮都正确重注入引导提示、追踪 token 用量、控制在预算内,并在有证据时接受完成。

**捕获的 LLM 输出**(demo 截断在 600 字符后;完整响应不持久化):

Turn 1:

```text
I'll write a well-documented Python function that computes the nth Fibonacci number iteratively, then explain its complexity.

```python
def fibonacci(n):
    """
    Compute the nth Fibonacci number iteratively.

    The Fibonacci sequence is defined as:
        F(0) = 0, F(1) = 1
        F(n) = F(n-1) + F(n-2) for n >= 2

    Parameters
    ----------
    n : int
        The index (non-negative integer) of the desired Fibonacci number.

    Returns
    -------
    int
        The nth Fibonacci number.

    Raises
    ------
    ValueError
        If n is not a non-negative integer.

    Exam...
```

Turn 2:

```text
I'll write a well-documented Python function that computes the nth Fibonacci number iteratively, then explain its complexity.

```python
def fibonacci(n: int) -> int:
    """
    Compute the nth Fibonacci number iteratively.

    The Fibonacci sequence is defined as:
        F(0) = 0
        F(1) = 1
        F(n) = F(n-1) + F(n-2) for n >= 2

    Parameters
    ----------
    n : int
        The index (non-negative integer) of the desired Fibonacci number.

    Returns
    -------
    int
        The nth Fibonacci number.

    Raises
    ------
    ValueError
        If n is negative.
    Type...
```

## 项目历程

完整的两栏(ME/YOU)构建历程见 [`JOURNEY.md`](JOURNEY.md):从持久化内核到六层
harness、两次外部审查、真正的组合接线,以及效率测量。
