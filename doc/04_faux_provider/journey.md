# 目标 2 Journey — faux provider

> 两列：YOU = 你（人）的请求/决策/纠偏；ME = 我（agent）的构建/发现/证伪/修复。

## 风险 / TODO

- **风险**：`FauxProvider` 队列耗尽时抛 `FauxProviderExhausted`，测试若少脚本化一条回复
  会直接炸，而不是静默回空。这是刻意选严（fail-fast 抓欠脚本），但新作者可能觉得突兀。
- ✅ **已解决**：`stream` 的 `tokens_per_second` 限速分支之前未测（要真实 sleep，时序测不稳），
  现用 monkeypatch `time.sleep` 补确定性测试，`provider.py` 覆盖率 100%。
- **TODO**：真 LLM 基线（`examples/llm_goal_loop.py` 的 MiniMax）没有 key，墙钟/保真度
  对比标「待确认」，拿到 key 后补。
- **TODO**：`events` 的事件类型固定为 `"call"`，plan.md 成功标准里写的是 `"maker_call"`，
  命名上有一处偏离（见下），若要统一可加一个 `FauxMaker` 层事件类型。

## 偏离 plan 的决策

1. **事件类型用 `"call"` 而不是 plan.md 里的 `"maker_call"`**：任务硬性 seam 明确写
   `events_of_type("call")`，plan.md 的成功标准写 `"maker_call"`，两者冲突。以任务
   seam 为准，用 `"call"`，因为 `FauxMaker` 每次 `__call__` 恰好等于一次 provider 调用，
   1:1 映射，「maker 被调用 N 次」= N 条 `"call"` 事件。
2. **队列耗尽契约选「抛错」而非「回空」**：任务说「抛错或回空（你定契约）」。选抛
   `FauxProviderExhausted`，fail-fast 抓欠脚本，docstring 写清。
3. **`tokens_used` 只按回复长度估算**（`len(response)`），不把 prompt 算进去。plan 说
   「用回复长度估算，不编 token 数」，按字面执行。

## 时间线

| YOU | ME |
|---|---|
| 给 plan.md + comparison.md + 目标 2 边界，明确「只替换 LLM 边界，loop 状态机全跑真货」 | 读 `roles.py`/`models.py`/`loop_runner.py`/`test_goal_loop.py` + `goal_persistence` 全链路，确认 `Maker` 是同步 callable、`steering` 是 `maybe_continue` 产出的 anti-drift prompt |
| — | 基线 `python3 -m pytest -q` = 109 passed（工作区已含目标 1/3 的未提交文件，比 brief 的 85 多） |
| 要求严格 red→green，先写失败测试 | 写 `tests/test_faux_provider.py`（FIFO / call_count / events / 动态 factory / 确定性 / 组合缝 / 回归命名），首跑红：`ModuleNotFoundError: No module named 'faux_provider'` |
| — | 实现 `faux_provider/`（provider.py 的 FIFO+factory+events+stream，maker.py 的 FauxMaker 转 MakerOutput，`__init__.py` 公开 API） |
| — | 转绿：`test_faux_provider.py` 13 passed |
| — | 跑 benchmark：确定性 diff=0，单轮 loop ~32.7ms，真 LLM 基线待确认 |
| 要求补 benchmark.md + journey.md，写清取舍 | 写 `benchmark.md`（确定性/墙钟/真 LLM 基线/取舍表）+ 本 journey |
| — | 全量 `python3 -m pytest -q` = **110 passed**，全绿 |

## 学到的

- **mock 大脑不 mock 身体**落地得很干净：`FauxProvider` 完全不知道 `LoopState` 长什么样，
  `context`/`state` 是 opaque 传参，所以动态 factory 能读到 anti-drift steering 这件事是
  从 `FauxMaker` 把 `steering` 当 `context` 传进去才成立的——边界接缝清晰。
- **确定性有边界**：loop 的 `datetime.now()` 和 `wall_ms` 让整份状态 JSON 永远不确定，
  能确定的是「假 LLM 说了什么 + 走到哪」。基准口径必须钉死这一层，否则会误报「不确定」。
- **一个冲突命名花了我一次返工**：任务 seam 写 `"call"`、plan 写 `"maker_call"`。以任务
  为准并记进偏离，而不是猜一个。
