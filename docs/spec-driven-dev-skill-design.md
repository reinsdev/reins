# spec-driven-dev Skill 实现方案

2026-09-26 · @Ronnie

`spec-driven-dev` 是 Reins 工件链的总控 skill：它不亲自写需求、设计或代码，只负责**建 change、路由 Phase、调度子 skill / subagent、跑验证门、做用户验收和归档**。本方案给出它的文件结构、状态模型、调度协议和验证门实现。

**适用范围：只支持 Java 项目**（Maven 或 Gradle 构建）。测试、覆盖率、静态质量等检查都只按 Java 工具链实现，不做其他语言的通用化。

相关文档：

- 《Reins 概要设计文档》（claude.ai artifact）——范围与总体取舍
- `spec-driven-workflow.md`（工作流指南）——每个 Phase 的详细行为与验证门口径
- `SpecToolChain.md`（PRD）——CLI、hook、安全护栏清单

---

## 1. 职责边界

| 归 spec-driven-dev | 不归 spec-driven-dev（委派） |
| --- | --- |
| Phase 0 建 change、写 `.meta.json` | Phase 1 需求澄清 → `requirements-clarify` / `bugfix` |
| Phase 路由：读 `.meta.json` 决定下一步、跳过哪些 Phase | Phase 2 方案对比 → `tech-design-tradeoff` |
| 复杂度通道：`complexity show/set/recheck`，只升不降 | Phase 3 spec.md → `api-design-rest`（REQ/SC + `## 接口契约`）+ `db-schema-design`（`## 数据模型` + 补 SC 的 DB 后置状态），共写一个文件、按节分工 |
| 调用验证门、解释结果、决定回退 | Phase 4 任务拆分 → `task-breakdown` |
| 调度四个 agent，校验评审者的 `generated-by` 标记，失败重试一次后 STOP | Phase 5/6/7 的实际评审、实现、QA |
| Phase 8.9 用户验收呈报 | Phase 8 code review → `code-reviewer` agent（按 `tiered-code-review` 规范执行） |
| Phase 9 归档：delta 合并进主 specs、ADR 蒸馏、architecture.md 更新提示 | 横切 skill（见 §1.1） |
| `resume` 冷启动恢复、`status` 进度 | 外部集成（日志、部署、Swagger） |

原则：主线只做「调度 + 验证门 + 决策」，不把源码正文和大段 diff 放进主上下文。

### 1.1 清单：17 个 skill + 4 个 agent

**主链 skill（8）**

| Skill | Phase | 职责 |
| --- | --- | --- |
| spec-driven-dev | 总控 | 建 change、Phase 路由、复杂度通道、跑 gate、调度 agent、Phase 8.9 验收、Phase 9 归档（含 ADR 蒸馏） |
| requirements-clarify | 1 | 歧义识别、AC 提取、代码现状扫描 |
| tech-design-tradeoff | 2 | ≥2 方案（L 档 ≥3）对比与明确推荐 |
| api-design-rest | 3a | spec.md 的 REQ/SC 行为主体 + `## 接口契约` |
| db-schema-design | 3b | `## 数据模型` + 补 SC 的 DB 后置状态 |
| task-breakdown | 4 | spec → tasks.md，按层拆分，关联 SC |
| tdd-implement | 6 | TDD 规范载体，由 implementation-generator agent 读取执行 |
| tiered-code-review | 8 | 分级评审规范载体，由 code-reviewer agent 读取执行 |

**变种 skill（1）**：`bugfix`，以 `/bugfix "描述"` 启动，写 bugfix-analysis.md 与 proposal.md，Phase 2/3 条件性瘦身。

**横切 skill（8）**

| Skill | 用途 | 推荐调用点 |
| --- | --- | --- |
| root-cause-analysis | 5 Whys / 鱼骨图根因分析，只分析不修 | Phase 1/6/7 |
| incident-analysis | 线上事故分析，只给建议不操作生产 | incident |
| code-quality-optimize | 早期返回、N+1、圈复杂度、命名、重复、嵌套 | Phase 6 重构后 / Phase 8 前 |
| codegraph | 符号源码 + 调用链 + 影响半径；探测不到就静默回退 Grep/Read | Phase 2/3/6/8 |
| log-search | 读本地日志文件，按时间范围 + 关键字检索，脱敏 | Phase 1/6/7 |
| local-deploy | 本地启动应用，产出 deploy-report.md，交给人工验收 | Phase 8.5 |
| openapi-check | 读本地 Swagger 端点，与 spec.md `## 接口契约` 比对 | Phase 6 实现后 / Phase 8 |
| safety-check | 平台 hook 不可用时显式调用 bash-guard / spec-gate / gate 护栏 | 平台 hook 不可用时 |

**Agent（4）**：spec-evaluator、implementation-generator、qa-evaluator、code-reviewer（见 §5）。

几点归属说明：

- 归档、ADR 蒸馏、architecture.md 更新提示、复杂度评估都由总控完成，不单列 skill。
- 弱测试启发式检查（空断言、`assertNotNull` 兜底、反射测私有方法）在 gate-6 内完成。
- 所有外部集成都是本地化的：日志读本地文件、部署在本机启动、接口比对读本地 Swagger，不依赖任何外部平台或模型服务。

---

## 2. 插件架构：一份插件目录，多运行时

Reins 支持 Claude Code、Codex、OpenCode 三个平台。做法是**一份手写的插件目录，三个平台直接读它**：入口各一份，核心内容只有一份，没有构建步骤。能下沉到 CLI 的逻辑全部下沉到 CLI，平台差异只留在很薄的入口层。

### 2.1 设计原则

1. **逻辑在 CLI，不在平台配置里**：gate、状态、路由、留痕、hook 判定全部实现在 `spec-driven` CLI 中。各平台的 hook 和命令只是一行调用，比如 `spec-driven hook pre-tool --runtime opencode`。
2. **内容只写一份，平台直接读**：skill 用标准 SKILL.md；agent 用 markdown + frontmatter，三个平台读同一个文件。平台读不了的格式在它自己的入口里就地转换（Codex 在 `reinsdev` 安装时转成 toml，OpenCode 在 `index.js` 启动时读取），仓库里不存放任何生成物。
3. **能力缺失时逐级降级，不能静默失效**：每条护栏都标明它在各平台靠什么落实、落不了时退到哪一层（§2.4）。`reinsdev doctor` 会把实际生效情况打印出来。

