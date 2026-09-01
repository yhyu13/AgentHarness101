# Enhancement Catalog — 109 条（P0/P1/P2），2026-09-01

> 本表是"100 条增强想法"头脑风暴的落库产物。六路并行 agent 各产 18–19 条，去重后共 **109** 条。
> 每行 = 标题 + 一句 why + 优先级标签 + 红先验收。锚点全来自真实源码符号，不编造 API。
> 与 doc/roadmap/100_tasks.md（#1–100 已执行）**不重叠**；本表是"下一批"。

## 优先级定义（沿用 100_tasks.md）

- **P0** 本仓库缺的核心运行时能力，可直接 TDD、Windows 可跑、不需要 OS 级隔离。本批执行。
- **P1** 加固/可靠性/审计/真 LLM 边界，让它从能跑到可依赖。
- **P2** 打磨、文档、可选/生态、性能，不阻塞。

---

## A. 沙箱 / 安全（src/sandbox, src/safety）

| # | 标签 | 标题 | why / 验收 |
|---|---|---|---|
| A1 | **P0** | 把 PathPolicy 接进 Sandbox（文件写隔离今天是死代码） | `sandbox.py` 从不 import `path_policy`，写隔离在运行时零生效 → 真实缺陷。`Sandbox(allowlist, path_policy=...)` 对越界写返回 `blocked=True` |
| A2 | **P0** | 启动前清洗继承环境变量 | 不传 `env=`，父进程 PATH/密钥泄漏给被允许的解释器。`SECRET` 经清洗后不出现在子进程 |
| A3 | **P0** | Sandbox 限定 cwd/工作目录 | 无 `cwd=`，命令跑在 harness 目录，cwd-相对写可逃逸根。`cwd=tmp` 下命令被政策约束 |
| A4 | **P0** | 关闭 argv[0] 绕过（绝对/相对/带路径名） | 允许表按裸"python"精确匹配，`C:\...\python.exe`、`./python`、符号链接都能绕。绝对路径被拒，裸名按 basename 匹配 |
| A5 | **P0** | HITL 审批绑定到原请求 | `approve()` 翻转任意 Pending 决策，无 request id、无审批人审计。R 造的决策只能由 R 的请求满足 |
| A6 | P1 | 字符串命令用 shlex 拆分（与 CommandVerifier 一致） | `command.split()` 朴素切分篡改引号参数，与 verifier 层冲突 |
| A7 | P1 | 限制 Sandbox 标准输出/错误大小 | 无上限，失控命令膨胀内存/冲爆上下文 |
| A8 | P1 | 危险子串硬拒绝清单（argv 之上第二层） | 允许的 python 仍可 `os.system('rm -rf /')` |
| A9 | P1 | 注入检测覆盖零宽/控制字符/同形字编码 | `ignore\u200b previous` 等绕过精确子串匹配 |
| A10 | P1 | 注入标记按词边界匹配，降误报 | "ignore her instructions" 不被误判 |
| A11 | P1 | 扩 `_HIGH_RISK_ACTIONS` + 拒随意降级 risk | overwrite/truncate/chmod 缺失，free-string risk 可把高危标低危 |
| A12 | P1 | RBAC write 权限限定到 PathPolicy allow_roots | write 角色无目标范围，配合沙箱才收敛 |
| A13 | P1 | PathPolicy 加 allow_read + deny_roots，钉 symlink 逃逸测试 | 判读无能力、无拒绝优先级 |
| A14 | P1 | PathPolicy 判含与写操作原子化（关 TOCTOU） | resolve-后-再写非原子，判定与写之间可被替换 |
| A15 | P1 | WorldVerifier 防非普通文件 + 超限/二进制读 | `read_bytes()` 无大小上限、无非文件守卫 |
| A16 | P1 | WorldVerifier 读产物加路径政策（fail-closed） | check 里的任意绝对路径可外泄 `/etc/passwd` |
| A17 | P1 | 允许的裸命令经 shutil.which 解析，拒 PATH 劫持 | 裸"python"走隐式 PATH 查找，可被替换二进制 |
| A18 | P2 | 每命令读写分离权限 + per-command allow_roots | 单个全局 root 无法表达"git 写 repo，python 只读 /tmp" |

## B. 目标循环 / 编排（src/goal_loop, orchestrator）

