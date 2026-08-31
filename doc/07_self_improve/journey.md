# 目标 7 Journey — 自我改进闭环（越跑越好 = 记忆闭环）

> 两列表：ME（人/需求） vs YOU（AI 实现）。顶部先放风险和 TODO。

## 风险与 TODO

- **[注意] `distill` 在每次 `_finalize` 都写教训，同 thread 多次收尾会覆盖同一条 key**
  （`self-improve::{thread_id}`）。对 `run_until_terminal` 的「stopped_max_rounds →
  后续 complete」这种中间态，先写 `[avoid]` 后被最终的 `[repeat]` 覆盖——last-write-wins，
  语义正确（最终结果才算数）。若未来要保留中间态，另加 append-only 轨迹。
- **[设计取舍] 检索是「词重叠」，不是语义相似**：换一种措辞（如 `fib` vs `fibonacci`）
  就召回不到。对「同 objective 跨 session 召回」够用；真需要跨措辞召回再升级 embedding，
  现在 YAGNI。
- **[注意] `facts()` 暴露了 `correct=False` 的事实**：这是自我改进需要的（读自己的失败），
  但对其他调用方意味着「能读到不该重复的事」。目前唯一调用方是 `SelfImprover`，可控。

## ME / YOU

| ME（需求 / 决策） | YOU（实现 / 发现） |
|---|---|
| 目标：给 goal_loop 加自我改进闭环，一次 run 的结果自动变成下次 run 会调用的教训 | 读了 `harness_skills.md`、`hippocampus/memory.py`、`loop_runner.py`、`runtime.py`，确认 hippocampus 是被动记忆、无闭环、`Hippocampus` 缺「列全部事实」方法 |
| 来源：§5 三条规律（claude-mem 的 capture→compress→reinject、self-rag 的 self-reflection、Acontext 的 skills-as-memory） | 提炼成 `SelfImprover` 三方法：`distill` / `relevant_lessons` / `steering_context` |
| 约定 seam：`SelfImprover(hippocampus)`，确定性纯函数，不发 LLM；`GoalLoopRunner` 加可选 `self_improver`，缺省 None 向后兼容 | 新建 `goal_loop/self_improver.py`，放 goal_loop 内（避免 `hippocampus → goal_loop` 环），只 import hippocampus |
| 要求 red→green，先写失败测试 | 先写 `tests/test_self_improver.py`，跑出 `ModuleNotFoundError: goal_loop.self_improver`（红），再实现转绿 |
| 失败教训用 `correct=False` 承载（hippocampus 已有该语义），不发明新字段 | `distill` 里 `repeatable = status == "complete"`，`correct=repeatable`；value 折进 objective 供检索对齐 |
| 需要「列全部事实」方法读失败教训 | 给 `Hippocampus` 加 `facts()`（委托 `store.list_facts()`），并加测试 `test_facts_lists_correct_and_incorrect` |
| 闭环成立的标准：run A blocked → avoid 教训 → run B 同 objective steering 含该教训 | `test_second_run_injects_prior_lesson_into_steering`：t0 阻塞跑 → t2 recording maker 断言 steering 含 `Prior lessons` + `[avoid]` |
| 向后兼容：不带 self_improver 行为不变 | `test_without_self_improver_is_backward_compatible` → `COMPLETE` |
| 空 objective 不匹配所有（fail-closed） | `test_relevant_lessons_empty_objective_matches_nothing`：`""` 和 `"a b"` 都空召回 |
| 不破坏现有 126 测试 | 全量 `python3 -m pytest -q` → 139 passed；`self_improver.py` 覆盖率 100%，总量 93.33% ≥ 92 |

## 关键决策与偏离

1. **放 `goal_loop/self_improver.py` 而非顶层 `self_improve/` 包**：顶层包会 `import
   goal_loop.models`（读 FinalResult）又会被 `goal_loop` import（runner 挂点），造环；
   放 goal_loop 内、只 import hippocampus，无环，和 `world_verifier.py` 同级对称。
2. **教训用 `MemoryFact` 既有字段，不加新表**：`correct`（repeat/avoid）、`evidence`
   （summary）、`source`（`"self-improve"`）已够；`key` 用 `self-improve::{thread_id}`
   前缀在检索时过滤，避免和普通 fact 混。
3. **接线是「加一句」不是「改状态机」**：`_finalize` 末尾加一句 `distill`、maker 调用
   前加一句 `steering_context` 拼进 steering。round/budget/blocked 全部没动。
4. **fail-open 而非 fail-closed**：`self_improver` 缺省 None（不启用），启用后若提炼抛
   异常也只影响这一句、不阻断收尾——因为「长记性失败」不该比「完成目标」更严重。
