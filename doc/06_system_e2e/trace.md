# 全系统 E2E —— 每轮对话 trace

> **结论先行**：下面两个场景的逐轮对话证明了两件事——① 正确产物时，8 层（faux + persistence
> + loop + sandbox + trace + hippocampus + world_verifier + checker）串成一条链，一轮 `complete`；
> ② 错误产物时，假 exit-0 的 `@verify` 命令和说谎的 checker 都放行，**唯一挡住假完成的是
> world verifier**（它重读磁盘，不信任自报），最终 4 轮 `blocked`。

## 怎么跑

```bash
py -3 examples/system_e2e_trace.py
```

脚本在 `examples/system_e2e_trace.py`，逐轮打印来自 `GoalLoopRunner.state.rounds`
（每轮的 maker 自报、checker 裁决、@verify 结果、world verifier 读到什么、loop 怎么判）。
`.trace-demo/` 是脚本跑完即删的临时目录，路径本身无意义。

---

## Scenario 1 — happy path（正确产物，真 @verify，world OK）

```
--- round 1 ---
  maker self-report : 'wrote hello world'
  checker verdict   : pass
  @verify           : py -c "import pathlib,sys;sys.exit(0 if pathlib.Path(sys.argv[1]).read_text()==sys.argv[2] else 1)" "D:/.../.trace-demo/happy/out.txt" "hello world" -> exit 0
  world verifier    : observed 'hello world' vs expected 'hello world' -> OK
  criteria satisfied: c1
  loop ruling       : progress (new criterion) -> unblock

  final status      : complete
  faux LLM calls    : 1
  trace events      : ['maker', 'checker', 'verification']
```

**这一轮发生了什么**：脚本化 maker 自报「写了 hello world」→ checker 判 `pass` → `@verify`
命令**真在沙箱里跑**（读产物文件、比内容，`exit 0`）→ world verifier 重读磁盘，`observed ==
expected` → OK → c1 满足 → 一轮 `complete`。faux LLM 只被消费 1 次，trace 恰好记录
`maker, checker, verification` 三事件。

---

## Scenario 2 — adversarial（错产物 + 假 exit-0 + 说谎 checker）

```
--- round 1 ---
  maker self-report : 'wrote hello world'
  checker verdict   : pass
  @verify           : py -c "pass" -> exit 0
  world verifier    : observed 'wrong content' vs expected 'hello world' -> FAIL
      what: artifact D:\...\.trace-demo\adversarial\out.txt content mismatch
      why : byte-identical check failed: bytes on disk differ from the expected content
      fix : rewrite D:\...\.trace-demo\adversarial\out.txt so its content is exactly 'hello world'
  criteria satisfied: c1
  loop ruling       : progress (new criterion) -> unblock

--- round 2 ---
  maker self-report : 'wrote hello world'
  checker verdict   : pass
  @verify           : py -c "pass" -> exit 0
  world verifier    : observed 'wrong content' vs expected 'hello world' -> FAIL
      ...(what/why/fix 同上)...
  criteria satisfied: c1
  loop ruling       : no progress -> blocked strike 1

--- round 3 ---
  ...(同上)...
  loop ruling       : no progress -> blocked strike 2

--- round 4 ---
  ...(同上)...
  loop ruling       : no progress -> blocked strike 3

  final status      : blocked
  faux LLM calls    : 4
  trace events      : ['maker', 'checker', 'verification'] * 4
```

**这四轮发生了什么**（每一轮 maker 都自报「写了 hello world」、checker 都说 `pass`、假命令
`py -c "pass"` 都 `exit 0`）：

| 轮 | 假命令 | 说谎 checker | world verifier | loop 怎么判 |
|---|---|---|---|---|
| 1 | exit 0 | pass | FAIL（磁盘是 wrong content） | **progress**（假命令让 c1 首次「满足」）→ unblock |
| 2 | exit 0 | pass | FAIL | no progress → strike 1 |
| 3 | exit 0 | pass | FAIL | no progress → strike 2 |
| 4 | exit 0 | pass | FAIL | no progress → strike 3 → **BLOCKED** |

**关键点**：

1. **world verifier 是唯一防线**。四轮里 `@verify` 全 exit 0（假命令）、checker 全 `pass`
   （说谎），如果只有这两道闸，第 1 轮就 `complete` 了。只有 world verifier 每轮都说 FAIL，
   因为磁盘上的字节 `wrong content != hello world`。
2. **第 1 轮为什么算 progress**：假 exit-0 命令让 `c1` 在 loop 眼里「首次满足」，被计为
   progress（`unblock`）；这正是「假命令能骗过 exit-code 检查」的体现，也是为什么还要
   world verifier。
3. **三振出局**：第 2/3/4 轮没有新准则被满足，累计 blocked strike 1→2→3，触
   `GoalRuntime.BLOCKED_THRESHOLD = 3`，翻成 `blocked`。faux LLM 恰好消费 4 次，trace 恰好
   12 个事件（4 轮 × 3 事件）。
4. **world verifier 的 `what/why/fix` 三段**给下游 agent 自纠错指引（learn-harness
   lecture-10:103-111），不是只报「错了」。
