# harness skills 调研 → 本仓库可落地的目标

> 调研源：`D:\GitRepo-AI\ai-scrape-research\github-research\AGENTS_REPO.md`（2026-08-30 live 快照，`stars:>1000`，六个主题 100+ 仓库）。
> 本文回答两个问题：这些「harness skills」谈的是什么、哪些是本仓库（AgentHarness101）**还缺**的、缺的部分怎么拆成可 TDD 的目标。
> 与 `comparison.md`（四仓库 TDD 对比）互补：那份聚焦「怎么测试」，这份聚焦「harness 还该有哪些能力」。

## 结论

**这 100+ 仓库谈的不是六个独立话题，而是 agent harness 从「能跑一个 loop」进化到「能无人值守跑一整夜、越跑越好」的六个台阶。** 本仓库（AgentHarness101）已经站在前两个台阶上（spec-driven 流程 + TDD 覆盖率闸门），中间的「无人值守」和「自我改进」两个台阶还缺。

六个主题按「离本仓库现状的距离」重排：

| 台阶 | 主题 | 本仓库现状 | 缺口 |
|---|---|---|---|
| ① 过程纪律 | spec-driven + TDD | **已有**：superpowers 流程 + `fail_under=92` 闸门 | 无（过程，非运行时能力） |
| ② 记忆 | self-learning / 长记忆 | **半有**：`hippocampus`（record/learn/replay） | 缺「闭环」：结果→教训→下次注入 |
| ③ 无人值守 | autonomous / night-run | **半有**：`run_until_terminal`、idle self-start、resume | 缺「调度器」：定时重臂、晨报 |
| ④ 编排 | multi-agent | **只两角色**：maker/checker | 缺「N 个专职子代理」编排 |
| ⑤ 生态 | skills / 框架 | **已在用**：superpowers 技能集 | 无（消费方，非产出方） |

真正值得抄的**不是哪个框架**，而是三条横切规律，横跨六个主题反复出现：

1. **「只 mock LLM 边界，其余跑真货」**（§6 obra/superpowers、pi 的 `replace the LLM`）——本仓库已内化为 `faux_provider`。
2. **「越跑越好」= 记忆闭环**（§5 claude-mem 的 `capture→compress→reinject`、self-rag 的 self-reflection、Acontext 的「skills as memory」）——本仓库**缺**，是目标 1。
3. **「无人值守」= 调度 + 收尾报告**（§3 openai/symphony 的 `overnight runs`、khoj 的 `schedule automations`、ralph 的 `loop till PRD done`）——本仓库**缺**，是目标 2。

## 六个主题的骨架（各只留对「抄什么」有用的）

### §1 spec-driven development（132k⭐ 领头）
github/spec-kit 的 `/specify→/plan→/tasks→/implement` 四段管线 + OpenSpec 的 agent-agnostic 化 + pilot-shell 的「spec + 强制 TDD + 持久记忆」三者合一。**抄点**：本仓库的 superpowers 流程已是同类；不值得另造一套。

### §2 test-driven development
learn-go-with-tests 的 red-green 纪律 + mockito/sinon 的「只 mock 边界」哲学。**抄点**：已被本仓库 `fail_under=92` + 「未覆盖行=死代码或行为」判定吸收，无新增。

### §3 autonomous / scheduled（「night runs」）
从 AgentGPT 的 `goal→task→execute` 到 openai/symphony 的「teams 管理工作而非监督 agent」、khoj 的 `schedule automations`、ralph 的 `loop until PRD done`、ARIS（`Auto-Research-In-Sleep`）。**抄点**：把「定时重臂 + 无人值守跑 + 早上读报告」做成一个运行时调度层——不是 cron 脚本，是 harness 的一个子系统。

### §4 multi-agent orchestration
MetaGPT 的 SOP 角色分工（PM/architect/engineer）、autogen 的 agent groups、swarm 的 handoffs、deepseek-harness 的 subagent 分解。**抄点**：本仓库 maker/checker 是「两角色 generator/evaluator 分离」，缺「N 个专职子代理 + 一个编排器」。

### §5 self-learning / self-improving（「越跑越好」）
claude-mem 的 `capture everything→compress→inject relevant context`、mem0 的可编程长记忆、self-rag 的 `retrieve→generate→critique`、Acontext 的「skills 本身作为记忆层」。**抄点**：这是最独特、离本仓库最近的缺口——`hippocampus` 已经能记，缺的是**自动从「一次 run 的结果」提炼教训、并在下一次 run 自动注入**的闭环。

### §6 skills / harnesses / frameworks（生态）
obra/superpowers、ECC（harness 性能优化）、hermes-agent（记忆+技能+cron+委派）、deepseek-harness（「everything is a plugin」）。**抄点**：本仓库是这些框架的**消费者**（用 superpowers 做流程），不是产出方；不作为目标。

## 落到本仓库的三个新目标

延续 `comparison.md` 的三目标打法（每个目标独立、文件不重叠、可并行、TDD）：

1. **自我改进闭环（§5）** → 新增 `goal_loop/self_improver.py`：一次 run 结束自动提炼教训（成功→`repeat`，失败→`avoid`），下次 run 开始时把相关教训注入 steering。落点：`SelfImprover` 组合现有 `Hippocampus`，`GoalLoopRunner` 加可选参数 fail-open。→ `doc/07_self_improve/plan.md`
2. **无人值守调度（§3）** → 新增 `goal_loop/scheduler.py`：定时重臂 active goals、串行跑、收尾生成晨报摘要。落点：组合 `goal_persistence.resume_all` + `run_until_terminal`。→ 待实施（本批先做目标 1）。
3. **多代理编排（§4）** → 新增 `goal_loop/orchestrator.py`：一个编排器把 goal 拆给 N 个专职子代理，maker/checker 之外引入 planner/executor/reviewer。→ 待实施。

每个目标都满足「mock 只发生在 LLM 边界」：自我改进的教训提炼是确定性纯函数、调度器不发 LLM 调用、编排器只路由 callable。三个目标各自对应一个 plan doc，文件不重叠（1=goal_loop/self_improver.py、2=goal_loop/scheduler.py、3=goal_loop/orchestrator.py）。
