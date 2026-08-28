# JOURNEY — Agent Harness 101

**项目:** AgentHarness101
**时间范围:** 2026-08-21 → 2026-08-28
**图例:** `ME = 用户`，`YOU = AI`

本文件把两份早期的分模块历史(`doc/01_goal_persistence/journey.md` 和
`doc/02_goal_loop/journey.md`)合并成一条时间线:先有持久化目标内核,再有目标循环,
最后是六层 harness。

## 风险与待办(高亮)

> 本段是顶部汇总;正文各 Era 里的风险/TODO 原样保留,不删除。每条都标注所属 Era。

### 风险

- **沙箱是白名单执行器,不是 OS 级隔离**(Era 18–19):`sandbox/` 只做 fail-closed +
  allowlist + `shell=False` + 超时,没有 `bubblewrap`/`Landlock`/`seccomp` 那种真正的
  进程/文件系统隔离。这是明确的边界,不是已完成项。
- **评测是确定性裁判,不是 LLM-judge**(Era 18):`eval_harness/` 默认用 `ExactJudge`
  做相等比较,可替换但尚未接入真实 LLM 裁判。
- **循环组合了 sandbox + trace + hippocampus,但还没接 `tool_registry`**(Era 19):
  maker/checker 目前是普通可调用对象,未经过工具注册表的权限门。
- **无 LLM 循环里 token 计数不可伪造**(Era 20):测量用墙钟时间而非脚本注入的 token;
  真实 token 只在 `llm_demo.py` 里才有意义。

### 待办(TODO)

- ✅ **用真实 LLM 跑一轮循环,报告实际 token 用量(需要凭据)**(Era 20)——
  `examples/llm_goal_loop.py` 已用 MiniMax-M3 跑通:2 轮、`complete`、**75 实际 token**,
  证据为机器验证的 `answer()==42`。
- ✅ **扫描窗口大小,验证压缩比随上下文增长仍然成立**(Era 20)——
  `tests/test_context_compaction.py::test_reduction_ratio_holds_as_window_grows` 扫描
  10/100/500 个噪声项,压缩比保持 < 0.3 且随噪声增多而下降。
- ✅ **用永远无进展的 maker 测病态循环,给 blocked 路径定上界**(Era 20)——
  `tests/test_goal_loop.py::test_never_progressing_maker_bounds_blocked_path` 证明
  病态 maker 在三击阈值处 BLOCKED,不会空转。
- ✅ **把 maker/checker 接到 `tool_registry` 权限门,完成最后一层真实组合**(Era 19)——
  `goal_loop/registered_roles.py` 的 `RegisteredMaker`/`RegisteredChecker` 把 maker/
  checker 变成经权限门 + schema 校验的注册工具,有测试钉住(含被禁用时的拒绝路径)。
- **(可选)升级沙箱到真正的 OS 级隔离后端**(Era 18)。

---

## 第一部分 — 目标持久化(持久化内核)

### Era 1 — 技能激活

| ME | YOU |
|---|---|
| 粘贴了 `goal-persistence` 技能规格和 `AgentHarness101` 课程大纲,没有明确指令,只有材料。 | 加载 `goal-persistence` 技能,读 `00-课程大纲.md` 理解课程语境(Harness 101、M5 状态层、Capstone),推断任务是把这个规格实现成课程模块。 |

### Era 2 — 规划

| ME | YOU |
|---|---|
| (隐式:继续实现。) | 建了一个 6 步的待办:设计数据模型、实现 SQLite store、记账、运行时、测试、README。从模型 + 状态机设计开始。 |

### Era 3 — 核心实现

| ME | YOU |
|---|---|
| (无纠正。) | 构建 `goal_persistence/models.py`(`Goal`、`GoalStatus`、`Usage`、迁移规则)、`store.py`(SQLite CRUD + schema)、`accounting.py`(`TurnAccounting`)、`runtime.py`(`GoalRuntime`:空闲自启动、续跑、anti-drift 提示、blocked/complete 审计)。 |

### Era 4 — 第一次测试(失败)

| ME | YOU |
|---|---|
| (无纠正。) | 写 `tests/test_harness.py` 并跑,16 通过、4 失败:blocked 计数没有在预 blocked 轮次间累加;从 `active` 调 `unblock` 抛 `TransitionError`;`mark_complete` 丢掉 evidence;全生命周期测试期望 3 次观察后 `blocked`,结果还是 `active`。 |

### Era 5 — 修 bug

| ME | YOU |
|---|---|
| (无纠正。) | 改 `models.py` 允许幂等自迁移并保留完成证据;改 `runtime.py` 的 `mark_blocked` 在状态翻转前累加 `blocked_count`,`unblock` 即使从 `active` 也重置计数。重跑:20 通过。 |

### Era 6 — 文档与 demo

