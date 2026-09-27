# Reins 开发架构

读完这一份，你应该能说清：Reins 由哪几块组成、一次需求在系统里怎么流动、你要开发的模块处在哪一层、它依赖谁、对外承诺什么。

- 产品是什么、每个 Phase 做什么：[spec-driven-workflow.md](../../spec-driven-workflow.md)
- 为什么这样设计、各验证门的口径：[spec-driven-dev-skill-design.md](../spec-driven-dev-skill-design.md)（下文简称「设计文档」）
- 编码与协作规约：[AGENTS.md](../../AGENTS.md)
- 任务拆分与分工：[tasks.md](tasks.md)

本文是开发视角的索引：产品规则以上面两份为准，接口以代码里的签名和 docstring 为准。三者冲突时，停下来找协调者。

---

## 1. 全景

### 1.1 用户看到什么

| 阶段 | 用户接触的东西 | 背后是谁 |
| --- | --- | --- |
| 安装 | 一行命令、`reinsdev install / update / uninstall / doctor / setup` | `install.sh` / `install.ps1` → `tools/reinsdev/` |
| 使用 | `/spec`、`/bugfix`、`/waive`，或直接用自然语言说「新需求」「放行」 | 入口 skill → 总控 skill → 子 skill / agent → `spec-driven` CLI |
| 被拦截 | 平台弹出的拦截原因、gate 的拦截清单 | 平台 hook → `spec-driven hook` → policies；`spec-driven gate` → gates |

`spec-driven` 是插件内部的 CLI，只由总控 skill 和平台 hook 调用，**用户看不到它**。

### 1.2 运行时组成

```
┌──────────────── 平台：Claude Code / Codex / OpenCode ────────────────┐
│                                                                      │
│  用户输入 ──► 入口 skill（spec / bugfix / waive）                     │
│                   │                                                  │
│                   ▼                                                  │
│            总控 skill spec-driven-dev ──► 子 skill（Phase 1–4，写工件）│
│               │    ▲                 └─► agent（Phase 5–8，独立评审/实现）│
│               │    │ 读输出、按退出码决策                              │
│               ▼    │                                                 │
│        ┌──────────────────────────┐        平台 hook（每次工具调用、   │
│        │  spec-driven CLI         │◄────── 每次用户输入）              │
│        │  commands/  gates/       │                                  │
│        │  policies/  核心模块      │                                  │
│        └──────────┬───────────────┘                                  │
└───────────────────┼──────────────────────────────────────────────────┘
                    ▼
     项目 .openspec/（工件与状态）   git（分支、提交、trailer）   ~/.reins/（日志、授权）
```

四个要点：

1. **skill 是大脑，CLI 是手和尺子。** skill 决定下一步做什么、怎么和用户对话；凡是需要「机械可验证」的事（建 change、判断能否进下一步、记录放行）都交给 CLI。skill 不自己判断工件是否合格。
2. **所有状态都在磁盘上。** 流程状态在 `.meta.json`，过程留痕在 `retrospective.md`，产出在工件 markdown 里。会话可以随时中断，`spec-driven resume` 能恢复。
3. **生成与评审分离。** 评审（spec-evaluator、qa-evaluator、code-reviewer）只能由独立 agent 做，报告首行带 `generated-by` 标记，gate 会校验。
4. **护栏三层落实**（设计文档 §2.4）：CLI 自己拒绝（第 1 层，所有平台）→ git hook 拒绝提交（第 2 层）→ 平台 hook 当场拦截（第 3 层，有则用）。任何一层缺失都不能让护栏静默失效。

### 1.3 一次需求怎么流动

