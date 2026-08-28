# JOURNEY — Agent Harness 101

**项目:** AgentHarness101
**时间:** 2026-08-21 到 08-28
**图例:** `ME = 用户`，`YOU = AI`

这个文件是把两份分模块的历史（`doc/01_goal_persistence/journey.md` 和
`doc/02_goal_loop/journey.md`）并成一条线：先有持久化的 goal 内核，再加 goal loop，
最后堆成六层 harness。

## 风险与待办（放最上面）

> 这只是顶部汇总，正文各 Era 里的风险和 TODO 都还在，没删。每条都标了 Era。

### 风险

- **沙箱不是真正的 OS 级隔离**（Era 18–19）：`sandbox/` 只做了 fail-closed + 白名单
  + `shell=False` + 超时，没有 bubblewrap/Landlock/seccomp 那套进程、文件系统隔离。
  这算一个边界，不算做完的事。
- **评测是确定性裁判，不是 LLM-judge**（Era 18）：`eval_harness/` 默认 `ExactJudge`
  做相等比较，可换但还没接真 LLM 裁判。
- **循环接了 sandbox + trace + hippocampus + tool_registry**（Era 19，已解决）：
  `registered_roles.py` 把 maker/checker 变成走权限门 + schema 校验的注册工具。
  原来「没接 tool_registry」这条已经关掉了。
- **无 LLM 的循环里，token 数不能自己编**（Era 20）：测量用墙钟时间，不用脚本注入
  的 token；真 token 只在 `llm_demo.py` 里有意义。
- **generator/evaluator 会被「被拦的 maker + 说 PASS 的 stub checker + 无命令准则」
  击穿**（Era 23，已修复）：`MakerOutput` 以前没有机器级的失败信号，导致被权限门
  拦下的 maker 在 stub checker 说 PASS 时可能被误判成完成。加了 `ok` 字段，用对抗
  测试钉住了。

### 待办（TODO）

- ✅ **用真 LLM 跑一轮循环，报实际 token 数（要凭据）**（Era 20）——
  `examples/llm_goal_loop.py` 用 MiniMax-M3 跑通了：2 轮、`complete`、**75 个实际
  token**，证据是机器验证的 `answer()==42`。
- ✅ **扫窗口大小，看压缩比随上下文变大还成立不**（Era 20）——
  `test_reduction_ratio_holds_as_window_grows` 扫了 10/100/500 个噪声项，压缩比一直
  在 0.3 以下，噪声越多压得越狠。
- ✅ **用永远没进展的 maker 测病态循环，给 blocked 路径定个上界**（Era 20）——
  `test_never_progressing_maker_bounds_blocked_path` 证明病态 maker 三击后 BLOCKED，
  不会空转。
- ✅ **把 maker/checker 接到 tool_registry 权限门，补最后一层真组合**（Era 19）——
  `RegisteredMaker`/`RegisteredChecker` 把 maker/checker 变成走权限门 + schema 校验的
  注册工具，有测试钉住（包括被禁用时的拒绝路径）。
- （可选）把沙箱升级成真正的 OS 级隔离后端（Era 18）。

---

## 第一部分 — 目标持久化（持久化内核）

### Era 1 — 技能激活

| ME | YOU |
|---|---|
| 把 `goal-persistence` 技能规格和 `AgentHarness101` 课程大纲贴过来，没下命令，只给了材料。 | 加载 `goal-persistence` 技能，读 `00-课程大纲.md` 弄清课程语境（Harness 101、M5 状态层、Capstone），判断任务是把这个规格做成课程模块。 |

### Era 2 — 规划

| ME | YOU |
|---|---|
| （没说，等于让我继续。） | 列了个 6 步待办：数据模型、SQLite store、记账、运行时、测试、README。从模型 + 状态机开始。 |

### Era 3 — 核心实现

| ME | YOU |
|---|---|
| （没纠正。） | 写了 `goal_persistence/models.py`（Goal、GoalStatus、Usage、迁移规则）、`store.py`（SQLite CRUD + schema）、`accounting.py`（TurnAccounting）、`runtime.py`（GoalRuntime：空闲自启动、续跑、anti-drift 提示、blocked/complete 审计）。 |

### Era 4 — 第一次测试（失败）

| ME | YOU |
|---|---|
| （没纠正。） | 写 `tests/test_harness.py` 跑了一遍，16 过 4 挂：blocked 计数没在预 blocked 轮次间累加；从 active 调 unblock 抛 TransitionError；mark_complete 丢 evidence；全生命周期测试期望 3 次观察后 blocked，结果还是 active。 |

### Era 5 — 修 bug

| ME | YOU |
|---|---|
| （没纠正。） | 改 `models.py` 允许幂等自迁移并保留完成证据；改 `runtime.py` 的 mark_blocked 在状态翻转前累加 blocked_count，unblock 即使从 active 也重置计数。重跑：20 过。 |

### Era 6 — 文档与 demo