| ME | YOU |
|---|---|
| (隐式:收尾。) | 写 `README.md`、`demo.py`、`pyproject.toml`。demo 成功:steering 提示打印、轮次被跟踪、重启续跑、带证据完成。 |

### Era 7 — 「没有 LLM」之问

| ME | YOU |
|---|---|
| "No LLM dependency — the runtime drives the lifecycle and produces steering prompts, but the caller decides how to invoke the model. wait no LLM, how does this even work, can you show me run reuslt or test reuslts?" | 重跑 `pytest -v`(20 通过)和 `demo.py`,然后解释关注点分离:harness = 内存 + 循环控制 + 护栏;LLM = 推理引擎。 |

### Era 8 — 切到 MiniMax-M3 并捕获 LLM 输出

| ME | YOU |
|---|---|
| 提供 `ANTHROPIC_MODEL=MiniMax-M3`,要求把测试结果 dump 到 README,然后想知道真实 LLM 输出。 | 更新 `llm_demo.py` 从环境读 `ANTHROPIC_MODEL`(默认 `MiniMax-M3`),加到 `.env` 并重跑。结果:2 轮、`complete`、948 / 5,000 token、无弃用警告。说明 demo 把回复截断到 600 字符,不持久化完整输出。 |

---

## 第二部分 — 目标循环(契约层)

### Era 9 — 任务到达与两仓对照

| ME | YOU |
|---|---|
| `/goal` 五步指令:迁移 goal harness、先写计划并自我批判、实现并自我批判、自测并在有 bug 时重复、最后 dump journey。来源:`D:\GitRepo-AI\learn-harness-engineering`。 | 读两个仓。发现来源的 "goal harness" 不是可运行文件——是第 13 讲的 `/goal` 循环(目标 + 验证 + 停止条件)加项目 07 的 maker/checker 分离,具体化为四个模板。发现本仓已有 `goal_persistence/`。 |

### Era 10 — 找到真正的缺口

| ME | YOU |
|---|---|
| (无纠正。) | 确定两个仓描述的是不同层:来源的 goal harness 是**循环契约**,本仓的 `goal_persistence` 是**持久化内核**。迁移应在上面加循环层,而不是重写 SQLite/空闲续跑/预算。 |

### Era 11 — 计划草稿 + 自我批判

| ME | YOU |
|---|---|
| (隐式:继续。) | 写 `doc/02_goal_loop/plan.md`,然后自我批判第一稿:砍掉冗余的 `VerificationMethod` 抽象、让完成靠机器落地、定义准确的完成证据、重命名含糊角色、移除碰文件系统的 demo。 |

### Era 12 — 实现 + 自我批判

| ME | YOU |
|---|---|
| (无纠正。) | 构建组合 `goal_persistence.GoalRuntime` 的 `goal_loop/`,然后自我批判并修四个 bug:预算后 blocked 的 `TransitionError`、坏掉的持久化续跑、假的二次 three-strike 重实现、不可往返的状态序列化。 |

### Era 13 — 自测(失败,再修)

| ME | YOU |
|---|---|
| (无纠正。) | 测试暴露了续跑时 round 号重置、以及 `max_rounds` 被累计。都修了,并修正一个错误测试。套件:33 通过。 |

### Era 14 — 第一次评审驳回「完成」

| ME | YOU |
|---|---|
| 交付一份结构化《工作审视报告》:happy-path 循环是真的,但「goal harness 已迁移」不成立——没有 `goal.md` 解析、steering 被丢、假用量、只支持 Windows 的 verifier、PASS 绕过 blocked、私有 `_store` 泄漏、没接课程、demo 盖章了预先存在的成功。 | 接受评审,重新打开工作。 |

### Era 15 — 契约迁移完成

| ME | YOU |
|---|---|
| (评审即纠正。) | 实现每个必须项:`GoalSpec.from_markdown`、steering 进 maker、真用量、基于 argv 的 verifier、单调进度、公开 `get_goal`、课程接线、先失败后通过的 demo。 |

---

## 第三部分 — 六层 harness

### Era 16 — 上下文管理(①)

| ME | YOU |
|---|---|
| 指向 `doc/harness-1hour.html` 第 ① 层,描述 80% 截断想法。 | 构建 `context_compaction/`:标记内容原样保留,其余归档并摘要。 |

### Era 17 — 海马体长期记忆(④)

| ME | YOU |
|---|---|
| 指向第 ④ 层,描述海马体想法。 | 构建 `hippocampus/`:轨迹 + 索引 + 缓存 + 学习/遗忘 + 回放。 |

### Era 18 — 其余层 + 横切面

| ME | YOU |
|---|---|
| (目标继续;gap 表就是规格。) | 补齐其余:`tool_registry/`、`sandbox/`、`eval_harness/`、`observability/`、`safety/`、`cost_control/`。 |