```
/spec 批量审批
  └► spec skill ──► 总控：spec-driven status          （还没有 change）
                    总控：spec-driven new batch-approve   ──► .meta.json、proposal.md 骨架、分支、git hooks
                    总控：调 requirements-clarify skill   ──► 写 proposal.md（AC、业务取值来源…）
                    总控：spec-driven gate 1              ──► 退出码 3：列出 BLOCK
                         └► 把原因原样给用户：「回去修」还是「放行」
                    …… Phase 2–4 同理，每个 Phase 结束都过 gate ……
                    总控：派 spec-evaluator agent         ──► spec-review.md（首行 generated-by）
                    总控：spec-driven gate 5
                    …… Phase 6 每个任务派 implementation-generator，提交带 Task-Id trailer ……
                    总控：spec-driven gate 6 / 6.5 / 6.7 ──► 覆盖率不达标 BLOCK
用户：「放行」
  └► waive skill ──► 列出 BLOCK 项，请用户给理由，再请用户输入口令
用户：确认放行 batch-approve 6 coverage
  └► UserPromptSubmit hook ──► policies/waive_grant ──► ~/.reins/grants/ 写一次性授权
     waive skill：spec-driven waive 6 coverage --reason "…" ──► 消费授权 ──► retrospective.md 追加一行
     总控：spec-driven gate 6 ──► 该项显示 [WAIVED]，放行
     …… Phase 7、8、8.5、8.9 ……
     总控：spec-driven archive ──► 合并主 specs、生成 ADR、git mv 到 archive/
```

同时，模型的每次工具调用都先经过平台 hook：比如在 Phase 4 试图改 `proposal.md`，`policies/spec_gate` 会以「上游已冻结」拦下。

---

## 2. 仓库布局与归属

```
reinsdev-plugin/                          插件本身（三个平台直接读）
├── .claude-plugin/ .codex-plugin/        平台清单                              T0
├── hooks/claude.json codex.json          平台 hook → spec-driven hook          T0
├── index.js package.json                 OpenCode 入口                         T0
├── agents/*.md                           4 个 agent                            T9
└── skills/
    ├── spec/ bugfix/ waive/              入口 skill（很薄）                     T0 / T8 / T6
    ├── spec-driven-dev/
    │   ├── SKILL.md                      总控主循环与硬规则                      T8
    │   ├── references/                   总控按 Phase 读取的细则、agent 调度模板   T8
    │   ├── templates/                    工件模板（格式的唯一来源）               T1
    │   └── scripts/
    │       ├── spec-driven(.cmd/.py)     启动器                                T0
    │       └── lib/spec_driven/          CLI 源码（见 §3）
    ├── requirements-clarify/ tech-design-tradeoff/ api-design-rest/
    │   db-schema-design/ task-breakdown/ tdd-implement/ tiered-code-review/   T8
    └── root-cause-analysis/ … openapi-check/ safety-check/                   T10

tools/reinsdev/  bin/reinsdev  install.sh  install.ps1   安装工具（不进插件）   协调者
tests/                                     单测；fixtures/<任务>/              各任务
docs/                                      设计、验证手册、本文                 协调者
```

「T0」是契约层，由协调者维护，其他任务不改（见 AGENTS.md §2）。

---

## 3. CLI 内部结构

### 3.1 分层与依赖方向

```
第 4 层  cli.py ──► commands/*            命令：解析参数、编排、打印
第 3 层  gates/*        policies/*         判定：返回 Finding / 拦截原因，不打印
第 2 层  router  locate  taskstate         推导：纯函数或只读
第 1 层  meta  config  gitutil  mdparse  retro  grants     领域模块：读写一种东西
第 0 层  errors  project  paths  frontmatter               基础：无业务
```

**只允许往下 import**，同层之间只允许第 1 层内部互相引用（如 grants 用 retro）。具体约束：

- gates 不 import commands、policies；policies 可以 import gates（gate_router 要跑 gate）。
- 除 `gitutil` 外，任何模块不直接调用 git；除 `mdparse` 外，任何模块不解析 markdown 结构。
- 只有 commands 打印输出、决定退出码。gates 的输出和退出码统一由 `gates/__init__.py` 生成。

### 3.2 模块一览

