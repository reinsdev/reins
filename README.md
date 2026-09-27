# Reins

规格驱动研发工件链插件：`proposal → design → spec → tasks → 实现 → QA → review → 归档`，每个阶段一道机器验证门，评审由独立 agent 完成。

适用于 **Java 项目**（Maven / Gradle）。

## 它做什么

AI 写代码很快，但需求只活在对话里、设计只在脑子里，一周后就答不出「为什么这么改」「验收标准是什么」「代码有没有偏离需求」。在 Java 企业项目里，还要加上一条：AI 很容易写出能编译、却不符合团队规范和架构约束的代码。Reins 把研发过程变成一条可校验、可追溯的工件链：

1. **工件链**：每个需求或 bugfix 是一个 change，按 `proposal → design → spec → tasks → 实现 → QA → code review → 用户验收 → 归档` 产出 markdown 工件，放在项目的 `.openspec/changes/<change>/` 下。
2. **验证门**：每个阶段结束由 `spec-driven` CLI 机械校验，不过门进不了下一步。例如：验收标准是否都映射到了测试场景、测试是否真的跑了、业务取值是不是模型自己编的。
3. **生成与评审分离**：写代码的 agent 和评审的 agent 分开。spec 评审、QA、code review 各由一个独立 agent 完成，评审者只写自己的报告，AI 不给自己打分。
4. **Java 企业级代码管控**：让 AI 产出的代码符合企业的各项要求，而不只是「能跑」：
   - **团队规范**：通用 skill 自动加载项目专属规约（`<项目>/.claude/skills/*-conventions/`），编码、命名、接口、DDL 规范按项目各自定制
   - **分层架构**：任务按 Foundation → Domain → Application → Adapter 分层拆分；分层和依赖方向约束写进 `architecture.md`，由 ArchUnit 落成测试强制执行
   - **静态质量**：Checkstyle、SpotBugs、PMD 在 Phase 6 出口把关，MyBatis mapper XML 和 Flyway 脚本经 SQLFluff 检查 SQL 规范
   - **测试真跑**：`-DskipTests`、surefire skip、0 个测试都会被拦截；RED 必须先于 GREEN；覆盖率（JaCoCo）不达标须由你本人确认并留痕
   - **接口与数据**：接口契约与 Swagger / OpenAPI 比对一致性；DDL 必须带索引设计和回滚脚本
5. **按复杂度分档**：S / M / L 三档。S 档跳过 Phase 2/3/5/7，保留 code review 和用户验收；复杂需求要求 ≥3 个方案对比、两轮评审。
6. **人工放行与留痕**：任何拦截都可以放行，由你本人在会话中输入完整确认口令，hook 签发一次性授权，总控消费授权后记进 `retrospective.md`；缺少提示词 hook 时，放行和验收可在真实终端确认。降档同样需要口令授权。归档时 spec 合并进项目主 specs，设计决策沉淀为 ADR。

一份源码，由 Claude Code、Codex、OpenCode 三个平台直接加载，无需构建插件。发布命名空间为 `reinsdev`：插件 ID `reins@reinsdev`，GitHub 仓库 `reinsdev/reins`，OpenCode npm 包 `@reinsdev/opencode`。文档索引见文末。

## 安装

支持 macOS、Linux、Windows。需要 Python 3.8+ 和 git；Windows 上必须安装 Git for Windows（Claude Code 靠 Git Bash 执行 hook），Codex 用户请使用 MSI 版 PowerShell 7 而非商店版（商店版会让 Codex hook 失效，见 openai/codex#47810）。

一行命令安装：

```sh
# macOS / Linux / Git Bash
curl -fsSL https://raw.githubusercontent.com/reinsdev/reins/main/install.sh | sh

# Windows PowerShell
irm https://raw.githubusercontent.com/reinsdev/reins/main/install.ps1 | iex
```

它会安装 Reins 的安装工具 `reinsdev`，再把插件装进本机已有的 Claude Code、Codex、OpenCode（Codex 的 4 个评审 agent 一并装好），最后运行 `reinsdev doctor` 检查环境。只装某个平台：`curl ... | sh -s -- --target codex`，Windows 上先设 `$env:REINS_TARGET="codex"`。

`reinsdev` 只在安装阶段用：

