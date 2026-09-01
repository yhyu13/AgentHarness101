# Cerebrum

> OpenWolf's learning memory. Updated automatically as the AI learns from interactions.
> Do not edit manually unless correcting an error.
> Last updated: 2026-08-30

## User Preferences

<!-- How the user likes things done. Code style, tools, patterns, communication. -->

## Key Learnings

- 本机 `python` = Python 2.7.18（无 pytest），`python3` = 3.13.13（有 pydantic/pytest）。**跑测试必须用 `python3`**。
- 覆盖率闸门：`pytest-cov` + `fail_under=92` + `precision=2`。不设 `precision` 会先四舍五入再比对，导致「打印 FAIL 但退出码 0」。
- 三个测试缝：① `scripts/check.sh`/coverage 配置（meta-test 用 `tomllib` 读 pyproject）；② `FauxProvider` 公开 API（mock LLM 边界，loop 状态机仍归 `GoalLoopRunner`）；③ `WorldVerifier.verify_all()`（重读磁盘产物，不信自报）+ `GoalLoopRunner` 可选 `world_verifier` 参数 fail-closed。
- `WorldVerifier` 用 `Path.read_bytes()` 做 byte-identical；`write_text` 在 Windows 会做 CRLF 翻译，会误红。
- 覆盖率未覆盖行的「死代码 vs 行为」判定：**已文档化 + 可达 + 有清晰语义 = 行为（补测试）；孤立/不可达 = 死代码（删）**。`stream()` 的 `tokens_per_second` 分块分支因 plan.md + docstring 均描述、参数真实可达，判行为。
- 流式限速测试确定性技巧：`monkeypatch.setattr("faux_provider.provider.time.sleep", lambda _s: None)` 把 `time.sleep` 置 no-op，避免时序抖，仍测分块契约（N 词→N 块、非末块带尾随空格）。
- 自我改进闭环的挂点：`GoalLoopRunner._finalize` 是 run 的唯一收尾点（status+summary 都在这聚合）→ 天然是「结果→教训」的 distill 挂点；`cont.steering_prompt`（anti-drift 模板）是「教训→注入」的挂点。教训用 `correct=False` 承载「别再这么做」（hippocampus 已有该语义），检索用确定性词重叠（`len>=3` 交集），全程不发 LLM——守住「只 mock LLM 边界」。
- 模块放置防环：新模块若既 `import goal_loop.models`（读 FinalResult）又被 `goal_loop` 用（runner 挂点），会造 `hippocampus→goal_loop` 环。解法是放 `goal_loop/` 内、只 `import hippocampus`，与 `world_verifier.py` 同级对称。

- 新模块接 loop 的两种正交模式：① `Scheduler` 只依赖一个 `Runner` Protocol（`run_until_terminal(thread_id)`），不硬绑 `GoalLoopRunner`，单元测试用 stub 隔离「排序/skip/错误隔离」逻辑，另留一条真 `GoalLoopRunner` 集成测试证明组合；② `Orchestrator.make`/`check` 的签名对齐 `Maker`/`Checker` Protocol，直接当 maker+checker 传进 `GoalLoopRunner`，无需改 loop。
- fail-closed 的「空 plan」边界：`Orchestrator.make` 的 `ok = not errors and bool(outputs) and all(o.ok)`。空 plan（零步）必须判 `ok=False`（没干活=不 ok），否则 `all([])` 的真空真会让「规划出 0 步」被误判成功。

## Do-Not-Repeat