| 模块 | 职责 | 对外接口（详见代码 docstring） | 归属 |
| --- | --- | --- | --- |
| `errors` | 退出码、用户可见的失败 | `OK/ERROR/WARN/BLOCK`、`fail()`、`unavailable()` | T0 |
| `project` | `.openspec/` 布局、工件文件名 | `Project`、`find_root()`、文件名常量 | T0 |
| `paths` | `REINS_HOME` | `reins_home()` | T0 |
| `frontmatter` | skill / agent 头部解析 | `parse()` | T0 |
| `config` | `.config.json` 与默认值 | `load()`、`gate_level()`、`DEFAULTS` | T0 |
| `meta` | `.meta.json` 读写与加锁 | `PHASES`、`GATES`、`new/load/save/update/lock` | T2 |
| `gitutil` | git 调用 | `git/head/current_branch/changed_files/commits/user_name` | T2 |
| `mdparse` | markdown 结构解析 | `parse/find/find_all/ids/tables/checkboxes`、`ALIASES`、`ID_PATTERNS` | T1 |
| `retro` | retrospective.md 三张表 | `Waiver`、`waivers()`、`todos()`、`append_waiver/append_tier_change/add_todo` | T6 |
| `grants` | 放行 / 降档一次性授权的存取 | `match_phrase()`、`issue()`、`consume()` | T6 |
| `router` | Phase 路由 | `next_phase()`、`skip_reason()`、`review_rounds()` | T2 |
| `locate` | 定位当前 change | `resolve()` | T2 |
| `taskstate` | 任务完成状态（来自 Task-Id trailer） | `done_tasks()`、`render()`、`open_tasks()` | T2 |
| `gates/__init__` | gate 框架 | `Finding`、`GateContext`、`evaluate()`、`render()`、`to_json()` | T0 |
| `gates/g*` | 14 道门的检查 | `check(ctx) -> List[Finding]` | T3 / T4 / T5 / T7 |
| `policies/__init__` | hook 判定链 | `PRE_TOOL`、`PROMPT`、`pre_tool()`、`prompt()` | T0 |
| `policies/*` | 各条 hook 规则 | `pre_tool(ev)` 或 `prompt(ev)` | T6 |
| `hook` | 平台事件 ⇄ 判定链 | `normalize()`、`run()` | T0（`normalize` 字段 T6 可追加） |
| `commands/*` | 子命令 | `register(sub)`、`run(a) -> int` | 见 `commands/__init__.py` |

### 3.3 核心契约

**命令**：`commands/<名>.py` 暴露 `register(sub)` 和 `run(a) -> int`。`cli.py` 按 `commands/__init__.py` 的 `COMMANDS` 自动注册，加命令不改 `cli.py`。参数由命令模块自己定义。

**退出码**：`0` 成功 / 放行，`1` 错误或能力不可用，`2` 仅告警，`3` 拦截。总控 skill 按这四个值分支，任何命令不得挪作他用。

**gate**：

```python
Finding(level="BLOCK", check="ac-mapped", reason="AC-3 没有映射到任何 SC",
        location="spec.md:12", fix="为 AC-3 补一个 SC", evidence="AC-3", locked=False)
```

- `gates.evaluate(gate, ctx)` 依次做：跳过的 Phase 直接放行 → 调 `check()` → 算指纹 → 按 `gates.<id>.level` 调整未锁定的 BLOCK → 匹配 retrospective 的放行记录（gate + check + 指纹）→ 算退出码。
- 指纹 = `sha1(gate, check, evidence 或 reason)` 前 8 位。所以 `evidence` 必须稳定：内容变了指纹才变，行号变了指纹不能变。
- `locked=True`：防自欺类检查（业务取值来源、subagent 标记、uatAccepted）和 gate-6.7，配置不能降级，只能人工放行。
- `ctx.extra` 放 gate 专用输入，目前只有 gate 6 的 `{"task": "T3"}`。

**hook 事件**（`hook.normalize()` 产出，policy 的唯一输入）：

| 字段 | 含义 |
| --- | --- |
| `runtime` | `claude` / `codex` / `opencode` |
| `event` | 平台事件名，或 `pre-tool` / `prompt-submit` |
| `tool`、`kind` | 工具名；`shell` / `edit` / `other` |
| `paths` | 编辑类工具涉及的文件，正斜杠 |
| `command` | shell 命令字符串 |
| `prompt` | 用户原文（只在内存里，不写日志） |
| `cwd` | 事件发生的目录 |
| `agent` | 子 agent 名（去掉 `reins:` 前缀）；主线程或平台不提供时为空。目前只有 Claude Code 提供（`agent_type`），Codex、OpenCode 的 PreToolUse 不带 |

新增事件字段只能在 `normalize()` 里追加，并先确认三个平台 payload 里的真实字段名。

**hook 输出**：pre-tool 拦截时，claude / codex 在 stdout 输出 `permissionDecision: deny` 的 JSON、退出码 0；opencode 退出码 2、原因写 stderr。prompt-submit 的提示经 `additionalContext` 返回。policy 不关心这些，只返回字符串。

