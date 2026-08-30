# 目标 3 — 让 agent 自己证明工作（verify the world, not self-report）

> 来源：抄 deepseek 的 `verify the world, not the self-report` + learn-harness 的验证子
> 系统。对应 `doc/reference_harness/comparison.md` 三问里的 **C**。

## 结论

**给 `goal_loop` 加一个独立的世界校验器 `WorldVerifier`：机器验收时重读产物文件、断言
内容（byte-identical / 关键词命中），而不是只信 maker/checker 的自报。用它证明「说谎
maker + 空转 checker + 假 exit 0」这条链无法把 goal 判成 complete。**

## 现状锚点

- `goal_loop/verifier.py:14-60` 的 `CommandVerifier` 只跑 `@verify` 命令、查 exit code
  （argv + shell=False），**不检查产物内容**——一个 `echo 0` 的假命令也能过。
- Era 23（`JOURNEY.md:192-196`）已补对抗测试：`test_lying_checker_with_failing_commands_blocks_not_completes`
  证明了「失败命令 + 说谎 checker」不 complete。但那条测的是「命令 exit 非 0」这条链，
  **没测「命令 exit 0 但产物是错的」这条链**——这正是 deepseek 的 `verify the world` 要
  堵的洞。
- `goal_loop/loop_runner.py` 的完成判定在 `GoalLoopRunner.run`（`:32-310`），当前完成靠
  「每 criterion 机器验证 + checker 非 FAIL」。

## 参考来源（抄什么）

| 模式 | 出处 |
|---|---|
| 重跑命令/重读文件，不探 agent 自报 | deepseek `testing.md:27-29`（`verify the world, not the self-report`） |
| 断言产物 byte-identical | deepseek `testing.md:29`（`Assert untouched files are byte-identical`） |
| 只有通过的测试算证据 | learn-harness `README.md:189`（`Only a passing test suite counts as evidence`） |
| e2e 才算真验证 | learn-harness `lecture-10:10`（`Only end-to-end testing can prove...`） |
| 错误信息带「怎么改」 | learn-harness `lecture-10:58`（agent-oriented error messages） |
| review 反馈提升为检查 | learn-harness `lecture-10:113-115`（review feedback promotion） |

## 方案

### 要建/改的文件

| 类型 | 文件 | 内容 |
|---|---|---|
| 新 | `goal_loop/world_verifier.py` | `WorldVerifier`：给定产物路径 + 期望内容断言（byte-identical / 关键词），重读文件独立裁决；返回带 `reported` vs `observed` 的 `VerificationResult` |
| 改 | `goal_loop/verifier.py` 或 `loop_runner.py` | 在完成判定里接入 `WorldVerifier`（或作为额外 evidence 通道），让「exit 0 但产物错」不能 complete |
| 新 | `tests/test_world_verifier.py` | 对抗测试：说谎 maker + 假 exit 0 + 错产物 → 不 complete |
| 新 | `doc/05_verify_world/benchmark.md` | 对抗 maker 的误完成率 = 0 的基准 |

### 关键决策

1. **`WorldVerifier` 是独立裁决，不是 maker/checker 的替身**：它只读磁盘上的产物，不接
   受任何进程内传进来的「自报」——deepseek `testing.md:27-29` 说「e2e 断言重读文件，
   关键字探针会让作弊 agent 通过」。
2. **完成判定接线要 fail-closed**：`WorldVerifier` 读到产物缺失/内容不匹配时，返回非
   完成信号，即使 checker 说 PASS。这条要写成测试（说谎 checker 不能覆盖世界校验）。
3. **错误信息带「怎么改」**：校验失败信息写「what / why / fix」三段
   （learn-harness `lecture-10:103-111`），让下游 agent 能自纠错。
4. **不重写 loop 状态机**：只在完成判定的「证据」这一环加世界校验，不动 round/budget/
   blocked 逻辑（那是已在测试里钉住的）。

## 成功标准（做完才叫 done）

1. **red-green**：先写 `test_world_verifier.py` 里「错产物 + 假 exit 0 不能 complete」的
   断言，证明它当前失败（红），再接线到绿。
2. **误完成率基准**：一组对抗 maker（说谎 maker、被拦 maker、崩溃 maker、假 exit 0 maker）
   跑 loop，误完成率 = 0（全部不 complete）。
3. **byte-identical 断言**：一条测试证明 `WorldVerifier` 对未改动的文件判定 byte-identical。
4. **全量测试仍绿**：`python -m pytest -q` 不破坏现有 85 测试（含 Era 23 的对抗测试）。

## 自我批判（写完第一稿后改了什么）

- **砍掉「重写 loop_runner 完成判定」**：初稿想直接在 `GoalLoopRunner.run` 里插一大段，
  但那样动到已在测试里钉死的状态机。改成「新增独立 `WorldVerifier` + 最小接线」，把
  风险面压到证据这一环。
- **砍掉「WorldVerifier 接 checker 内部」**：checker 是外部 callable（可能是 LLM），不该
  让它依赖我们的世界校验器。世界校验是**机器侧独立证据**，和 checker 的裁决并列，谁
  说 FAIL 都不能 complete。
- **明确和 Era 23 的边界**：Era 23 测的是「命令 exit 非 0」，本目标测的是「命令 exit 0
  但产物错」——两个不同的洞，不重复。

## 边界（子代理不要碰）

- 不碰 `pyproject.toml`、`AGENTS.md`、`scripts/check.sh`（目标 1）。
- 不碰 `faux_provider/`（目标 2）。
- 不碰 `JOURNEY.md`、`.wolf/STATUS.md`、`README.md`。