- [2026-08-28] 用 `python` 跑 pytest（2.7 无 pytest，报 No module named pytest）。用 `python3`。
- [2026-08-28] meta-test 硬编码精确列表（`assert source == [...]`），新增包就红。改断言为子集 `set(REQUIRED) <= set(actual)`。
- [2026-08-28] 三个子代理并行改同一仓库时，各自跑全量会看到彼此中间态（如 `faux_provider` 未生成时 collection 报错）。最终全量验证由主代理串行做，不依赖子代理的「全绿」报告。
- [2026-08-29] 用 edit 改 `safety.py` 时，oldString 用 `@dataclass\nclass SafetyGuard:` 当锚点想插常量，结果把 docstring 首行一起删了。教训：改类定义前先 Read 精确行号，oldString 要含完整 docstring 首行，别只锚「类名行」。
- [2026-08-29] 下结论「X 钩子缺失/没装」前，先查 `token-ledger.json` 的 `lifetime.total_sessions` 和 `.wolf/hooks/_session.json`。数字=0 不一定是钩子没装，可能只是「还没跑过一个会读/写文件的会话」。Kilo 钩子其实早已由 `openwolf init --agent kilo` 生成在 `.kilo/plugin/openwolf/`（11 个 .ts），且 `session.created`/`session.idle` 已触发过（total_sessions 0→1、stop_count 1）。

- [2026-09-01] 本机有 GateGuard「Fact-Forcing Gate」钩子，每次 Edit/Write 前都要先回 4 条事实（谁 import 这文件 / 是否已有同用途文件 / 数据结构 / 用户指令原文）。先 Grep 一次「谁 import」+ Glob「是否已有同用途」再一次性把 4 条写进消息里即可通过，别干等。
- [2026-09-01] src 布局迁移后，`examples/*.py` 的 `sys.path.insert(0, parent.parent)` 还指 repo root，不是 `src/`，直接跑会 `ModuleNotFoundError: goal_loop`。迁移布局时要连 examples 的 sys.path 一起改成 `parent.parent / "src"`（已修 9 个示例）。
- [2026-09-01] 跑真 LLM 基线前先核对 model/base_url/key 三件套是否对齐，别假设示例默认值就是对的：本机 env 的 `ANTHROPIC_MODEL=deepseek/deepseek-v4-pro` 与示例硬编码 `MiniMax-M3` 冲突，用「DeepSeek 模型 + MiniMax key」跑出 maker 0 token、goal BLOCKED。环境里可能配的是另一家 provider。
- [2026-09-01] thinking 模型（deepseek-v4-pro）的 `response.content` 里 `content[0]` 是 `ThinkingBlock`（只有 `.thinking`），不是 `TextBlock`，直接 `.text` 抛 `AttributeError`。提取文本用 `"".join(b.text for b in content if b.type == "text")`。真 LLM 基线跑通三处要改：① thinking block 提取 ② key 顺序 `ANTHROPIC_AUTH_TOKEN or MINIMAX_API_KEY`（对齐 env 三件套）③ token 记账 `input+output`（llm-proxy 的 `input_tokens` 与 `cache_read_input_tokens` 互不重叠，相减得负值 `-97`）。
- [2026-09-01] 不同 provider 的 API 格式不一样，别默认都是 Anthropic：deepseek/grok/minimax 走 Anthropic 兼容（`/v1/messages`），kimi 走 OpenAI 兼容（`/chat/completions`，用 anthropic 客户端会 404）；glm 的 429 code 1113 = 账户无额度，不是配置错。接新 provider 先按文档/错误码定格式，别硬套。
- [2026-09-01] thinking 模型（kimi 的 `reasoning_content`、deepseek 的 `ThinkingBlock`）会把 `max_tokens` 预算先花在推理上，小 cap（≤128）会返回空 `content`/`answer`。接 thinking 模型的 judge/summarizer 要留足 headroom（512 起），否则输出是空串、被误判 FAIL。

## Decision Log

- coverage `source` 断言用「子集」而非「精确相等」：允许新增生产包进闸门，不因列表变化而红。
- 三个目标并行派发子代理，文件不重叠（目标1=pyproject/scripts/AGENTS，目标2=faux_provider，目标3=goal_loop/world_verifier），最终由主代理统一全量验证。
- crashed-maker 兜底「维持现状 vs 加兜底」分支：核实代码里早已 fail-closed（`loop_runner.py:210-219` 捕获 maker/checker 异常 → `ok=False`/`FAIL`），`test_red_team.py:61` 已钉。结论是「维持现状 + 测试已钉」，只订正 STATUS 的过时描述，不新增代码。
