# 目标 2 Benchmark — faux provider 的确定性 / 速度

> 测量口径：`FauxProvider` + `FauxMaker` + 真 `GoalLoopRunner`（真 SQLite store、
> 真 verifier、真状态机），只替换「LLM 说什么」。单轮 loop = 一个命令无（checker 裁决）
> 的验收项，checker 一次判 PASS 即 complete。

## 确定性

| 指标 | 值 |
|---|---|
| 同一脚本队列跑 10 遍的字节级 diff 计数 | **0**（完全确定） |
| 每遍产出的规范 trace | `done|complete` |

同一 `FauxProvider(["done"])` 脚本跑 10 个全新 loop（全新 db + state_dir），把每遍的
`("|".join(回复序列) + "|" + 终态)` 序列化后逐字节比对，10 遍无一处差异。diff 计数
口径是「与第一遍不同的遍数」，0 = 完全确定。

注意：`LoopState` 里带 `datetime.now()` 时间戳、`goal.usage.wall_ms` 是真实单调时钟，
所以**整份状态 JSON 不是字节确定的**；确定的是「假 LLM 说了什么 + loop 走到哪」这条
可观察链路。这正是 faux provider 要保证的那一层。

## 墙钟

| 指标 | 值 |
|---|---|
| 100 遍单轮 loop 总耗时 | **3270.7 ms** |
| 平均单轮 loop | **~32.7 ms** |

口径：每次 run 都新建一个 SQLite db 文件 + 一个 state_dir，包含 store 建表、写
`loop_state.json` 的磁盘 I/O。纯 loop 逻辑开销低于这个数。

## 真 LLM 基线

| 指标 | 值 |
|---|---|
| 模型 | `deepseek/deepseek-v4-pro`（经 `https://llm-proxy.tapsvc.com`，`ANTHROPIC_AUTH_TOKEN`） |
| 终态 | **complete**（1 轮） |
| 真 token 数 | **185**（首次冷缓存 565；`input+output`，随缓存波动） |
| 墙钟 | **5.19–7.50s / 平均 6.21s**（3 次干净 run，`python3 examples/llm_goal_loop.py`） |
| 机器 checker | `py -c ...assert m.answer() == 42` → **PASS** |

跑通前提是修了三处示例里「假设过时」的地方，全在 `examples/llm_goal_loop.py`：

1. **ThinkingBlock 提取**（第 66 行）：`response.content[0].text` → `"".join(b.text for b in
   response.content if b.type == "text")`。`deepseek-v4-pro` 是 thinking 模型，`content[0]`
   是 `ThinkingBlock`（只有 `.thinking`），直接 `.text` 抛 `AttributeError`。
2. **key 对齐**（第 37 行）：`MINIMAX_API_KEY or ANTHROPIC_AUTH_TOKEN` → `ANTHROPIC_AUTH_TOKEN
   or MINIMAX_API_KEY`。本机 env 的 MODEL/BASE_URL/AUTH_TOKEN 三件套已对齐到 llm-proxy，
   但旧顺序先取 `MINIMAX_API_KEY`，用「DeepSeek 端点 + MiniMax key」跑出 0 token、三轮
   `no progress` → BLOCKED。
3. **token 记账**（第 71 行）：`input - cache_read + output` → `input + output`。llm-proxy
   把 `input_tokens` 和 `cache_read_input_tokens` 报成**互不重叠**的两桶，缓存命中时相减
   会得到负值（实测 `-97`），导致 `assert goal.usage.tokens > 0` 间歇性挂掉。

结论：真 LLM 能把 harness 跑通（maker 写 `answer()==42`、机器 checker 独立裁决 PASS），
代价是每次 run 秒级 + 不确定（token 数 185/565 漂移）。faux provider 仍不可替代——它回答
「状态机对『LLM 说了 X』作何反应」，真 LLM 回答「真模型能不能完成任务」，两层不冲突。

## 取舍

| 维度 | faux provider | 真 LLM |
|---|---|---|
| 速度 | 毫秒级、无网络 | 秒级、有网络/限流 |
| 确定性 | 逐字节确定、可回归 | 不确定，同 prompt 每次不同 |
| 保真度 | **低**：回复是脚本，不是真推理 | **高**：真实模型行为 |

faux provider 回答「loop 状态机对『LLM 说了 X』作何反应」，回答不了「真模型能不能
完成任务」。两者是两层，谁也不取代谁（对应 `comparison.md` 里 pi 的「禁真实 API」
vs deepseek 的「别省真实 API」的同一分工）。
