# 目标 9 Journey — 多代理编排（planner/executor/reviewer）

> 两列表：ME（人/需求） vs YOU（AI 实现）。顶部先放风险和 TODO。

## 风险与 TODO

- **[注意] planner/executor/reviewer 是注入的 callable，编排器不校验它们的身份**：任何
  满足 `__call__` 签名的对象都能当 executor。这是有意为之（Protocol 鸭类型），但意味着
  「真 LLM 三角色」的落地（P1.41）要由调用方保证 planner 拆出的 step 真的能被执行——
  编排器不保证 step 语义正确，只保证「每步都交出去了、结果都聚合了」。
- **[设计取舍] `make` 的 summary 是拼接字符串，不是结构化 steps**：聚合 summary 把每步
  executor 的 summary 用换行拼起来。晨报/审计若要看「哪一步失败」的粒度，需要 executor
  侧透传 step 标签，本批 summary 只作人读聚合。
- **[注意] executor 崩溃时 summary 里记 `crashed`，但异常 traceback 没保留**：只有一句
  `step crashed`，丢堆栈。night-run 排障可能要看完整 traceback，本批未接线，属 P2 观测
  深水区。

## ME / YOU

| ME（需求 / 决策） | YOU（实现 / 发现） |
|---|---|
| 目标：把 goal 拆 N 步、每步专职 executor、reviewer 复核 | 读了 `loop_runner.py`（Maker/Checker Protocol）、`models.py`（MakerOutput/CheckerOutput），确认缺「拆步编排」中间层 |
| 来源：§4 三条（MetaGPT SOP / autogen groups / deepseek subagent） | 提炼成 `Planner`/`Executor`/`Reviewer` 三 Protocol + `Orchestrator.make/check` |
| 约定 seam：三角色全注入，编排器只组合 | 新建 `goal_loop/orchestrator.py`，`Plan` frozen dataclass 承载 objective + steps |
| 要求 red→green，先写失败测试 | 先写 `tests/test_orchestrator.py`，跑出 `ModuleNotFoundError`（红），再实现转绿 |
| 扇出：每步都交 executor | `test_fans_out_to_every_step`：三步 plan 的 summary 含全部三步 |
| fail-closed：executor 报失败/崩溃/空 plan 都 `ok=False` | `test_ok_false_when_executor_reports_failure` / `_crashes` / `test_empty_plan_is_not_ok` |
| reviewer 委托 | `test_check_delegates_to_reviewer`：reviewer 判 FAIL → `check` 返回 FAIL |
| 循环集成：编排器当 maker+checker 跑一轮 | `test_orchestrator_runs_goal_loop_to_completion`：接 `GoalLoopRunner` → COMPLETE |
| 不破坏现有基线 | 全量 `python3 -m pytest -q` → 154 passed；`orchestrator.py` 100%，总量 93.79% ≥ 92 |

## 关键决策与偏离

1. **放 `goal_loop/orchestrator.py` 而非顶层包**：与 `scheduler.py`/`self_improver.py`
   同级，只 `import goal_loop.models`，无环。
2. **三 Protocol 全注入、编排器纯路由**：编排器不构造任何 executor，测试用 `_Planner`
   /`_Executor`/`_Reviewer` stub 精确控制每个 step 的返回/崩溃，把「扇出 vs fail-closed」
   两条行为分开钉死。
3. **`Plan` 是 frozen dataclass 而非裸 list**：`objective + steps` 一起承载，reviewer
   能拿到完整上下文，避免「只有 step 字符串、丢了 objective」的隐式丢失。
4. **空 plan 显式 `ok=False`**：零步不该算完成，避免编排器在 planner 返回空时误判
   success。这是从「扇出 fail-closed」延伸出的第二个 fail-closed 边界。