**`.meta.json`**：字段和取值见设计文档 §3.2，`meta.new()` 按它生成。只有 `meta.update()` 能写，且必须在锁内完成。

**retrospective.md**：三张表的列固定（见 `retro.py` 顶部），只能追加，只有 CLI 写。每次写入同时记录内容哈希（`.retro.sha256`），git pre-commit 据此拒绝手工改动。它是 CLI 自己写的固定格式，`retro` 自带只认这种格式的读取逻辑，是「只有 mdparse 解析 markdown」规则的唯一例外。

**授权**：只有 `policies/waive_grant` 在用户原文完整匹配口令、且确认的对象真实存在（当前未放行的 BLOCK，或低于已确认档位的降档）时签发。放行授权绑定该检查项全部 BLOCK 的指纹，内容变了就要重新确认。`waive` 和 `complexity set --downgrade` 必须 `grants.consume()` 成功才执行；`waive` 在真实终端（TTY）里还可以让用户输入 change 名确认，作为没有提示词 hook 的平台的退路。

---

## 4. 两类 markdown 的约定

**工件**（用户项目里的 proposal.md、spec.md …）：模板在 `spec-driven-dev/templates/`，标题别名在 `mdparse.ALIASES`，二者由 T1 同步维护。写工件的 skill 按模板写，读工件的 gate 按别名找，谁都不自创格式。

