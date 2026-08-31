# 目标 7 — 自我改进闭环（越跑越好 = 记忆闭环）

> 来源：抄 §5 self-learning / self-improving 的三条横切规律——claude-mem 的
> `capture→compress→reinject`、self-rag 的 `retrieve→generate→critique`、Acontext 的
> 「skills as memory」。对应 `doc/reference_harness/harness_skills.md` 的**目标 1**。

## 结论

**给 `goal_loop` 加一个 `SelfImprover`：一次 run 结束自动把结果提炼成一条持久教训
（成功→`repeat`，失败→`avoid`），下一次 run 开始时把相关教训注入 steering。用它把
`hippocampus` 从「被动记忆」升级成「越跑越好」的闭环——本仓库之前只会记，不会自动
从结果里长记性、也不会在下一次自动调用这些记性。**

## 现状锚点

- `hippocampus/memory.py` 已有 `record_step` / `learn` / `unlearn` / `correct` /
  `replay` / `retrospective`，但**都是被动的**：必须有人显式调用 `learn` 才会长记性，
  且没有任何地方会「读回这些记性」去影响下一次 run。
- `goal_loop/loop_runner.py` 的 `_finalize`（`loop_runner.py` 末尾）是每个 run 的唯一
  收尾点，`status` + `summary` 都在这里聚合——是提炼教训的天然挂点。
- `GoalLoopRunner.run` 里 `cont.steering_prompt`（`goal_persistence/runtime.py` 的
  anti-drift 模板）是注入上下文的天然挂点——现在只注入 objective + 审计契约，不注入
  历史教训。
- `Hippocampus` 只暴露 `retrospective()`（仅 correct 事实）和 `get(key)`，**没有**
  「列出全部事实」的公开方法，自我改进要读自己的失败教训就需要它。

## 参考来源（抄什么）

| 模式 | 出处 |
|---|---|
| `capture everything → compress → inject relevant context` | claude-mem（§5，92k⭐） |
| 自我反思 `retrieve → generate → critique` | self-rag（§5） |
| skills 本身作为记忆层，越用越厚 | Acontext（§5） |
| 「只 mock LLM 边界」——教训提炼是确定性纯函数，不发 LLM 调用 | §6 obra/superpowers + pi |

## 方案

### 要建/改的文件

| 类型 | 文件 | 内容 |
|---|---|---|
| 新 | `goal_loop/self_improver.py` | `SelfImprover`：`distill`（结果→教训）、`relevant_lessons`（词重叠检索）、`steering_context`（渲染成注入块） |
| 改 | `hippocampus/memory.py` | 加 `facts()` 公开方法（列全部事实，含 `correct=False` 的失败教训） |
| 改 | `goal_loop/loop_runner.py` | 加可选 `self_improver` 参数；maker 调用前注入教训；`_finalize` 提炼教训 |
| 改 | `goal_loop/__init__.py` | 导出 `SelfImprover` |
| 新 | `tests/test_self_improver.py` | 单元 + 循环集成测试（13 条） |
| 新 | `doc/07_self_improve/{plan,journey,benchmark}.md` | 本目标文档 |

### 关键决策

1. **`SelfImprover` 是确定性纯函数，不发 LLM 调用**：教训提炼（`distill`）和检索
   （`relevant_lessons`）都只操作 hippocampus 索引，token 重叠是确定的。守住「只 mock
   LLM 边界」——这里根本没有 LLM 边界要 mock。
2. **失败教训用 `correct=False` 承载**：hippocampus 的 `correct` 语义本来就是「False =
   该停止重复的事实」。所以成功→`correct=True`（继续这么做）、失败→`correct=False`
   （别再这么做），不用发明新字段。
3. **接线 fail-open 且向后兼容**：`self_improver` 是可选参数，缺省 `None` 时行为与现状
   完全一致。提炼失败（理论上不抛）不阻断 `_finalize` 收尾。
4. **检索用「词重叠」而非向量/语义**：内容词（`len>=3`）取交集，确定性、零依赖、够用。
   空 objective（无内容词）匹配空集，不是「匹配所有」——这是 fail-closed。
5. **不重写 loop 状态机**：只在 `_finalize` 加一句提炼、在 maker 调用前加一句注入，
   不动 round/budget/blocked 逻辑（已在测试里钉死）。

## 成功标准（做完才叫 done）

1. **red-green**：先写 `test_self_improver.py`，跑出 `ModuleNotFoundError`（红），再实现
   转绿。
2. **闭环成立**：一条集成测试证明「run A blocked → 留下 avoid 教训 → run B 同 objective
   的 steering 里出现 `Prior lessons` + 该教训」。
3. **失败教训可读回**：`Hippocampus.facts()` 能列出 `correct=False` 的事实。
4. **向后兼容**：`test_without_self_improver_is_backward_compatible` 证明不带
   `self_improver` 时 complete 行为不变。
5. **全量测试仍绿**：`python3 -m pytest -q` 不破坏现有 126 测试。

## 自我批判（写完第一稿后改了什么）

- **砍掉「新建 `self_improve/` 顶层包」**：初稿想把自我改进做成独立顶层包，但它要
  `import goal_loop.models`（FinalResult）又会被 `goal_loop` import（runner 挂点），
  会造 `hippocampus → goal_loop` 的环。改成放 `goal_loop/self_improver.py`（与
  `world_verifier.py` 同级），只 `import hippocampus`，无环。
- **砍掉「教训存独立表/新字段」**：hippocampus 的 `MemoryFact` 已有 `correct` /
  `evidence` / `source`，够承载「repeat/avoid + 出处 + 证据」，另起 schema 是过度设计。
- **砍掉「向量检索」**：YAGNI——词重叠对「同 objective 的教训召回」已经足够，向量库是
  给海量记忆准备的，本仓库规模用不上。
- **`distill` 把 objective 折进 value**：检索靠 token 重叠，必须让 value 里含有能跟新
  objective 对齐的词，所以把 objective 写进 lesson 文本，而不是只存 summary。

## 边界

- 不碰 `pyproject.toml` / `scripts/check.sh`（覆盖率闸门已覆盖 `goal_loop`，新增模块
  自动进闸门，无需改 source 列表）。
- 不碰 `scheduler.py` / `orchestrator.py`（harness_skills 目标 2 / 目标 3，本批不做）。
- 不碰 `JOURNEY.md` / `.wolf/STATUS.md` / `README.md`（收口阶段统一更新）。
