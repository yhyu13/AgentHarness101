# 目标循环(Goal Loop):从状态机到自跑循环

## 一句话

`goal_persistence` 让一个目标「跨 turn / 跨会话 / 跨重启都不丢」;`goal_loop` 让它
「自己跑起来」:人写一份 `goal.md`,机器按「目标 → maker → 独立 checker → 机器验证 →
状态 → 再循环」一直跑到验收标准全部被证明,或触发停止条件。

## 这不是什么

- 不是把 SQLite 状态机重写一遍。`goal_loop` 叠在 `goal_persistence.GoalRuntime` 之上,
  持久化、空闲自启动、anti-drift、预算、blocked/complete 审计都仍由内核负责。
- 不是 maker 自报「做完了」就停。maker 的自我验证只写进状态,从来不算完成证据。
- 不是定时器(`/loop`)或事件驱动。这里只有「一个目标,跑到完成为止」。

## 三个组成

`/goal` 的本质是三个东西,缺一不可:

1. **目标 + 验收标准**(goal + acceptance):可机器验证的「什么算做完」。
2. **独立判断完成**(independent checker):写代码的人不能给自己批作业。
3. **停止条件**(stop conditions):除了验收全过,还要有最大回合、预算、无进展上限。

## 和 `goal_persistence` 的对应

| goal.md 里的字段 | 落到哪 |
|---|---|
| 目标 | `Goal.objective`(SQLite 一行) |
| 验收标准 | `GoalSpec.acceptance_criteria`(每个可带 `@verify <command>`) |
| 可以改 / 不能改 | `Scope`(写进 steering,但不做文件访问控制) |
| 验证方式 | `CommandVerifier`(argv 列表,`shell=False`) |
| 最大回合 | `StopCondition(kind="max_rounds")` |
| 连续无进展 | `goal_persistence` 的 `mark_blocked` 三次阈值 |
| 预算 | `goal_persistence` 的 `budget_tokens` / `budget_wall_ms` |

## generator/evaluator 分离

`Maker` 和 `Checker` 是两个协议。`GoalLoopRunner` 只相信 `CheckerOutput` 的判定,只
在「每个验收命令 exit 0 + checker 非 FAIL」时才 `mark_complete`。这就是 L13 反复强调的:
**干活的 session 不能自己判停。**

## 为什么这个补上了缺口

本仓原来的 `goal_persistence` 是 Codex goal 功能的「内核」:有状态机、有 idle/resume、
有 anti-drift 字符串。但学生看不到「写 goal.md → 跑循环 → 看停止」的入口,也没有
「写代码的人不能自批作业」这一层。`goal_loop` 补的是这层契约教学,不是重写内核。
