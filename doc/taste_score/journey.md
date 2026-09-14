# taste_score + agent-cron Journey

> 两列表：ME（人/需求） vs YOU（AI 实现/发现）。顶部先放风险与 TODO。
> 本次覆盖：把 openwolf 的「agent cron」真正拉起（不是配置了≠在跑），
> 并把 CSDD 分数从「误导值」修成「诚实合规分」。

## 风险与 TODO

- **[注意] 分数与 cron 是两条独立系统**：OpenWolf cron 是记忆/影像/审计的维护调度，
  它**不出分数**。`taste_score` 的竞争分数目前**没有 cron 在调度**——`--constitution`
  只是手动跑一次写 ledger。要「每晚过夜竞争」，得另外给它建 cron，本批未建。
- **[评分语义缺口] 分数仍是 agent 无关的**：`TraceabilityVerifier.verify(name, probe)`
  只看 `name` 不看、却读**同一份 `src/`**，所以单 agent 下读数恒等，分不出谁是谁。
  若要真多 agent 区分，需 per-agent 工作区（worktree）或 per-agent 证据，属下一步。
- **[openwolf Windows 坑] `openwolf daemon start` 失败**：内部 `execFileSync(pm2Bin(),…)` 在
  Windows 调 `.cmd` 包装缺 `shell:true` → 抛异常被吞，只报 "Failed to start daemon."。
  绕法 = 项目根手动 `pm2 start wolf-daemon.js`（带 `OPENWOLF_PROJECT_ROOT`）。
- **[AI 任务静默空转] `cerebrum-reflection`/`project-suggestions`** 需 3am 联网调 LLM；
  若缺额度/断网 → `log_and_continue`，静默产出空。这类「失败」无告警。

## 拉起 agent cron（2026-09-02）

- **判断死活在心跳/端口，不在 state 文件**：`cron-state.json` 写 `engine_status:running`、
  `openwolf status` 报 "Daemon: running"，但 `last_heartbeat` 已 5378 分钟（≈3.7 天）、
  端口 18809 无监听——**守护进程是死的**。这就是「配置了≠在跑」。
- **6 个任务重新 enabled**（manifest 里 `enabled:false→true`）：anatomy-rescan /
  memory-consolidation / hippocampus-consolidation / token-audit / cerebrum-reflection /
  project-suggestions。
- **手动拉起（绕 pm2 坑）**：`OPENWOLF_PROJECT_ROOT=<root> pm2 start <wolf-daemon.js> --name openwolf-AgentHarness101 --cwd <root>`，再 `pm2 save`。
- **实证在跑**：端口 18809 LISTENING（pid 29068）、heartbeat 归 0 分钟、`openwolf cron list`
  全部 `Status: enabled`、手动 `cron run anatomy-rescan` → daemon.log
  `Executing task → completed in 1432ms`。

## 修 CSDD 分数（2026-09-02）

- **坏分数**：带 `--constitution` 跑三个 demo agent 全是 `golden=0.029`、rejected 全 False。
  逐条拆解（34 探针 = 3 宪法 + 31 增强）：
  - 31 条增强探针：verify 不认识 → `(did_expand=False, safe=False)`，全 0 分，只撑大分母。
  - SEC-01/02（MUST→hold）：证据 `(True,True)`（护栏在且净），但 hold 判 `golden_expand=False` → `True==False` 不命中。
  - 只有 SEC-03（SHOULD→expand）命中。**1/34 = 0.029**。
- **修两处**：
  1. `_from_constitution`：MUST→hold 错配 → 全部改 `expand`（装护栏本身就是安全的拓边；
     MUST/SHOULD 严格度留在宪法 `level`，不进判分）。
  2. `TraceabilityVerifier.compliance()`：单 agent 累计合规分 =「已实现且净的原则数 / 总原则数」，
     暴露为 `ledger['csdd_score']`，只按宪法原则算、不再掺 31 条无关题稀释。
- **fail-closed 回修**：锚点文件缺失（护栏没装）时，原 `verify`/`matrix` 的正则匹配空串
  误报 `safe=True`。改 `_run`：`exists and …`，缺失 = 既无拓边证据、也不安全。
- **诚实分数**：`csdd_score = 1.0`（当前 `src/` 满足全部 3 条原则，各条 `expanded=True/safe=True`）。

## 修 AI-task cron 崩溃（2026-09-02）

- **坏的只是 2 个 AI 任务**：本地任务（anatomy/memory/hippocampus/token）早就能跑，
  `cerebrum-reflection` / `project-suggestions` 每次报 `claude -p failed: spawnSync claude.cmd EINVAL`，
  `suggestions.json` 一直 `generated_at: null`。
- **根因（Windows 壳坑的同一类）**：`openwolf/dist/src/daemon/cron-engine.js:294` 用
  `spawnSync("claude.cmd", [...])` 但没 `shell:true` → Windows 调 `.cmd` 包装抛 EINVAL。
  和之前 pm2 的 `execFileSync` 坑同根源。pm2 实际跑的是全局
  `C:\nvm4w\nodejs\node_modules\openwolf\...`（`D:\GitRepo-AI\openwolf` 是它的链接），改那儿就对了。
