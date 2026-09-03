# Cerebrum

> OpenWolf's learning memory. Updated automatically as the AI learns from interactions.
> Last updated: 2026-09-04

## User Preferences

## Key Learnings

- 本机 `python` = Python 2.7.18（无 pytest），`python3` = 3.13.13（有 pydantic/pytest）。**跑测试必须用 `python3`**。
- 覆盖率闸门：`pytest-cov` + `fail_under=92` + `precision=2`。不设 `precision` 会先四舍五入再比对，导致「打印 FAIL 但退出码 0」。coverage `source` 断言用「子集」而非「精确相等」，允许新增生产包进闸门。
- 三个测试缝：① `scripts/check.sh`/coverage 配置（meta-test 用 `tomllib` 读 pyproject）；② `FauxProvider` 公开 API（mock LLM 边界，loop 状态机仍归 `GoalLoopRunner`）；③ `WorldVerifier.verify_all()`（重读磁盘产物，不信自报）+ 可选 `world_verifier` 参数 fail-closed。
- `WorldVerifier` 用 `Path.read_bytes()` 做 byte-identical；`write_text` 在 Windows 会做 CRLF 翻译，会误红。
- 覆盖率未覆盖行的「死代码 vs 行为」判定：**已文档化 + 可达 + 有清晰语义 = 行为（补测试）；孤立/不可达 = 死代码（删）**。`stream()` 的 `tokens_per_second` 分块分支因 plan.md + docstring 均描述、参数真实可达，判行为。
- 流式限速测试确定性技巧：`monkeypatch.setattr("faux_provider.provider.time.sleep", lambda _s: None)` 把 `time.sleep` 置 no-op，避免时序抖，仍测分块契约。
- 自我改进闭环挂点：`GoalLoopRunner._finalize` 是 run 的唯一收尾点 → 天然是「结果→教训」的 distill 挂点；`cont.steering_prompt` 是「教训→注入」挂点。教训用 `correct=False` 承载「别再这么做」，检索用确定性词重叠（`len>=3` 交集），全程不发 LLM——守住「只 mock LLM 边界」。
- 模块放置防环：新模块若既 `import goal_loop.models` 又被 `goal_loop` 用，会造 `hippocampus→goal_loop` 环。解法是放 `goal_loop/` 内、只 `import hippocampus`，与 `world_verifier.py` 同级对称。
- 接 loop 的两种正交模式：① `Scheduler` 只依赖一个 `Runner` Protocol（`run_until_terminal(thread_id)`），单元测试用 stub 隔离，另留真 `GoalLoopRunner` 集成测试；② `Orchestrator.make`/`check` 签名对齐 `Maker`/`Checker` Protocol，直接当 maker+checker 传进 `GoalLoopRunner`。
- fail-closed 的「空 plan」边界：`Orchestrator.make` 的 `ok = not errors and bool(outputs) and all(o.ok)`。空 plan（零步）必须判 `ok=False`，否则 `all([])` 真空真会让「规划出 0 步」被误判成功。

## Do-Not-Repeat

