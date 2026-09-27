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
| `grants` | 放行 / 降档一次性授权 | `WAIVE_PHRASE`、`issue_from_prompt()`、`consume()` | T6 |
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

T6 需要子 agent 身份等字段时，在 `normalize()` 里追加，并确认三个平台 payload 里的真实字段名。

**hook 输出**：pre-tool 拦截时，claude / codex 在 stdout 输出 `permissionDecision: deny` 的 JSON、退出码 0；opencode 退出码 2、原因写 stderr。prompt-submit 的提示经 `additionalContext` 返回。policy 不关心这些，只返回字符串。

**`.meta.json`**：字段和取值见设计文档 §3.2，`meta.new()` 按它生成。只有 `meta.update()` 能写，且必须在锁内完成。

**retrospective.md**：三张表的列固定（见 `retro.py` 顶部），只能追加，只有 CLI 写。

**授权**：只有 `policies/waive_grant` 在用户原文完整匹配口令时签发；`waive` 和 `complexity set --downgrade` 必须 `grants.consume()` 成功才执行。

---

## 4. 两类 markdown 的约定

**工件**（用户项目里的 proposal.md、spec.md …）：模板在 `spec-driven-dev/templates/`，标题别名在 `mdparse.ALIASES`，二者由 T1 同步维护。写工件的 skill 按模板写，读工件的 gate 按别名找，谁都不自创格式。

**插件内容**（SKILL.md、agents/*.md）：

- frontmatter 只用 `frontmatter.py` 支持的子集。agent 必须同时写 `tools`（Claude Code）和 `access`（Codex、OpenCode 换算），`tests/test_plugin.py` 校验一致。
- 入口 skill 设 `disable-model-invocation: true` 时只能用户触发；总控设了 `user-invocable: false`，只能模型触发。
- skill 调 CLI 的写法：`<spec-driven-dev skill 目录>/scripts/spec-driven <命令>`。

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
