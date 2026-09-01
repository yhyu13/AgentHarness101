# Roadmap — 100 任务（P0 / P1 / P2）

> 本文是本仓库剩余工作的单一规划源。每条任务可独立 TDD、文件尽量不重叠、可并行。
> 生成时基线：**140 passed**、覆盖率 **93.33% ≥ 92**、11 个 src 包、`fail_under=92` 闸门。
> 硬目标只剩 harness_skills.md 里的 **目标 2（无人值守调度）** 与 **目标 3（多代理编排）**；crashed-maker 兜底已实现（`loop_runner.py:210-219`），只需补一条显式单测。

## 优先级定义

- **P0**：本仓库当前缺的核心运行时能力，本批就做（目标 2 + 目标 3 + crashed-maker 钉测试）。
- **P1**：加固 + 真 LLM 基线，让 harness 从「能跑」到「能无人值守一整夜 + 可审计」。
- **P2**：文档、打磨、可选的生态/整合项，不阻塞主流程。

## 铁律（每条任务都遵守）

1. 只 mock LLM 边界，其余跑真货（`faux_provider` 已内化）。
2. 每条任务先写能复现的用例（red），再改到通过（green），不编造不存在的 API。
3. 落点挂靠现有 `GoalRuntime.resume_all` / `run_until_terminal` / `Maker`/`Checker` Protocol，不重写内核。

---

## P0 — 核心剩余能力（本批执行，1–14）

### 目标 2：无人值守调度 `goal_loop/scheduler.py`

| # | 任务 | 验收（done 判据） |
|---|---|---|
| 1 | 定义 `ScheduledRun` 数据模型（thread_id / objective / 终态 status / 摘要） | `ScheduledRun` frozen dataclass，字段可往返 `to_dict` |
| 2 | `Scheduler.__init__(runtime, runners: dict[thread_id, GoalLoopRunner])` 挂接依赖 | 构造无异常，持有 runtime 与 runner 映射 |
| 3 | `Scheduler.active_goals()` 走 `runtime.resume_all()` 只取 active | 返回 `list[Continuation]`，不含 terminal |
| 4 | `Scheduler.run_once()`：串行 `run_until_terminal` 每个 active goal，收集 `ScheduledRun` | 顺序确定、每个 goal 跑完、结果按输入序返回 |
| 5 | `run_once` 遇无 runner 的 active goal → 记 `skipped`，不 crash、不拖垮其他 goal | 缺失 runner 不抛异常，`ScheduledRun.status` 标 skip |
| 6 | `run_once` 遇 runner 崩溃 → 捕获、记 `errored`，继续下一个 goal | 单 goal 崩溃不中断批次 |
| 7 | `Scheduler.morning_report(results)` 生成晨报 markdown（状态计数 + 逐 goal 一行） | 输出含总数/完成/阻塞/出错计数，逐行可读 |
| 8 | `Scheduler.run_periodic(sleep=..., stop_after=...)` 周期重臂 + 收尾报告 | 注入 sleep/now，可确定性测「跑 N 轮后停」 |

### 目标 3：多代理编排 `goal_loop/orchestrator.py`

| # | 任务 | 验收（done 判据） |
|---|---|---|
| 9 | 定义 `Planner` / `Executor` / `Reviewer` 三个 Protocol | 三个 `__call__` 契约清晰、可静态检查 |
| 10 | `Orchestrator.make(spec, state, steering)` 组合 planner→executor→聚合 `MakerOutput` | 输出 `ok` = 所有 executor 都 `ok`，summary 合并 plan 步 |
| 11 | `Orchestrator.check(spec, output)` 把 reviewer 包装成 `CheckerOutput` | reviewer 判定映射成 Verdict + issues |
| 12 | `Orchestrator` 拆 N 步、executor 崩溃 → `ok=False`（fail-closed） | 任一 executor 异常不拖垮编排，聚合 `ok=False` |
| 13 | `Orchestrator` 接入现有 `GoalLoopRunner`（as_maker/as_checker）跑通一轮 | 真实 `run()` 一轮，编排器当 maker+checker 不破坏循环契约 |
| 14 | crashed-maker 兜底显式单测（钉住 `loop_runner.py:210-219` 的 fail-closed） | 崩溃 maker → 单轮 `ok=False` 不崩、不误判 `complete`（连续无进展仍走 blocked 审计） |