- [2026-08-28] 用 `python` 跑 pytest → `No module named pytest`。用 `python3`。
- [2026-08-28] meta-test 硬编码精确列表（`assert source == [...]`），新增包就红。改断言为子集 `set(REQUIRED) <= set(actual)`。
- [2026-08-28] 三个子代理并行改同一仓库时，各自跑全量会看到彼此中间态。最终全量验证由主代理串行做，不依赖子代理的「全绿」报告。
- [2026-08-29] 用 edit 改 `safety.py` 时，oldString 只锚 `@dataclass\nclass SafetyGuard:` 想插常量，结果把 docstring 首行一起删了。教训：改类定义前先 Read 精确行号，oldString 要含完整 docstring 首行。
- [2026-08-29] 下结论「X 钩子缺失/没装」前，先查 `token-ledger.json` 的 `lifetime.total_sessions` 和 `.wolf/hooks/_session.json`。数字=0 不一定是没装，可能只是「还没跑过会读/写文件的会话」。
- [2026-09-01] GateGuard「Fact-Forcing Gate」钩子：每次 Edit/Write 前先回 4 条事实（谁 import / 是否已有同用途文件 / 数据结构 / 用户指令原文）。先 Grep「谁 import」+ Glob「是否已有同用途」再一次性写入即可通过。
- [2026-09-01] src 布局迁移后，`examples/*.py` 的 `sys.path.insert(0, parent.parent)` 还指 repo root。连 examples 的 sys.path 一起改成 `parent.parent / "src"`（已修 9 个）。
- [2026-09-01] 接真 LLM / provider：核对 model/base_url/key 三件套对齐（示例硬编码 `MiniMax-M3` 常与 env 冲突）；不同 provider API 格式不同（deepseek/grok/minimax 走 Anthropic 兼容 `/v1/messages`，kimi 走 OpenAI 兼容，用 anthropic 客户端 404；glm 429 code 1113 = 账户无额度，非配置错）。按文档/错误码定格式，别硬套。
- [2026-09-01] thinking 模型的 token 预算先花在推理上：deepseek-v4-pro 的 `content[0]` 是 `ThinkingBlock`（只有 `.thinking`），提取文本用 `"".join(b.text for b in content if b.type == "text")`；kimi 用 `reasoning_content`；小 cap（≤128）会返回空 `content`/`answer`。judge/summarizer 留足 headroom（512 起），否则输出空串被误判 FAIL。token 记账用 `input+output`（`input_tokens` 与 `cache_read_input_tokens` 互不重叠，相减得负值 `-97`）。
- [2026-09-04] 用 shell `python3 -c "...\"backslash\"..."` 做反斜杠替换，会因 bash 嵌套引号/转义把 `\\` 翻倍或吃掉（我一次把它从单反斜杠翻成 4/8 个，把 `_partial` 也顺手弄坏）。教训：改字符串字面量里的反斜杠用**文件式脚本** + `chr(92)` 精确比较字节，别在外层 shell 里拼。也印证既有规则：优先 write_file 再 `python -m`，避免 inline `python -c`。
- [2026-09-02] OpenWolf cron「配置了≠在跑」：cron-manifest.json 列了任务、cron-state.json 显示 running，但守护进程可能 4 天没心跳、端口无监听。判断死活看进程/端口/heartbeat，别只看 manifest/state。停 cron = manifest 各任务 `enabled` 置 false，无进程可杀。
- [2026-09-02] CSDD 论文（2602.02584v1）接进 taste_score：宪法（版本化+CWE 映射+MUST/MAY+rationale）→ 显式安全边界 S；spec 驱动探针生成替代正则手抠；compliance traceability matrix（原则→文件:行号）→ 静态 `verify` 证据来源（L7 自动 100% vs 手工 94%）；L4「宪法抗投毒」→ 第六道锁「禁改尺子」（宪法版本+哈希校验，改宪法=刷分=否决）。L5：3-5 条任务相关原则（96%）优于整篇（78%）。
- [2026-09-03] 给 `constitution.toml` 追加 `[[principles]]` 块时，若 patch 的 old_string 只锚一个完整 block，会把它**整体替换**成新块（我拿 id=SEC-08 那块当锚，结果 SEC-08 被覆盖成 SEC-09，险丢一条已提交原则）。教训：追加必须 old_string 锚「待插入的前一个 block 的结尾 + 下一段的开头」，命中后立即 `grep -c 'id = "SEC-'` 校验全部 id 齐全再跑测试。
- [2026-09-04] 给 mutation-score 加「更细假守卫」时，STATEMENT-FRAGMENT token（如 SEC-10 的 `permission not in self._enabled`）的假守卫**必须把字面量嵌进真守卫代码**，且 `_guard_symbol` 对这类 token 返回 `None`——初版 `_constant_hidden` 对 fragment 只吐 `true = True` + 一个空守卫，字面量没出现 → `re.search(pattern,text)` 为 None → 被「拒」但**拒错理由**（pattern 不存在，不是惰性被判），把测量带偏。改法：fragment 分支先把 token 里的正则转义剥掉，再把真句子嵌进 `if ...:` 守卫体。
- [2026-09-04] 测试 fixture 里拿 `def allow(path): return True` 当「合规守卫」范例已失效——那正是 verifier 判定的惰性「永远放行」作弊（恒返回常量、不看输入）。凡作「已实现守卫」范例的 fixture 用真决策守卫 `return path in _allowed_roots`（非常量返回），否则 compliance 从 1.0 掉到 0.0（`test_taste_score.*`/`test_taste_score_constitution.*` 三个 fixture 已改）。
- [2026-09-04] 给 verifier 加「裸 class-body attribute VALUE 常量」检测（`return self._ALWAYS` / `_Helper().val` / `_Mod.val`，`_ALWAYS = True` 在类体），必须把 `_resolve_literal_key` 加一个 `ast.Attribute` 分支并委托给新的 `_resolve_attribute_value_constant`，且对三类 receiver 都解析：`self.X`（current_class）、`_Helper().X`（ast.Call→classes）、`_Mod.X`（裸 Name→classes）。**第三类（裸类名）最容易被漏测**，不留一个 `test_module_class_attribute_value_is_rejected` 就成了死分支（trace.py 覆盖掉到 78% 以下）。防过收紧哨兵仍是 `test_hardened_verifier_still_sees_every_constitution_anchor_as_compliant`：它过说明 11 个真实锚文件没被误判 inert，csdd 才保 1.0。每抓一级必加「更细假守卫」（class-body attr-value 被抓 → 加「`__init__` 里绑的实例 attribute」= instance-attr-hidden）并把拆分测试的「仍 bless」断言改成「拒」、留一条新的仍-bless 断言钉住，否则 verifier_strength 饱和到 1.0 触发 `test_verifier_strength_is_bounded_and_honestly_unsaturated` 红。

