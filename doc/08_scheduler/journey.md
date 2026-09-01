# 目标 8 Journey — 无人值守调度（night runs）

> 两列表：ME（人/需求） vs YOU（AI 实现）。顶部先放风险和 TODO。

## 风险与 TODO

- **[注意] `active_goals()` 只列 ACTIVE 的 goal**：`resume_all()` 走 `list_active()`，
  已 BLOCKED/COMPLETE 的不会重臂。这是刻意行为（终态不重复跑），但意味着「一个 goal
  卡在 BLOCKED 一整夜」不会自己恢复——需要人看晨报手动 `unblock`。若要自动恢复，另加
  重试策略，本批不做。
- **[设计取舍] `run_periodic` 是「跑一轮→重臂→再跑」的串行循环，不是并发调度**：一个
  goal 卡住（虽然不 crash）会占住整夜。真正的并行/超时抢占是 P2，本批串行已够
  night-run 语义。
- **[注意] `ScheduledRun.summary` 只在 `errored` 时兜底填异常信息**：正常 complete/
  blocked 的 summary 是空字符串，晨报逐行只显示 status + thread_id。若要看「为什么
  blocked」，需要 runner 侧把 reason 透传出来，本批未接线。

## ME / YOU

| ME（需求 / 决策） | YOU（实现 / 发现） |
|---|---|
| 目标：定时重臂 active goals、串行跑、收尾晨报 | 读了 `runtime.py`（`resume_all` / `list_active`）、`loop_runner.py`（`run_until_terminal`），确认缺「组合层」 |
| 来源：§3 三条（symphony overnight / khoj schedule / ralph loop-until-done） | 提炼成 `Scheduler` 四方法：`active_goals` / `run_once` / `morning_report` / `run_periodic` |
| 约定 seam：`Scheduler(runtime, runners: dict[thread_id, Runner])`，纯路由不发 LLM | 新建 `goal_loop/scheduler.py`，`Runner` Protocol 只要求 `run_until_terminal` |
| 要求 red→green，先写失败测试 | 先写 `tests/test_scheduler.py`，跑出 `ModuleNotFoundError`（红），再实现转绿 |
| 单 goal 崩溃不中断批次 | `run_once` 逐个 try/except，崩溃记 `errored` 继续；`test_run_once_isolates_crashed_runner` |
| 缺 runner 不 crash | `test_run_once_skips_goal_without_runner`：无 runner 的 goal 记 `skipped` |
| 晨报计数 + 逐行 | `test_morning_report_counts_and_lists` 断言 `total=4/completed=1/blocked=1/errored=1/skipped=1` |
| 周期重臂可确定性测 | `run_periodic` 注入 `sleep=lambda s: None`；`test_run_periodic_stops_after_goals_terminal` / `_respects_stop_after` |
| 不破坏现有基线 | 全量 `python3 -m pytest -q` → 154 passed；`scheduler.py` 100%，总量 93.79% ≥ 92 |

## 关键决策与偏离

1. **放 `goal_loop/scheduler.py` 而非顶层包**：顶层 `scheduler/` 会 `import goal_loop`
   又被 `goal_loop` import，造环。放 goal_loop 内、只依赖 `goal_persistence`，与
   `orchestrator.py` / `self_improver.py` 同级。
2. **`Runner` Protocol 只要求 `run_until_terminal`**：调度器不关心 runner 内部（maker/
   checker/budget），只要它能「把一个 goal 跑到终态」。这让测试能用 `_Runner` stub
   控制返回/崩溃，隔离调度器自身逻辑。
3. **`ScheduledRun` frozen + `to_dict`**：运行时不可变，`to_dict()` 只作序列化出口，
   晨报/落盘由它展开。
4. **`run_periodic` 注入 `sleep`**：不内置真实 `time.sleep`，测试传空函数可瞬间跑完
   N 轮，避免 CI 睡真时间。
