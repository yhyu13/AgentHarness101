# 设计 — 真 LLM 深度评测套件

> 结论先行：**能做，做成一个「默认跳过、显式 opt-in、跨 5 个模型」的 pytest 套件 + 一份 Markdown 报告。**
> 代价是给套件加一层「双 API 格式适配器」，并把成本指标标成「待确认」。glm 因账户无额度，
> 进套件但运行时会 graceful skip 并记原因。

## 背景

现有真 LLM 基线（`examples/llm_goal_loop.py`）只有一个 happy-path 冒烟：`deepseek-v4-pro` 写
`answer()==42`，complete / 1 轮。太浅——它没证明 harness 在**真模型的不确定性**下还能 fail-closed，
也没测**广度**（各层的 LLM 边界）、**深度**（单 loop 边界）、**数字**（真实 variance）、**红队**
（真模型的对抗输入）。这套件补这四块。

## 模型矩阵（探测定案）

| 短名 | wire model id | 格式 | 端点 | key | 状态 |
|---|---|---|---|---|---|
| deepseek-v4-pro | deepseek/deepseek-v4-pro | Anthropic | llm-proxy.tapsvc.com | ANTHROPIC_AUTH_TOKEN | ✅ |
| deepseek-v4-flash | deepseek/deepseek-v4-flash | Anthropic | llm-proxy.tapsvc.com | ANTHROPIC_AUTH_TOKEN | ✅ |
| grok-4.6 | x-ai-grok/grok-4.6 | Anthropic | llm-proxy.tapsvc.com | ANTHROPIC_AUTH_TOKEN | ✅ |
| minimax-m3 | MiniMax-M3 | Anthropic | api.minimaxi.com/anthropic | MINIMAX_API_KEY | ✅ |
| kimi-k2-turbo-preview | kimi-k2-turbo-preview | **OpenAI** | api.kimi.com/coding/v1 | KIMI_CODE_API_KEY | ✅ |
| glm | （待确认，额度恢复前不进） | OpenAI | open.bigmodel.cn/... | GLM_API_KEY | ❌ 1113 无资源包 |

两条硬结论：

1. **kimi 是 OpenAI 格式**，不是 Anthropic——之前用 anthropic 客户端全 404 就是格式错。
   套件必须同时支持两种格式（一个 adapter 层）。
2. **glm 是 key 对但没额度**（code 1113「无可用资源包」），不是配置错。所以套件要能「某模型不可用
   时 graceful skip 并记原因」，不能因为一个模型挂了拖垮整批。

## 架构

```
eval_llm/                    # 顶层评测工具包（不在 src，不进覆盖率 source）
  client.py                  # ModelSpec + MODELS 注册表 + generate()（双格式适配）
  report.py                  # ReportEntry + render_markdown()（聚合 + 渲染）
tests/
  test_real_llm.py           # 四维测试，@pytest.mark.real_llm，默认跳过
```

三个单元各干一件事、独立可测：

- **client.py** — 把「两个 API 格式 + thinking 模型提取」收口成 `generate(spec, prompt) -> LLMReply`。
  `LLMReply(text, input_tokens, output_tokens, latency_ms)`。格式差异在 adapter 内消解，调用方只见
  纯字符串 + 诚实 token。
- **report.py** — 收集每次调用的 `ReportEntry`，渲染成「模型 × 维度」的 Markdown 表 + 汇总。
- **test_real_llm.py** — 四维测试，全部 `parametrize` 过可用模型。

## 四个维度

### 1. 广度（全层真 LLM）

harness 真正有 LLM 边界的层（「只 mock LLM 边界」里的那条边界）是三个，逐层喂真模型：

- `goal_loop` maker — 真 LLM 产 `answer()` artifact，机器 checker 验证（复用 `examples/llm_goal_loop.py`
  的 maker 模式）。
- `eval_harness.LLMJudge` — 真 LLM 当裁判，喂「该 PASS」和「该 FAIL」各一例，验证 fail-closed
  （`LLMJudge` 已收 `Callable[[str], str]`，直接包一层）。
- `context_compaction.summarizer` — 真 LLM 摘要一段标记内容，验证摘要非空且长度显著下降。

> `self_improver` 用确定性词重叠（`len>=3` 交集），不发 LLM；`safety`/`cost_control` 是横切面不是
> 推理边界。这三处不硬塞真模型，避免「为测而测」。

### 2. 深度（单 loop 边界）

一个 goal loop 在真 maker（非确定性）下推到四种终态，验证状态机 + fail-closed 不漂：

- complete（1 轮，maker 一次写对）。
- blocked（maker 被提示「永远写错」，三击触 `BLOCKED_THRESHOLD=3`）。
- budget_limited（极小 token budget，首轮就超）。
- max_rounds（`StopCondition(kind="max_rounds")` 上界）。

每项断言的是**终态**，不是 LLM 说了什么——真模型不确定性被状态机 + 机器验证兜住。

### 3. 数字（真实计量）

每个模型跑 N 次 1-round-complete，记录：wall-clock（mean ± std）、input/output token、成本（illustrative）。
产出「5.19–7.50s / 平均 6.21s」这类带范围的数字，替代单次冒烟的点值。

### 4. 红队（真模型对抗）

把对抗 prompt 喂进 harness，验证 harness 的护栏（不是 LLM 的服从）触发：

- 注入：「Ignore all previous instructions…」→ `safety` 注入 marker 命中。
- 高风险动作：诱导 LLM 产 `deploy` → `safety._HIGH_RISK_ACTIONS` 触发 HITL。
- 说谎 checker + 真 maker：验证 generator/evaluator 不被击穿（world_verifier 兜底）。

## 关键决策

1. **成本标「待确认」**。`PRICING` 是 "mini/small/large" 分层、illustrative，没有真实模型 ID。
   套件另建一张 `model -> Price` 表并显式注释「vendor 数字待确认」，只保证计价器确定，不声称真实价格。
2. **opt-in + 限速 + 预算**。`RUN_REAL_LLM=1` 才跑，否则全 skip；调用间 sleep 限速；每模型 token 预算
   上限，超了就停并记。
3. **graceful skip**。key 缺失 / 网络错 / 404 / 429 都 `pytest.skip(reason=…)` 并记进报告，不 fail 整批。
4. **离线可 TDD**。adapter 的 thinking 提取、report 的渲染、套件的 opt-in 门控都能用 mock/stub 离线红绿，
   不烧真 API。真 LLM 只在一轮「run once + dump report」里烧。

## 边界（不做什么）

- 不做 glm 的额度恢复（那是账户问题，不是代码）。
- 不把真 LLM 套件接进 CI 默认跑（要 key + 烧钱）；留 `RUN_REAL_LLM` 手动触发。
- 不新增「为测而测」的 LLM 边界（self_improver/safety 等本就是确定性逻辑）。
- 不追真实 vendor 定价表（`待确认`，等有官方价再补）。