---

## P1 — 加固与真 LLM 基线（15–46）

### 真 LLM 基线（需 `MINIMAX_API_KEY`，无 key 时标 `待确认`）

| # | 任务 | 验收 |
|---|---|---|
| 15 | `examples/llm_goal_loop.py` 接 `Scheduler` 跑一批 goal | 真实 loop 串行跑完，产出晨报 |
| 16 | 记录真 token/墙钟基线，写进 `doc/04_faux_provider/benchmark.md` | 数字带参照物（模型/轮数/条件），不编 |
| 17 | `doc/08_scheduler`、`doc/09_orchestrator` 各自 benchmark 补真数字 | 有 key 后补，无 key 标 `待确认` |

### 沙箱 OS 级隔离

| # | 任务 | 验收 |
|---|---|---|
| 18 | `sandbox` 加 seccomp/Landlock 后端（平台相关，Windows 降级） | 进程级隔离，有测试证明阻断越界 |
| 19 | 文件系统写隔离：白名单外路径拒绝 | 对抗测试写越界路径被拦 |
| 20 | 网络/子进程隔离（禁用出网、fork） | 测试证明被 fail-closed |

### eval_harness LLM-judge

| # | 任务 | 验收 |
|---|---|---|
| 21 | `eval_harness` 加 `LLMJudge`（接真 LLM 裁判） | 可换 `ExactJudge`，接口一致 |
| 22 | judge 超时/异常 fail-closed（不误判 PASS） | 对抗测试：judge 崩溃 → 判 fail |

### 观测与成本

| # | 任务 | 验收 |
|---|---|---|
| 23 | token-ledger 持久化 + 跨会话累加报表 | 重启动不丢数，报表可读 |
| 24 | `cost_control` 按模型计价（不同模型不同单价） | 计价可测，不硬编码单模型 |
| 25 | `observability.trace` 加 span/耗时字段 | 每轮 maker/checker 耗时可追溯 |

### 对抗与边界（补红队）

| # | 任务 | 验收 |
|---|---|---|
| 26 | scheduler 对抗：崩溃 runner 不拖垮其他 goal | 红队攻击转绿 |
| 27 | orchestrator 对抗：executor 崩溃 → `ok=False` | 红队攻击转绿 |
| 28 | 串行/并发隔离：多 goal 状态不串扰 | 测试证明线程内隔离 |
| 29 | `resume_all` 幂等：重复 resume 不重复跑同一 goal | 幂等测试通过 |

### 打包与 CI

| # | 任务 | 验收 |
|---|---|---|
| 30 | `scripts/check.sh` 扩到「fmt + lint + test + coverage」单命令闸门 | 一条命令全绿 |
| 31 | coverage `source` 子集 meta-test 保活（新增包不红） | `set(REQUIRED) <= set(actual)` |
| 32 | ruff/format 检查接入 CI | 风格违规即红 |
| 33 | Windows/posix 路径兼容测试（`shlex`/反斜杠） | 跨平台路径不漂 |

### 文档补齐（P1 级，跟实现同步）

| # | 任务 | 验收 |
|---|---|---|
| 34 | `doc/08_scheduler/plan.md`（目标 2 规格 + 自我批判） | 沿用 harness_skills.md 目标拆分 |
| 35 | `doc/08_scheduler/journey.md` | red→green 记录 + 风险 |
| 36 | `doc/09_orchestrator/plan.md`（目标 3 规格 + 自我批判） | 同上 |
| 37 | `doc/09_orchestrator/journey.md` | red→green 记录 + 风险 |
| 38 | README 补 `scheduler` / `orchestrator` 模块 + 测试总数 | 模块 + 数字同步 |
| 39 | JOURNEY.md 补 Era 32（目标 2/3 实现） | 保留 ME/YOU 叙事 |
| 40 | `.wolf/anatomy.md` 重建索引（含新增 2 模块） | `openwolf scan` 后索引新鲜 |

