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