| ME | YOU |
|---|---|
| （没说，收尾。） | 写了 README、demo.py、pyproject.toml。demo 能跑：steering 提示打印、轮次被跟踪、重启续跑、带证据完成。 |

### Era 7 — 「没有 LLM」之问

| ME | YOU |
|---|---|
| "No LLM dependency — the runtime drives the lifecycle and produces steering prompts, but the caller decides how to invoke the model. wait no LLM, how does this even work, can you show me run reuslt or test reuslts?" | 重跑 `pytest -v`（20 过）和 demo.py，然后解释关注点分离：harness 管内存 + 循环控制 + 护栏，LLM 是推理引擎。 |

### Era 8 — 切到 MiniMax-M3，抓 LLM 输出

| ME | YOU |
|---|---|
| 给了 `ANTHROPIC_MODEL=MiniMax-M3`，让把测试结果 dump 到 README，又问真实 LLM 输出长啥样。 | 更新 `llm_demo.py` 从环境读 `ANTHROPIC_MODEL`（默认 MiniMax-M3），加进 `.env` 重跑。结果：2 轮、complete、948 / 5,000 token、没弃用警告。说明 demo 把回复截到 600 字符，不存完整输出。 |

---

## 第二部分 — 目标循环（契约层）

### Era 9 — 任务到达，两个仓库对了一遍

| ME | YOU |
|---|---|
| `/goal` 五步指令：迁移 goal harness、先写计划并自我批判、实现并自我批判、自测有 bug 就重复、最后 dump journey。来源：`D:\GitRepo-AI\learn-harness-engineering`。 | 读两个仓。发现来源的 "goal harness" 不是可运行文件——是第 13 讲的 /goal 循环（目标 + 验证 + 停止条件）加项目 07 的 maker/checker 分离，落成四个模板。本仓已有 goal_persistence。 |

### Era 10 — 找到真正的缺口

| ME | YOU |
|---|---|
| （没纠正。） | 确定两边说的是不同层：来源的 goal harness 是循环契约，本仓的 goal_persistence 是持久化内核。迁移应该往上加循环层，而不是重写 SQLite / 空闲续跑 / 预算。 |

### Era 11 — 计划草稿 + 自我批判

| ME | YOU |
|---|---|
| （没说，继续。） | 写 `doc/02_goal_loop/plan.md`，然后自我批判第一稿：砍掉冗余的 VerificationMethod，让完成靠机器落地，把完成证据写准，重命名含糊角色，删掉碰文件系统的 demo。 |

### Era 12 — 实现 + 自我批判

| ME | YOU |
|---|---|
| （没纠正。） | 写了组合 goal_persistence.GoalRuntime 的 goal_loop，然后自我批判修四个 bug：预算后 blocked 的 TransitionError、坏掉的持久化续跑、假的二次 three-strike、不可往返的状态序列化。 |

### Era 13 — 自测（先挂，再修）

| ME | YOU |
|---|---|
| （没纠正。） | 测试暴露续跑时 round 号重置、max_rounds 被累计。都修了，还改了一个错测试。套件 33 过。 |

### Era 14 — 第一次评审，驳回「完成」

| ME | YOU |
|---|---|
| 交了份结构化《工作审视报告》：happy path 是真的，但「goal harness 已迁移」不成立——没 goal.md 解析、steering 被丢、假用量、只支持 Windows 的 verifier、PASS 绕过 blocked、私有 _store 泄漏、没接课程、demo 盖章了本来就存在的成功。 | 接受，重新打开工作。 |

### Era 15 — 契约迁移做完

| ME | YOU |
|---|---|
| （评审就是纠正。） | 把必须项都做了：GoalSpec.from_markdown、steering 进 maker、真用量、argv verifier、单调进度、公开 get_goal、课程接线、先失败后通过的 demo。 |

---

## 第三部分 — 六层 harness

### Era 16 — 上下文管理（①）

| ME | YOU |
|---|---|
| 指着 `doc/harness-1hour.html` 第 ① 层，讲了 80% 截断的想法。 | 写 `context_compaction/`：标记的内容原样留，其余归档 + 摘要。 |

### Era 17 — 海马体长期记忆（④）

| ME | YOU |
|---|---|
| 指着第 ④ 层，讲了海马体的想法。 | 写 `hippocampus/`：轨迹 + 索引 + 缓存 + 学习/遗忘 + 回放。 |

### Era 18 — 其余层 + 横切面

| ME | YOU |
|---|---|
| （目标继续，gap 表就是规格。） | 补齐其余：tool_registry、sandbox、eval_harness、observability、safety、cost_control。 |

### Era 19 — 第二次评审：层是并排的，不是组合的

| ME | YOU |
|---|---|
| 交第二次评审：demo 的 verify_command 是永远 exit 0 的裸比较；所谓六层从不互相调用；unlearn 留缓存；80% 是死常量；system: 太宽；SQLite 旁路文件没忽略；lab 用了 happy path。 | 每项都修，并接线让 GoalLoopRunner 组合 Sandbox + TraceLog + Hippocampus。 |