### 2.2 仓库布局

```
reins/                                   GitHub reinsdev/reins，官网 reinsdev.com
├── .claude-plugin/marketplace.json      # Claude Code marketplace「reinsdev」→ ./reinsdev-plugin
├── .agents/plugins/marketplace.json     # Codex marketplace「reinsdev」→ ./reinsdev-plugin
├── reinsdev-plugin/                     # 插件本身，手写
│   ├── .claude-plugin/plugin.json       # Claude Code 清单，hooks → hooks/claude.json
│   ├── .codex-plugin/plugin.json        # Codex 清单，skills → skills/，hooks → hooks/codex.json
│   ├── hooks/claude.json  codex.json    # 两个平台的 hook，都转调 spec-driven hook <event>
│   ├── package.json  index.js           # OpenCode：npm 包 @reinsdev/opencode 与插件入口
│   ├── skills/spec-driven-dev/          # 总控 SKILL.md + scripts/（spec-driven CLI）
│   │   └── scripts/lib/spec_driven/     # cli / hook / status / frontmatter / paths
│   ├── skills/spec/  skills/bugfix/     # 入口 skill：/spec、/bugfix（Codex 为 $spec、$bugfix）
│   └── agents/<name>.md                 # frontmatter：name / description / tools / role / access / report / model
├── tests/                               # CLI 与插件结构的测试
├── tools/reinsdev/  bin/reinsdev        # 安装工具：install / update / uninstall / doctor / setup
├── install.sh  install.ps1              # 一行命令安装入口
└── .github/workflows/ci.yml             # Linux / macOS / Windows × Python 3.8 / 3.12
```

**两个命令行工具分工**：`spec-driven` 是给使用者的工件链 CLI，只含运行时命令，就放在插件内；`reinsdev` 是 Reins 仓库自己的开发工具，只负责把本仓库的插件装到本机各平台，不进插件。

**CLI 在插件内**：`reinsdev-plugin/skills/spec-driven-dev/scripts/` 下有 `spec-driven`（sh）、`spec-driven.cmd`、`spec-driven.py` 和 `lib/spec_driven/`，原生安装不需要额外装 CLI。hook 通过平台提供的插件根目录变量调用它：Claude Code 用 `${CLAUDE_PLUGIN_ROOT}`，Codex 用 `${PLUGIN_ROOT}`；OpenCode 的 index.js 按自身位置找。

**平台差异的落点**：

| 内容 | Claude Code | Codex | OpenCode |
| --- | --- | --- | --- |
| skills | 直接读 | 直接读 | `index.js` 把 `skills/` 加进 `skills.paths` |
| agents | 直接读，用 frontmatter 的 `tools` | `reinsdev` 安装时转成 toml 写入 `~/.codex/agents/`，用 `access` 算出 `sandbox_mode` | `index.js` 启动时读取，用 `access` 算出 `permission` |
| 入口 | skill `spec`、`bugfix` | 同一对 skill，用 `$spec`、`$bugfix` 调用 | `index.js` 读取两个入口 skill，注册为 `/spec`、`/bugfix` 命令 |
| hook | `hooks/claude.json` | `hooks/codex.json`（多一个 `commandWindows`） | `index.js` 的 `tool.execute.before` |

总控 SKILL.md 用一张表写明三个平台各自调度子 agent 的方式，由模型按所在平台选用。

agent 的工具权限用**能力级别**（`access`）描述；Claude Code 直接读的 `tools` 必须与它一致，由单测检查：

| 能力级别 | 含义 | Claude Code `tools` |
| --- | --- | --- |
| `read` | 读文件、搜索 | `Read, Grep, Glob` |
| `shell-readonly` | 可以跑测试、git log/diff，修改类命令由 hook 或 git 层拦截 | `Bash` + bash-guard 规则 |
| `write-own-report` | 只能写自己的报告文件 | `Write` + spec-gate 路径锁 |
| `write` | 可写代码，禁写 `.openspec/`、禁删测试 | `Read, Grep, Glob, Edit, Write, Bash` + spec-gate |

### 2.3 平台能力对照（按官方文档核实）

结论：三个平台都支持 SKILL.md、子 agent、工具调用前 hook，Reins 的核心设计在三个平台上都能落地。差异集中在**入口命令、插件打包、hook 挂在哪里**三处，另有一个已知缺陷需要实测。

| 能力 | Claude Code | Codex | OpenCode |
| --- | --- | --- | --- |
| Skill（SKILL.md） | 支持 | 支持：`.agents/skills/`、`~/.agents/skills/`；`$名称` 或 `/skills` 调用 | 支持：`.opencode/skills/`，**也直接读 `.claude/skills/` 和 `.agents/skills/`**；由模型调 `skill` 工具加载 |
| 斜杠命令 | 支持：`commands/*.md` | **不支持**：自定义 prompt 已被官方废弃，官方建议改用 skill | 支持：`.opencode/commands/*.md`，`$ARGUMENTS` |
| 子 agent 定义 | `agents/*.md` | `.codex/agents/*.toml`（name、description、developer_instructions、model、sandbox_mode） | `.opencode/agents/*.md`，`mode: subagent` |
| 子 agent 限权 | `tools` / `disallowedTools` | **只有沙箱级别**：`sandbox_mode = "read-only"` 连报告也写不了，细粒度要靠 hook | `permission`：read / edit / bash 等逐项 allow / ask / deny，bash 支持命令通配 |
| 子 agent 触发 | 主线调用 Agent 工具 | 用户或 skill 指令**明确要求**时才派生 | 主线调 `task` 工具，或用户 `@名称` |
| 工具调用前 hook | PreToolUse，可拦截 | PreToolUse，覆盖 Bash、`apply_patch`（改文件）、MCP、`spawn_agent`；exit 2 或 `decision: block` 拦截 | JS 插件的 `tool.execute.before`，throw 即拦截 |
| 用户输入 hook | UserPromptSubmit | UserPromptSubmit，可拦截 | 无同名事件，可用消息事件近似（需实测） |
| 插件打包 | plugin + marketplace | plugin：`.codex-plugin/plugin.json`，可带 skills、hooks、MCP，**不含 agents**；`codex plugin marketplace add` 安装 | npm 包或 `.opencode/plugins/` 目录 |

