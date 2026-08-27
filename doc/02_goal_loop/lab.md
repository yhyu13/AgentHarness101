# 实验:把 `goal.md` 变成自跑循环

## 目标

亲手写一份 `goal.md`,让 `GoalLoopRunner` 按验收标准跑完,而不是直接调 Python API。
然后体验「maker 自夸不算、独立 checker 才算」的差别。

## 前置

- 已安装依赖:`py -3 -m pytest` 能跑。
- 本仓根目录有 `goal_loop/` 和 `goal_persistence/`。

## 步骤 1:写 goal.md

复制 `goal_loop/templates/goal.md` 到任意位置,改成一个真实可跑的目标,例如:

```markdown
## Goal

确认 goal_loop 包能导入且测试通过。

## Acceptance Criteria

- [ ] 包能导入 @verify python -c "import goal_loop"
- [ ] 测试通过 @verify python -m pytest tests/test_goal_loop.py -q

## Scope

### Fair game

- goal_loop/
- tests/

### Hands off

- goal_persistence/

## Stop Conditions

- Max turns reached: 5

## How to Work

1. 读代码结构。
2. 实现。
3. 每步验证。
```

## 步骤 2:解析并跑(先失败一轮再通过)

这里不用 `EchoMaker` + `StaticChecker(PASS)` 的 happy path,而是用
`examples/goal_loop_demo.py` 里那个会失败的 maker / 会 assert 内容的 checker:

```python
from pathlib import Path
import sys
sys.path.insert(0, ".")

from goal_loop import GoalLoopRunner, GoalSpec
from goal_persistence import GoalRuntime, GoalStore
from examples.goal_loop_demo import ArtifactChecker, ArtifactMaker

spec = GoalSpec.from_markdown("goal.md")  # 缺目标/验收/停止会直接抛 ValueError
runtime = GoalRuntime(GoalStore("lab.db"))
artifact = Path("lab-artifact.txt")

runner = GoalLoopRunner(
    spec,
    runtime,
    ArtifactMaker(artifact),    # 第一轮不写产物,第二轮才写
    ArtifactChecker(artifact),  # 独立子进程 assert 内容,不轻信 maker 自报
)
status = runner.run("lab-thread")
print(status.value)  # 期望: complete(第一轮失败,第二轮才通过)
```

## 步骤 3:制造「自夸不算」的对照

把 checker 换成 `StaticChecker(Verdict.FAIL)`,只留一个**没有** `@verify` 的验收项:

```python
from goal_loop import GoalSpec, AcceptanceCriterion, StopCondition
from goal_loop.roles import EchoMaker, StaticChecker, Verdict

spec = GoalSpec(
    objective="只靠 maker 自报完成",
    acceptance_criteria=[AcceptanceCriterion("c1", "checker 决定")],
    stop_conditions=[StopCondition(kind="max_rounds", value=1)],
)
runner = GoalLoopRunner(spec, runtime, EchoMaker("我全做完了"), StaticChecker(Verdict.FAIL))
status = runner.run("lab-thread-2")
assert status.value != "complete"  # maker 自夸不算
```

## 步骤 4:记录并回答

1. 你的 goal.md 里哪条验收是机器可验证的?哪条只能靠 checker?
2. 如果 checker 一直 PASS 但验收命令一直失败,循环最终会怎样?(应被 `blocked`,而不是空转)
3. maker 和 checker 如果共用同一个模型,还算是 generator/evaluator 分离吗?

## 验收

- [ ] `goal.md` 被 `from_markdown` 成功解析,缺段会被拒。
- [ ] 合法 goal.md 能跑出 `complete`,且 `mark_complete` 的证据字符串里含 verdict 和验收 id。
- [ ] 「maker 自夸 + checker FAIL」跑不出 `complete`。
