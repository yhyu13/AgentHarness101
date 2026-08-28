# 面试可以照着讲的项目：Agent Harness 101

这个文档是给你面试用的。不是给面试官看的简历，是给你自己捋一遍「这项目我到底干了啥、为什么、怎么讲才有底气」。全部能对上代码和测试，没有吹。

> 每个论点后面都标了源码位置（文件:行号）和测试用例名。面试被追问时，你能当场翻到。

## 一句话开场

我做了一个 agent 的「外壳」（harness）——就是让大模型从「能聊天」变成「能可靠地干长任务」的那套工程。核心是：**模型负责想下一步，harness 负责管它能看到什么、能调什么、怎么执行、记什么、怎么才算做完。** 我把它拆成六层，每层都写了能跑的代码和测试，85 个测试全绿。

## 先讲明白一个判断

大部分 demo agent 的问题不在模型，在环境。同一个模型，裸跑就乱改文件、说「修好了」其实没测、重启就忘了干到哪。我的做法是把这些风险都挡在模型外面：**即使模型想错，它也碰不到不该碰的东西。** 这是整个项目的主线。

## 我实际做了什么（六层 + 两个横切面）

按「为什么需要这一层」的顺序讲，别背名词。

### 1. 上下文管理

长对话越长越贵、也越容易跑偏。我做了个 80% 截断：对话中标记重要内容，上下文快满的时候，只留标记的部分原样，其余归档到磁盘并生成摘要，把「摘要 + 归档引用」喂回去。实测 48,550 字符能压到 609 字符（98.75% 缩减），重要内容一个没丢。

留痕：`context_compaction/compactor.py:41`（`compact_window` 实现 80% 窗口）、
`context_compaction/compactor.py:93`（归档 + 摘要）、
`tests/test_context_compaction.py:90`（`test_window_80_percent_triggers_compaction`）、
`tests/test_context_compaction.py:110`（`test_reduction_ratio_holds_as_window_grows`）。
数字出处：`doc/02_goal_loop/efficiency.md`。

### 2. 工具管理

工具不是越多越好，模型选错的概率会涨。我做了个注册表：每个工具有权限标签（读/写/执行/网络），按任务显式启用，参数做 schema 校验。默认最小权限，不启用就不能调。

留痕：`tool_registry/registry.py:9`（`ToolRegistry`）、`tool_registry/registry.py:38`
（`call` 里的权限门 + schema 校验）、`tool_registry/models.py:6`（`Permission` 枚举）。
测试：`tests/test_harness_layers.py:34`（`test_permission_gate`）、
`tests/test_harness_layers.py:43`（`test_schema_validation`）。

### 3. 执行环境（沙箱）

这是最关键的层。命令必须走白名单 + `shell=False`（防注入）+ 超时。最关键的是**失败就关闭**：没配沙箱后端就返回 `SANDBOX_UNAVAILABLE` 拒绝执行，绝不裸跑。实测加这层只多 5% 开销。

留痕：`sandbox/sandbox.py:46`（`run` 里的 fail-closed + 白名单）、
`sandbox/sandbox.py:95`（`_blocked`）。测试：`tests/test_harness_layers.py:63`
（`test_fail_closed_when_unavailable`）、`tests/test_adversarial_boundaries.py:155`
（`test_unconfigured_sandbox_fails_closed`）。

### 4. 状态与记忆

分两层：一是**持久化目标**——一个目标存成 SQLite 一行，带状态机（active/paused/blocked/complete 等），重启能续跑，超预算自动停；二是**长期记忆**（我管它叫「海马体」）——记录任务轨迹、索引重要内容、存本地缓存，能「学习正确、忘掉错误」，还能回放。

留痕：`goal_persistence/store.py:64`（`GoalStore` + SQLite）、
`goal_persistence/models.py:9`（`GoalStatus` 状态机 + 迁移规则）、
`goal_persistence/runtime.py:47`（`GoalRuntime` 的续跑/空闲自启动）。
测试：`tests/test_harness.py:56`（`test_goal_survives_store_reopen`）、
`tests/test_harness.py:87`（`test_budget_auto_transition`）、
`tests/test_harness.py:138`（`test_resume_re_arms_idle_loop`）。
记忆层留痕：`hippocampus/memory.py:9`（`Hippocampus`）、`hippocampus/store.py:56`
（`upsert_fact` 索引 + 缓存）、`hippocampus/store.py:68`（`forget_fact` 删索引也删缓存）。
测试：`tests/test_hippocampus.py:28`（`test_learn_unlearn_correct`）、
`tests/test_hippocampus.py:55`（`test_unlearn_clears_cache`）。

### 5. 验证与评估

这里有条我特别想讲的原则：**写代码的人不能给自己批作业。** 所以我把「maker」（干活）和「checker」（独立验收）拆成两个角色。完成必须同时满足：① 每个验收标准的机器命令真的退出码 0；② 独立 checker 给 pass。maker 自己说「做完了」不算数。

留痕：`goal_loop/loop_runner.py:83`（`_verify_criterion` 命令验证）、
`goal_loop/loop_runner.py:291`（完成判定 `all_satisfied and verdict_ok and maker_succeeded`）、
`goal_loop/roles.py:8`（Maker 协议）和 `goal_loop/roles.py:21`（Checker 协议）。
测试：`tests/test_goal_loop.py:204`（`test_completes_with_evidence`）、
`tests/test_goal_loop.py:256`（`test_does_not_complete_on_maker_self_report_only`）。