| # | 标签 | 标题 | why / 验收 |
|---|---|---|---|
| B1 | **P0** | 每轮记录 per-criterion 通过/失败 verdict 表 | `RoundRecord` 只存通过的 id，无法审计哪个条件卡住 |
| B2 | **P0** | 完成证据串纳入每条件 stdout/stderr | `_build_evidence` 只给 `command:returncode`，丢失已捕获的输出 |
| B3 | **P0** | 人机干预检查点信号：暂停而非终态 | `human_intervention` 字段存在但无人设置，无法停下来等人 |
| B4 | P1 | Orchestrator.check 对 reviewer 崩溃 fail-closed | `check` 未守卫 reviewer，崩溃会杀掉循环（make 已守卫） |
| B5 | P1 | 聚合 executor 的 modified_files 进 MakerOutput | 目前只并 summary/tokens，`files_changed` 恒为 0 |
| B6 | P1 | 记录每轮墙钟耗时 + 循环总耗时 | 无法回答"这轮花了多久" |
| B7 | P1 | 保留 Windows 反斜杠路径（runner verify 路径） | `_run_verification` shlex 重拆分，回退 CommandVerifier 已修的漂移 |
| B8 | P1 | 被中止的轮次 crash 可见且非致命 | `_verify_criterion` 崩溃无 trace，静默丢弃本轮 maker 产物 |
| B9 | P1 | 记录 `run_until_terminal` 每次恢复的瞬断 crash | 恢复零日志，trace 里不可见 |
| B10 | P1 | FinalResult 丰富 token 总量/墙钟/轮数 | 收官记录无法从状态直接求和 |
| B11 | P1 | maker 侧预算超限时轮间等待，不静默越过 | 单轮超预算会跑完才触发 |
| B12 | P2 | 从持久化 LoopState 确定性重放某轮 | 无轮次叙事重建，重启后不可推导 |
| B13 | P1 | RoundRecord 上 per-round maker/checker token 归属 | now 混合一个 input 总量，无法归因 |
| B14 | P1 | Orchestrator 确定性并行 executor fan-out | N 步纯串行是墙钟瓶颈 |
| B15 | P2 | Orchestrator 输出结构化 step 错误归因 | 错误被平铺进 summary 字符串 |
| B16 | P2 | 拒绝/警告 goal.md 未识别的停止条件行 | `_parse_stop_conditions` 静默丢弃无法归类行 |
| B17 | P1 | 落库并显露 blocked-strike 与 LoopState.blockers 的漂移 | 同一停滞的两套表示会漂 |
| B18 | P2 | run_until_terminal 的无 sleep 重臂 + 可注入崩溃率守卫 | max_crashes/crashes 私有，测试无法证明恢复 |

## C. 调度 / 持久化（src/goal_persistence, scheduler）

| # | 标签 | 标题 | why / 验收 |
|---|---|---|---|
| C1 | **P0** | 崩溃恢复部分运行 goal（对账悬空 in-flight 轮） | `_active_turns` 纯内存，start/end 之间崩丢半轮 |
| C2 | **P0** | 瞬时调度错误退避重试 | `run_once` 把所有异常记为 ERORRED，瞬断 LLM 失败不重试 |
| C3 | **P0** | 持久化 RunHistory/每 goal 结果账本 | 终态覆盖上一行，无多少轮各为何状的审计轨迹 |
| C4 | **P0** | 死信/毒 goal 隔离 | 老 Error 的 goal 每轮循环不停，`run_periodic` 永不空 |
| C5 | **P0** | 预算在轮中即判（不依赖 end_turn 冲刷） | 预算检查只在 end_turn apply_usage，长轮大超冲 |
| C6 | **P0** | 调度器整进程重启 mid-run 可重入 | 批状态在局部变量，重启丢整批，无本轮已终态去重 |
| C7 | P1 | 优先序调度 active goals | `list_active` 无 ORDER BY，无法排关键任务先跑 |
| C8 | P1 | 并发 run_once 幂等加固 | start_turn 只守一个内存 dict，check-then-write 无原子性 |
| C9 | P1 | max_rounds 停止条件独立于墙钟 | `StopCondition(kind="max_rounds")` 已解析但未执行 |
| C10 | P1 | BUDGET_LIMITED 预算重置/重臂 | 终态无出边，合法超限后永久死 |
| C11 | P2 | 接或删死代码 USAGE_LIMITED | 枚举+迁移在，但 apply_usage 从不设置它 |
| C12 | P1 | run_once 确定性排序保证 | `list_active` 顺序依 SQLite 不保证 |
| C13 | P1 | 时区感知调度窗口（本地时间夜间跑） | `run_periodic` 有 sleep 无 now()，无法真正门到 HH:MM |
| C14 | P2 | 终态 goal 的 GC/归档 | `GoalStore.delete` 存在但无人调用，completed 无限累积 |
| C15 | P1 | 陈旧 updated_at 的停滞检测 | ACTIVE 但 updated_at 冻结、resume_all 持续重臂 = 死转 |
| C16 | P1 | 调度器瞬时/永久错误分类 | 所有异常都 ERORRED，重试逻辑需区分 |
| C17 | P1 | store 写入乐观并发 / compare-and-set | get→mutate→persist 无版本检查，竞态悄悄丢更新 |
| C18 | P0 | 持久化 in-flight 轮标记（崩溃安全预算） | 无记录"正在轮中"，中断与干净轮无法区分（与 C1 同组） |