### Era 20 — 测量效率

| ME | YOU |
|---|---|
| "measure out new design effiency" | 写 `examples/measure_efficiency.py` 出真实数字（轮数/墙钟、压缩比、回放延迟、沙箱开销）。删掉一个编造的 token 节省指标。 |

### Era 21 — 记录效率

| ME | YOU |
|---|---|
| （没再纠正。） | 把实测结果写进 `doc/02_goal_loop/efficiency.md`：2 轮 / 约 1.2 秒；压缩 98.75% 缩减；回放约 0.6 毫秒；沙箱约 5% 开销。 |

### Era 22 — 清掉四个待办

| ME | YOU |
|---|---|
| 从 JOURNEY.md 顶部贴出四条 TODO，让落实。 | 逐条做并验证：① 真 LLM 跑循环——llm_goal_loop.py 用 MiniMax-M3，2 轮、complete、75 实际 token；② 窗口扫描——新测试证明压缩比随上下文变大还成立；③ 病态循环——新测试证明无进展 maker 三击 BLOCKED；④ tool_registry 接线——RegisteredMaker/RegisteredChecker 把 maker/checker 变成走权限门 + schema 校验的注册工具。套件 75 → 79 全绿。 |

### Era 23 — 对抗边界测试，打出一个真 bug

| ME | YOU |
|---|---|
| "能不来一个完整的难一点的测试测测我们的边界?" | 没写又一个 happy path，而是写了一套对抗测试 `tests/test_adversarial_boundaries.py`，过程中抓到一个真 bug：RegisteredMaker 被权限门拦下时只改 summary、不返回失败信号，导致「被拦 maker + stub PASS checker + 无 @verify 命令的准则」误判完成——generator/evaluator 被击穿。修复：MakerOutput 加 ok 字段（默认 True 向后兼容），被拦 maker 返回 ok=False，loop_runner 的进度和完成判定都要求 maker_succeeded。新增 6 个对抗测试覆盖：被拦 maker 不得 complete、说谎 checker 不得绕过失败命令、预算耗尽是硬终态、空配置沙箱 fail-closed、trace 跨重启字节级重建。套件 79 → 85 全绿。 |

---

## 这个项目怎么教 vibe coding

### 人的工作

- **丢一份规格定范围。** goal-persistence 技能 + 课程大纲让 AI 不用逐步指令就能猜到要建什么。*(Era 1)*
- **问「等等，怎么做到的?」** "No LLM, how does this work?" 逼出一次关注点分离的解释和一个真 demo。*(Era 7)*
- **给流程，不只是给结果。** 计划 → 自我批判 → 实现 → 自测 → journey 五步，逼着工作先被证伪再被信。*(Era 9)*
- **用具体细节驳回假的完成。** 两次评审列了具体缺陷，AI 逐条修。*(Era 14、Era 19)*

### AI 的工作

- **先建最小可证伪单元。** 状态机 + store 先于运行时糖，让迁移 bug 早点冒出来。*(Era 3)*
- **报失败带证据，不打马虎眼。** 「16 过 4 挂」并写清症状。*(Era 4)*
- **动工前把解释锁死。** 「goal harness」变成可证伪目标：持久化之上的循环层，不是重写。*(Era 10、Era 11)*
- **自我批判拿具体 diff。** 计划和实现都对着缺陷清单改。*(Era 11、Era 12)*
- **把硬评审当新证据。** 早先的「完成」是假阳性；按评审重开，把草稿变成真 harness。*(Era 14)*
- **组合，不是共存。** 「六个并排玩具」逼出真接线，用测试证明，不是靠嘴上说。*(Era 19)*
- **用对抗测试打边界，不是再写 happy path。** 用户要难一点的测试，就构造「被拦 maker + 说谎 checker」，才炸出 MakerOutput 缺失败信号的假完成。*(Era 23)*

### 踩过之后记下来的

1. harness 管状态、预算、循环控制，模型管推理。20 个测试零 LLM 调用就过了。*(Era 3–7)*
2. 状态机迁移得单测，不能肉眼估。*(Era 4)*
3. 完成靠机器落地，不能靠 maker 自报。*(Era 12)*
4. 自我批判发现什么，自测再证明什么。*(Era 12、Era 13)*
5. 「测试绿了」只说明测试覆盖到的地方。*(Era 14)*
6. 「层存在」不等于「层组合」。*(Era 19)*
7. 测量用真数字，不用注入常量。*(Era 20)*
8. generator/evaluator 得防「自报失败」这一侧：checker 自夸不算，maker 被拦/崩溃也不能算成功。*(Era 23)*

### 一句话

人给规格、流程和硬评审，AI 建可证伪的组件、老实报失败，让失败的测试和被驳回的「完成」逼着设计真正组合起来，而不是停在能跑的 happy path 上。