**插件内容**（SKILL.md、agents/*.md）：

- frontmatter 只用 `frontmatter.py` 支持的子集。agent 必须同时写 `tools`（Claude Code）和 `access`（Codex、OpenCode 换算），`tests/test_plugin.py` 校验一致。
- 入口 skill 设 `disable-model-invocation: true` 时只能用户触发；总控设了 `user-invocable: false`，只能模型触发。
- skill 调 CLI 的写法：`<spec-driven-dev skill 目录>/scripts/spec-driven <命令>`。

### 4.1 跨任务共用格式（契约）

凡是「一个任务写、另一个任务读」的格式都在这里定义，写的一方和读的一方都以本节为准，不以对方的实现为准。要改格式，先改本节（协调者），再各自跟进。

| 格式 | 写的一方 | 读的一方 |
| --- | --- | --- |
| 评审报告（§4.2） | T9 的 agent 与报告模板 | T4 的 gate 5 / 7 / 8 |
| 提交 trailer（§4.3） | T8 的 tdd-implement、T9 的 implementation-generator | T2 的 taskstate、T6 的 commit-msg、T5 的 gate 6 |
| 静态分析报告（§4.4） | T5 的 gate 6.7 | T9 的 code-reviewer |

骨架模板在 `spec-driven-dev/templates/reports/`，由协调者维护结构，T1 的模板测试校验它们与 ALIASES 一致。

标题一律经 `mdparse.find()` 按下文给出的 ALIASES 键查找，表格一律经 `mdparse.tables()` 读取。

### 4.2 评审报告：spec-review.md / qa-report.md / code-review.md

三份报告的骨架相同：

```markdown
<!-- generated-by: code-reviewer-subagent -->
# Code Review: <change-name>

## 结论

| BLOCK | WARN | INFO |
| --- | --- | --- |
| 1 | 2 | 0 |

## 问题清单

| 级别 | 位置 | 问题 | 建议 |
| --- | --- | --- | --- |
| BLOCK | src/main/java/…/OrderService.java:42 | 批量审批没有校验状态 | 调用前检查 PolicyStatus |
| WARN | … | … | … |
```

- **首行**：第一个非空行必须恰好是 `<!-- generated-by: <agent 名>-subagent -->`，agent 名为 `spec-evaluator`、`qa-evaluator`、`code-reviewer`。
- **标题**：`# Spec Review` / `# QA Report` / `# Code Review`，冒号后是 change 名。
- **`## 结论`**（ALIASES 键 `conclusion`）：只有一张表，表头恰好是 `BLOCK | WARN | INFO`，一行，三个非负整数。
- **`## 问题清单`**（键 `findings`）：只有一张表，表头恰好是 `级别 | 位置 | 问题 | 建议`；「级别」只能是 `BLOCK`、`WARN`、`INFO`；「位置」写 `文件:行` 或 `-`。没有问题时保留表头、不写数据行。
- **一致性**：结论表的三个数必须等于问题清单里对应级别的行数。
- **qa-report 另有 `## SC 验证结果`**（键 `sc-results`）：表头恰好是 `SC | 结果 | 证据`；spec.md 里每个 SC 一行；「SC」只写 ID（如 `SC-policy-approval-001`），「结果」只能是 `PASS` 或 `FAIL`。
- **spec-review 在 bugfix 模式下另有 `## bugfix 升级判定`**（键 `bugfix-upgrade`）：第一个非空行恰好是 `保持 bugfix` 或 `应升级 design`。
- **其他小节**（评审范围、说明等）可以自由写，gate 不读。报告里其他地方出现 `[BLOCK]` 之类文字不计数。
- **读取规则（gate）**：
  - 以上任何必需的小节、表格、表头缺失或取值不合法，都是 BLOCK，原因写清楚哪一项不合格。不能当成「0 个问题」放行。
  - 结论表与问题清单的计数不一致是 BLOCK。
  - gate 8 的「WARN 已进待优化清单」：问题清单里每个 WARN 行的「问题」原文，都必须作为一条内容出现在 `retro.todos()` 里（完全相等）。总控对每条 WARN 执行 `spec-driven retro add --source "code-review WARN" "<问题原文>"`。
- **多轮评审**（L 档 spec 评审两轮）：每轮覆盖写同一个文件，gate 只看最新内容。

### 4.3 提交 trailer

- **`Task-Id: <任务 ID>`**：任务 ID 为 `T<数字>` 或 `T-regression`，一个提交涉及多个任务时用逗号分隔（`Task-Id: T3, T4`）。Phase 6 里改动了 `.openspec/` 以外文件的提交必须带（commit-msg hook 强制）。
- **`TDD-Phase: RED | GREEN | REFACTOR`**：RED 提交必须带 `TDD-Phase: RED`（兼容标题以 `RED:` 开头的写法）；GREEN、REFACTOR 建议带。
- **完成判定**：任务完成 = 自 `baseCommit` 以来存在带该 `Task-Id` 的非 RED 提交（`taskstate.done_tasks()`）。RED 提交只证明测试先于实现，不算完成。
- trailer 写在提交信息最后一段，与正文空一行，按 `git interpret-trailers` 的规则解析。

### 4.4 静态分析报告：static-analysis-report.md

由 gate 6.7 生成（CLI 写入，不是 agent 产出），code-reviewer 在 Phase 8 先读它，已被机器抓到的问题不重复标记。

```markdown
<!-- generated-by: spec-driven gate-6.7 -->
# Static Analysis: <change-name>

## 结论

| 新增 | 存量 | 已偿还 |
| --- | --- | --- |
| 2 | 15 | 1 |

## 新增违规

| 检查 | 规则 | 位置 | 说明 |
| --- | --- | --- | --- |
| checkstyle | LineLength | src/main/java/…/A.java:12 | 行长 132 > 120 |

## 存量违规

（同上表头）

## 已偿还

（同上表头）
```

- ALIASES 键：`conclusion`、`new-violations`（新增违规）、`baseline-violations`（存量违规）、`repaid-violations`（已偿还）。
- 「检查」取值：`archunit`、`checkstyle`、`spotbugs`、`pmd`、`sqlfluff`，与 `.config.json` 的 `quality.<检查>` 键一致。
- **告警级违规**：工具把某条规则标为告警（如 SQLFluff 的 `warnings` 配置）时，新增的这类违规仍列在「新增违规」表里，但「说明」列以 `[WARN] ` 开头；gate 6.7 对它们给 WARN、不拦截，也不计入结论表的「新增」数。存量和已偿还的判定与其他违规相同。
- **新增的判定按数量**：同一指纹（检查 + 文件 + 规则 + 规范化消息）的违规，当前数量多于基线数量时，多出的部分算新增；少于基线时，少掉的部分算已偿还。

### 4.5 用户决策命令

用户做的决定由总控经这些命令落盘，总控不直接改 `.meta.json` / `retrospective.md`。需要授权的命令，没有授权就拒绝并说出口令；授权由 `policies/waive_grant` 在用户原样输入口令时签发（与放行同一机制，§3.3）。

| 命令 | 何时用 | 授权 | 效果 |
| --- | --- | --- | --- |
| `spec-driven uat accept` | Phase 8.9，用户看完验收摘要表示通过 | 用户输入 `确认验收 <change 名>`；授权绑定当时 spec.md 与 qa-report.md 的内容，之后二者变化须重新确认 | 写 `uatAccepted=true` 与时间；retrospective「用户验收记录」追加一行 |
| `spec-driven uat reject --phase N --reason "…"` | Phase 8.9，用户要修改 | 不需要 | 记入「用户验收记录」，然后等同 `retry N` |
| `spec-driven scope set --files N [--cross-service] [--ddl] [--public-api]` | bugfix 模式、Phase 1，用户确认 bugfix-analysis 之后 | 不需要 | 写 `.meta.json` 的 `bugfixScope`，决定 Phase 2 / 3 是否跳过；输出跳过判定 |
| `spec-driven scope show` | 任意时刻 | 不需要 | 显示当前评估与跳过判定 |
| `spec-driven deploy skip --reason "…"` | Phase 8.5，用户选择不做部署验收 | 不需要 | Phase 8.5 标为跳过并记下理由，进入 Phase 8.9；retrospective「部署验收记录」追加一行 |

- 以上命令都接受 `--change`；Phase 不对时拒绝并说明当前 Phase。
- `uat accept` 在真实终端（TTY）里也可以让用户输入 change 名确认，作为拿不到用户消息时的退路，与 `waive` 一致。
- 理由（`--reason`）只能来自用户原话。

---

## 5. 按场景开发

| 我要… | 改哪里 | 必须同时做 |
| --- | --- | --- |
| 实现一道 gate | `gates/g<id>.py` 的 `check()` | 每个 check 一组合格 / 不合格 fixture；需要的章节别名向 T1 要 |
| 实现一个命令 | `commands/<名>.py` 的 `run()` | 退出码遵守 §3.3；用 `locate.resolve()` 定位 change，`meta.update()` 改状态 |
| 实现一条 hook 规则 | `policies/<名>.py` | 拦截 / 放行 / 异常输入三类测试；1 秒内返回 |
| 加一个配置项 | `config.DEFAULTS` 追加 | 交付说明里写键名、默认值、含义 |
| 写一个子 skill | `skills/<名>/SKILL.md` | 按 templates/ 写工件；结束时交回总控跑 gate |
| 写一个 agent | `agents/<名>.md` | `tools` 与 `access` 一致；报告首行 generated-by 标记 |
| 改契约 | 不要改 | 在交付说明里提，由协调者改 |

---

## 6. 测试与调试

- 全部测试：`python3 -m unittest discover -s tests -t .`；`tests/test_contracts.py` 守护本文 §3 的结构，改坏契约会直接失败。
- 在临时项目里跑 CLI：`cd <临时目录> && <仓库>/reinsdev-plugin/skills/spec-driven-dev/scripts/spec-driven <命令>`。
- 设 `REINS_HOME=<临时目录>`，hook 日志和授权都写到那里，不碰真实的 `~/.reins`。
- hook 日志：`$REINS_HOME/logs/hooks.jsonl`，每次调用一行；policy 抛异常时记在 `policyErrors`。
- 模拟 hook：`echo '<JSON>' | spec-driven hook pre-tool --runtime claude`，JSON 形状见 `tests/test_hook.py`。
- gate 的机器可读输出：`spec-driven gate <id> --json`。

---

## 7. 术语

| 术语 | 含义 |
| --- | --- |
| change | 一个需求或缺陷的完整工件集，目录 `.openspec/changes/<change>/` |
| Phase | 工件链的一个阶段（0–9，含 8.5、8.9）；gate 6.5、6.7 是 Phase 6 的子门 |
| 档位 | S / M / L，决定哪些 Phase 跳过、评审几轮 |
| 冻结 | 进入 Phase N 后，更早 Phase 的工件只读，要改走 `retry` |
| 放行 | 用户本人确认某个 BLOCK 可接受，记入 retrospective.md，按指纹绑定 |
| 授权 | 用户输入口令后签发的一次性凭据，放行和降档必须消费它 |
| 指纹 | 拦截内容的哈希；内容变了放行就失效 |
| generated-by 标记 | 评审报告首行 `<!-- generated-by: <agent>-subagent -->`，证明由独立 agent 产出 |
| 协调者 | 维护契约层（T0）和文档、合并各任务的人 |