## D. 记忆 / 上下文（src/context_compaction, hippocampus）

| # | 标签 | 标题 | why / 验收 |
|---|---|---|---|
| D1 | **P0** | 预算约束的压缩循环 | important 项总数可超阈值，压缩从不保证输出适配预算 |
| D2 | **P0** | 跨压缩保护目标/验收锚点 | 未标记的 goal 项在 80% 被归档，丢失目标不可恢复 |
| D3 | **P0** | 常驻 Do-Not-Repeat 注入 | correct_facts 过滤 correct=False，"别再犯"对 briefing 不可见 |
| D4 | P1 | 归档关键字召回（重扩/搜索路径） | 压缩有损，无按关键字查回并重注入单条的能力 |
| D5 | P1 | summary 带 id 溯源供单条重扩 | summary 是黑盒散文，无从对应到归档项 |
| D6 | P1 | 归档谱系（不静默覆盖） | 同 archive_name 第二次压缩毁第一次 |
| D7 | P1 | size_of 用 token 计数 | len 数字符，80% 不是真 token 预算 |
| D8 | P1 | 超越二值 important 的显著性评分 | 二值导致保留全部/丢弃全部，无分级 |
| D9 | P1 | 顺序无关的确定性摘要 | `material[:max]` + most_common 随插入序漂移，违"确定性"docstring |
| D10 | P1 | 跨 run 主题召回（关联检索） | `get` 需精确 `task::action` 键，无按主题召回先验教训 |
| D11 | P1 | upsert_fact 冲突/去重对账 | 撞键静默覆盖，correct 替换所引证据丢失无信号 |
| D12 | P1 | 回放暴露修正与结果，不只 important_lines | replay 忽略 outcome 与 facts verdicts |
| D13 | P1 | record_step/learn 接线进 trajectory.facts | 事实无法归属到产生的轨迹 |
| D14 | P2 | 记忆衰减/遗忘策略 | 无时间戳无强度，索引缓存无限胀 |
| D15 | P2 | 归档上限与逐出 | archive_dir 无上限，每次压缩都增 |
| D16 | P2 | 置信度打分召回排序 | 只有 correct/evidence，无相关性信号排序 |
| D17 | P2 | 增量预算压缩传递 | compact_window 一次冲爆全部，无逐轮削低显著性前缀的 API |
| D18 | P2 | 归档/索引读 fail-soft | `_read_index`/json.loads 盲目，损坏文件崩掉 recall/replay |

## E. 评估 / 可观测 / 成本（src/eval_harness, observability, cost_control）

| # | 标签 | 标题 | why / 验收 |
|---|---|---|---|
| E1 | **P0** | RegressionGate：与黄金 EvalReport 比对检测漂移 | `EvalRunner.run` 只报固定集 pass/fail，无法说改东西是变好还是变坏 |
| E2 | **P0** | 预算守卫：预估成本超阈值拒绝启动 | 会算成本但从不阻止超预算 run 先花 |
| E3 | **P0** | 成本 trace 事件接入可观测（每次 LLM 调用） | TraceLog 与 cost.py 完全脱节，事件流看不到成本内联 |
| E4 | **P0** | trace 输出跳过/遮蔽密钥 | `payload` 原样持久化，prompt 里的 key 会落盘 |
| E5 | P1 | 黄金轮次落盘为耐久、有版本基线 | 黄金 EvalReport 镜像需重启存活才用于回归 |
| E6 | P1 | 阈值门：正确率/延迟/成本漂移超 X% 则 fail | harness 需要发布门/金丝雀指标 |
| E7 | P1 | 部分得分评分（0..1，非二值 pass/fail） | 近失与全失同计，隐藏质量回归 |
| E8 | P1 | 持久化每 run EvalReport 审计产物（稳定 schema） | EvalReport 是活动对象，无落盘不可审计 |
| E9 | P1 | 每 goal 时延预算燃尽（P50/P95） | span 有 duration 但无忌分位/燃尽 |
| E10 | P1 | 成本归属到每 goal | estimate_cost 计价但无键关联回 goal/thread |
| E11 | P1 | 由 trace 重放驱动确定性重跑 | replay 重建事件，无回喂进 run 的路径 |
| E12 | P1 | blocker 关联到致其轮次 | 平坦 /seq 事件，无 tool-call → blocker 因果链 |
| E13 | P2 | 环形缓冲区/保留策略（trace log） | 严格 append-only，长跑 JSONL 无界 |
| E14 | P2 | 汇总可观测摘要（per-goal 计数/总耗时/span，稳定 schema） | 原始事件在，无编译可查询摘要 |
| E15 | P1 | 在线限流重试/退避而非平拒 | `RateLimiter.allow()` 返回 bool，burst 直接丢无 retry_after |
| E16 | P2 | 缓存感知成本核算：报 ToolResultCache 省了多少 | 缓存避免了调用但无人记省下的 token/成本 |
| E17 | P2 | 估值精度守卫：超 20% 偏差告警 | estimate_cost 信任传入 tokens，无期望-实际 sanity check |

