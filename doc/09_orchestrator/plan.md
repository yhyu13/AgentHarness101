# 目标 9 — 多代理编排（maker/checker → planner/executor/reviewer）

> 来源：抄 §4 multi-agent orchestration 的横切规律——MetaGPT 的 SOP 角色分工、
> autogen 的 agent groups、deepseek-harness 的 subagent 分解。对应
> `doc/reference_harness/harness_skills.md` 的**目标 3**。

## 结论

**给 `goal_loop` 加一个 `Orchestrator`：一个编排器把 goal 拆成 N 步，每步交给一个
专职 executor，最后让 reviewer 审聚合输出。用它把 maker/checker 的「两角色
generator/evaluator 分离」升级成「planner/executor/reviewer 三角色分工」——本仓库
之前只有一个 maker 干全部活，没有「先规划、再分工、再复核」的编排层。**

## 现状锚点

- `goal_loop/loop_runner.py` 的 `Maker`/`Checker` Protocol 是「一个 maker 产出全部 +
  一个 checker 复核全部」的两角色模型，**没有「拆成 N 步、每步独立 executor」的
  中间层**。
- `goal_loop/models.py` 的 `MakerOutput`（`ok`/`summary`/`tokens_used`）和
  `CheckerOutput`（`verdict`/`issues`）已定义好聚合的输入/输出类型，编排器只需组合。
- `goal_loop/registered_roles.py` 的 `RegisteredMaker` 是 maker 的注册表角色，说明
  「角色」这个抽象已经在用，只是还没到「多角色编排」这一级。

## 参考来源（抄什么）

| 模式 | 出处 |
|---|---|
| SOP 角色分工（PM/architect/engineer） | MetaGPT（§4） |
| agent groups / 子代理分解 | autogen / deepseek-harness（§4） |
| generator/evaluator 分离 | 本仓库 maker/checker 已内化 |
| 「编排器只路由 callable，不发 LLM」 | §6 只 mock LLM 边界 |

## 方案

### 要建/改的文件

| 类型 | 文件 | 内容 |
|---|---|---|
| 新 | `goal_loop/orchestrator.py` | `Plan` 数据模型 + `Planner`/`Executor`/`Reviewer` 三 Protocol + `Orchestrator`（`make` / `check`） |
| 改 | `goal_loop/__init__.py` | 导出 `Orchestrator`、`Plan` |
| 新 | `tests/test_orchestrator.py` | 单元 + 循环集成测试（6 条） |
| 新 | `doc/09_orchestrator/{plan,journey}.md` | 本目标文档 |

### 关键决策

1. **三个 Protocol 都是 `__call__` 契约，可静态检查**：`Planner(spec) -> Plan`、
   `Executor(spec, plan, step) -> MakerOutput`、`Reviewer(spec, output) ->
   CheckerOutput`。编排器自己不干活，只组合这三个 callable。
2. **`make` 聚合 `ok` = 所有 executor 都 `ok` 且非空**：任一 executor 报 `ok=False`
   或抛异常，聚合结果 `ok=False`（fail-closed）。空 plan（零步）也 `ok=False`，不能
   空跑误判完成。
3. **`check` 把 reviewer 包成 `CheckerOutput`**：编排器当 checker 用时，`check` 直接
   委托 reviewer，返回值就是 loop 要的 `CheckerOutput`，不额外包装。
4. **编排器兼容 loop 的 maker/checker 契约**：`Orchestrator.make` 签名对齐 `Maker`，
   `Orchestrator.check` 签名对齐 `Checker`，所以能直接 `GoalLoopRunner(spec, runtime,
   orch.make, orch.check, ...)` 跑一轮。
5. **编排器不发 LLM 调用**：planner/executor/reviewer 的真实实现接在 LLM 边界之外
   （真 LLM 基线是 P1.41，需 key），编排器本身只路由，测试用 stub 即可。

## 成功标准（做完才叫 done）

1. **red-green**：先写 `test_orchestrator.py`，跑出 `ModuleNotFoundError`（红），再实现转绿。
2. **扇出**：planner 拆 N 步，每个 step 都交给 executor，聚合 summary 含全部步。
3. **fail-closed**：任一 executor `ok=False` 或崩溃 → 聚合 `ok=False`；空 plan → `ok=False`。
4. **reviewer 委托**：`check` 把 reviewer 的 `CheckerOutput` 原样返回。
5. **循环集成**：`Orchestrator` 当 maker+checker 接 `GoalLoopRunner` 跑一轮到 COMPLETE。
6. **全量测试仍绿**：`python3 -m pytest -q` 不破坏现有基线。

## 自我批判（写完第一稿后改了什么）

- **砍掉「编排器自己造 executor」**：初稿想让 `Orchestrator` 按 plan 内部生成 executor，
  但那样测试无法注入崩溃/失败。改成三 Protocol 全注入，编排器只组合，测试用 stub
  精确控制每个 executor 的返回。
- **空 plan 显式 fail-closed**：初稿「零步 = 无事可做 = ok」是错的——空跑不该算完成。
  改成 `not outputs` 时 `ok=False`，并加 `test_empty_plan_is_not_ok`。
- **`check` 不重写 verdict 映射**：reviewer 已返回 `CheckerOutput`，编排器再映射一次是
  多余。`check` 直接透传，保持单一直通。

## 边界

- 不碰 `scheduler.py`（目标 2，另一条垂直线）。
- 不碰 `loop_runner.py` 的状态机（只复用 maker/checker 契约，不改 round/budget/blocked）。
- 真 LLM 三角色（P1.41）依赖 key，本批用 stub 编排器跑通契约，不接真模型。
