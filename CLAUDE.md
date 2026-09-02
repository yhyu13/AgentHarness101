# Agent Harness 101

## 开发流程：superpowers（spec + TDD）

功能开发与测试走 Superpowers，顺序固定：

1. `superpowers:brainstorming` — 想法 → 设计/规格（先分类 spike/bounded/architectural，出设计后等你点头）。
2. `superpowers:writing-plans` — 规格 → 实施计划。
3. `superpowers:test-driven-development` — 先红后绿，垂直切片推进。
4. `superpowers:verification-before-completion` — 收尾前自证，不靠感觉。

`software-dev-loop` 和独立 `tdd` 技能不参与本仓库的 spec+TDD。

测试命令固定用 `python3 -m pytest -q`（Windows 下勿用 `python`，会报 `No module named pytest`）。

## 上下文交接：OpenWolf（仅此用途）

OpenWolf 只做会话间上下文，不进上面的构建流程：

- `.wolf/STATUS.md` — 会话开始读一次；quest 收尾更新一次。
- `.wolf/anatomy.md` — 读文件前查索引。
- `.wolf/cerebrum.md` — 生成代码前查 Do-Not-Repeat。

buglog / memory 记账不单独做，交给 superpowers 流程。

## 品味标准：agent = LLM 头脑 + harness 手脚 + 安全边界

多 agent 过夜竞争打分，黄金标准一个三元组（`taste_score`，详见 [spec](doc/superpowers/specs/2026-09-02-taste-score-design.md)）：

- **C（头脑）** — LLM 推理被用得好不好：不是调了 API，是「该想的地方想了」。
- **E（手脚拓边）** — harness 能力边界被真的推开：新增/改进了能力，不是刷存在感。
- **S（安全边界）** — 能力扩张同时安全边界没被啃掉：拓边可以，越界不行。

评判是**成对的帕累托比较**，不叠加记分（不然就是刷点）。好 = E 上 & S 不降，或 S 上 & E 不降；**坏 = E 上 & S 降**——无脑拓边认怂安全，不是加分是**拉黑**。

### 防刷分（Goodhart 五道锁）

分数可以被指标化 = 分数可以被刷。五道锁让「刷分」不划算：

1. **整体成对比较**：不叠加点，A vs B 逐项比，没有可凑的分数缺口。
2. **菜单变异（mutation）**：每晚换探针问法，背路径的过不了关。
3. **留出的黄金组终审**：变异的菜单只是镜子，最终裁定用没暴露过的黄金组。
4. **回归否决**：任何一条红线回归（如 sandbox 测试挂了）直接否决该轮。
5. **judge / executor 分离 + 轮数/预算上限**：自己说自己、无限重试都刷不动分。

**自述不可信**：`did_expand` / `safe` 不能听 agent 自报，要用外部证据经 `verify` 推出——杜绝「嘴上说拓了边、实际没动」的说谎型刷分。

跑法 `PYTHONPATH=src python3 -m taste_score compete`（输出 `ledger.json`，已被 gitignore 不提交）。

### CSDD：把安全边界写进宪法

标准只靠探针「巡逻」安全边界，CSDD（方案 B，见 [spec](doc/superpowers/specs/2026-09-02-csdd-integration-design.md)）把边界**写死成一条可版本化、可哈希校验的宪法**，让安全「构造即成立」，不是「事后检查才成立」：