## F. 打包 / CI / 工具（pyproject, scripts, tests）

| # | 标签 | 标题 | why / 验收 |
|---|---|---|---|
| F1 | **P0** | 加 `[build-system]` 使 src-layout 真可 pip 安装 | pyproject 无 build-system，`import goal_loop` 仅靠 pytest pythonpath hack 和 sys.path.insert 解析 → 干净 clone 无法 `pip install -e .` |
| F2 | **P0** | 开发向 console script（`ah`）+ `python -m agent_harness` 入口 | 现只能手编示例跑，无 CLI 入口 |
| F3 | **P0** | 安装后"每个包都能 import"冒烟测试 | 无任何测试保证 11 个 src 包实际安装后干净 import |
| F4 | **P0** | 打包元数据 meta-test（build-system + scripts + py.typed 存在） | installable 契约无守卫，现缺 build-system/py.typed 却自称 done |
| F5 | **P0** | per-directory 覆盖率门（非仅聚合） | 单一 fail_under=92 让一个热点包掩盖另一个跌到 60% 的包 |
| F6 | **P0** | demo/示例冒烟测试（clean cwd 下 runpy 跑通） | demo 从未被测试调用，各自 sys.path.insert，可悄悄坏 |
| F7 | P1 | 确定性测试排序 / 跨测试隔离守卫 | 测试共享真磁盘工件（.db），依赖 run order |
| F8 | P1 | 多 Python 版本 CI 矩阵（.github/workflows） | 无 .github/，requires-python>=3.11 从未验证 |
| F9 | P1 | 单命令 task runner 包 check.sh（跨平台 python3/py） | check.sh bash 硬编码 python3 -m，Windows 需 python |
| F10 | P1 | measure_efficiency 回归基线测试 | 只断言 > 0，无墙钟/开销比例回归守卫 |
| F11 | P1 | pre-commit hooks（ruff + eof + 密钥扫描） | 门只在 check.sh，可跑可不跑 |
| F12 | P2 | 结构化链接检查/文档构建测试 | doc/ 11 目录 + html 无 Sphinx/MkDocs 配置，无失效链接守卫 |
| F13 | P2 | 每个公开符号有 docstring（inspection 测试） | `ToolRegistry._validate` 等无 docstring，无测试强制 |
| F14 | P2 | 公开 API 面约定测试（__init__ 导出） | 测试 import 深层名，顶层面不稳定 |
| F15 | P1 | GoalSpec markdown-template 产物守卫 | `parent.parent / "src"` 硬编码相对路径，install 后坏 |
| F16 | P1 | Windows/POSIX python-vs-python3 启动器抽象 | check.sh 硬编码 python3，本需 py，脚本自身跑不起来 |
| F17 | P2 | 版本策略 + changelog meta-test | version=0.1.0 无 CHANGELOG，包版本可静默漂移 |
| F18 | P1 | coverage source 子集活保持一致（运行时重推导） | `test_coverage_gate.py:15` 硬编码 11 包名，加第 12 包逃断言 |

---

## 统计

- 本表共 **109** 条（A18 + B18 + C18 + D18 + E17 + F18）。
- **P0 共 25 条**：A1–A5（5）、B1–B3（3）、C1–C6/C18（7）、D1–D3（3）、E1–E4（4）、F1–F6（6）。

## 评审剔除记录（bad ideas）

下列"候选"未进上表，理由：

- **Linux-only OS 隔离（seccomp/Landlock/network egress/fork 禁）**：本机 Windows，无法 TDD 验证，标"pending Linux host"，不入本批。
- **需外部认证服务的生态整合**（第二 provider、deepseek-harness/hermes 对齐、多 provider 路由）：超出"核心运行时能力"，归 P2 生态，未展开。
- **纯性能剖析/依赖瘦身**：无行为契约，不是"能力缺口"，归 P2 打磨。
- **B18 / D18 / E17 等"可暴露但低优先级"**：已保留但降级 P2，不阻塞。