| 命令 | 作用 |
| --- | --- |
| `reinsdev install [--target ...]` | 安装到各平台；新装了某个平台后再运行一次 |
| `reinsdev update` | 拉取最新版本，重装已安装的平台 |
| `reinsdev doctor` | 检查环境和各平台护栏落实情况 |
| `reinsdev uninstall [--target ...]` | 卸载 |

源码放在 `~/.reins/src`，`reinsdev` 在 `~/.reins/bin`（可用 `REINS_HOME` 换目录）。macOS / Linux 上安装脚本会提示把 `~/.reins/bin` 加进 PATH；Windows 上自动加入用户 PATH。

### 使用

| 平台 | 开始需求 | 修缺陷 | 放行拦截 |
| --- | --- | --- | --- |
| Claude Code、OpenCode | `/spec <需求一句话>` | `/bugfix "<问题描述>"` | `/waive`，或直接说「放行」 |
| Codex | `$spec <需求一句话>` | `$bugfix "<问题描述>"` | `$waive`，或直接说「放行」 |

Codex 没有自定义斜杠命令，入口是同名 skill。OpenCode 里也可以用 `@spec-evaluator` 直接调用评审 agent。

### 从需求到验收

总控用 `new` 建 change，再用 `advance` 校验当前阶段并推进。`gate` 只检查，不推进；WARN 需要用户确认后通过 `advance --ack-warn` 继续，BLOCK 留在原阶段。S 档跳过的阶段会在路由经过时记入状态。

- bugfix 的影响范围由总控在 Phase 1 用 `scope set --files N` 落盘，`--cross-service`、`--ddl`、`--public-api` 决定是否需要设计和规格。
- 提交带 `Task-Id` trailer，RED 另带 `TDD-Phase: RED`。总控用 `tasks-sync --apply` 同步勾选。`new` 安装的 git hook 检查提交证据和留痕完整性。
- 首次接入先由总控运行 `quality setup --dry-run` 展示改动，用户同意改 pom 后执行 `quality setup`；用户同意联网时加 `--online` 预热 Maven 依赖。再执行 `init-config --java --dry-run` 和 `init-config --java` 建立真实质量基线。
- 评审报告按插件 `templates/reports/` 填写。首行是对应 agent 的 `generated-by` 标记，结论表的 BLOCK/WARN/INFO 数量必须与问题清单一致。不能用一句“通过”代替。
- 用户不做部署验收时，总控在 Phase 8.5 执行 `deploy skip --reason "用户理由"`。Phase 8.9 输入 `确认验收 <change>` 后，总控才能 `uat accept`；需要修改时用 `uat reject --phase N --reason "用户理由"` 回退。
- 放行口令是 `确认放行 <change> <gate> <check>`。`check` 必须用当前 BLOCK 输出中的完整标识。口令不是普通“继续”，授权绑定拦截内容，内容改变需要重新确认。

