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