- **修一行**：`spawnSync(..., { ..., shell: process.platform === "win32" })`，改完 `pm2 restart openwolf-AgentHarness101` 载入新代码。
- **实证**：重启后两个 AI 任务都通过（cerebrum 34.7s / suggestions 20.0s），`cerebrum.md`
  更新时间对上、`suggestions.json` 的 `generated_at` 不再是 null 且有真实 achievements/risks。
- **[脆弱][待确认] 补丁在全局 node_modules**：`npm i -g openwolf` 更新会覆盖；P1 已修但需上游 PR 或 vendoring 才持久。

## 修 CSDD 分数退化为同值（2026-09-02）

- **坏分数**：带 `--constitution` 跑，robust/reckless/liar 三个 demo agent 全
  `golden≈0.088、robust=0.0`、rejected 全 False——**区分不出谁是谁**，帕累托否决也没触发。
- **根因**：`verify`（宪法 TraceabilityVerifier）只知道 3 条宪法原则；对其它 31 条
  增强/红队探针和所有 mutation 菜单，它返回硬编码 `(did_expand=False, safe=False)`：
  1) mutation 鲁棒性被清成 0（菜单全是它不认的增强探针）；2) golden 分母被稀释到 3/34；
  3) verify 读真实 `src/`（agent 无关）→ 三个 agent 读数恒等。
- **修两处**：
  1. `TraceabilityVerifier.verify`：无锚点的探针返回 `None` 而非 `(False, False)`——没证据就是没证据，别替你下结论。
  2. `gate.run`：verify 返回 `None` 时回退到 agent 自报；`compete` 用 `make_demo_aware_verify`
     把「宪法证据 + hostile-honest demo verify」组合，宪法有锚用宪法、无锚回退 demo（识别说谎/鲁莽）。
- **诚实分数**：`csdd_score=1.0`（3 条原则全实现且净）；竞争侧 robust `0.882/1.0`、liar `0.206/0.0`、
  reckless `0.088/0.0` **rejected**「expanded but regressed safety boundary」——帕累托否决真正触发。
- **回归**：`python3 -m pytest -q` 296 passed, 56 skipped（Linux-only），覆盖率 95.42%（过 92 闸）。

## 深化宪法 3→5 原则（2026-09-03）

- **分数到顶后的拓边方向**：`csdd_score` 被设计封顶 1.0（合规分=已实现且净的原则数/总数），
  「改进」只能靠**加真原则**，不能靠把 1.0 再拿高。本批加两条真护栏。
- **SEC-04 命令注入（CWE-78）**：新增 `src/sandbox/command_policy.py` 的 `CommandPolicy`
  ——只允许白名单 argv 列表、拒绝裸 shell 字符串、空白名单全拒（与 `PathPolicy` 同 fail-closed 底）。
- **SEC-05 提示注入（CWE-77）**：新增 `src/security/injection_guard.py` 的 `InjectionGuard`
  ——窄标记集检测「覆盖 harness 权限门」的注入语，自身无 `eval`/`exec`。
- **宪法登记** 5 条原则，digest 更新为 `9d25b3…`（版本+哈希改宪法定拉黑，第六道锁）。
- **实证**：`301 passed, 56 skipped`（+5 guard 测试，含宪法 meta-test 锚点全解析）；
  `csdd_score=1.0`（5/5 原则 expanded+safe）；`compete --constitution` 反古德哈特仍判别——
  robust `0.889/1.0` **accepted**、liar `0.25/0.0`、reckless `0.139/0.0` **rejected**
  「expanded but regressed safety boundary」——帕累托 E 上/S 下 拉黑照常触发。

## ME / YOU

| ME（需求 / 决策） | YOU（实现 / 发现） |
|---|---|
| 让 cron 跑起来 | 查实是「配置了≠在跑」；绕 openwolf Windows pm2 坑，手动拉起并实证执行 1.0 |
| 分数要加入 CSDD，单 agent 每次修改加分 | `compliance()` 定为「已实现且净的原则数/总数」，修 MUST→hold 错配 + 去稀释，fail-closed |
| cron 有 bug 就修、跑得越快越好 | 修 AI 任务 EINVAL：`spawnSync` 加 `shell:true`（Windows 壳坑），pm2 restart 实证两个 AI 任务通过 |
| 检查/改进分数：mutation + 反古德哈特 judge | 查实宪法下分数退化为同值；verify 无锚回退 `None` + gate 回退 agent 自报，帕累托否决/说谎识别真正触发，回归通过 |
| cron 贡献太小；要全天自动、别问 | 不是 bug：cron 与 score 是两条没接上的轨道。把修复落到 openwolf **源码**（junction 指向用户自己的库）并给 cron 加 `run_command` 动作，注册 `score-run`（`*/5 * * * *`）每天自动跑 `compete --constitution` 写 ledger（~500ms/次，实测 `Command python3 succeeded`）。AI 任务 `shell:true` 修复也进源码，重建后不再丢 |

