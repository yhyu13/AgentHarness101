# 目标 2 — 测 agent loop 的 faux provider（mock LLM 边界）

> 来源：抄 pi 的 faux provider 全套哲学。对应 `doc/reference_harness/comparison.md` 三问
> 里的 **B**。

## 结论

**给 `goal_loop` 做一个确定性的 `FauxProvider`——只替换「LLM 说什么」这一个边界，让
maker 走假 LLM，其余（loop 状态机、verifier、sandbox、trace、hippocampus）全跑真货。
这样整个 goal loop 在无 API key 下确定性跑通、毫秒级、可回归。**

## 现状锚点

- `goal_loop/roles.py` 里 `Maker` 是 `(spec, state, steering) -> MakerOutput` 的 callable，
  现有 `EchoMaker`（回显，玩具）和 `StaticChecker`（静态裁决）。
- `examples/llm_goal_loop.py:40-87` 的 `LlmMaker` 真调 MiniMax API，要 key，进不了 CI。
- 没有「脚本化 LLM 回复 + 事件捕获」的确定性测试 harness——测 loop 要么用 EchoMaker
  （测不到「LLM 说了什么→loop 怎么反应」这条链路），要么要真 key。
- 已有测试里 `tests/test_goal_loop.py` 用 `EchoMaker`/`StaticChecker` 组合，没有
  「假 LLM 说话」的测试。

## 参考来源（抄什么）

| 模式 | 出处 |
|---|---|
| 只替换 LLM 边界，其余全真 | pi `harness_methods_1/PHILOSOPHY.md:20-27`（`mock the brain, not the body`） |
| 统一思想一句话 | pi `harness_methods_1/PHILOSOPHY.md:132-137`（`replace exactly one boundary, observe the rest`） |
| FIFO 脚本队列 + 动态 factory | pi `harness_methods_1/harness-philosophy.md:10-24`、`:193-212` |
| 流式而非一次性返回 | pi `harness_methods_1/harness-philosophy.md:172-189` |
| 事件流是一等输出 | pi `harness_methods_1/harness-philosophy.md:230-240` |
| callCount 验证重试 | pi `harness_methods_1/harness-faux.md:55-63` |
| 回归命名 `<issue>-<slug>` | pi `AGENTS.md:55`、`test/suite/README.md:13-15` |
| suite 禁真实 API 的契约 | pi `test/suite/README.md:6-10` |

## 方案

### 要建的文件

| 类型 | 文件 | 内容 |
|---|---|---|
| 新 | `faux_provider/__init__.py` | 公开 API：`FauxProvider`、`FauxResponseStep`、`FauxResponseFactory` |
| 新 | `faux_provider/provider.py` | `FauxProvider`：FIFO 脚本队列 + 动态 factory + `call_count` + 流式分块（可配 `tokens_per_second`）+ 事件捕获（`events` 列表 + `events_of_type`） |
| 新 | `faux_provider/maker.py` | `FauxMaker`：把 `FauxProvider` 接进 `goal_loop` 的 `Maker` 协议（产出 `MakerOutput`） |
| 新 | `tests/test_faux_provider.py` | 确定性 + 回归 + callCount + 事件流测试 |
| 新 | `doc/04_faux_provider/benchmark.md` | 确定性/速度基准 vs 真 LLM 基线 |

### 关键决策

1. **FauxProvider 自己不做 loop 状态机**：它只负责「脚本化地吐 LLM 回复 + 记录事件」，
   loop 的状态机（round、budget、blocked）仍由 `GoalLoopRunner` 驱动。这是 pi 的
   `harness.ts contains no phase logic`（`PHILOSOPHY.md:74-79`）同款原则。
2. **流式用同步生成器模拟**：本仓库 maker 协议是同步 callable，不搞真异步流；用
   「按 token 分块 yield」模拟流式，让「中途截断/多轮」可测，不引入 asyncio。
3. **事件捕获是核心交付物**：`FauxProvider` 把「每次被调用了什么、回了什么、耗时多久」
   记进 `events`，因为 messages 记录不了重试/轮次切换（pi `harness-philosophy.md:238`）。
4. **动态 factory 支持「验证上下文」**：`FauxResponseFactory(context, state) -> str` 让
   测试能「看到 maker 收到什么才回什么」（pi `harness-philosophy.md:193-212`），这是测
   anti-drift steering 是否真被注入的关键。

## 成功标准（做完才叫 done）

1. **red-green**：先写 `tests/test_faux_provider.py` 里至少一条会失败的断言（比如
   `call_count` 或 FIFO 消费顺序），再实现到绿。
2. **确定性基准**：同一个脚本队列跑 10 遍 loop，输出逐字节一致（determinism = 1.0）；
   墙钟时间 vs `examples/llm_goal_loop.py` 的真 LLM 基线（要 key 的跑不了就标 `待确认`）。
3. **事件流断言**：一条测试证明 `events` 记录了「maker 被调用 N 次 + 每次的回包」，
   且 `events_of_type("maker_call")` 能按类型过滤。
4. **回归命名**：至少一条回归测试用 `<issue>-<slug>` 命名（模拟 issue 号）。
5. **全量测试仍绿**：`python -m pytest -q` 不破坏现有 85 测试。

## 自我批判（写完第一稿后改了什么）

- **砍掉 asyncio 真流式**：初稿想真异步流式，但 maker 协议是同步的，引入 asyncio 会
  逼着改 `GoalLoopRunner` 的调用面。改成同步生成器模拟分块，够用且不越界。
- **砍掉「在 FauxProvider 里做 loop 状态」**：初稿想让 FauxProvider 管轮次，被 pi 的
  `no phase logic in harness.ts` 原则否决——loop 状态属于 `GoalLoopRunner`。
- **明确「确定性基准」的可测部分**：真 LLM 基线可能要 key，把它标 `待确认` 而不是
  编一个数字。

## 边界（子代理不要碰）

- 不碰 `pyproject.toml`、`AGENTS.md`、`scripts/check.sh`（那是目标 1 的）。
- 不碰 `goal_loop/verifier.py`、`goal_loop/loop_runner.py` 的完成判定逻辑（那是目标 3 的；
  本目标只新增 `faux_provider/` 包 + 测试，不改 loop 核心）。
- 不碰 `JOURNEY.md`、`.wolf/STATUS.md`、`README.md`。
