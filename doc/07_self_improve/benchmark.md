# 目标 7 — 自我改进闭环基准（越跑越好 = 记忆闭环）

> 验证 `goal_loop/self_improver.py` 的 `SelfImprover` 是否真的把「一次 run 的结果」变成
> 「下一次 run 会调用的教训」。核心断言：**run A 失败 → 留下 avoid 教训 → run B 同
> objective 的 steering 里出现该教训**；retrieval 是确定性的词重叠，不是撞运气。

## 方法

把 `SelfImprover` 接到同一个 `hippocampus`（临时目录）上，跑两组对比：

- **对照组（无 self_improver）**：一个 completing run，断言 `COMPLETE`，且 hippocampus
  里**没有** `self-improve::*` 事实——证明缺省接线向后兼容、不产生副作用。
- **实验组（有 self_improver）**：先跑一个 blocking run（`py -c "exit(1)"` + 恒 PASS
  checker → 三振 `BLOCKED`），断言留下一条 `[avoid]` 教训；再跑一个同 objective 的
  recording maker，断言它收到的 steering 里含 `Prior lessons` 和 `[avoid]`。

## 结果

```
无 self_improver:
  completing run          -> COMPLETE, hippocampus 无 self-improve 事实

有 self_improver:
  blocking run (t0)       -> BLOCKED, distill [avoid] 教训 (correct=False)
  second run (t2) steering -> 含 "Prior lessons" + "[avoid] write a fibonacci function"
```

## 结论

**闭环成立**：

- 失败 run 在 `_finalize` 处确定性提炼出 `[avoid]` 教训（`correct=False`），persist 进
  hippocampus 索引（`self-improve::t0`）。
- 下一次同 objective 的 run，在 maker 调用前注入 `## Prior lessons on similar goals` +
  该 `[avoid]` 教训，maker 收到的是「anti-drift 模板 + 历史教训」拼起来的 steering。
- 不带 `self_improver` 时行为与现状完全一致（complete 正常、无副作用），向后兼容。

确定性来自「词重叠检索」：objective `write a fibonacci function` 与教训文本里的
`write`/`fibonacci`/`function` 取交集命中；`build a web server with sockets` 与它零
重叠 → 空召回（`test_relevant_lessons_ignores_unrelated_objective` 钉住）。空
objective（`""` / `"a b"`）同样空召回，不会退化成「匹配所有」。
