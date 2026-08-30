# 目标 1 benchmark — 覆盖率闸门基线

> 记录时间：2026-08-29（目标 1 完成后）。
> 数字来源：`python3 -m pytest --cov --cov-report=term-missing -q` 实测，非估算。

## 当前覆盖率

| 指标 | 值 |
|---|---|
| TOTAL | **92.69%** |
| Statements | 1350（Miss 66） |
| Branch | 264（BrPart 50） |
| 平台 | win32, Python 3.13.13 |
| 测试数 | 110 passed |

> 注：实测分两个时点。设门槛时的快照是 **92.48%**（1291 stmts），
> 到最终验收时另两个目标（faux_provider / world_verifier）的代码并行走入，
> `goal_loop/world_verifier.py` 让总量涨到 1350 stmts、覆盖率升到 **92.69%**。
> 两个时点都 ≥ 92，`fail_under = 92` 始终成立。

## 缺失行清单（term-missing，贴前 20 行）

```
context_compaction\compactor.py       45      1     10      1  96.36%   35
context_compaction\models.py          21      1      0      0  95.24%   45
context_compaction\summarizer.py      27      1      6      1  93.94%   38
cost_control\__init__.py               2      0      0      0 100.00%
cost_control\cost.py                  39      2      6      1  93.33%   59-60
eval_harness\__init__.py               3      0      0      0 100.00%
eval_harness\judge.py                 18      0      2      0 100.00%
eval_harness\models.py                33      1      0      0  96.97%   55
goal_loop\__init__.py                  6      0      0      0 100.00%
goal_loop\loop_runner.py             145      6     38      5  93.99%   74, 84, 159, 171, 183-187
goal_loop\models.py                  262     11     72     13  92.81%   132, 309, 334->336, 393, 402, 427, 437, 471, 480->468, 485, 487, 490, 493, 504->502
goal_loop\registered_roles.py         27      2      4      1  90.32%   87-89
goal_loop\roles.py                    16      0      0      0 100.00%
goal_loop\verifier.py                 20      2      0      0  90.00%   52-53
goal_loop\world_verifier.py           56      0     12      0 100.00%
goal_persistence\__init__.py           5      0      0      0 100.00%
goal_persistence\accounting.py        26      1      4      2  90.00%   24->exit, 36->38, 47
goal_persistence\models.py            75      6     14      1  89.89%   25, 91-94, 132
goal_persistence\runtime.py          100      9     32     10  85.61%   88, 91, 93, 106, 115, 123, 156->155, 180, 192, 216
goal_persistence\store.py             72      7      6      3  87.18%   146, 154, 163, 168-173
```

（后略；完整清单跑 `scripts/check.sh` 可见。）

## `fail_under` 设多少、为什么

- 设 **`fail_under = 92`**（`[tool.coverage.report]`）。
- 依据：设门槛时实测 **92.48%**，`向下取整 = floor(92.48) = 92`。即「当前值不减的下限」
  （plan.md 决策 1：先测基线、设不减下限、再逐模块爬向 100%）。
- 与 100% 的关系：**还差 8 个点**。这 8 个点里，绝大多数是「未覆盖行」，按 deepseek 哲学
  （`testing.md:10`「An uncovered line is often dead code」），它们的归途是**删掉死代码**，
  不是凑测试。`fail_under` 不是质量分数，只是「别让覆盖率倒退」的地板。
- 为什么必须加 `precision = 2`：pytest-cov 7.1.0 在比对 `fail_under` 时先按 `precision`
  四舍五入（默认 0，即整百分比）。默认精度下 91.62% 会被 round 成 92，`92 < 92` 为假，
  **闸门不会真的报红**（只打印 `FAIL ... not reached`，退出码仍是 0）。设 `precision = 2`
  后，比对用两位小数：91.62% < 92.00 → 退出非 0；92.69% ≥ 92.00 → 通过。这是让
  「check.sh 退出行为」这个 seam 真正成为闸门的必要配置，不算偏离 plan。

## watch-red 三段证据（deepseek `testing.md:34`：introduce the regression, watch red, revert）

往 `observability/trace.py` 末尾临时加一段死函数 `_dead_code_for_watch_red_proof`
（约 14 个 statement，永不被调用），验证闸门能抓到未覆盖行，然后删掉。

### ① 加之前（绿）

```
TOTAL                               1350     66    264     50  92.69%
Required test coverage of 92.0% reached. Total coverage: 92.69%
110 passed
（退出码 0）
```

### ② 加了死代码之后（红）

```
ERROR: Coverage failure: total of 91.62 is less than fail-under=92.00
observability\trace.py                50     12     14      1  67.19%   50, 66-77
TOTAL                               1362     77    272     50  91.62%
FAIL Required test coverage of 92.0% not reached. Total coverage: 91.62%
（退出码 1）
```

`observability/trace.py` 从 38 stmt/1 miss 变成 50 stmt/12 miss，死函数的
66-77 行全部被 term-missing 标出，覆盖率掉到 91.62%，闸门退出非 0。

### ③ 删掉死代码恢复（绿）

```
TOTAL                               1350     66    264     50  92.69%
Required test coverage of 92.0% reached. Total coverage: 92.69%
110 passed
（退出码 0）
```

三段结论：**闸门不是摆设**——加一行未覆盖代码就红、删掉就绿。

## 结论

`fail_under = 92` 是诚实的地板：它锁住当前 92.69% 不退步，把「爬向 100%」留给
后续逐个模块删死代码。闸门「必要不充分」：它只证明行跑过，不证明行为对（见
`AGENTS.md` 测试纪律第三条）。