以上 CLI 由总控调用，用户在会话中仍使用 `/spec`、`/bugfix`、`/waive`。开发者可运行 `python3 tools/e2e/run.py` 在临时 Maven 项目中复现 CLI 流程，无需启动 AI 平台。联调发现的阻塞（E2E-01 至 E2E-04）已转为任务，见 [任务书](docs/dev/tasks.md) 的 T14、T16、T17；修复前带 `--diagnose` 的运行不能视为完整通过。详细步骤见 [验证手册](docs/verification.md#17-cli-端到端联调)。Windows 验证延后。

质量接入支持 Maven 的 JUnit 4/5：添加 ArchUnit 1.3.0 测试依赖和冻结分层测试；Checkstyle 3.6.0、PMD 3.26.0、SpotBugs 4.9.3.0 使用完整插件坐标写入配置，不额外改 pom。默认离线只写文件，返回 2 表示依赖尚未验证；`--online` 成功返回 0，仍需初始化基线。改 pom 前保存 `pom.xml.reins-bak`，失败恢复本次管理的文件。已有依赖、测试和团队配置保留；多模块只处理有 Java 源码的模块，包名或 JUnit 无法确定时需明确确认。Gradle 自动接入暂不支持，CLI 会给出手工步骤。

有 SQL/MyBatis 资源时，接入命令先列出 JDBC 方言候选，由用户确认后通过 `--sql-dialect` 生成 `.sqlfluff`；已有文件仅展示差异。默认启用 CP01（关键字大写）、CP02–CP04（标识符、函数、字面量写法一致）、AM04（限制 `SELECT *`）、RF02（多表字段限定）及 LT05（120 字符，告警级），关闭 AL01、AL02、LT02。placeholder 模板识别 MyBatis `#{…}` 和提取后的 `?`。无 SQL 时不生成配置；缺少 SQLFluff 时只提示安装，不自动安装。规则可由团队调整，配置语义见 [SQLFluff 规则配置](https://docs.sqlfluff.com/en/stable/configuration/rule_configuration.html)和 [placeholder 文档](https://docs.sqlfluff.com/en/stable/configuration/templating/placeholder.html)。

### 用平台原生命令安装

不想装 `reinsdev` 时，也可以直接用各平台自己的命令：

```sh
# Claude Code（会话里用 /plugin marketplace add、/plugin install 也一样）
claude plugin marketplace add reinsdev/reins
claude plugin install reins@reinsdev

# Codex：插件不能打包 agent，4 个评审 agent 仍要用 reinsdev setup codex 安装
codex plugin marketplace add reinsdev/reins
codex plugin add reins@reinsdev

# OpenCode
opencode plugin @reinsdev/opencode -g
```

### 卸载

```sh
reinsdev uninstall                  # 卸载所有平台；只卸一个加 --target codex
rm -rf ~/.reins                     # 连同 reinsdev、源码和 hook 日志一起删除
```

卸载只移除插件本身，不会动项目里的 `.openspec/` 工件。

用原生命令装的，用原生命令卸：

- **Claude Code**：`claude plugin uninstall reins@reinsdev`，再 `claude plugin marketplace remove reinsdev`。装的是项目级（project scope）时，要在那个项目目录里执行，并加 `--scope project`。
- **Codex**：`codex plugin remove reins@reinsdev`，再 `codex plugin marketplace remove reinsdev`。`reinsdev setup codex` 装的 agent 用 `reinsdev uninstall --target codex` 删除，然后重启 Codex。
- **OpenCode**：没有卸载插件的命令。从配置文件的 `plugin` 数组里删掉 `"@reinsdev/opencode"`，重启 OpenCode：`-g` 安装的在 `~/.config/opencode/opencode.jsonc`（可能是 `opencode.json`），项目级的在项目根目录的 `opencode.json(c)`。`opencode debug config` 里 `command` 没有 `spec` / `bugfix` 即卸载完成。

## 仓库结构

仓库里只放原料，没有构建步骤。`reinsdev-plugin/` 手写而成，既是源码也是插件本身，三个平台直接读它：入口各一份，核心内容只有一份。

```
.claude-plugin/marketplace.json      Claude Code marketplace「reinsdev」→ ./reinsdev-plugin
.agents/plugins/marketplace.json     Codex marketplace「reinsdev」→ ./reinsdev-plugin

reinsdev-plugin/                     插件本身
│  ── 平台入口（每个平台一份，都很薄）──
├── .claude-plugin/plugin.json       Claude Code 清单，hooks 指向 hooks/claude.json
├── .codex-plugin/plugin.json        Codex 清单，hooks 指向 hooks/codex.json
├── hooks/claude.json  codex.json    两个平台的 hook，都转调 spec-driven hook
├── package.json  index.js           OpenCode：npm 包清单和插件入口
│  ── 核心内容（三个平台共用）──
├── skills/spec-driven-dev/          总控 skill；scripts/ 下是 spec-driven CLI（启动器 + lib/spec_driven/）
├── skills/spec/ bugfix/ waive/      入口：/spec、/bugfix、/waive（Codex 上为 $spec 等）
└── agents/*.md                      4 个评审 / 实现 agent

tests/                               CLI 与插件结构的测试（不进插件）
tools/e2e/                           临时 Java 项目的 CLI 联调脚本与样例
tools/reinsdev/  bin/reinsdev        安装工具 reinsdev（不进插件）
install.sh  install.ps1              一行命令安装入口；在仓库里运行则安装工作区
docs/                                设计方案、验证手册
```

### 平台差异在哪里处理

| 内容 | Claude Code | Codex | OpenCode |
| --- | --- | --- | --- |
| skills | 直接读 | 直接读 | `index.js` 把 `skills/` 加进 `skills.paths` |
| agents（`agents/*.md`） | 直接读（frontmatter 里的 `tools`） | `reinsdev` 安装时转成 toml，写入 `~/.codex/agents/` | `index.js` 启动时读取，按 `access` 换算成 `permission` |
| 入口 `/spec`、`/bugfix`、`/waive` | skill | skill（`$spec`） | `index.js` 读取三个入口 skill，注册为命令 |
| hook | `hooks/claude.json` | `hooks/codex.json` | `index.js` 的 `tool.execute.before` |

agent 的 frontmatter 同时写了 `tools`（给 Claude Code）和 `access`（给 Codex、OpenCode 换算），`tests/test_plugin.py` 会检查两者一致。版本号出现在 `spec_driven.VERSION`、两份 `plugin.json`、`package.json` 和 Claude marketplace 里，测试同样会检查它们一致。

### 两个命令行工具

| 工具 | 给谁用 | 命令 | 位置 |
| --- | --- | --- | --- |
| `reinsdev` | 用户，只在安装阶段 | `install` / `update` / `uninstall` / `doctor` / `setup` / `version` | `tools/reinsdev/`，经 `bin/reinsdev` 运行；用户由一行命令安装到 `~/.reins/`，不进插件 |
| `spec-driven` | 总控和各平台 hook，用户看不到 | `new` / `advance` / `gate` / `tasks-sync` / `init-config` / `uat` / `scope` / `deploy` / `waive` / `archive` 等 | 插件内 `skills/spec-driven-dev/scripts/`，随插件分发 |

两者都只用 Python 3.8+ 标准库，共用 `spec_driven` 里的版本号和 frontmatter 解析。用户在会话里只接触 `/spec`、`/bugfix`、`/waive`。

### 跨平台

插件里的 `spec-driven` 有三个启动器，由它们在运行时处理操作系统差异，插件本身在 macOS、Linux、Windows 上是同一份文件：

| 启动器 | 作用 | 调用方 |
| --- | --- | --- |
| `spec-driven.py` | 真正的入口，从同目录的 `lib/` 加载 CLI | 另外两个启动器；OpenCode 的 `index.js` 直接调用 |
| `spec-driven`（sh） | 依次尝试 `python3` / `python` / `py -3`，找到 3.8+ 后运行 `.py` | Claude Code 的 hook（Windows 上经 Git Bash）、macOS / Linux 上的 Codex hook、终端 |
| `spec-driven.cmd` | 同样的查找逻辑，Windows 批处理版本 | Windows 上的 Codex hook（经 PowerShell）、cmd / PowerShell |

每个候选解释器都先实际执行一次版本检查，以排除微软商店的 `python3` 空壳。找不到 Python 时，`hook` 命令放行、其他命令失败：不会卡住会话，也不会让验证门静默通过。`.gitattributes` 把 `.cmd` / `.ps1` 固定为 CRLF、其余为 LF，不受 `core.autocrlf` 影响。

## 开发

直接改 `reinsdev-plugin/` 下的文件，改完即生效，没有构建步骤。

```sh
python3 -m unittest discover -s tests -t .                                  # 全部单测
bin/reinsdev doctor                                                         # 环境与护栏检查
claude plugin validate reinsdev-plugin                                      # Claude Code 清单校验
```

## 本地加载与验证

在本机加载插件做验证，不经过 GitHub / npm。下面的命令里，`<仓库>` 指本仓库的绝对路径。完整的验证清单见 [docs/verification.md](docs/verification.md)。

### 加载方式总览

| 平台 | 临时加载（不改配置） | 原生命令 | 安装脚本（推荐） |
| --- | --- | --- | --- |
| Claude Code | `claude --plugin-dir <仓库>/reinsdev-plugin` | 本地 marketplace `reinsdev` | `./install.sh --target claude` |
| Codex | — | 本地 marketplace `reinsdev` + `bin/reinsdev setup codex` | `./install.sh --target codex` |
| OpenCode | 插件目录转引文件 | npm 包（需本地 registry） | `./install.sh --target opencode` |

在仓库里运行 `./install.sh`，走的就是用户一行命令安装的同一套流程，只是源码用当前工作区，而不是 `~/.reins/src` 里的 clone。仓库根目录本身就是 Claude Code 和 Codex 的 marketplace，名字都叫 `reinsdev`，插件 ID、命令、agent 名称和用户安装完全一样。注意 `./install.sh` 会把 `~/.reins/bin/reinsdev` 指向当前工作区。

### Claude Code

```sh
# 临时加载：只在本次会话生效，退出即清理；改了文件后重开会话即可
claude --plugin-dir <仓库>/reinsdev-plugin

# 原生方式：本地 marketplace（会话里也可以用 /plugin marketplace add、/plugin install）
claude plugin marketplace add <仓库>
claude plugin install reins@reinsdev

# 改了文件后刷新（插件安装时会复制到缓存，不会实时读取仓库），然后重开会话
claude plugin marketplace update reinsdev
claude plugin update reins@reinsdev

# 清理
claude plugin uninstall reins@reinsdev
claude plugin marketplace remove reinsdev
```

### Codex

```sh
# 推荐：一条命令装好 marketplace、插件和 4 个 agent；改了文件后重复执行即可更新，然后重启 Codex
./install.sh --target codex
bin/reinsdev uninstall --target codex     # 清理
```

想逐步复现最终用户的流程时，改用原生方式：

```sh
codex plugin marketplace add <仓库>
codex plugin add reins@reinsdev
bin/reinsdev setup codex                  # 安装 4 个 agent；不装时进会话用 $spec，总控会提示先装

# 改了文件后刷新：Codex 没有 plugin update，marketplace upgrade 只刷新 Git 来源，所以先删再装
codex plugin remove reins@reinsdev
codex plugin add reins@reinsdev

# 清理
codex plugin remove reins@reinsdev
codex plugin marketplace remove reinsdev
bin/reinsdev uninstall --target codex     # 删除 setup codex 装的 agent
```

### OpenCode

OpenCode 没有 marketplace，插件只有两种来源：npm 包，或插件目录里的 JS 文件。

```sh
# 插件目录转引（推荐）：放在项目的 .opencode/plugins/（只对该项目生效）或 ~/.config/opencode/plugins/（全局）
mkdir -p .opencode/plugins
printf 'export * from "file://%s/reinsdev-plugin/index.js"\n' "<仓库>" > .opencode/plugins/reins.js
```

转引文件加载的是仓库里的同一份代码，改了文件后重启 OpenCode 即可，不用重装。

想连 npm 安装流程也验证（比如 `package.json` 的 `files` 字段是否漏了文件），可以用 verdaccio 等工具起一个本地 npm registry，在 `reinsdev-plugin/` 下 publish，再 `opencode plugin @reinsdev/opencode -g`。

### 安装脚本

```sh
./install.sh [--target claude,codex,opencode|all] [--dry-run] [--force]   # macOS / Linux / Git Bash
.\install.ps1 [--target ...]                                              # Windows PowerShell
bin/reinsdev uninstall [--target ...]                                     # 按 ~/.reins/installed.json 精确撤销
```

脚本就是把上面的原生方式串起来：Claude Code 和 Codex 以本仓库为本地 marketplace 安装，Codex 的 agent 一并装好；OpenCode 写入全局转引文件 `~/.config/opencode/plugins/reinsdev.js`。装完自动运行 `reinsdev doctor`。

验证一行命令安装本身（clone、启动器、`update`），可以把工作区提交到一个临时 git 仓库，再用 `REINS_REPO=<临时仓库> REINS_HOME=<临时目录>` 执行 `cat install.sh | sh`。

## 发布

- **Claude Code / Codex / 一行命令安装**：推送到 GitHub `reinsdev/reins` 的 `main` 即发布。原生安装的 marketplace 直接读取仓库里的 `reinsdev-plugin/`；一行命令安装的用户运行 `reinsdev update` 拉取。
- **OpenCode**：在 `reinsdev-plugin/` 下 `npm publish --access public`。`package.json` 的 `files` 只包含 `index.js`、`agents/`、`skills/`。

发布前确认版本号已同步更新（单测会检查各处一致）。

## 文档

- [docs/spec-driven-dev-skill-design.md](docs/spec-driven-dev-skill-design.md)：spec-driven-dev skill 实现方案（插件架构、状态模型、验证门）
- [docs/verification.md](docs/verification.md)：验证手册（离线检查、各平台本地加载、会话内验证清单）
- [spec-driven-workflow.md](spec-driven-workflow.md)：工作流指南，每个 Phase 做什么、验证门查什么
- [SpecToolChain.md](SpecToolChain.md)：产品需求（PRD）