**已知缺陷（需实测）**

**OpenCode 子 agent 绕过 hook**：`tool.execute.before` 可能拦不住经 `task` 派生的子 agent 的工具调用（[#5894](https://github.com/sst/opencode/issues/5894)，issue 已关闭，修复情况未确认）。如果未修复，implementation-generator 的路径锁在 OpenCode 上只能靠 agent 的 `permission` 和 git 层。

**对设计的影响**

- **入口**：`/spec` 在 Claude Code、OpenCode 上构建为命令；在 Codex 上构建为名叫 `spec` 的入口 skill，用 `$spec` 调用。`bugfix` 本身已经是 skill，直接兼任入口。
- **Codex 评审者写报告**：用 `sandbox_mode = "workspace-write"`，再由 PreToolUse hook 拦截 `apply_patch`，把可写路径锁到自己的报告文件。不能用 `read-only`，否则报告写不出来。Codex 插件不打包 agents，agent 的 TOML 由安装脚本复制到 `.codex/agents/`。
- **OpenCode 的 skill 目录**：它能直接读 `.claude/skills/`，但 Reins 仍统一安装到 `.opencode/skills/`，避免和 Claude Code 那份 skill 重复加载。

来源：[Codex Skills](https://learn.chatgpt.com/docs/build-skills)、[Codex Hooks](https://learn.chatgpt.com/docs/hooks)、[Codex Subagents](https://learn.chatgpt.com/docs/agent-configuration/subagents)、[Codex Plugins](https://developers.openai.com/codex/plugins/build)、[Codex 自定义 prompt 失效](https://github.com/openai/codex/issues/15941)、[OpenCode Agents](https://opencode.ai/docs/agents/)、[OpenCode Plugins](https://opencode.ai/docs/plugins/)、[OpenCode Commands](https://opencode.ai/docs/commands/)、[OpenCode Skills](https://opencode.ai/docs/skills/)。

### 2.4 护栏的三层落实与降级

每条关键护栏都尽量落在**不依赖平台**的层上，平台 hook 只作为额外的一层：

| 护栏 | 第 1 层：CLI 自身（所有平台） | 第 2 层：git hook（所有平台） | 第 3 层：平台 hook（有则用） |
| --- | --- | --- | --- |
| 验证门 | 总控主循环显式调用 `spec-driven gate` | pre-commit：当前 Phase 的 gate 未通过时拒绝提交 | 用户输入关键字时自动触发 gate-router |
| 上游冻结 / 路径锁 | gate 比对冻结工件的 hash，被改动即 BLOCK | pre-commit：拒绝提交对冻结工件和 retrospective.md 的非 CLI 改动 | 编辑前直接拦截（spec-gate） |
| 只有用户能豁免 / 降档 | `waive` 和 `complexity set --downgrade` 必须消费一次性授权，否则拒绝执行（§6.6） | commit-msg：没有 CLI 签名的 retrospective 改动拒绝提交 | UserPromptSubmit 只在用户本人输入确认口令时签发授权；编辑前 hook 禁止模型改动授权文件。没有提示词 hook 的平台退回终端 TTY 确认 |
| 评审者隔离 | — | — | 有「子 agent + 工具限制」时用子 agent；没有时退为**另起一个无头进程**跑评审（如 `claude -p`、`codex exec`、`opencode run`），用只读沙箱，报告仍经 `generated-by` 标记校验 |
| Task-Id / 测试真跑 | gate-6 / gate-6.5 读 git 历史判定 | commit-msg 校验 trailer | — |

`reinsdev doctor` 逐条输出「这条护栏在当前平台由哪一层落实」。某条护栏只剩第 1 层时，要明确打印提示，不能默默降级。

### 2.5 构建、发布与安装

命名：插件名 `reins`，发布命名空间 `reinsdev`。Claude Code 与 Codex 的 marketplace 名为 `reinsdev`，插件 ID 为 `reins@reinsdev`；GitHub 仓库 `reinsdev/reins`；OpenCode 的 npm 包 `@reinsdev/opencode`；官网 reinsdev.com。

**用户安装：一行命令（推荐）**

`curl -fsSL https://raw.githubusercontent.com/reinsdev/reins/main/install.sh | sh`（Windows：`irm .../install.ps1 | iex`）。脚本把仓库 clone 到 `~/.reins/src`，在 `~/.reins/bin` 生成 `reinsdev` 启动器，然后运行 `reinsdev install` 和 `reinsdev doctor`：以这份 clone 为本地 marketplace 给检测到的平台装插件，Codex 的 agents 一并转换安装，OpenCode 写一个转引 `index.js` 的插件文件。三个平台由同一份源码安装，`reinsdev update` 拉取并重装，`reinsdev uninstall` 按 `~/.reins/installed.json` 精确撤销。

用户可见的命令分两类：安装阶段只用 `reinsdev`；使用阶段只用 `/spec`、`/bugfix`、`/waive`。插件内的 `spec-driven` 由总控和 hook 调用，用户看不到。`reinsdev` 不随插件分发。

**用户安装：原生命令（不装 reinsdev）**

| 平台 | 安装 | 入口 |
| --- | --- | --- |
| Claude Code | 会话里 `/plugin marketplace add reinsdev/reins`，`/plugin install reins@reinsdev` | `/spec`、`/bugfix`、`/waive` |
| Codex | `codex plugin marketplace add reinsdev/reins`，`codex plugin add reins@reinsdev`；agents 用 `reinsdev setup codex` 安装，缺少时总控请用户运行 | `$spec`、`$bugfix`、`$waive` |
| OpenCode | `opencode plugin @reinsdev/opencode -g`，或写进 `opencode.json` 的 `plugin` 数组 | `/spec`、`/bugfix` |

一个仓库同时充当 Claude Code 和 Codex 的 marketplace：两个平台读取根目录下各自的 marketplace 文件，都指向 `./reinsdev-plugin`，互不干扰。OpenCode 的 index.js 在 `config` 钩子里注入 agents、commands 和 skills 路径，所以一个 npm 包就是完整安装。

**发布流程**

- Claude Code / Codex / 一行命令：推送到 GitHub `main` 即发布。原生安装的 marketplace 直接读取仓库里的 `reinsdev-plugin/`，一行命令安装的用户用 `reinsdev update` 拉取。
- npm：在 `reinsdev-plugin/` 下 `npm publish --access public`；`package.json` 的 `files` 只收录 `index.js`、`agents/`、`skills/`，并排除 `__pycache__`。
- 版本号出现在 `spec_driven.VERSION`、两份 `plugin.json`、`package.json` 和 Claude marketplace，单测检查它们一致。

**本地试装**：在仓库里运行 `./install.sh`（或 `.\install.ps1`）走的是同一个脚本，只是不 clone，直接以工作区为源码安装。覆盖非 Reins 文件前整体拒绝，不会留下半安装状态。

**Windows 支持**：只用 Python 3.8+ 标准库和 POSIX sh（Git Bash），不依赖任何 macOS 或 Linux 特有功能。

- 启动器：sh 版依次尝试 `python3`、`python`、`py -3`；cmd 版依次尝试 `py -3`、`python`、`python3`。每个候选都先实际执行一次版本检查，以识别微软商店的 `python3` 空壳。
- 路径传递：只用脚本路径参数，不用 `PYTHONPATH`（Git Bash 对路径列表的转换不可靠）。
- 编码：所有文件读写和子进程输出一律 UTF-8；标准输入输出重设为 UTF-8，中文 Windows 下 hook 输出不会乱码。
- 换行：`.cmd` / `.ps1` 用 CRLF，其余文件用 LF，由 `.gitattributes` 固定，不受 `core.autocrlf` 影响。
- 外部命令：先用 `shutil.which` 解析出 `claude.cmd` / `codex.cmd` 的完整路径再执行。
- 路径比较：hook 把所有路径统一成 `/` 分隔。
- 文件锁：用 `os.open(O_CREAT | O_EXCL)` 创建锁文件，加超时和过期清理，不用 Windows 上没有的 `fcntl`。
- hook 在 Windows 上的执行方式（已查证）：
  - **Claude Code**：用 Git Bash 执行 hook 命令，没有 Git Bash 时退回 cmd.exe（[claude-code#59225](https://github.com/anthropics/claude-code/issues/59225)）。所以 Windows 用户必须装 Git for Windows；doctor 会检查。
  - **Codex**：优先用 `commandWindows`，经会话 shell（通常是 `pwsh -NoProfile -Command`）执行。Reins 的 `commandWindows` 用 PowerShell 语法 `& "$env:PLUGIN_ROOT\...\spec-driven.cmd" ...`。`-Command` 会把原生命令的非零退出码一律变成 1，exit 2 拦不住（[codex#48183](https://github.com/openai/codex/issues/48183)，未修复）。
  - **因此拦截统一用 JSON**：Claude Code 和 Codex 的 hook 在拦截时输出 `hookSpecificOutput.permissionDecision = "deny"` 并以 0 退出，这是两个平台官方推荐的写法，不依赖退出码。OpenCode 由我们自己的 JS 插件读取子进程退出码，仍用 exit 2。
  - **已知平台缺陷**：Codex 选中商店版 pwsh 时 hook 会报 os error 5 而失效（[codex#47810](https://github.com/openai/codex/issues/47810)，未修复）。doctor 检测到时给出规避方法。
- Linux（已实测）：Debian 12（dash，Python 3.8）与 Alpine 3.24（busybox sh，Python 3.12）上单测、三个启动器、hook 拦截、`setup codex` 全部通过；没有 Python 时 hook 放行、其他命令失败。

---

## 3. 状态模型

### 3.1 工件目录

工件统一放在项目根 `.openspec/` 下：

```
.openspec/
├── .config.json                 # 团队级配置（gate 级别、可选能力开关）
├── specs/<capability>.md        # 主 specs（归档合并目标）
├── specs/README.md              # 能力索引
├── decisions/NNNN-<slug>.md     # ADR
├── architecture.md
└── changes/
    ├── <change>/
    │   ├── .meta.json
    │   ├── invariants.json      # 业务取值 / 字段映射 / 环境备忘，跨压缩注入
    │   ├── proposal.md  design.md  spec.md  tasks.md
    │   ├── spec-review.md  implementation-log.md  qa-report.md  code-review.md
    │   └── retrospective.md     # 过程留痕：人工豁免、待优化清单、验收与部署结论；首次需要时创建
    └── archive/<YYYY-MM-DD>-<change>/
```

### 3.2 `.meta.json`

```json
{
  "change": "batch-approve-policy",
  "mode": "feature",
  "source": null,
  "defect_code": null,
  "complexity": "M",
  "tierConfirmed": false,
  "phase": "1",
  "phaseStatus": {"0": "passed", "1": "in_progress"},
  "skipped": {"2": null, "3": null},
  "designDecision": null,
  "branch": "feat/batch-approve-policy",
  "baseCommit": "d4267c5",
  "uatAccepted": false,
  "uatAcceptedAt": null,
  "staleFrom": null
}
```

- `phaseStatus` 取值：`pending / in_progress / passed / skipped / stale`。回退时把下游全部置 `stale`，即工作流指南「阶段间回退机制」中的「后续工件标记待重新评审」。
- `complexity` / `tierConfirmed` 只记当前档位。档位的每次变更（Phase 1 末尾选定、Phase 2/3 复评升档、PM 手动降档）都经 `spec-driven complexity set` 写入 `retrospective.md` 的「档位变更记录」表：

  ```markdown
  ## 档位变更记录

  | 时间 | Phase | 变更 | 类型 | 理由 | 确认人 |
  | --- | --- | --- | --- | --- | --- |
  | 2026-09-26 10:15 | 1 | M → M | 选定 | 推荐档，用户确认 | ronnie |
  | 2026-09-27 16:40 | 3 | M → S | 降档 | 只改一个查询条件，接口与表不变 | ronnie |
  ```

- 降档和覆盖率豁免同等对待：用户本人输入确认口令后，总控才能执行 `complexity set --downgrade --reason`（§6.6）；选定和升档可以由总控在用户口头确认后执行。
- `baseCommit` 是 Phase 0 建 change 时的 HEAD。增量覆盖率、新增违规、scope 外文件检查都以它为起点比较。
- `.meta.json` 只记录流程状态（当前在哪、下一步去哪），不记录过程留痕。人工确认、豁免、待优化清单这类记录一律写进 `retrospective.md`。
- 所有写入经 `meta.py` 的文件锁（`os.open(O_CREAT | O_EXCL)` 锁文件 + 超时 + 过期清理，三个系统行为一致），即 PRD 中的「.meta.json 并发锁」。

### 3.3 Phase 状态机

```
0 → 1 → [2] → [3] → 4 → [5] → 6 → [7] → 8 → [8.5] → 8.9 → 9
```

`[n]` 是条件 Phase，是否执行由 `router.next_phase(meta)` 决定：

| Phase | S | M | L | bugfix 额外规则 |
| --- | --- | --- | --- | --- |
| 2 | 跳过 | 走 | 走（≥3 方案） | 未跨 ≥3 文件 / 跨服务 / 改 DDL / 改公开 API → 跳过 |
| 3 | 跳过 | 走 | 走 | 不改接口且不改 DDL → 跳过 |
| 5 | 跳过 | 走 | 走 2 轮 | — |
| 7 | 跳过 | 走 | 走 | — |
| 8.5 | 问用户 | 问用户 | 问用户 | — |

跳过的 Phase 写 `skipped.<n> = "<理由>"`，对应 gate 检查理由非空后放行。

---

## 4. SKILL.md 主循环

SKILL.md 只放主循环和硬规则，细节下沉到 `references/`，按 Phase 读取，控制主上下文体积。

```
1. 定位 change：参数 > 当前分支绑定 > changes/ 下唯一活跃 change > 问用户
2. spec-driven status --json → 当前 phase、phaseStatus、下一步
3. 按 next_phase 分派：
     Phase 0      → 本 skill 执行 new-change.sh
     Phase 1-4    → Skill 调用对应子 skill（先 scaffold-artifact.sh 生成骨架）
                    Phase 3 按需调用：改接口 → api-design-rest，改表 → db-schema-design；
                    两者都要时先接口后数据库（数据库 skill 需要回填 SC 的 DB 后置状态）
     Phase 5/6/7  → Agent 调用对应 subagent（见 §5）
     Phase 8      → Agent 调用 code-reviewer（见 §5）
     Phase 8.5    → 显式问用户 y/n/skip
     Phase 8.9    → 本 skill 呈报验收摘要
     Phase 9      → 本 skill 执行 archive-change.sh
4. 子步骤结束 → spec-driven gate <n>
     0 放行 → 更新 phaseStatus，回到 2
     2 WARN → 把告警原文给用户，由用户决定继续或修
     3 BLOCK → 回当前 Phase 修；不得绕过，不得改 gate 脚本
5. 上下文紧张 / 完成 1-2 个 Phase → 建议 commit checkpoint + /clear + spec-driven resume
```

硬规则（写进 SKILL.md 顶部，每条都能被 gate 机械校验）：

1. 上游冻结：进入 Phase N 后，Phase < N 的工件只读；要改就走回退流程。spec-gate hook 拦截对冻结工件的 Edit/Write。
2. 业务取值（常量、字段映射、格式）只能来自用户，不得用默认值填。
3. 评审和 QA 报告只能由 subagent 产出；subagent 失败重试一次，仍失败则 STOP。
4. 「编译通过」不等于完成；完成的证据是带 `Task-Id` trailer 的 commit 加上测试跑绿。
5. 未经 Phase 8.9 用户验收不得归档。
6. 任何 BLOCK 都可以放行，但只能由用户本人确认，并在 retrospective.md 留痕（§6.6）；模型不得自行放行、不得绕过、不得改 gate。

---

## 5. Subagent 调度协议

| Agent | 输入（只传路径，不传正文） | 产出 | 工具 |
| --- | --- | --- | --- |
| spec-evaluator | proposal / design 或 bugfix-analysis / spec / tasks 的路径 + `references/review-template.md` | `spec-review.md` | 只读 |
| implementation-generator | 单个任务 ID + tasks.md + spec.md 路径 + invariants.json 摘要 + 允许改的 scope | commits + `implementation-log.md` 追加段 | 可写；spec-gate 路径锁禁写 `.openspec/`，bash-guard 禁删测试目录 |
| qa-evaluator | spec.md + 代码分支 + 测试命令 | `qa-report.md` | 只读 + 可跑测试 |
| code-reviewer | 基线 commit..HEAD 范围 + 全部工件路径 + `static-analysis-report.md`（若有）+ `tiered-code-review` 规范 | `code-review.md` | 只读 + 可跑 git / 测试 |

角色划分依据 Generator-Evaluator 分离原则：**评判者**（spec-evaluator、qa-evaluator、code-reviewer）必须是只读 agent，由原则强制；**产出者**中只有 implementation-generator 做成 agent，理由是上下文卫生，其余产出类角色都是主线执行的 skill。`tiered-code-review` 是 skill，只承载分级规则和检查清单，由 code-reviewer agent 读取执行。

评审者的写权限：工具白名单包含 `Write`，但 spec-gate hook 把可写路径锁定到该 agent 自己的报告文件（`spec-review.md` / `qa-report.md` / `code-review.md`）；`Bash` 由 bash-guard 拦截修改类命令（写文件、git commit/checkout/reset 等）。不采用「agent 返回全文、主线落盘」的做法，避免报告内容经过主线。

流程：

1. 主线 `Agent(subagent_type=<name>, prompt=<模板化指令>)`。prompt 由 `references/subagent-protocol.md` 的模板生成，只含路径和约束，不带主线的推理过程，保证上下文隔离。
2. 返回后主线**只检查文件**：存在、非空、首行是 `<!-- generated-by: <name>-subagent -->`。
3. 不满足 → 重试一次（可换模型，`.config.json` 中 `agents.<name>.model`）。
4. 仍不满足 → 写 `phaseStatus.<n>="blocked"`，告诉用户「独立评审未完成，需人工介入」，停止。
5. gate-5 / gate-7 / gate-8 再次机械校验标记，并扫描「主线自评」「直接根据代码验证」等降级措辞。

Phase 6 默认串行：每个任务派一个 implementation-generator，主线只收回 commit hash、测试结果和改动文件清单。多 agent 并行（worktree）是可选能力，默认关闭。

---

## 6. 验证门实现

### 6.1 公共约定

- 入口：`spec-driven gate <n|all> [--strict|--soft] [--json]`
- 退出码：`0` 放行、`2` WARN、`3` BLOCK
- 输出：每条检查一行 `[BLOCK|WARN|INFO] <检查项> — <文件:行> <原因> → <修复建议>`；`--json` 供 hook 与 SKILL 解析
- 级别可配：`.openspec/.config.json` 的 `gates.<n>.level` 可设 `block|warn|info|off`，便于团队逐步开启；**以下检查不能在配置里降级或关闭**：防自欺类（业务取值来源、subagent 标记、uatAccepted）与静态质量门 gate-6.7。配置管的是团队默认规则；具体某一次拦截要放行，一律走人工放行（§6.6）
- 人工放行：所有 BLOCK 都可由用户本人确认放行并留痕，放行后该项输出为 `[WAIVED]`，不再计入退出码（§6.6）
- 触发：gate-router hook（UserPromptSubmit）按关键字（「进入 Phase N」「继续」「/archive」）调用；SKILL 主循环也会显式调用。平台 hook 不可用时由 `safety-check` skill 显式补偿

### 6.2 各门校验口径

| Gate | 校验内容 | 默认级别 |
| --- | --- | --- |
| 0 | 项目根（或上级目录）有 `pom.xml` / `build.gradle(.kts)`，否则提示「Reins 只支持 Java 项目」；change 名 kebab-case 且 ≥5 字符；目录与 proposal.md 存在；`.meta.json.mode ∈ {feature,bugfix}` | BLOCK |
| 1 | ≥1 用户故事，每条 ≥1 AC；Out of Scope 显式声明；歧义全部 ✅；**类型=业务取值的行来源必须=用户**；命中字段映射关键词时映射确认表必填；`tierConfirmed=true`；bugfix 额外检查 AUTO-DRAFTED 标记已删 | BLOCK |
| 2 | 方案数 ≥2（L ≥3），每个方案 6 字段；`**AI 推荐**` / `**最终选择**` 可解析；`meta.designDecision == 最终选择`；影响面含文件路径；4 个压测场景有回答；复杂度复评只升不降，升档出 WARN | BLOCK |
| 3 | 每条 AC 映射到 ≥1 SC；REQ 为 H2、SC 为 H3，WHEN/THEN 完整；接口契约节 5 要素；数据模型节含回滚；复杂度复评 | BLOCK |
| 4 | 任务数 ≥1，每个任务关联 SC（或 bugfix 修改点）；分层顺序；bugfix 必有 `T-regression` | BLOCK |
| 5 | subagent 标记；BLOCK 数 = 0 或显式接受风险；bugfix 未被标「应升级 design」 | BLOCK |
| 6 | 有新增或改动的测试文件（`src/test/java`）；Maven surefire / Gradle test 报告中测试运行数 > 0，命令不含 `-DskipTests`、`-Dmaven.test.skip`、`-x test`，pom 未配置 surefire `<skip>`；`implementation-log.md` 存在；JaCoCo **增量**覆盖率阈值（只算本次改动的行） | 测试真跑：BLOCK；覆盖率不达标：BLOCK，直到有人工豁免记录（§6.4） |
| 6.5 | 先跑 `tasks-sync`，再查 tasks.md 无裸 `- [ ]` | M/L/bugfix BLOCK，S WARN |
| 6.7 | 静态质量：ArchUnit（分层与依赖方向）、Checkstyle、SpotBugs、PMD、SQLFluff（MyBatis mapper XML、Flyway 脚本）；结果写入 `static-analysis-report.md` 供 Phase 8 使用 | 新增违规 BLOCK，存量违规不拦截；所有档位一致（见 §6.5） |
| 7 | subagent 标记；所有 SC 为 PASS | BLOCK |
| 8 | code-review.md 由 code-reviewer agent 产出（首行标记）；BLOCK = 0；WARN 已进 retrospective 待优化清单 | BLOCK |
| 8.5 | 用户选择部署验收时，`deploy-report.md` 存在且结论为 passed；选择跳过时 retrospective 已记录 | BLOCK |
| 8.9 | `uatAccepted == true` | 拒绝归档 |
| 9 | change 目录已迁移；archive 完整；主 specs 已合并；retrospective 存在 | BLOCK |

### 6.3 Markdown 解析

`mdparse.py` 是所有 gate 的共同依赖，需要单独写足单测：

- 按标题层级切 section（兼容中英文标题别名，如「Out of Scope」/「范围外」）
- 抽取 ID：`AC-\d+`、`REQ-<cap>-\d{3}`、`SC-<cap>-(\d{3}|E\d+)`、`T\d+`、`T-regression`
- 解析 pipe 表格（歧义清单、字段映射表、风险表）
- 解析复选框 `- [ ]` / `- [x]` / `- [~]`

模板和解析器用同一份「标题别名表」，避免模板改了而 gate 没同步。

### 6.4 覆盖率：只考核本次改动，不达标须人工确认

存量项目整体覆盖率往往很低，不能要求一次 change 把全项目补上去。所以 gate-6 的覆盖率**只看本次 change 改动的代码**（增量覆盖率）：

- 取 `git diff <change 基线 commit>..HEAD` 中 `src/main/java` 下新增和修改的行，用 JaCoCo XML 报告算出这些行的覆盖率。
- 阈值默认 80%，在 `.openspec/.config.json` 的 `test.coverage.diff_threshold` 配置。全项目覆盖率只写进报告，不参与判定。

增量覆盖率低于阈值时，gate-6 BLOCK，直到用户亲自确认并留下记录：

1. gate-6 输出实际值、阈值和未覆盖的改动行（文件:行）。
2. 总控用 AskUserQuestion 让用户二选一：「补测试」（回 Phase 6），或「接受当前覆盖率」并填写理由。
3. 用户选择接受后，按人工放行流程（§6.6）由用户本人输入确认口令，总控执行 `spec-driven waive 6 coverage --reason "<理由>"`，在 `retrospective.md` 的「人工确认记录」表追加一行：
   ```markdown
   ## 人工确认记录

   | 时间 | Gate | 检查项 | 拦截内容 | 理由 | 确认人 | 指纹 |
   | --- | --- | --- | --- | --- | --- | --- |
   | 2026-09-26 14:02 | 6 | coverage | 增量覆盖率 62% < 80%（T5） | 遗留 DAO 无法 mock，已由集成测试覆盖 | ronnie | 3fa1c09e |
   ```
4. 重跑 gate-6：gate 读取 `retrospective.md` 的这张表，存在覆盖当前值的记录即放行。如果覆盖率比记录时又下降了，记录失效，需要重新确认。
5. 归档时这张表随 retrospective.md 一起进入 archive，不需要再汇总。

防止 AI 自己豁免，要堵两条路：

- **命令**：`waive` 只有在消费到用户本人签发的一次性授权时才执行（§6.6），模型自己调用会被拒绝。三层落实方式见 §2.4。
- **文件**：retrospective.md 是普通 markdown，模型可以直接改。所以 spec-gate 禁止模型用 Edit/Write 修改 retrospective.md，这个文件只能经 `spec-driven retro` 系列命令写入：待优化清单、部署结论等由总控调用 `spec-driven retro add`，人工确认记录只能由 `waive` 写入。没有编辑前 hook 的平台，由 git pre-commit 拒绝提交非 CLI 写入的改动（§2.4）。

### 6.5 静态质量门（gate-6.7）：新增违规一律拦截，存量违规不追溯

原则是**新代码必须合规，历史债务不强制本次偿还**。gate-6.7 不做「只告警」，也不因 S 档降级；但只拦截本次 change 引入的违规，不因项目里原有的违规卡住开发。

1. **命令驱动**：`.openspec/.config.json` 的 `quality` 块为每个检查配置 `command`（如 `mvn -q checkstyle:check`、`mvn -q spotbugs:check`、`mvn -q pmd:check`、ArchUnit 测试类、`sqlfluff lint`）和 `report_path`。Checkstyle、PMD、SpotBugs 的 XML 报告和 SQLFluff 的 JSON 输出都是标准格式，gate 直接解析出逐条违规。
2. **基线**：项目首次接入时，`spec-driven init-config --java` 生成配置，并跑一遍全部检查，把现有违规记为基线 `.openspec/quality-baseline.json`（提交进仓库）。每条违规用「文件 + 规则 + 规范化后的消息」做指纹，不含行号，代码上下移动不影响匹配。ArchUnit 直接用它自带的 `FreezingArchRule` 冻结存量违规。
3. **判定**：
   - 本次 change 引入、基线里没有的违规 → **BLOCK**，回 Phase 6 修复。
   - 基线里已有的违规 → 不拦截，只在报告里列为「存量」。
   - 本次 change 修掉的存量违规 → 报告里列为「已偿还」，归档时从基线移除。基线只减不增。
4. **首次使用不拦截**：项目第一次用 Reins 时还没有配置和基线。第一个 change 的 Phase 0 由总控在用户确认后运行 `init-config --java`，生成配置和基线后才开始 Phase 1。这是一次性的接入步骤，而不是在 Phase 6 才突然被 BLOCK。已接入的 Java 项目若配置被删掉，gate-6.7 BLOCK，经用户确认后由总控重新运行 `init-config --java`。
5. **新增违规的放行途径是人工放行**：确实无法在本次修复的新增违规（如框架限制），用户本人确认放行（§6.6），由 `spec-driven waive 6.7 <检查名> --reason "<理由>"` 记入 retrospective.md「人工确认记录」，与覆盖率豁免同一机制（§6.4）。豁免只对记录时的违规有效，再有新增即失效。
6. **产出报告**：无论通过与否，都写 `static-analysis-report.md`，分「新增 / 存量 / 已偿还」三栏列出违规。Phase 8 的 code-reviewer 先读它，机器已抓到的问题不重复标记。

### 6.6 人工放行：所有拦截通用

任何 gate 的任何 BLOCK 都可以放行，前提是用户本人确认，并留下记录。覆盖率（§6.4）和静态质量（§6.5）只是其中两个例子。常见场景：

| 拦截 | 放行时记录的内容 |
| --- | --- |
| 业务取值来源不是用户（gate-1） | 哪些字段、为什么先按推断值走 |
| 独立评审 agent 两次失败（gate-5 / 7 / 8） | 本次没有独立评审，由谁人工看过 |
| 测试未真跑、无新增测试（gate-6） | 为什么这次不需要或无法测试 |
| 增量覆盖率、静态质量新增违规（gate-6 / 6.7） | 当时的数值或违规清单 |
| 未经用户验收就归档（gate-8.9） | 跳过验收的原因 |

**流程**

用户看不到 `spec-driven`，放行在对话里完成：输入 `/waive`，或在拦截后直接说「放行」「接受当前覆盖率」等，由 waive 入口 skill 接手。关键词只负责触发 skill，不代表确认。

1. gate BLOCK 后，总控把拦截原因原样给用户，请用户选择「回去修」或「放行」。
2. 用户选择放行时，waive skill 列出 BLOCK 项（gate、检查项、拦截内容、指纹），请用户给出理由，再请用户**原样输入**确认口令 `确认放行 <change 名> <gate> <检查项>`。
3. 平台的 UserPromptSubmit hook（`spec-driven hook prompt-submit`）读到的是用户本人提交的原文，模型无法伪造。原文匹配口令、且该项当前确实处于 BLOCK 时，hook 在 `~/.reins/grants/` 签发一次性授权：绑定项目、change、gate、检查项和指纹，10 分钟内有效。
4. 总控执行 `spec-driven waive <gate> <检查项> --reason "<理由>"`。命令找到匹配的授权才执行，执行后作废该授权；找不到就拒绝，报「没有有效授权」。然后在 retrospective.md 的「人工确认记录」表追加一行：时间、Gate、检查项、拦截内容、理由、确认人（git user.name）、指纹。
5. **指纹**是 gate 对本次拦截内容算出的哈希，比如违规清单、覆盖率数值、缺失的字段。重跑 gate 时，拦截内容和指纹一致才放行；内容变了（出现新违规、覆盖率又下降）就重新 BLOCK，需要再次确认。放行只对「当时看到的那些问题」有效。
6. 放行后该项输出 `[WAIVED]`，不计入退出码。retrospective.md 随归档进入 archive，放行记录永久保留。

降档用同一机制，口令为 `确认降档 <change 名> <档位>`，授权由 `complexity set --downgrade` 消费。

**防止 AI 自行放行**：

- **授权只来自用户输入**：只有 UserPromptSubmit 能签发授权，模型的输出、工具结果都不经过它。口令带 change 名和检查项，用户随口说「放行」「可以」不会签发；说「不要放行」只会触发 waive skill，不会签发。
- **授权文件受保护**：编辑前 hook 禁止模型写 `~/.reins/grants/`，bash-guard 拦截对它的 shell 写入。
- **retrospective.md 只能经 CLI 写入**：禁止模型直接编辑（§6.4）。
- **没有提示词 hook 的平台**（OpenCode 需实测插件能否拿到用户消息）：退回原方案，由用户本人在自己的终端执行 `spec-driven waive`，命令要求在 TTY 里输入 change 名确认。这是用户唯一会直接接触 `spec-driven` 的场合，`doctor` 会标出。

---

## 7. Phase 0 / 8.9 / 9 细节（本 skill 亲自执行的三段）

### Phase 0：new-change.sh

1. 校验在 git 仓库内，否则提示 `git init`
2. 建 `.openspec/` 与 `changes/<change>/`
3. feature：名称由用户确认；bugfix：`fix-<YYYYMMDD>-<slug>`
4. 写 `.meta.json`（provisional M，`tierConfirmed=false`）和 proposal.md 骨架
5. 建议并绑定分支 `feat/<change>` 或 `fix/<change>`，写 `meta.branch`
6. 跑 gate-0

### Phase 8.9：用户验收

从 proposal 的字段映射确认表、spec.md 的 SC 标题、qa-report 结论生成一屏摘要，用 AskUserQuestion 询问「通过 / 需要修改」。选择通过则写 `uatAccepted` 和时间戳；选择修改则让用户指出问题所在 Phase，并走回退流程。

### Phase 9：archive-change.sh

1. 前置：gate-8.9 通过
2. 读 spec.md 的 Capability ID，按 REQ 粒度合并进 `specs/<capability>.md`：同 ID 替换、新 ID 追加；SC ID 冲突时 BLOCK，交给用户处理
3. 从 design.md 的「最终选择」和理由蒸馏出 `decisions/<NNNN>-<slug>.md`，编号取现有最大值 +1
4. 若 design 中出现层边界或依赖方向约束，提示是否更新 `architecture.md` §4（不自动写）
5. 补全 retrospective.md（部署结论、复盘小结）；文件此前已存在的，保留已有的人工确认记录和待优化清单
6. `git mv` 到 `archive/<date>-<change>/`，刷新 `specs/README.md` 索引
7. 跑 gate-9

合并逻辑是整条链最容易出错的部分，要求用 fixture 做单测：新能力、已有能力追加 REQ、同 REQ 覆盖、SC 冲突，四类场景。

---

## 8. 回退与恢复

- **回退**：`spec-driven retry <phase> --reason "<原因>"` 做四件事：在目标工件顶部写 `<!-- revised at <date>: <reason> -->`；把该 Phase 置为 `in_progress`；把所有下游 Phase 置为 `stale`；解除该工件的冻结。之后所有 stale Phase 必须重新过门。
- **恢复**：`spec-driven resume` 输出一屏内容：change、mode、档位；当前 Phase 与下一步命令；invariants 摘要；本 Phase 需要读的工件路径。SKILL.md 规定新会话第一步就跑它。

---

## 9. 测试策略

`tests/` 下每个 gate 配一组「合格 / 不合格」fixture 工件；`tests/test_plugin.py` 检查插件结构：各平台清单指向的文件存在、版本号一致、agent 的 `tools` 与 `access` 一致、Codex toml 转换结果合法。CI 用 unittest 在 macOS、Linux、Windows 上运行，并用 Node 加载 OpenCode 入口、跑三个启动器和 hook 拦截探针。

---

## 10. 关键取舍

1. **Phase 3 / 4 的归属**：Phase 3 = `api-design-rest` + `db-schema-design`，共写一个 `spec.md`、按节分工；Phase 4 = 独立的 `task-breakdown`。两者都不在总控内，总控只负责调度和跑 gate-3、gate-4。
2. **评审与实现角色做成 agent**：spec-evaluator、implementation-generator、qa-evaluator、code-reviewer 定义为 `agents/*.md`，code-reviewer 只读、执行 Phase 8（依据 Generator-Evaluator 分离原则，见 §5）。skill 清单里不列这些角色。
3. **bugfix 入口**：只有 `/bugfix "描述"` 一种，缺陷信息人工录入；`source` 字段为接入缺陷平台留位。bugfix 不做「立单门槛判定」：gate-1 不要求相关章节，spec-evaluator 也不因改动大小 BLOCK 要求补缺陷单。bugfix 改动大时按 §3.3 的条件走 Phase 2/3。
4. **降档**：允许 PM 手动降档，须用户本人输入确认口令（§6.6），记录写入 retrospective.md「档位变更记录」（§3.2）。
5. **gate-6 / gate-8 级别**：「测试真跑」为 BLOCK；覆盖率不达标需人工确认，记录写入 retrospective.md（§6.4）。gate-8 为 BLOCK。
6. **Phase 8.5 部署**：本地启动加人工验收，由 `local-deploy` 产出 `deploy-report.md`；gate-8.5 检查报告存在且结论为 passed。
7. **工件根目录**：`.openspec/`。
8. **Skill 数量**：17 个 skill（主链 8 + 变种 1 + 横切 8）+ 4 个 agent，清单见 §1.1。
9. **静态质量门**：gate-6.7 不按档位降级。对存量项目不追溯：用基线区分新增与存量违规，只拦截新增；覆盖率只考核本次改动的代码。首次接入在 Phase 0 引导生成配置和基线。新增违规唯一放行途径是用户本人豁免并留痕（§6.4、§6.5）。
10. **适用范围**：只支持 Java 项目（Maven / Gradle），gate-0 检查构建文件。
11. **人工放行**：所有 BLOCK 都可由用户本人确认放行，记入 retrospective.md「人工确认记录」，按指纹绑定当时的拦截内容，内容变化即失效（§6.6）。配置层面不允许关闭防自欺类检查和 gate-6.7。