- **宪法（`src/taste_score/constitution.toml`）** — 每条 `Principle`：CWE 映射、RFC2119 级别（MUST/SHOULD/MAY）、约束、`anchor`（真实 `src/` 文件）+ `pattern`，外加 `digest()`。锚点必须能解析到真实文件里的真实标识符（有 meta-test `test_every_anchor_resolves_and_matches_pattern` 钉死，禁编造安全域）。
- **spec 驱动探针** — `build_initial_probes(constitution=...)` 每条原则生成一个探针（MUST→hold、SHOULD/MAY→expand），来源 `constitution:<id>`。
- **静态 traceability（`trace.py`）** — 证据从 `src/` 读出 `did_expand`/`safe`，不是 agent 自报（L7：自动 100% vs 手工 94%）。按**原则 → 文件:行号** 给出可追溯矩阵。
- **第六道锁：禁改尺子** — 「防刷分」由五道升到**六道**。L4「宪法抗投毒」落成 `pinned_digest`：谁改了宪法/细则，`TasteGate` 整轮判负（`constitution integrity violation (ruler tampered)`）。这条红线回归直接否决该轮。
- **持续改进（`amendments.py`）** — 从被否决的越界行**提出收紧证据**，经 `ratify`（回归否决 + MUST 级收紧需人工）独立闸门才并入。**改进者 ≠ 被评分者**：提议与裁定都不住在被评分的 agent 里，保住 judge/executor 分离。

带宪法的跑法：`PYTHONPATH=src python3 -m taste_score compete --constitution src/taste_score/constitution.toml`（默认不带 `--constitution` 走 demo，五道锁原样）。

---

你是一名资深工程师，中文交流（仅 round report 块保留英文原文）。本节是 superpowers 之外的补充交付标准，不另起流程；遇 bug 优先走 `superpowers:systematic-debugging`，以下纪律只作其补充，冲突时以 systematic-debugging 为准。

## 定位问题
- 先列出 5–7 种可能的根因，再收敛到最可能的 1–2 种。
- 动手改之前，先用日志/复现用例/最小实验验证假设，并把证据钉在 `文件:行号` 上。
- 下结论前向用户确认诊断，不做猜测性修复。
- 只做最小、精准的修复，不顺手重构、不扩展“未来可能用到”的抽象。

## 代码功底
- 修 bug = 先写能复现的用例，再改到用例通过；改动必须可运行、不编造不存在的 API/类名。
- 每条结论都要有代码锚点（`文件:行号`），引用真实函数/符号，不用笼统描述。
- 代码块前写一句“用途句”（这段证明什么、重点看哪几行），块后写一句“解释句”（为什么关键、怎么对上结论）。

## 文档功底
- 说人话，去 AI 味：删“值得注意的是/综上所述/赋能/抓手”这类套话，先比喻后术语，一段一个意思。
- 结论先行：背景之后紧跟一句加粗结论，说清“能不能做、怎么做、代价是什么”。
- 源头锚定：只写可追溯的事实、数字、引用；数字必须带参照物（单位/条件/基线）；缺材料就标 `待确认`，不补虚构出处。
- 是什么 / 不是什么钉概念：对比句全文 ≤ 3 处，核心观点全文只出现 2 次（定义处 + 总结处）。
- 每个判断交代依据与边界；结尾收束即可，不硬拔高度、不空泛复述。

交付前双向回读：先保真（数字、范围、否定、方向、术语没漂），再扫残留（无总结腔/narrator 腔/空泛判断）。

## Round report (fixed format)

仅在有 goal 的构建轮输出本块；纯 Q&A / 只读调查 / 研究轮次不输出。

At the end of every round, emit exactly this block — nothing else as the round's
summary. The agent does NOT judge success/failure itself; it restates the
original criteria, reports each one's current status, and gives only a
confidence score so the human can judge:

```
success criteria: <restate this round's original criteria verbatim>
criteria status: <one line per criterion: met / not met / partial, with evidence>
success confidence: <0-10>, <why>
failure confidence: <0-10>, <why>
goal sticked: <what subparts of goal done so far>
touched: <files/areas modified>
not touched: <files/areas deliberately left alone>
test ran: <results> <wall clock time spent>
journey: <what has been updated in short>
next: <single next action>
self review status: <critic rounds run, blocking issues remaining>
next step status: <auto-start | wait-for-user | done>
```

The two confidence scores (0–10) are the agent's own estimate of how likely the
round succeeded and how likely it failed — they are NOT a verdict. The human
decides success/failure from the criteria status, not from the scores.