### 6. 观测与审计

出问题不能只剩一句「抱歉失败了」。我做了 append-only 的 trace 日志，每个事件一条 JSON，能字节级重建当时模型看到的东西。这就是「可回放」。

留痕：`observability/trace.py:19`（`TraceLog`）、`observability/trace.py:32`（`append`）、
`observability/trace.py:43`（`replay`）。测试：`tests/test_harness_layers.py:101`
（`test_append_only_and_replay`）、`tests/test_adversarial_boundaries.py:163`
（`test_trace_survives_restart_and_reconstructs_exactly`）。

另外两个横切面：**安全**（RBAC 角色 + 高风险动作人机确认 + 注入检测）和**成本控制**（令牌桶限流 + 工具结果缓存）。

留痕：`safety/safety.py:34`（`SafetyGuard` 的 RBAC + HITL）、`safety/safety.py:66`
（`check_prompt` 注入检测）；`cost_control/cost.py:17`（`RateLimiter`）、
`cost_control/cost.py:41`（`ToolResultCache`）。
测试：`tests/test_harness_layers.py:120`（`test_rbac_denies`）、
`tests/test_harness_layers.py:124`（`test_high_risk_requires_human`）、
`tests/test_harness_layers.py:142`（`test_rate_limiter`）。

## 一个能体现思考深度的真实案例

我讲这个，因为它不是「又加了个功能」，而是踩了个真 bug。

当时我把 maker/checker 接进工具权限门。结果发现：maker 被权限拦下时，代码只改了个字符串说明「被拦了」，没有返回任何「失败」信号。于是出现一个假完成：**maker 没干成活 → 但我配了个说 pass 的 stub checker → 再加上这条验收标准没有机器命令 → 循环就误判完成了。** 这直接击穿了「写代码的人不能自批作业」这条原则。

修法很简单但关键：给 maker 输出加了个 `ok` 字段，被拦就返回 `ok=False`，循环的进度和完成判定都强制要求 maker 真成功了。然后我写了 6 个「对抗测试」——专门构造恶意场景打边界，不是再写一个 happy path。

留痕：bug 根因在 `goal_loop/registered_roles.py:43`（被拦时原本只返回字符串，无失败信号）；
修复在 `goal_loop/models.py:181`（`MakerOutput` 加 `ok` 字段）、
`goal_loop/registered_roles.py:48`（被拦返回 `ok=False`）、
`goal_loop/loop_runner.py` 里 `maker_succeeded = maker_output.ok` 及完成判定。
测试：`tests/test_adversarial_boundaries.py:78`
（`test_blocked_maker_never_completes_even_with_pass_checker`）就是这个 bug 的精确复现。

这个故事能证明几件事：我知道 happy path 之外的边界、我会写测试去主动找 bug、我能在架构原则和实现细节之间对上号。

## 数字能证明什么

- **85 个测试全绿**，覆盖六层 + 两个横切面，其中 6 个是对抗边界测试。
- **真 LLM 跑通过**：用 MiniMax-M3 实际驱动一轮循环，2 轮、75 个真实 token、机器验证完成。
- **压缩比 98.75%**（上下文）、**沙箱开销约 5%**、**记忆回放约 0.6 毫秒**。

这些不是我编的，是 `examples/measure_efficiency.py` 跑出来的，写进了 `doc/02_goal_loop/efficiency.md`。

留痕：`tests/test_efficiency.py:18`（`test_measurements_are_sane`）、
`examples/measure_efficiency.py`（测量脚本）、`examples/llm_goal_loop.py`（真 LLM 循环）。

## 我能主动坦白边界

面试官如果问「这沙箱是真正的隔离吗」，我会直说：不是。现在做的是白名单执行器 + fail-closed + 超时，还没上 bubblewrap/Landlock/seccomp 那种 OS 级隔离。评测也是确定性裁判，不是真 LLM-judge。这些我都记在 JOURNEY 的风险里了——**知道哪里没做完，比假装都做完更能证明工程判断。**

留痕：`JOURNEY.md` 顶部的「风险与待办」里明明白白列了这两条边界，没藏。

## 如果只给我 30 秒

我做了一套 agent harness：六层——上下文、工具、执行、状态、验证、观测——每层能跑、有测试，85 个全绿。核心思想是「模型负责想，harness 负责兜住它想错之后的每一步」，完成必须机器验证 + 独立验收，而不是模型自己说完成。我还在对抗测试里抓到并修了一个「权限被拦却误判完成」的真 bug。

## 延伸问题（面试官可能追问）

- **为什么不用现成的 LangGraph/框架？** 我用它讲概念，但手写了状态机，因为要理解每一层的边界，而不是框架帮我遮住。
- **token 预算怎么管？** 记账里区分 input/cached/output，超预算在写入时自动转成终态 `budget_limited`，不会继续烧钱。
- **blocked 怎么判？** 不是模型喊一句「卡住了」就 blocked，而是同一个阻塞连续出现 3 轮才翻转，防止模型过早放弃。
- **generator/evaluator 为什么要拆？** 模型是「自己输出的最佳辩护律师」，它回头看自己的代码看不到错，所以验收必须交给独立的 checker。
