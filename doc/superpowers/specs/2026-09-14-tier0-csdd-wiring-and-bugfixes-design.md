# Tier-0 接线与真 bug 修复 — 设计规格

来源：2026-09-14 全仓审计（12 维度 / 28 agent / 84 条幸存 gap）。本规格只收 Tier-0：
**4 条 CSDD 接线断裂 + 5 条真 bug**，共 9 项。全部是 stdlib 小改，零新依赖，符合仓库
「E 上且 S 不降」标准：它们不扩能力面，只把已建成的守卫接到运行路径上。

## 背景：为什么先修这些

审计的结论是「概念全仓唯一新，工程约三成接通」。仓库最值钱的三样东西——机器检查的
完成门、反自述验证器（`trace.py` 1,197 行 + mutation score 0.95）、宪法锚点
（`constitution.toml` 13 条）——里有三处**造好了但没插电**：守卫文件存在、
`Test` 覆盖 100%、却没有任何 `src/` 调用方。按仓库自己的标准，这正是
「E 上 & S 降」的形状，应判负而非加分。

Tier-0 的判据是**每一条都能用一条红测证明它现在是坏的**，不需要新抽象、不需要新包。

## 范围

### A. CSDD 接线（4 条）

| ID | 锚点 | 现状 | 修法 |
|---|---|---|---|
| A1 Lock 6 死代码 | `src/taste_score/__main__.py:95` | `gate.score(agents, golden=…, mutants=…, verify=…)` 没传 `constitution=`，而 `gate.py:52-56` 的否决分支要求 `constitution is not None` → 分支不可达 | 补 `constitution=constitution` |
| A2 尺子自证 | `src/taste_score/__main__.py:125` | `pinned = constitution.digest()`：拿被检对象自己的 digest 当基准，同义反复，篡改后必然匹配 | pin 来自进程之外：环境变量 `AH_CONSTITUTION_PIN` > 仓库常量文件 `constitution.pin` |
| A3 改进环空转 | `src/taste_score/__main__.py:153` | `"probe": ""` 写死，`amendments.py:36-37` 要求 pid 为真 → `suggest_amendments` 恒返回 `[]` | 换成真实 probe id |
| A4 Lock 4 未武装 | `src/taste_score/gate.py:98` 的 `regress` | 参数存在，全 `src/` 无调用方传入 | `rank()` / `compete()` 透传，调用方可注入 |

**A2 的设计（external anchor）**：pin 必须不是被评分进程能顺手产出的。取
环境变量优先、仓库文件兜底；两者都没有则视为未 pin（`None`，行为同今天）。
配一条 meta-test 钉「仓库里的 pin 等于仓库里的宪法 digest」——否则 pin 悄悄
写错会让真跑每次全判负，或者被人用「重新生成 pin」抹平篡改。

**A4 的边界（明确不做）**：Tier-0 只做「把参数接到真实调用方」。**不**造一个仓库级
默认回归套件——`regress(name) -> list[str]` 的语义是「这个 agent 破了哪条红线」，
而 `compete()` 里的 robust/reckless/liar 是合成 agent，没有真实套件可跑。
强行默认化会造出假证据。仓库级默认属 Tier-1。

### B. 真 bug（5 条）

| ID | 锚点 | 现状 | 修法 |
|---|---|---|---|
| B1 sqlite 非原子 | `goal_persistence/store.py:156-172` | `transition()` / `apply_usage()` 走 `get()`（一条连接）再 `_persist()`（另一条连接），读-改-写跨连接 | 同一 `_connect()` 内读改写；顺手开 WAL + `busy_timeout` |
| B2 路径穿越 | `goal_loop/loop_runner.py:90` vs `:235-238` | 同一个 `thread_id`，写状态文件名时未消毒，写 hippocampus 轨迹时已消毒 | 抽一个消毒函数，`_persist_state` 与 `_load_state` 同时用 |
| B3 暂停原因丢失 | `goal_persistence/models.py:111-114` | `with_status(PAUSED, reason)` 落进 `else` 分支，`last_blocked_reason = None`，operator 拿不到原因 | 加 PAUSED 分支保留 reason |
| B4 聚合丢字段 | `goal_loop/orchestrator.py:68-74` | `MakerOutput` 不并 `modified_files` → `loop_runner.py:266` 的 `files_changed` 恒 +0 | 聚合各 executor 的 `modified_files` |
| B5 slots 上读 `__dict__` | `context_compaction/models.py:46-47` | `frozen=True, slots=True` 的 dataclass 没有 `__dict__`，`to_dict()` 抛 `AttributeError` | 改 `dataclasses.asdict` |

**B2 的关键约束**：`_persist_state`（`:86-91`）与 `_load_state`（`:93-98`）必须用
**同一个**消毒函数。只改写入侧会让恢复路径按原始 id 找不到文件，把「路径穿越」
换成「状态静默丢失」——更糟。

## 不在范围内

- 工具调用环（D9-G1 / D5-G1）、虚拟文件系统（D0-2）——Tier-1，另起规格。
- `.github` CI、mypy 8 处注解、P2 文档深水区。
- 删除死模块（`cost_control` ×4、`injection_guard`、`Orchestrator` 的降级）——
  先接线再决定去留，这条顺序是审计对「保不保 CSDD」的回答。
- 任何 parity 驱动的抽象（reducer / time-travel / ThreadPoolExecutor）。

## 验收

1. 每条 A / B 各带一条红测，先证明现状是坏的，再改到绿。
2. `python3 -m pytest -q` 全绿，`fail_under = 92` 与 per-package `default_floor = 70` 不退。
3. 端到端红测：篡改一份宪法副本，真跑 `compete(constitution=tampered, pin=真 digest)`，
   断言每个 agent 都被判 `constitution integrity violation (ruler tampered)`。
4. 不新增第三方依赖；`src/` 保持零第三方 import。