### 真 LLM 编排验证（依赖 key）

| # | 任务 | 验收 |
|---|---|---|
| 41 | orchestrator 用真 LLM 当 planner/executor/reviewer 跑一轮 | 真实三角色分工，报告产出 |
| 42 | scheduler 用真 LLM 跑整夜（≥N 个 goal） | 无人值守 + 晨报，无人工干预 |
| 43 | 对比「faux vs 真 LLM」结果一致性 | 记录差异，判断 faux 保真度 |
| 44 | 真 LLM 失败重试/回退策略验证 | 瞬断恢复、持久崩溃上抛 |

### 横切质量

| # | 任务 | 验收 |
|---|---|---|
| 45 | 覆盖率补到 95% 以上（未覆盖行判定「行为 vs 死代码」） | `fail_under=95` 过 |
| 46 | 全量回归 + 覆盖率双绿（P1 收口） | `python3 -m pytest -q` 全绿 |

---

## P2 — 文档、打磨与可选整合（47–100）

### 文档深水区

| # | 任务 |
|---|---|
| 47 | README.zh-CN 与 README 同步（补 2 新模块） |
| 48 | INTERVIEW.md 补 src 布局 + 2 新模块谈点 |
| 49 | 课程大纲 `doc/course` 接 scheduler/orchestrator 模块 |
| 50 | 写一份「无人值守 vs 多代理」架构决策记录（ADR） |
| 51 | 写一份「只 mock LLM 边界」的实践速查卡 |
| 52 | doc/reference_harness 补 scheduler/orchestrator 调研对照 |
| 53 | 把 100_tasks.md 挂到 README 索引 |
| 54 | 生成一份模块→测试→覆盖率的三列映射表 |

### 测试深度

| # | 任务 |
|---|---|
| 55 | property-based 测试（hypothesis）覆盖状态机迁移 |
| 56 | 状态机迁移穷举（全 `ALLOWED_TRANSITIONS` 组合） |
| 57 | `GoalSpec.from_markdown` 的 fuzz 解析（畸形 goal.md 不崩） |
| 58 | scheduler 排序稳定性测试（100 个 goal 乱序输入） |
| 59 | orchestrator 大 N（≥50 子代理）性能/正确性 |
| 60 | 内存泄漏回归（跑 1000 轮 RSS 不涨） |
| 61 | 快照/黄金文件测试（晨报格式固定） |
| 62 | 慢测/快测分层（标记 `@pytest.mark.slow`） |
| 63 | 覆盖率按模块细分报表（逐包覆盖率） |
| 64 | 测试间隔离（不共享 SQLite 临时库）审计 |

### 可观测性深水区

| # | 任务 |
|---|---|
| 65 | 结构化日志（JSONL）统一输出 |
| 66 | 每 goal 的耗时/预算燃尽曲线导出 |
| 67 | 晨报加「待人工关注」高亮（阻塞/超预算） |
| 68 | 告警钩子（阻塞 N 次触发回调） |
| 69 | trace 导出 OpenTelemetry 兼容格式 |
| 70 | 仪表盘（本地 HTML）可视化 goal 状态 |

### 安全与合规

| # | 任务 |
|---|---|
| 71 | 密钥扫描接入 CI（防 `.env`/key 入库） |
| 72 | prompt 注入再加固（更多变体 + 空白/大小写归一化） |
| 73 | 危险动作白名单审计（`_HIGH_RISK_ACTIONS` 穷尽） |
| 74 | 依赖审计（`pip-audit`）接入 CI |
| 75 | 越权路径穿越攻击测试（`../` 逃逸） |
| 76 | SQL 注入面审计（store 全部参数化确认） |

### 打包与发布