- [2026-09-04] 抓「__init__ 绑定的实例属性常量」（instance-attr-hidden）要**两处一起改**，缺一不可：①加 `_resolve_instance_attr_constant`（只在 `__init__` 里**恰好一次**赋给可证常量时才解析，重赋值/来自参数/无赋值都回 `_NON_CONSTANT`）；②`_is_inert_function` 的 no-return 分支必须改成「全语句惰性才判惰性」——否则一个只赋常量的 `__init__`（无 return，旧分支直接 `return False`）会把整个 class 染成非惰性，作弊从 `_resolve_attribute_value_constant` 那层照样漏网。防过收紧三件套：`self._allowed = allowed`（来自参数非常量）、`self._ALWAYS = True; self._ALWAYS = False`（重赋值——保守回非恒定）、`__init__` 里带真实 CALL（`self._setup()` 是真实 action）——都判真实决策绝不误杀。**裸 name token 的新假守卫必须包成真实函数 `def <sym>(...)`**：我初版把 new-ratchet 冒充当 `{sym} = True`，整模块全惰性 → 被正确拒掉（不是我要的「仍 bless」余量），测量带偏。凡「仍 bless」的假守卫，其 guard 函数必须返回「解析器证不出常量」的值（如 `h.val` / 非 __init__ 里绑的 `self._ALWAYS`），否则整模块惰性、被拒且「拒错理由」。
- [2026-09-04] 抓「mutator 绑定实例属性常量」（inst-attr-mutator-hidden）要加**调用点溯源**：`_resolve_attribute_value_constant` 得知道**正在分析的围函**（`enclosing_fn`，从 `_is_inert_function` 传）与**局部实例→类映射**（`locals_map`，由 `x = _Cls()` 经 `_named_local_classes` 建），再用 `_iter_calls_of`（**不**下钻嵌套 def/class/lambda）找围函对接收类的方法调用 + `_method_binds_attr_constant`（该方法是否**恰好一次**把 `self.<attr>` 绑到可证常量；重赋值/来自参数回 `_NON_CONSTANT`）串起来。**新「仍-bless」ratchet 必须经解析器不追踪的接收者读常量**：工厂函数返回的实例 `_make().val`——我把 `h = _Helper(); h._setup(); return h._val` 当「仍 bless」余量，但那正是本 fire 要抓的 def-form mutator 作弊（局部实例 + 调 mutator 绑常量），会被正确拒绝，不是我要的余量。另一个坑：生成假守卫源码的字符串字面量用 `\n`（单反斜杠），**不要** `\\n`（双）——patch 里打 `\\n` 会让运行时 fake 文本含字面 `\n`，`ast.parse` 报「unexpected character after line continuation」，13 条假守卫全 SyntaxError。

