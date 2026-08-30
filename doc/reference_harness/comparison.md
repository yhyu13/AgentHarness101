# 四个 reference harness 的 TDD 对比

> 对比对象：`deepseek-harness/docs`、`codex/docs`、`learn-harness-engineering`、`pi`。
> 本文回答两个问题：它们各自怎么「测试」、能抄的共同模式是什么、差异在哪。
> 证据都用 `文件:行号` 锚定，不写笼统判断。

## 结论

**这四个仓库谈的不是同一个「TDD」——它们回答三个不同的问题，混在一起抄会抄错。**
共同点只有一条值得抄：*把 LLM 边界 mock 掉，其余全部跑真货*；差异在「谁写测试、
测试证明什么、为保真付多大成本」三件事上各选了不同的点。

## 先钉清概念：这里的「TDD」其实是三件事

| 编号 | 问题 | 谁写测试 | 测试证明什么 |
|---|---|---|---|
| **A** | 怎么开发 harness 自身的代码？ | 人/agent 写 red→green | 改动的行为正确 |
| **B** | 怎么确定性地测试一个 agent loop？ | 测试作者脚本化 LLM 回复 | 完整 agent 生命周期走通 |
| **C** | 怎么让 agent 验证自己的工作？ | agent 跑既有测试作为「完成证据」 | 产品真的可用，不是自报完成 |

四个仓库落在不同的格子里：

- **codex**：明确做了 **A**（经典 red-green），也做了 **B**（`TestCodexBuilder`）。
- **deepseek-harness**：**A** 的极致版 + **B** + **C** 全做，是四个里测试工程最重的。
- **pi**：**B** 做得最深最系统，附带 **A** 的回归命名约定。
- **learn-harness-engineering**：只做 **C**，且是教学层面——**它根本没有经典 TDD**
  （全仓库 grep `test-driven`/`red-green` 只有一条韩语术语表定义），它的「验证」是
  harness 的五个子系统之一。

## 逐仓库：各自怎么做，证据在哪

### codex —— 唯一把 red-green 白纸黑字写出来的

`contributing.md:40`：

> A bug fix should generally come with test coverage that **fails before your change
> and passes afterwards**. 100% coverage is not required, but aim for meaningful assertions.

这是四个里唯一一句字面意义的 TDD 规则。配套两点：

- 每个 feature 文档末尾有固定小节 `## How to reproduce / test`，写死命令并指向「权威」
  集成测试。例：`goal-feature.md:140-159` 说 `harness test is the authoritative, runnable
  proof of the mechanism`；`function-calling.md:186-197` 说 `integration tests drive a real
  turn loop against a TestCodexBuilder`。
- 本地校验用 `just test -p <crate>`（`contributing.md:57`），强调「CI 能本地抓到的别拖到 CI」。

**它的 TDD 很轻**：只为 bug fix 要求先红后绿，明确「不要求 100% 覆盖」。

### deepseek-harness —— 测试工程最重，TDD 是隐含的纪律

它没有「先写失败测试」的字面规则，但 `testing.md` 里到处是 red-green 的操作化要求。
最直接的一句在 `testing.md:34`：

> prove it: introduce the regression, watch red, revert.

这就是 red-green 被降格成「验证测试有效性」的步骤——不是「先写测试驱动开发」，而是
「写完测试必须证明它真能抓到回归」。整套政策分五层（`testing.md:9-13`）：

1. 单元测试（vitest）
2. **覆盖率闸门：`packages/*/*/src` 每文件 100%**（`testing.md:10`）——且明说
   「没覆盖到的那行通常是该死代码，不是该补的测试」
3. 真实 API e2e（`testing.md:11`）
4. 快照测试（`testing.md:12`）
5. Web 浏览器快照（`testing.md:13`）

三条独特哲学：

- **「inference is cheap here」**（`testing.md:17-19`）：「我们是 DeepSeek，不要省真实
  API 测试。无 key 测试只证明管道通，只有带 key 才证明 agent 真能用。」点名 postmortem
  0001 是「绿单测、坏产品」这一类，mocks 抓不到。
- **「verify the world, not the self-report」**（`testing.md:27-29`）：e2e 断言要重跑命令/
  重读文件，不能只探 agent 自己的输出，「否则一个作弊的 agent 也能过」。
- **「prefer the real implementation over a mock」**（`testing.md:21-24`）：只 mock 贵的/
  不确定的边界（LLM、网络、时钟），下游全真；`makeBridgeHarness({withBash:true})` 用
  脚本化 mock 模型 + 真 bash 工具跑 `echo`。

### pi —— 「怎么测 agent 系统」答得最系统

核心文件 `harness_methods_1/PHILOSOPHY.md`，一句话概括（`:132-137`）：

> **replace exactly one boundary, observe everything else through the event stream**
> （只替换一个边界——LLM 回复，其余全通过事件流观察）。

落地（`harness_methods_1/harness-philosophy.md` 的 13 条）：

- **mock 大脑，不 mock 身体**：`registerFauxProvider` 只在流边界替换 provider，真实的
  `Agent`/`AgentSession`/`SessionManager`/扩展 hook 全跑（`PHILOSOPHY.md:97-183`）。
- **全内存存储**：每个存储层都配 `inMemory()` 工厂，测试毫秒级、零串扰
  （`harness-philosophy.md:27-46`）。
- **事件流是一等测试输出**：`eventsOfType<T>()` 类型化过滤，因为「messages 记录不了
  retry/abort/compaction/模型切换的完整时间线」（`harness-philosophy.md:230-240`）。
- **faux provider 要真的流式**：模拟 `text_start→delta→end` 全事件序列、可配
  `tokensPerSecond`，否则测不到中途取消/steering（`harness-philosophy.md:172-189`）。