| # | 任务 |
|---|---|
| 77 | 打包成可安装 wheel（`src` 布局收尾） |
| 78 | `py.typed` + type checker（mypy）接入 |
| 79 | 版本号策略（semver）+ changelog |
| 80 | 发布到内部 PyPI（可选） |
| 81 | Docker 镜像（跑整夜调度的容器） |
| 82 | 定时调度接入系统 cron（真实无人值守） |

### 生态整合（可选）

| # | 任务 |
|---|---|
| 83 | 接 `superpowers` 技能产出 goal 直接跑（spec→goal.md 桥） |
| 84 | 接 OpenAI/Anthropic 等第二 provider（faux 之外真边界） |
| 85 | 接 hermes-agent 的 cron/委派对齐 |
| 86 | 接 deepseek-harness 的 plugin 模型对齐 |
| 87 | 多 provider 路由（按 goal 类型选模型） |
| 88 | goal 模板库（常见任务预制 goal.md） |

### 打磨与重构

| # | 任务 |
|---|---|
| 89 | `loop_runner.run` 抽小函数（去深嵌套） |
| 90 | 统一错误类型（不用裸 `RuntimeError` 分支） |
| 91 | 配置对象化（散落的阈值/常量收敛） |
| 92 | 类型提示补全（`mypy --strict` 目标） |
| 93 | 死代码清扫（未覆盖且判死代码的删） |
| 94 | docstring 一致性（全部模块统一风格） |
| 95 | 命名统一（thread_id/objective/status 对齐） |
| 96 | 性能剖析（最慢路径定位 + 优化） |
| 97 | 依赖瘦身（去未用依赖） |
| 98 | `__init__.py` 公开 API 收敛（少暴露内部） |

### 收口

| # | 任务 |
|---|---|
| 99 | 全量回归 + 覆盖率 + fmt + lint 四绿（最终闸门） |
| 100 | JOURNEY.md 收尾 + STATUS.md 推进 + 风险条目勾销 |

---

## 依赖与顺序（供执行参考）

- **P0** 是两条独立垂直线（scheduler / orchestrator），可并行，文件不重叠（`scheduler.py` vs `orchestrator.py`）。
- **P1** 前半（真 LLM 基线 / 沙箱 / LLM-judge / 观测成本）可并行；后半（CI / 文档 / 真 LLM 编排）依赖 P0 落定。
- **P2** 绝大多数独立，可随时穿插；47–54 依赖 P0 文档就绪，77–82 依赖 P1 打包。

---

## 自我评审（写完即审，审后修正）

> 本块是「plan → 自我批判」的产物，四个发现，一条已改、三条钉进执行纪律。

1. **P0.14 措辞不准（已改）**：原写「崩溃 maker → goal 停 `active`」。但 `loop_runner.run` 里 maker 崩溃 → `ok=False` → `round_made_progress=False` → `mark_blocked` 累加，**连续 3 轮无进展会走到 BLOCKED**，不是永远停 active。正确断言是「单轮不崩、`ok=False`、不误判 complete」。已把验收改为「单轮 `ok=False` 不崩、不误判 complete（连续无进展仍走 blocked 审计）」。

2. **真 LLM 基线任务（P1.15/16/17/41–44）被 key 卡死**：这些任务无 `MINIMAX_API_KEY` 时「完成」=「标 `待确认`」，不是「编数字」。执行时要把「无 key 的验收态」显式写进 plan，避免把「待确认」当「完成」交。

3. **plan doc 前置被推迟了**：harness_skills.md 要求目标 2/3 各写 `doc/08_*`、`doc/09_*` plan doc（含自我批判），本表把它排到 P1.34/36。但 P0 就要实现——**应先写 plan（superpowers writing-plans）再 TDD**。执行 P0 时把 plan doc 作为 TDD 前置补上，不等 P1。

4. **覆盖率基线数字会漂**：表头写「93.33%」是 139 测试时的快照，现 140 测试，实测值 ±0.1% 属正常。数字是参照物，不构成规划依赖；最终以 `python3 -m pytest --cov` 实跑为准。