### Era 19 — 第二次评审:层是并排的,不是组合的

| ME | YOU |
|---|---|
| 交付第二次评审:demo 的 `verify_command` 是永远 exit 0 的裸比较;所谓「六层」从不互相调用;`unlearn` 留缓存;80% 比例是死常量;`system:` 过度宽;SQLite 旁路文件没忽略;lab 用了 happy path。 | 每项都修,并接线让 `GoalLoopRunner` 组合 `Sandbox` + `TraceLog` + `Hippocampus`。 |

### Era 20 — 测量效率

| ME | YOU |
|---|---|
| "measure out new design effiency" | 构建 `examples/measure_efficiency.py` 返回真实数字(循环轮数/墙钟、压缩比、回放延迟、沙箱开销)。移除一个伪造的 token 节省指标。 |

### Era 21 — 记录效率

| ME | YOU |
|---|---|
| (无进一步纠正。) | 把实测结果写进 `doc/02_goal_loop/efficiency.md`:2 轮 / 约 1.2 秒;压缩 98.75% 缩减;回放约 0.6 毫秒;沙箱约 5% 开销。 |

### Era 22 — 清掉四个待办

| ME | YOU |
|---|---|
| 从 `JOURNEY.md` 顶部贴出四条 TODO,要求落实。 | 逐一落地并验证:① 真实 LLM 跑循环 —— `examples/llm_goal_loop.py` 用 MiniMax-M3,2 轮、`complete`、75 实际 token;② 窗口扫描 —— 新测试证明压缩比随上下文增长仍成立;③ 病态循环 —— 新测试证明无进展 maker 三击 BLOCKED;④ `tool_registry` 接线 —— 新增 `RegisteredMaker`/`RegisteredChecker`,把 maker/checker 变成经权限门 + schema 校验的注册工具。套件 75 → 79 全绿。 |

---

## 这个项目如何教 vibe coding with AI

### 人的工作

- **丢一份规格来定范围。** `goal-persistence` 技能 + 课程大纲让 AI 在没有逐步指令的情况下推断构建目标。*(Era 1)*
- **问「等等,怎么做到的?」** "No LLM, how does this work?" 逼出一次关注点分离的解释和一个真实 demo。*(Era 7)*
- **给流程,而不只是给结果。** 计划 → 自我批判 → 实现 → 自测 → journey 的五步指令,迫使工作在被信任前先被证伪。*(Era 9)*
- **用具体细节驳回假的「完成」。** 两次评审列出具体缺陷,AI 逐条修复。*(Era 14、Era 19)*

### AI 的工作

- **先建最小可证伪单元。** 状态机 + store 先于运行时糖,让迁移 bug 尽早暴露。*(Era 3)*
- **用证据报失败,不打马虎眼。** 「16 通过、4 失败」并给出确切症状。*(Era 4)*
- **在构建前锁死解释。** 「goal harness」被变成一个可证伪目标:持久化之上的循环层,而不是重写。*(Era 10、Era 11)*
- **用具体 diff 自我批判。** 计划和实现都对照一张命名缺陷清单被修改。*(Era 11、Era 12)*
- **把硬评审当新证据。** 早先的「完成」是假阳性;基于评审重开工作,把状态机草稿变成真 harness。*(Era 14)*
- **组合,而不是共存。** 「六个并排玩具」评审逼出真接线(循环 → 沙箱 → trace → 海马体),用测试而非散文证明。*(Era 19)*

### 可复用的规则

1. **harness 拥有状态、预算和循环控制;模型拥有推理。** 20 个测试在零 LLM 调用下通过。*(Era 3–7)*
2. **状态机迁移必须单测,不能肉眼估。** 20 个测试里有 4 个专门验证允许/禁止的迁移。*(Era 4)*
3. **完成必须靠机器落地,不能靠 maker 自报。** 只有独立 checker 判定加验证过的命令才能结束。*(Era 12)*
4. **自我批判发现什么,自测再证明什么。** 对照内核语义重读代码抓到的 bug,被测试钉死。*(Era 12、Era 13)*
5. **「测试绿了」只证明测试覆盖到的东西。** 第一次绿是在 stub maker/checker 上;评审把缺口变具体。*(Era 14)*
6. **「层存在」不等于「层组合」。** 第二次评审逼出真接线,由组合测试证明。*(Era 19)*
7. **用真实数字测量,不用注入常量。** 一个伪造的 token 节省指标被抓住并移除;最终报告说明每个数字证明什么。*(Era 20)*

### 一句话总结

**人提供规格、流程和硬评审;AI 构建可证伪组件、诚实报告失败,并让失败测试和被驳回的「完成」判定迫使设计真正组合起来——而不是满足于一个能跑的 happy path。**
