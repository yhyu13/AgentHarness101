# Agent Harness 101

## 开发流程：superpowers（spec + TDD）

功能开发与测试走 Superpowers，顺序固定：

1. `superpowers:brainstorming` — 想法 → 设计/规格（先分类 spike/bounded/architectural，出设计后等你点头）。
2. `superpowers:writing-plans` — 规格 → 实施计划。
3. `superpowers:test-driven-development` — 先红后绿，垂直切片推进。
4. `superpowers:verification-before-completion` — 收尾前自证，不靠感觉。

`software-dev-loop` 和独立 `tdd` 技能不参与本仓库的 spec+TDD。

## 上下文交接：OpenWolf（仅此用途）

OpenWolf 只做会话间上下文，不进上面的构建流程：

- `.wolf/STATUS.md` — 会话开始读一次；quest 收尾更新一次。
- `.wolf/anatomy.md` — 读文件前查索引。
- `.wolf/cerebrum.md` — 生成代码前查 Do-Not-Repeat。

buglog / memory 记账不单独做，交给 superpowers 流程。

## 测试纪律

- 修 bug 必须带一个「修复前失败、修复后通过」的回归测试（`fails before, passes afterwards`）。没有先红的测试不算数。
- 覆盖率闸门是 `scripts/check.sh`（`python3 -m pytest --cov --cov-report=term-missing`，`fail_under` 见 `pyproject.toml`）。未覆盖的行先考虑**删**（是死代码），不是先补测试。
- 覆盖率只证明「这行跑过」，不证明「行为对」。闸门是必要不充分条件：它抓得到回归，但绿不代表产品对。

## 品味标准：agent = LLM 头脑 + harness 手脚 + 安全边界

多 agent 过夜竞争打分，黄金标准一个三元组（`taste_score`，详见 [spec](doc/superpowers/specs/2026-09-02-taste-score-design.md)）：

- **C（头脑）** — LLM 推理被用得好不好：不是调了 API，是「该想的地方想了」。
- **E（手脚拓边）** — harness 能力边界被真的推开：新增/改进了能力，不是刷存在感。
- **S（安全边界）** — 能力扩张同时安全边界没被啃掉：拓边可以，越界不行。

评判是**成对的帕累托比较**，不叠加记分（不然就是刷点）。好 = E 上 & S 不降，或 S 上 & E 不降；**坏 = E 上 & S 降**——无脑拓边认怂安全，不是加分是**拉黑**。

### 防刷分（Goodhart 五道锁）

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
