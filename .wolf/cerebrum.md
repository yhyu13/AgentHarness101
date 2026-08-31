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

## Do-Not-Repeat

- [2026-08-28] 用 `python` 跑 pytest（2.7 无 pytest，报 No module named pytest）。用 `python3`。
- [2026-08-28] meta-test 硬编码精确列表（`assert source == [...]`），新增包就红。改断言为子集 `set(REQUIRED) <= set(actual)`。
- [2026-08-28] 三个子代理并行改同一仓库时，各自跑全量会看到彼此中间态（如 `faux_provider` 未生成时 collection 报错）。最终全量验证由主代理串行做，不依赖子代理的「全绿」报告。
- [2026-08-29] 用 edit 改 `safety.py` 时，oldString 用 `@dataclass\nclass SafetyGuard:` 当锚点想插常量，结果把 docstring 首行一起删了。教训：改类定义前先 Read 精确行号，oldString 要含完整 docstring 首行，别只锚「类名行」。
- [2026-08-29] 下结论「X 钩子缺失/没装」前，先查 `token-ledger.json` 的 `lifetime.total_sessions` 和 `.wolf/hooks/_session.json`。数字=0 不一定是钩子没装，可能只是「还没跑过一个会读/写文件的会话」。Kilo 钩子其实早已由 `openwolf init --agent kilo` 生成在 `.kilo/plugin/openwolf/`（11 个 .ts），且 `session.created`/`session.idle` 已触发过（total_sessions 0→1、stop_count 1）。

## Decision Log

- coverage `source` 断言用「子集」而非「精确相等」：允许新增生产包进闸门，不因列表变化而红。
- 三个目标并行派发子代理，文件不重叠（目标1=pyproject/scripts/AGENTS，目标2=faux_provider，目标3=goal_loop/world_verifier），最终由主代理统一全量验证。
