# 目标 1 JOURNEY — harness 代码的 red-green + 覆盖率闸门

## 风险 / TODO

- **并发写入竞争**：执行过程中另两个目标（faux_provider、world_verifier）的代码并行走入
  工作区，中途一度出现 `tests/test_faux_provider.py` 因 `faux_provider/__init__.py` 未生成
  而 collection 报 `ModuleNotFoundError`，几分钟后对方补齐 `__init__.py` 自行恢复。本目标
  的所有数字以最终稳定态（110 passed / 92.69%）为准。
- **`scripts/check.sh` 在纯 Windows PowerShell 下无 `sh`**：需借 Git Bash 的
  `C:\Program Files\Git\bin\sh.exe` 才能跑 `#!/usr/bin/env sh` 脚本。闸门命令本身
  （`python3 -m pytest --cov --cov-report=term-missing`）在 PowerShell 下等价可跑，
  退出码一致。
- **TODO（后续目标）**：把 `fail_under` 从 92 逐模块爬向 100%，方式是**删死代码**，不是凑测试。

## 过程

| ME（用户/主代理给的指令） | YOU（我的实现与发现） |
|---|---|
| 读 plan.md、comparison.md、pyproject.toml、AGENTS.md、两个 tests 了解风格 | 确认现状：pyproject 无 coverage，dev 依赖只有 pytest，AGENTS.md 只有 OpenWolf 一条，tests 是 pytest 风格、函数式 + class 混用 |
| 先写失败测试 `tests/test_coverage_gate.py`，用 tomllib 读 pyproject 断言 dev 含 pytest-cov、`[tool.coverage.run]` 有 source/branch/omit、`[tool.coverage.report]` 有 fail_under(整数)/show_missing | 写成 3 个 test 函数，`ROOT = Path(__file__).resolve().parents[1]` 定位根目录；跑出 **3 failed（红）**：`assert False`（缺 pytest-cov）+ 两个 `KeyError: 'coverage'` |
| 改 pyproject：dev 加 `pytest-cov>=7.0`，加 `[tool.coverage.run]`（source=10 包、branch=true、omit tests/examples）和 `[tool.coverage.report]`（show_missing、fail_under） | 先不加 fail_under，跑 `--cov --cov-report=term-missing` 实测 **92.48%**（1291 stmts），再设 `fail_under = floor(92.48) = 92` |
| fail_under 设「当前覆盖率向下取整」的地板 | 设 92。**关键发现**：pytest-cov 7.1.0 比对 fail_under 前按 precision 四舍五入，默认 precision=0 会把 91.62% round 成 92，导致「打印 FAIL 但退出码 0」——闸门名存实亡。补 `precision = 2` 后闸门才真正按两位小数比对、能退出非 0 |
| 建 `scripts/check.sh`，一行命令 + shebang + set -e | 内容 `python3 -m pytest --cov --cov-report=term-missing "$@"`，用 Git Bash 的 sh 验证可跑通（exit 0） |
| 改根 AGENTS.md 追加「测试纪律」三规则（codex `contributing.md:40` + deepseek `testing.md:10/34`、`AGENTS.md:122`） | 三条：① bug 修复必须带先红后绿的回归测试；② 闸门是 check.sh、未覆盖行先删不先补；③ 覆盖率只证明行跑过不证明行为对 |
| 跑红转绿 | `tests/test_coverage_gate.py` **3 passed（绿）** |
| watch-red：临时加死代码 → 红 → 删 → 恢复 | 在 `observability/trace.py` 加 `_dead_code_for_watch_red_proof`（14 stmt）→ 覆盖率掉到 91.62%，`ERROR: Coverage failure`，退出码 1；删掉 → 恢复 92.69% 退出码 0 |
| 最终 `python3 -m pytest -q` 全绿 | **110 passed**（85 基线 + 我 3 + 并发目标 22） |
| 写 benchmark.md + journey.md | benchmark 记覆盖率、fail_under 依据、watch-red 三段；journey 记风险与过程 |

## 关键决策（偏离 plan 之处）

1. **`precision = 2` 是 plan 之外新增的必要配置**。不加它，config 里的 `fail_under` 只警告
   不失败（pytest-cov 的 `should_fail_under` 先 round 到整百分比再比），闸门会形同虚设。
   这是为了满足 seam「check.sh 退出行为」真正生效，不算超出边界（仍是 coverage 配置，不是新依赖）。
2. **fail_under = 92 而非 90**。plan/user 指令写「向下取整」（floor），实测 92.48%，floor=92。
   （用户举例「87→85」是「留点余量」的示意；但这里「刚过地板」的语义和 floor(92.48)=92
   一致，且 watch-red 能干净触发。）已在 benchmark.md 写清该数字与 100% 的 8 点差距。
3. 其余严格按 plan，未碰 `goal_loop/`、`faux_provider/`，未碰 JOURNEY.md / .wolf/STATUS.md /
   README，只加了 `pytest-cov` 一个依赖。