- [2026-09-04] 抓「工厂函数返回类的常量」（factory-hidden → nested-factory ratchet）要**三处一起改**，缺一不可：①加 `_factory_return_class`/`_return_expr_class`/`_factory_receiver`——**只**解析「纯构造工厂」（`h = _Cls(...); return h` 或 `return _Cls(...)` 的单一返回类）；返回参数/带分支返回不同类/返回任意表达式都回 `None`（否则把真实动态工厂误判常量，过收紧）。②`_resolve_attribute_value_constant` 在 `_instance_receiver_class` 落空后走工厂路径，**并把工厂本身作 `enclosing`、`_named_local_classes(工厂)` 作 `receiver_locals`**——因为绑常量的 mutator 调用（`_setup()`）在工厂体内，不在 guard 里，用 guard 当 enclosing 会漏。③`_is_inert_function` 的 returns 分支要对「返回全惰性类实例」判惰性——否则 `_make` 返回非恒量 `h` 会把整模块染成非惰性、让 factory-hidden 漏网；用 `_class_is_fully_inert` + `_returns_inert_instance`，自引用类加 `_depth>8` 防挂死。**防过收紧哨兵**仍是 `test_hardened_verifier_still_sees_every_constitution_anchor_as_compliant`（过 ⇒ csdd 保 1.0）+ 4 个 anti-over-rejection 测试（`_make().allows_write(path)` 真决策 / `_make(kind)` 分支返回两类 / 类成员真实状态分支 / 真 branching guard）。**注意**：`_factory_receiver` 里的 `sources` 可能为 `None`（`_module_constants` 路径只传 `env`），必须先 `and sources` 再 `value.func.id in sources`，否则 `in None` 抛 TypeError。每抓一级必加「更细假守卫」（工厂被抓 → 加「工厂再委托给另一个 builder」=`nested-factory-hidden`，解析器只追一层不递归），并把拆分测试的「仍 bless」断言改成「拒」、留一条新的仍-bless 断言，否则 verifier_strength 饱和到 1.0 触发 `test_verifier_strength_is_bounded_and_honestly_unsaturated` 红。

- [2026-09-04] 抓「工厂链委托（nested-factory-hidden，`_make()` 返回 `_build()` 再读 `_make().val`）」要**三处一起改**，缺一不可：①`_factory_return_class`/`_return_expr_class` 加 `sources`/`_depth`，对「return 表达式本身是另一个工厂调用」**递归**解析到**基 builder** 的返回类（不递归则 `_factory_return_class(_make)` 返回 `None`、工厂路径落空）；②`_factory_receiver` 改为**先递归走委托链**、返回**基 builder** 作 enclosing——mutator（`_setup()`）在基 builder 体内被调，用包装工厂 `_make` 当 enclosing 会漏（`_make` 体只是 `return _build()`，没有 `_setup` 调用，`_mutator_bound_attr_constant` 找不到）；③`_returns_inert_instance` 把 `sources` 传给 `_return_expr_class`，否则 `_make` 返回 `_build()`（解析器不递归到惰性实例）会把整模块染成非惰性、让 `_guard` 漏网。**防过收紧哨兵仍是 `test_hardened_verifier_still_sees_every_constitution_anchor_as_compliant`**（过 ⇒ csdd 仍 1.0）。每抓一级必加「更细假守卫」（嵌套工厂被抓 → 加「class-level factory METHOD」= `static-factory-hidden`，解析器只住模块级**工厂函数**链、溯不到 `@staticmethod`/`@classmethod` 工厂方法的返回类型），并把拆分测试的「仍 bless」断言改成「拒」、留一条新的仍-bless 断言，否则 verifier_strength 饱和到 1.0 触发 `test_verifier_strength_is_bounded_and_honestly_unsaturated` 红。


## Decision Log

- coverage `source` 断言用「子集」而非「精确相等」：允许新增生产包进闸门，不因列表变化而红。
- 三个目标并行派发子代理，文件不重叠（目标1=pyproject/scripts/AGENTS，目标2=faux_provider，目标3=goal_loop/world_verifier），最终由主代理统一全量验证。
- crashed-maker 兜底「维持现状 vs 加兜底」分支：核实代码里早已 fail-closed（`loop_runner.py:210-219` 捕获 maker/checker 异常 → `ok=False`/`FAIL`），`test_red_team.py:61` 已钉。结论是「维持现状 + 测试已钉」，只订正 STATUS 的过时描述，不新增代码。