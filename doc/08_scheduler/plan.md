# 目标 8 — 无人值守调度（night runs = 定时重臂 + 晨报）

> 来源：抄 §3 autonomous/scheduled 的横切规律——openai/symphony 的「overnight runs」、
> khoj 的「schedule automations」、ralph 的「loop until PRD done」。对应
> `doc/reference_harness/harness_skills.md` 的**目标 2**。

## 结论

**给 `goal_loop` 加一个 `Scheduler`：定时重臂 active goals、串行跑每个 goal 到终态、
收尾生成晨报。用它把 harness 从「能跑一个 loop」升级到「能无人值守跑一整夜、早上读
报告」——本仓库之前有 `resume_all` 和 `run_until_terminal`，但没有把它们组合成一个
会自己重臂、会出报告的调度层。**

## 现状锚点

- `goal_persistence/runtime.py` 已有 `resume_all()`（列出全部 active goals 的
  `Continuation`）和 `run_until_terminal` 的挂点，但**没有任何运行时子系统的循环调
  用它们**——重臂靠人手。
- `goal_loop/loop_runner.py` 的 `run_until_terminal`（`loop_runner.py` 末尾）已经能
  把一个 goal 跑到终态，但一次只能跑一个，跑完就停，不产生跨 goal 的汇总。
- `GoalRuntime` 的 `list_active()`（`goal_persistence/store.py`）已能列 active goals，
  调度器的 `active_goals()` 只需委托它。

## 参考来源（抄什么）

| 模式 | 出处 |
|---|---|
| `overnight runs`：无人值守跑一批，早上看报告 | openai/symphony（§3） |
| `schedule automations`：定时重臂 | khoj（§3） |
| `loop until PRD done`：跑到终态为止 | ralph（§3） |
| 「调度器不发 LLM 调用，只路由 runner」 | §6 只 mock LLM 边界 |

## 方案

### 要建/改的文件

| 类型 | 文件 | 内容 |
|---|---|---|
| 新 | `goal_loop/scheduler.py` | `ScheduledRun` 数据模型 + `Scheduler`（`active_goals` / `run_once` / `morning_report` / `run_periodic`） |
| 改 | `goal_loop/__init__.py` | 导出 `Scheduler`、`ScheduledRun` |
| 新 | `tests/test_scheduler.py` | 单元 + 循环集成测试（8 条） |
| 新 | `doc/08_scheduler/{plan,journey}.md` | 本目标文档 |

### 关键决策

1. **`Scheduler` 是纯路由，不发 LLM 调用**：它只组合 `resume_all`（列 active goals）
   和 `run_until_terminal`（跑一个 goal），本身不碰模型。守住「只 mock LLM 边界」。
2. **`runners: dict[thread_id, Runner]` 显式注入**：调度器不构造 runner，由调用方把
   `thread_id → GoalLoopRunner` 映射传进来。缺 runner 的 goal 记 `skipped`，不 crash、
   不拖垮批次。
3. **单 goal 崩溃不中断批次**：`run_once` 用 try/except 隔离每个 runner，崩溃记
   `errored` 后继续下一个——night run 的关键是「一个 goal 挂不能停掉一整夜」。
4. **`run_periodic(sleep=..., stop_after=...)` 注入时钟**：`sleep` 和停止条件都可注入，
   测试里用 `sleep=lambda s: None` + `stop_after=N` 确定性断言「跑 N 轮后停」。
5. **晨报是 markdown 计数表 + 逐行**：`morning_report(runs)` 输出 `total/ completed/
   blocked/ errored/ skipped` 计数，再逐 goal 一行，供人早上一眼扫完。

## 成功标准（做完才叫 done）

1. **red-green**：先写 `test_scheduler.py`，跑出 `ModuleNotFoundError`（红），再实现转绿。
2. **顺序确定**：`run_once` 按 `resume_all` 的输入序串行返回 `ScheduledRun`，结果与输入同序。
3. **skip/errored 隔离**：无 runner → `skipped`；runner 崩溃 → `errored`，都继续下一个。
4. **晨报可读**：`morning_report` 含五类计数 + 逐 goal 一行。
5. **周期可测**：`run_periodic` 注入 sleep/停止条件，可确定性测「跑 N 轮后停」。
6. **全量测试仍绿**：`python3 -m pytest -q` 不破坏现有基线。

## 自我批判（写完第一稿后改了什么）

- **砍掉「新顶层 `scheduler/` 包」**：调度器要 `import goal_loop.loop_runner`（Runner
  Protocol）又会被 `goal_loop` import（导出），会造环。放 `goal_loop/scheduler.py`，与
  `orchestrator.py` / `self_improver.py` 同级对称，只依赖 `goal_persistence`。
- **`run_periodic` 不内置真实 `time.sleep` 语义**：初稿想直接 `while ... time.sleep()`,
  但那样测试无法确定性终止。改成注入 `sleep` callable + `stop_after`，测试传空函数。
- **`ScheduledRun` 用 frozen dataclass 而非 dict**：`to_dict()` 只作序列化出口，运行
  时保持不可变，避免跨 goal 意外改状态。

## 边界

- 不碰 `orchestrator.py`（目标 3，另一条垂直线）。
- 不碰 `loop_runner.py` 的状态机（round/budget/blocked 逻辑不动，只复用
  `run_until_terminal`）。
- 不碰 `pyproject.toml` / `scripts/check.sh`（新增模块自动进 `src` 覆盖闸门）。
