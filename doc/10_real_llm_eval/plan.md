# 实施计划 — 真 LLM 深度评测套件

垂直切片，先红后绿。前四片离线可测（mock/stub，不烧 API），最后一片才 run once 烧真 LLM。

## Slice 1 — adapter（`eval_llm/client.py`）

- `ModelSpec`（frozen dataclass）：`key / model_id / base_url / api_key_env / format`。
- `MODELS`：5 个模型注册表（glm 不入，标注释「额度待恢复」）。
- `LLMReply`（frozen dataclass）：`text / input_tokens / output_tokens / latency_ms`。
- `_load_env()`：手读 `.env` + 合并 `os.environ`（`.env` 不在进程 env，见 cerebrum Do-Not-Repeat）。
- `generate(spec, prompt, max_tokens=256, system=None) -> LLMReply`：
  - Anthropic 分支：过滤 `TextBlock`；token = `input + output`（不 `-cache`，见技术债）。
  - OpenAI 分支：用 `message.content`（忽略 `reasoning_content`）。
  - 用 `time.monotonic` 量 latency。
- **红**：用 mock client 断言 thinking 提取 + token 记账 + 双格式分支。

## Slice 2 — report（`eval_llm/report.py`）

- `ReportEntry`（dataclass）：`model / dimension / test_id / status / input_tokens / output_tokens / latency_ms / cost_usd / note`。
- `render_markdown(entries) -> str`：按「模型 × 维度」排成表 + 汇总行。
- **红**：固定 entries 断言渲染结果含表头、每行模型名、成本列。

## Slice 3 — opt-in pytest 套件（`tests/test_real_llm.py`）

- `pytestmark = pytest.mark.real_llm`；session 级 autouse fixture：`RUN_REAL_LLM` 未设则 skip 全模块。
- `models` fixture：对 `MODELS` 逐个探测，缺 key / 调用 404/429 → `skip(reason=…)`。
- 四维测试函数，`parametrize("model", ...)`：
  - breadth：maker 产 artifact、LLMJudge fail-closed、summarizer 摘要。
  - depth：complete / blocked / budget_limited / max_rounds 四终态。
  - metrics：N 次 1-round 计时 + token + cost。
  - redteam：注入 marker、高风险 HITL、说谎 checker 不击穿。
- **红**：`RUN_REAL_LLM=0` 下断言「全 skip + 套件结构（marks/gating）正确」，不烧 API。

## Slice 4 — 跑一轮 + 出报告 + 文档

- `RUN_REAL_LLM=1 python3 -m pytest tests/test_real_llm.py -q`，报告写 `doc/10_real_llm_eval/report.md`。
- 更新 JOURNEY（Era 35）、STATUS、README（测试计数 + 真 LLM 深度评测一节）、cerebrum（kimi=OpenAI 格式教训）。
- 提交推远程。

## 边界

- glm 不进 MODELS（额度）；`MODELS` 里留 `# glm 待恢复` 注释。
- 不接 CI 默认跑；`RUN_REAL_LLM` 手动触发。
- 成本用 `model -> Price` 映射，显式标「vendor 待确认」。
