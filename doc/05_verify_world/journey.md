# 目标 3 Journey — 独立世界校验器（verify the world, not self-report）

> 两列表：ME（人/需求） vs YOU（AI 实现）。顶部先放风险和 TODO。

## 风险与 TODO

- **[已解决] byte-identical 测试在 Windows 的 CRLF 坑**：`Path.write_text` 走文本模式会做
  换行翻译，`"hello world\n"` 落盘变成 `"hello world\r\n"`，导致 byte-identical 断言
  误红。改成 `write_bytes(b"hello world\n")` 直接写原始字节，语义上才是「byte-identical」。
- **[遗留] 崩溃 maker 不在 loop 内兜底**：`GoalLoopRunner.run` 不捕获 maker 异常，崩溃
  maker 会直接抛 `RuntimeError`、goal 停在 `active`。这是**现有行为**，本目标明确不碰
  状态机，故未改；只是不会误判 complete。若要优雅降级（崩溃→blocked），另开目标。
- **[注意] `WorldVerifier.verify_all()` 空 checks 返回 ok=True**：语义是「没配检查就
  不拦」，不是「没配检查就 fail-closed」。若未来想强制至少一条世界检查，要在构造器层
  断言，别在这里改。
- **[未做] 没把 WorldVerifier 导出到 `goal_loop/__init__.py`**：边界只许新增
  `world_verifier.py` + 改 `loop_runner.py`，故测试直接 `from goal_loop.world_verifier import ...`。

## ME / YOU

| ME（需求 / 决策） | YOU（实现 / 发现） |
|---|---|
| 目标：给 goal_loop 加独立世界校验器，重读磁盘产物、断言内容，不信 maker/checker 自报 | 读了 `doc/05_verify_world/plan.md`、`comparison.md`、`verifier.py`、`loop_runner.py`、`models.py`、`test_adversarial_boundaries.py`，确认洞在 `_verify_criterion` 只查 exit code |
| 已约定 seam：`WorldVerifier.verify(...)` 公开 API（observed vs expected）；`GoalLoopRunner` 加可选 `world_verifier` 参数，默认 None 向后兼容，fail-closed | 新建 `goal_loop/world_verifier.py`：`WorldCheck`（path + expected/contains 二选一）、`WorldVerificationResult`（observed/expected/what/why/fix）、`WorldVerifier.verify` / `verify_all` |
| 要求 red→green，先写失败测试 | 先写 `tests/test_world_verifier.py`，跑出 `ModuleNotFoundError: goal_loop.world_verifier`（红），再实现转绿 |
| 对抗：假 exit 0 + 说谎 checker + 错产物 → 不得 complete | `test_wrong_artifact_with_fake_exit_0_does_not_complete`：命令 `py -c "pass"`（Windows 版 `echo 0`）+ 恒 PASS checker + 写错产物 → 断言 `BLOCKED` |
| 对抗：产物缺失 + exit 0 → 不得 complete | `test_missing_artifact_with_fake_exit_0_does_not_complete` → `BLOCKED` |
| 正例：产物正确 + exit 0 → complete | `test_correct_artifact_with_exit_0_completes` → `COMPLETE` |
| 错误信息带「怎么改」（what/why/fix） | `test_failure_message_includes_fix_guidance`：断言 `what`/`why`/`fix` 非空且 `fix` 含产物路径和期望内容 |
| 边界：`goal_loop/` 只许新增 `world_verifier.py` + 最小改 `loop_runner.py`；不碰 models/roles/verifier/registered_roles；不碰 __init__ | 只动了 loop_runner 三处：加 import、`__init__` 末尾加 `world_verifier` 参数、完成判定加 `world_ok` 一条；`__init__.py` 未动，测试直接 import 子模块 |
| 不破坏 Era 23 与 test_goal_loop | 全量 `python3 -m pytest -q` → 109 passed（0 failed），旧测试无一破坏 |
| 基准：对抗 maker 集误完成率 = 0/N | 跑 5 场景（说谎/被拦/崩溃/假 exit-0/产物错），`0/5`，各 status 见 `benchmark.md` |

## 关键决策与偏离

1. **`WorldVerifier` 是独立证据，不是 checker 替身**：只读磁盘 bytes，不接任何进程内
   自报。完成判定里它是与 machine command / checker verdict **并列**的第三个门，谁不
   过都不 complete。
2. **完成判定只加 `world_ok` 一个条件，不碰 blocked 状态机**：世界校验失败那轮不
   complete，下一轮因无新 satisfied criterion 自动走 no-progress → 三振 → `blocked`。
   这正是 fail-closed 想要的：不 complete，且由既有 blocked 审计兜底，不需要我额外
   `mark_blocked`。
3. **`expected` 用 `str` 而非 `bytes`**：byte-identical 语义下按 utf-8 编码比对，对文本
   产物等价于逐字节比对；省掉 `bytes` 分支的复杂度。若未来要校验二进制产物再扩。
4. **`verify_all` 返回单个 result（首个失败）而非列表**：loop 只需要一个 `ok` 布尔 +
   一条修复指引，列表是过度设计。
