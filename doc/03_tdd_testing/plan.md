# 目标 1 — harness 代码的 red-green + 覆盖率闸门

> 来源：抄 codex 的入门版（red-green + 单命令测试）+ deepseek 的闸门版（覆盖率门槛 +
> 「没覆盖的行是死代码」）。
> 对应 `doc/reference_harness/comparison.md` 的三问里的 **A**。

## 结论

**给这个 Python 仓库加两样东西：① codex 式 red-green 纪律（bug 修复必须带「先红后绿」
的回归测试），② deepseek 式覆盖率闸门（pytest-cov 对包模块设门槛，未覆盖的行视为待删
死代码）。用基准数字证明闸门有效，而不是「加了个配置」。**

## 现状锚点

- `pyproject.toml:15-17` 只有 `[tool.pytest.ini_options] testpaths=["tests"] pythonpath=["."]`，
  无 coverage 工具。
- `pyproject.toml:10-13` dev 依赖只有 `pytest>=8.0`。
- 已有 85 个测试（`tests/` 下 7 个文件），但**没有任何覆盖率和 red-green 纪律的约束**。
- `AGENTS.md` 只有 OpenWolf 一条，没有「怎么写测试」的规则。
- 包模块：`goal_persistence/`、`goal_loop/`、`context_compaction/`、`hippocampus/`、
  `tool_registry/`、`sandbox/`、`eval_harness/`、`observability/`、`safety/`、
  `cost_control/`（共 10 个）。

## 参考来源（抄什么）

| 模式 | 出处 |
|---|---|
| bug 修复先红后绿 | codex `contributing.md:40`（`fails before... passes afterwards`） |
| 单命令跑相关测试 | codex `contributing.md:57`（`just test -p <crate>`） |
| 覆盖率闸门 = 每文件 100% | deepseek `testing.md:10`（`per-file 100% on packages/*/*/src`） |
| 未覆盖行 = 待删死代码 | deepseek `testing.md:10`（`An uncovered line is often dead code`） |
| 证明测试能抓到回归 | deepseek `testing.md:34`（`introduce the regression, watch red, revert`） |
| 测试描述行为，不是正确性 | deepseek `AGENTS.md:122` |

## 方案

### 要建/改的文件

| 类型 | 文件 | 内容 |
|---|---|---|
| 改 | `pyproject.toml` | dev 依赖加 `pytest-cov>=5.0`；加 `[tool.coverage.run]`（`source` 指向 10 个包模块，`branch=true`）和 `[tool.coverage.report]`（`fail_under` + `show_missing`） |
| 新 | `scripts/check.sh` | 单命令：`python -m pytest --cov --cov-report=term-missing`，对应 `just test` |
| 改 | `AGENTS.md` | 追加「测试纪律」小节：red-green 规则 + 覆盖率闸门 + 未覆盖行=死代码 |
| 新 | `tests/test_coverage_gate.py` | 一个证明：断言覆盖率配置存在且 fail_under 生效（meta-test） |
| 新 | `doc/03_tdd_testing/benchmark.md` | 覆盖率基线数字 vs 目标 |

### 关键决策

1. **门槛定多少**：deepseek 是「每文件 100%」。Python 里等价做法是 `[tool.coverage.run]
   source` 指向包模块 + `[tool.coverage.report] fail_under = 100`。但本仓库已有 85 测试
   不一定覆盖到 100%，所以**第一步先跑出当前基线，把 `fail_under` 设成「当前值不减」的
   下限，再逐个模块爬向 100%**。不能让「达不到 100%」直接让 CI 红、逼着补一堆凑行数的
   测试——deepseek 的哲学是「没覆盖的行该删」，不是「该凑」。
2. **闸门是「必要不充分」**：覆盖率只证明行跑过，不证明行为对。文档里要写清这一条
   （deepseek `testing.md:10` 原话）。
3. **red-green 纪律写成规则，不写成代码**：`AGENTS.md` 加一条「修 bug 必须带一个先失败
   的回归测试」，并用一个真实例子钉住（见下面的验证）。

## 成功标准（做完才叫 done）

1. **red-green 可复现**：选一个现有的真实函数，写一个回归测试，先证明它失败（红），
   再证明修复后通过（绿）。把「红」和「绿」两段输出抄进 benchmark 文档。
2. **闸门能抓未覆盖行**：故意在一个包模块里加一行死代码 → `scripts/check.sh` 覆盖率
   报红 → 删掉 → 绿。这是 deepseek `testing.md:34` 的 `watch red` 证明。
3. **基准数字**：`benchmark.md` 记录「当前覆盖率 %（含缺失行清单）」作为基线，和
   `fail_under` 门槛的关系。
4. **全量测试仍绿**：`python -m pytest -q` 85 个原有测试 + 新测试全过。

## 自我批判（写完第一稿后改了什么）

- **砍掉「一步到位 100%」**：初稿想直接 `fail_under = 100`，但那样会逼着给未覆盖行凑
  测试，违背 deepseek 的「死代码该删，不是该测」。改成「先测基线、设不减下限、逐模块
  爬升」。
- **砍掉 Makefile/justfile 二选一**：本仓库是 Python 且没装 make/just，用一个
  `scripts/check.sh` 足够，不引入额外工具链。
- **明确「闸门≠行为正确」**：避免把覆盖率数字当质量分数，文档里写死这一条。

## 边界（子代理不要碰）

- 不碰 `goal_loop/`、`faux_provider/`、`goal_loop/world_verifier.py`（那是目标 2/3 的）。
- 不碰 `JOURNEY.md`、`.wolf/STATUS.md`、`README.md`（汇总由主代理做）。
- 只加 `pytest-cov` 一个依赖，不加其它。