- **回归测试命名约定**：`<issue-number>-<short-slug>.test.ts` 放 `test/suite/regressions/`
  （`AGENTS.md:55`、`test/suite/README.md:13-15`）。
- **测试边界是「社会契约」**：`test/suite/README.md:6-10` 写死「no real provider APIs,
  real keys, network, or paid tokens」。

注意 pi 的取舍和 deepseek **相反**：deepseek 说「别省真实 API 测试」，pi 说「suite 测试
绝对禁止真实 API」。这不是矛盾，是分工——pi 的确定性 suite 是常态，真实 provider 验证
放别处（`AGENTS.md:49` 的 `./test.sh` 剥掉所有 key 再跑）。

### learn-harness-engineering —— 只有 C，没有经典 TDD

它的「验证」不是写测试，是给 agent 挂一个「没跑通测试就不许说完成」的闸门。
`README.md:189`：

> Verification — Only a passing test suite counts as evidence. The agent cannot declare
> victory without runnable proof.

两处有料的地方：

- **lecture-10**（`docs/en/lectures/lecture-10-.../index.md`）：论点「只有全链路跑通才算真
  验证」，单测「系统性看不见组件边界缺陷」（`:10`）；把架构规则变成可执行检查、把 review
  反馈提升为自动化测试（`review feedback promotion`）、错误信息要带「怎么改」让 agent 自
  纠错（`:58`）。
- **harness-creator SKILL.md**：五个子系统表里 Verification 的产物是「`init.sh` 或文档化
  命令」，规则「把验证命令写明确、可运行」「标 done 前必须有证据」（`SKILL.md:26-29, 94-95`）。

## 共同模式（值得抄的）

1. **mock 只发生在 LLM 边界，其余跑真货**——四个里横跨三个真实 harness 的公约数。
   - pi：`replace the LLM, not the infrastructure`（`PHILOSOPHY.md:20-27`）
   - deepseek：`Mock only the expensive or non-deterministic boundary; keep everything
     downstream real`（`testing.md:22`）
   - codex：`integration tests drive a real turn loop against a TestCodexBuilder`
     （`function-calling.md:197`）
2. **测试必须能证明自己有用（不是写了就算）**：
   - deepseek：`introduce the regression, watch red, revert`（`testing.md:34`）
   - codex：`fails before... passes afterwards`（`contributing.md:40`）
   - pi：回归测试必须对号到 issue 号（`AGENTS.md:55`）
3. **bug 修复必须带回归测试**：三个真实 harness 全有。
4. **「不信任 agent 的自报」**：deepseek 的 `verify the world, not the self-report`
   （`testing.md:27-29`）和 learn-harness 的 `cannot declare victory without runnable proof`
   （`README.md:189`）是同一句话的两个版本。

## 差异（各自选了什么点）

| 维度 | codex | deepseek-harness | pi | learn-harness |
|---|---|---|---|---|
| 有没有字面 red-green | **有**（`contributing.md:40`） | 隐含（`testing.md:34` 反向验证） | 隐含（回归命名） | **无** |
| 覆盖率要求 | 不要求 100% | **每文件 100% 闸门**（`testing.md:10`） | 未声明 | 无（不做单测） |
| 对真实 API 的态度 | 需 key 的集成测试存在 | **默认要跑真实 API**（`testing.md:17-19`） | **suite 禁真实 API**（`README.md:8`） | 不涉及 |
| 测什么 | harness 代码 + 真实 turn loop | harness 代码 + 真实 API + 快照 | **agent loop 确定性行为** | agent 工作的完成证据 |
| 独特贡献 | 最轻、最可抄的入门 TDD | 快照测试 + 覆盖率闸门哲学 | faux provider 全套设计 | 验证作为 harness 子系统 + e2e 哲学 |

两组最值得注意的「相反」：

- **deepseek 重、codex 轻**：同样是 harness 代码，deepseek 把测试当成「绿套件本身要有
  意义」来维护（五层 + 闸门 + 快照必加），codex 只要求「有意义断言、不要求全覆盖」。
- **pi 的「禁真实 API」vs deepseek 的「别省真实 API」**：pi 把确定性 suite 当每天常态
  （毫秒级、CI-safe），真实 provider 验证外包给别处；deepseek 反过来说「无 key 测试只
  证明管道通」。两者都对，只是把「确定性」和「保真度」放在两层，谁也不该取代谁。

## 落到本仓库（AgentHarness101，Python）的三条目标

本仓库是 Python，`goal_loop` 的 maker/checker 是 callable，真 LLM 只在
`examples/llm_goal_loop.py`（要 key）。把上面的三问映射成三个可实施的目标：

1. **harness 代码怎么写测试（A）** → 抄 codex 的 red-green 入门版 + deepseek 的覆盖率
   闸门版。落地：pytest-cov 闸门 + 「bug 修复必须先红后绿」的纪律 + 一个证明闸门能抓
   未覆盖行的回归测试。
2. **怎么测 agent loop 本身（B）** → 抄 pi 的 faux provider 全套（mock 流边界、in-memory、
   事件流输出、回归命名）。落地：一个确定性 `FauxProvider` 接进 `goal_loop`，让整个 loop
   在无 key 下确定性跑通、可回归。
3. **怎么让 agent 自己证明工作（C）** → 抄 learn-harness 的验证子系统 + deepseek 的
   `verify the world, not the self-report`。落地：一个独立的世界校验器（重读产物文件、
   断言 byte-identical），说谎 maker 不能过。

三条各自独立，文件不重叠，可并行实施。每条对应一个 plan doc：

- 目标 1 → `doc/03_tdd_testing/plan.md`
- 目标 2 → `doc/04_faux_provider/plan.md`
- 目标 3 → `doc/05_verify_world/plan.md`
