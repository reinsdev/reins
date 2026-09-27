# Reins 验证手册

按本手册可以在本机从工作区加载 Reins，逐项确认它在 Claude Code、Codex、OpenCode 三个平台上生效：插件能加载、入口能触发、hook 能拦截、评审 agent 能调度。平台加载不经过 GitHub 或 npm。CLI 联调默认离线；示例 Maven 依赖需预先缓存，显式传 `--online` 才允许下载。Windows 相关验证延后，本轮不执行。

下文命令默认在仓库根目录执行，`$REINS` 指仓库根目录的绝对路径：

```sh
export REINS="$(pwd)"
```

---

## 0. 准备

| 项 | 要求 | 检查 |
| --- | --- | --- |
| Python | 3.8+ | `python3 --version` |
| git | 任意 | `git --version` |
| 平台 CLI | 仅会话验证需要，CLI 联调不需要。至少装一个：`claude` / `codex` / `opencode` | `claude --version` 等 |
| Windows：Git Bash | 安装 Git for Windows（Claude Code 靠 Git Bash 执行 hook） | PowerShell 里 `where.exe git`，同一 Git 安装目录下存在 `bin\bash.exe` |
| Windows：PowerShell 7（仅 Codex） | 用 MSI 版，不用商店版（商店版会让 Codex hook 失效） | `(Get-Command pwsh).Source`，路径里不含 `WindowsApps` |

这里只用系统自带命令检查环境，不依赖 Reins。§1.6 的 `doctor` 会再把这两项查一遍。

准备一个用来试用的 Java 示例项目，不要在 Reins 仓库里直接试：

```sh
python3 tools/e2e/run.py
# 从输出的证据目录中选择 flow-a / flow-b / flow-c 作为真实 Maven 示例。
# JDK/Maven 不存在时脚本停止；依赖未缓存时构建失败，不生成假报告。
```

**没有构建步骤。** 各平台加载的就是仓库里的 `reinsdev-plugin/`，改完文件直接验证即可。

仓库里有两个命令行工具，别混用：

| 工具 | 给谁用 | 在哪里 |
| --- | --- | --- |
| `reinsdev` | 用户，只在安装阶段：`install`、`update`、`uninstall`、`doctor`、`setup` | 仓库里：`bin/reinsdev`；用户由一行命令装到 `~/.reins/bin/`；不进插件 |
| `spec-driven` | 总控和平台 hook（用户看不到）：`new`、`advance`、`gate`、`uat`、`scope`、`deploy`、`archive` 等 | 插件内：`reinsdev-plugin/skills/spec-driven-dev/scripts/spec-driven` |

下文用 `$CLI` 指插件内的 CLI（验证 hook 用）：

```sh
export CLI="$REINS/reinsdev-plugin/skills/spec-driven-dev/scripts/spec-driven"
export REINS_HOME="$(mktemp -d)"   # 本次验证的日志和授权，不碰 ~/.reins
```

---

## 1. 离线检查（不启动任何平台）

这一组检查不需要登录，也不会调用模型，也**不需要安装插件**：插件目录里的启动器可以在仓库里就地运行。每次改动后都应先跑一遍。

| # | 命令 | 预期 |
| --- | --- | --- |
| 1.1 | `python3 -m unittest discover -s tests -t .` | `OK`；含插件结构检查：清单指向的文件存在、版本号一致、agent 的 `tools` 与 `access` 一致 |
| 1.2 | `claude plugin validate reinsdev-plugin` | `✔ Validation passed` |
| 1.3 | `claude plugin validate .` | 校验 `.claude-plugin/marketplace.json`，`✔ Validation passed` |
| 1.4 | `"$CLI" version` | 打印版本号，说明插件内的启动器能找到 Python |
| 1.5 | `REINS_HOME=$(mktemp -d) CODEX_HOME=$(mktemp -d) bin/reinsdev setup codex` | 在临时目录生成 4 个 agent 的 toml，不碰真实的 `~/.codex` 和 `~/.reins` |
| 1.6 | `bin/reinsdev doctor`（Windows：`bin\reinsdev.cmd doctor`） | 列出 Python、git、系统，以及本机已有平台 CLI 的护栏落实层；Windows 上还会检查 Git Bash 和 pwsh；没有 `✗` |

**hook 探针**：路径或命令含 `.reins-probe-block` 时会被拦截。实际策略还检查上游工件冻结、评审角色权限、状态/留痕保护、测试删除和提交约束。探针用于检查 hook 是否接通。三个平台的拦截方式不同，分别验证：

```sh
PROBE='{"tool_name":"Bash","tool_input":{"command":"touch a.reins-probe-block"}}'
NORMAL='{"tool_name":"Bash","tool_input":{"command":"ls"}}'

# Claude Code / Codex：退出码 0，stdout 输出 JSON deny
echo "$PROBE" | "$CLI" hook pre-tool --runtime claude
echo "$PROBE" | "$CLI" hook pre-tool --runtime codex

# OpenCode：退出码 2，stderr 输出拦截原因
echo "$PROBE" | "$CLI" hook pre-tool --runtime opencode; echo "rc=$?"

# 普通命令：无输出，退出码 0
echo "$NORMAL" | "$CLI" hook pre-tool --runtime claude; echo "rc=$?"
```

| 运行时 | 探针预期 | 普通命令预期 |
| --- | --- | --- |
| claude / codex | `rc=0`，stdout 含 `"permissionDecision": "deny"` 和「Reins 探针拦截」 | `rc=0`，无输出 |
| opencode | `rc=2`，stderr 为「Reins 探针拦截：…」 | `rc=0`，无输出 |

每次 hook 调用都会追加一行到 `$REINS_HOME/logs/hooks.jsonl`，含 `verdict: allow / block`，不含原始 prompt。

**OpenCode 入口**（需要 Node，不需要装 OpenCode）：加载 `index.js`，确认它读到 4 个 agent 和 3 个命令，并能拦截探针：

```sh
node --input-type=module -e '
const m = await import("./reinsdev-plugin/index.js")
const { agents, commands } = m.loadContent()
console.log(Object.keys(agents), Object.keys(commands))
const p = await m.ReinsPlugin({ directory: "." })
await p["tool.execute.before"]({ tool: "bash" }, { args: { command: "touch a.reins-probe-block" } })'
```

预期打印 4 个 agent 名和 `[ 'spec', 'bugfix', 'waive' ]`，随后以「Reins 探针拦截」报错退出。

**安装预演**：`bin/reinsdev install --target all --dry-run` 只打印将要执行的命令和写入的文件，不做任何改动。

---

### 1.7 CLI 端到端联调

运行脚本，不启动 Claude/Codex/OpenCode，不调用模型。需要真实 JDK 17、Maven 及示例 POM 中的依赖：

```sh
python3 tools/e2e/run.py                      # 离线，某流程失败后继续其他独立流程
python3 tools/e2e/run.py --flows B C          # 仅工件评审/放行与 bugfix 范围
python3 tools/e2e/run.py --online             # 明确允许 Maven 下载依赖
python3 tools/e2e/run.py --diagnose           # 仅临时 A 流程诊断放行；有偏差仍返回 1
```

每次都建新的临时目录，打印目录位置。`steps.json` 保留命令、cwd、stdin、完整 stdout/stderr、实际及预期退出码；`steps.md` 给出逐步可读记录；`summary.json` 列出中断与诊断偏差。A 流程另保存真实 RED/GREEN Surefire XML 和 JaCoCo XML。`REINS_HOME` 指向本次临时目录。Maven 默认读取本机缓存，可用 `--maven-repo <路径>` 指定其他缓存；联网模式会向该缓存下载依赖。

脚本中的评审报告是按 `templates/reports/` 填写的协议测试输入，附有联调说明，不代表真实独立 agent 评审。只有 Surefire、JaCoCo 和 Maven 日志来自实际 Java 执行；不生成假的测试或静态分析报告。Windows 验证延后，Linux 本轮未实测。

| 流程 | 覆盖 | 判断 |
| --- | --- | --- |
| A：S feature | new、advance、TDD 提交、tasks-sync、init-config、6/6.5/6.7、code review、deploy skip、uat accept/reject、archive | 基线存在阻塞；诊断模式放行后探查后续，不能标为全链通过 |
| B：M feature | proposal/design/spec/tasks/spec-review、gate 5 拦截、口令授权、waive、推进 Phase 6 | 未授权 waive 应返回 1；gate BLOCK 为 3；授权后 WAIVED 为 0 |
| C：bugfix | new --mode bugfix、scope show/set、Phase 2/3 路由 | 2 个文件、不跨服务/DDL/API 时跳过 2/3；3 个文件且改 API 时两阶段必走；离开 Phase 1 后 scope set 返回 1 |

具体发现、任务归属和复现记录见 [联调报告](dev/e2e-report.md)。

#### 总控命令顺序

以下用于开发者复现总控调用。日常用户只接触 `/spec`、`/bugfix`、`/waive`，不需要手动敲内部 CLI。

```sh
"$CLI" new points-demo                       # Phase 0，创建分支、proposal、状态及 git hook
"$CLI" advance                               # gate 0 通过，进入 Phase 1
# 按 templates/proposal.md 填写真实输入
"$CLI" complexity set S                      # 正式选档
"$CLI" advance                               # S 跳过 2/3，进入 4
# 按 templates/tasks.md 填写任务；当前 S 的关联规则冲突见联调报告
"$CLI" advance                               # gate 4 通过才进入 6，跳过 5
# RED 提交：Task-Id: T1 + TDD-Phase: RED；GREEN：Task-Id: T1
"$CLI" tasks-sync                            # 只预览
"$CLI" tasks-sync --apply                    # 写入勾选，RED 不算完成
"$CLI" init-config --java --dry-run
"$CLI" init-config --java
"$CLI" advance                               # 同时检查 6、6.5、6.7；S 随后跳过 7
# 独立 code-reviewer 写 code-review.md
"$CLI" advance                               # 8 → 8.5
"$CLI" deploy skip --reason "用户原话"         # 8.5 → 8.9，CLI 留痕
# 用户输入完整验收口令后
"$CLI" uat accept                            # 消费授权，只记录验收，不自动推进
"$CLI" advance                               # 8.9 → 9
"$CLI" archive --dry-run
"$CLI" archive
```

`advance` 的 0 表示成功推进，2 表示 WARN 且尚未推进，3 表示 BLOCK 且停在原阶段；一般参数或环境错误返回 1。用户确认接受 WARN 后使用 `advance --ack-warn`，该参数不能绕过 BLOCK。单独运行 `gate N` 不推进阶段。

M 档需在 Phase 2 填 `design.md`，`design set "方案名"` 和文档的 `**最终选择**` 保持一致；Phase 3 填 `spec.md`；Phase 4 填 `tasks.md`；Phase 5 用 `spec-review.md` 过门。bugfix 在 Phase 1 填 `bugfix-analysis.md` 与 proposal，然后 `scope set --files 2`，必要时追加 `--cross-service`、`--ddl`、`--public-api`。`scope show` 可查看判定。

#### 用户口令与决策

在真实会话中必须由用户本人输入口令。只有本节的临时联调允许脚本模拟 UserPromptSubmit，不可用于替真实用户授权。

```sh
# 在 points-b 的临时项目根目录；check 必须取自 gate 输出
python3 -c 'import json,os; print(json.dumps({"hook_event_name":"UserPromptSubmit", "cwd":os.getcwd(), "prompt":"确认放行 points-b 5 g5-block-count"}))' \
  | "$CLI" hook prompt-submit --runtime claude
"$CLI" waive 5 g5-block-count --reason "联调演练接受预设风险"
```

Claude prompt-submit 返回 0，签发结果在 JSON 的 `hookSpecificOutput.additionalContext` 中。退出码 0 本身不代表授权成功；随后 `waive` 成功及 gate 的 `[WAIVED]` 才是完整证据。授权绑定 change、gate、检查项和当前 BLOCK 内容，不能复用到其他问题。

验收口令为 `确认验收 <change>`，同样经 prompt-submit；在 Phase 8.9 执行 `uat accept`。验收授权绑定 spec/QA 内容。拒绝验收使用 `uat reject --phase 8 --reason "用户要修改的内容"`，撤销验收并回退。先前的部署跳过决定会保留，重新通过 Phase 8 后可直接进入 8.9。`deploy skip --reason "用户理由"` 只在 Phase 8.5 生效，记录 `DEPLOY-VERIFIED: NO` 后进入 8.9。均可加 `--change` 定位。

#### git hook、报告和初始化

`new` 自动安装 `pre-commit` 和 `commit-msg`，也可以 `githook install` 重装。Phase 6 的源码/测试提交缺少 `Task-Id` 会被拒；RED 也应带 Task-Id，并另带 `TDD-Phase: RED`。勾选来自非 RED 提交；不得手写 `.meta.json`、`retrospective.md` 或其哈希文件。冻结工件的合法 CLI 更新与 pre-commit 目前有冲突，见报告；不要用关闭 hook 作为正常操作指南。

评审报告必须使用 `templates/reports/spec-review.md`、`qa-report.md`、`code-review.md`。首个非空行分别是 `<!-- generated-by: spec-evaluator-subagent -->`、`qa-evaluator-subagent`、`code-reviewer-subagent` 标记。`## 结论` 的表头为 `BLOCK | WARN | INFO`，唯一数据行是三个非负整数；`## 问题清单` 表头为 `级别 | 位置 | 问题 | 建议`，数量与结论一致，零问题时只留表头。QA 另有 `SC | 结果 | 证据` 表，逐个 SC 标 PASS/FAIL；bugfix spec-review 另有 `## bugfix 升级判定`。code-review 的 WARN 原文需经 `retro add --source "code-review WARN" "问题原文"` 记录。

`init-config --java --dry-run` 不执行质量命令、不写文件。正式初始化执行 ArchUnit、Checkstyle、SpotBugs、PMD 等检查，成功后写 `.openspec/.config.json` 和 `quality-baseline.json`。默认 Maven 质量命令带 `-o`，不会在线补依赖。配置命令、规则、依赖和报告路径必须可用；一个只有 Surefire/JaCoCo 的 POM 并不足以完成初始化。失败时不把失败结果保存为有效基线。gate 6.7 即使拦截也会生成 `static-analysis-report.md`；报告存在不能证明静态检查通过。

---

## 2. 在各平台本地加载

每个平台都给出几种加载方式，按需选一种。「临时加载」不改动任何全局配置，最适合反复验证。

### 2.1 Claude Code

**方式 A：临时加载（推荐）**

```sh
cd /tmp/reins-demo
claude --plugin-dir "$REINS/reinsdev-plugin"
```

插件只在这次会话里生效，退出即消失。改了文件后重开会话即可。

**方式 B：本地 marketplace**

仓库根目录本身就是一个 marketplace（`.claude-plugin/marketplace.json` → `./reinsdev-plugin`）。在 Claude Code 会话里：

```
/plugin marketplace add /absolute/path/to/reins
/plugin install reins@reinsdev
```

或在终端执行等价命令：

```sh
claude plugin marketplace add "$REINS"
claude plugin install reins@reinsdev
```

改了文件后：`claude plugin marketplace update reinsdev` 和 `claude plugin update reins@reinsdev`（安装时插件会复制到缓存），然后重开会话。

**方式 C：本地开发安装脚本**

```sh
./install.sh --target claude        # Windows：.\install.ps1 --target claude
```

脚本以本仓库为本地 marketplace 安装，最后运行 `reinsdev doctor`。重复执行即可更新。和用户的一行命令安装是同一套流程，只是源码用工作区。

**确认已加载**：`claude plugin list` 能看到 `reins@reinsdev`（方式 B / C）；会话里输入 `/` 能看到 `spec`、`bugfix`（插件 skill，可能显示为 `/reins:spec`，记下实际形式）；`/agents` 里能看到 `reins:spec-evaluator` 等 4 个 agent。

### 2.2 Codex

Codex 插件不能打包 agent，所以除了装插件，还要把 `agents/*.md` 转成 TOML 装到 `~/.codex/agents/`。

**方式 A：本地开发安装脚本（推荐）**

```sh
./install.sh --target codex   # Windows：.\install.ps1 --target codex
```

一条命令完成三件事：以本仓库为本地 marketplace、安装插件、安装 4 个 agent。改了文件后重复执行即可更新（Codex 没有 `plugin update`，脚本会先删再装）。装完重启 Codex。

已存在且内容不同、又不是 Reins 装的同名 agent 文件时整体拒绝，确认无误可加 `--force`。先看要执行什么可加 `--dry-run`。

**方式 B：原生命令（模拟用原生命令安装的用户）**

```sh
codex plugin marketplace add "$REINS"
codex plugin add reins@reinsdev
bin/reinsdev setup codex   # 安装 4 个 agent；加 --project 则装到当前目录的 .codex/agents/
```

想验证缺 agent 时的提示，先不运行 `setup codex`，直接进会话用 `$spec`：总控应停下并请你运行 `reinsdev setup codex`，而不是自己生成 agent 文件。

改了文件后：`codex plugin remove reins@reinsdev` + `codex plugin add reins@reinsdev`；agent 有改动时重新执行 `setup codex`。

**确认已加载**：`codex plugin list` 能看到 `reins`；`codex plugin marketplace list` 能看到 `reinsdev`；`~/.codex/agents/` 下有 `spec-evaluator.toml` 等 4 个文件；会话里 `$spec`、`$bugfix` 可用。

### 2.3 OpenCode

OpenCode 的插件是一个 JS 模块，`reinsdev-plugin/index.js` 在 `config` 钩子里读取共用的 agents 和入口 skill、注入 agents、commands 和 skills 路径，所以只要让 OpenCode 加载这个文件即可。

**方式 A：项目级插件文件（推荐）**

在示例项目里放一个转引文件，只对这个项目生效：

```sh
mkdir -p /tmp/reins-demo/.opencode/plugins
printf 'export * from "file://%s/reinsdev-plugin/index.js"\n' "$REINS" \
  > /tmp/reins-demo/.opencode/plugins/reins.js
cd /tmp/reins-demo && opencode
```

Windows 上 `file://` 后面用正斜杠的盘符路径，如 `file:///C:/work/reins/reinsdev-plugin/index.js`。

改了文件后重启 OpenCode 即可，转引文件不用动。

**方式 B：本地开发安装脚本（全局）**

```sh
./install.sh --target opencode      # Windows：.\install.ps1 --target opencode
```

脚本写入 `~/.config/opencode/plugins/reinsdev.js`（遵循 `OPENCODE_CONFIG_DIR` / `XDG_CONFIG_HOME`），转引 `reinsdev-plugin/index.js`，对所有项目生效。

**确认已加载**：会话里 `/spec`、`/bugfix`、`/waive` 命令可用；输入 `@` 能看到 `spec-evaluator` 等 4 个 agent。

---

### 2.4 一行命令安装

验证用户用的 `curl ... | sh` 流程：clone、启动器、PATH 提示、`update`。仓库改动先要进一个 git 仓库才能被 clone，所以用一个临时仓库当远程，所有目录都指向临时位置：

```sh
T=$(mktemp -d)
rsync -a --exclude .git "$REINS/" "$T/remote/" && git -C "$T/remote" init -q -b main && git -C "$T/remote" add -A && git -C "$T/remote" commit -qm snap
export REINS_REPO="$T/remote" REINS_HOME="$T/home" XDG_CONFIG_HOME="$T/cfg" CODEX_HOME="$T/codex"
cd "$T" && cat "$REINS/install.sh" | sh -s -- --target opencode
```

| # | 检查 | 预期 |
| --- | --- | --- |
| 2.4.1 | `ls "$T/home/src" "$T/home/bin"` | 源码已 clone；`bin/reinsdev` 存在 |
| 2.4.2 | 安装输出末尾 | 有 `reinsdev doctor` 的输出，并提示把 `$T/home/bin` 加进 PATH |
| 2.4.3 | `"$T/home/bin/reinsdev" version` | 打印版本号 |
| 2.4.4 | 在 `$T/remote` 再提交一次，然后 `"$T/home/bin/reinsdev" update` | `git pull` 拉到新提交，并重装 opencode |
| 2.4.5 | `"$T/home/bin/reinsdev" uninstall` | 删除 `$T/cfg/opencode/plugins/reinsdev.js`，`$T/home/installed.json` 为 `{}` |

Windows 上对应 `install.ps1`：设好同样的环境变量（`$env:REINS_REPO` 等，外加 `$env:REINS_TARGET="opencode"`），在仓库根目录执行 `Get-Content .\install.ps1 -Raw | iex`。

## 3. 会话内验证清单

以下平台会话验证本轮未执行。把下文 `/tmp/reins-demo` 替换成实际示例目录，再启动已加载 Reins 的平台，逐项执行。表中「入口」一列：Claude Code、OpenCode 用 `/spec`、`/bugfix`、`/waive`，Codex 用 `$spec`、`$bugfix`、`$waive`。

| # | 操作 | 预期 |
| --- | --- | --- |
| 3.1 | 输入 `/spec 批量审批返利政策` | 触发 spec-driven-dev 总控；它先运行打包在插件里的 `spec-driven status`，报告当前项目状态；全新项目会提示尚未启用，脚本生成的项目会报告已有 change 状态 |
| 3.2 | 继续让它建 change | 总控调用 `new` 创建分支、proposal 和状态，安装 git hook；用 `advance` 通过 gate 0 进入 Phase 1 |
| 3.3 | 输入 `/bugfix "登录后首页 500"` | 同样触发总控，以 bugfix 模式处理 |
| 3.4 | 让模型执行 `touch a.reins-probe-block` | 被 hook 拦截，提示「Reins 探针拦截」；`ls` 看不到该文件 |
| 3.5 | 让模型新建文件 `b.reins-probe-block` | 同样被拦截（编辑类工具走同一个判定点） |
| 3.6 | 让模型执行 `ls` 或读一个普通文件 | 正常执行，不受影响 |
| 3.7 | 查看 `$REINS_HOME/logs/hooks.jsonl` 末尾几行 | 3.4 / 3.5 为 `"verdict": "block"`，3.6 为 `"allow"`；记录中没有 prompt 原文 |
| 3.8 | M 档写完 proposal/design/spec/tasks，用 `advance` 到 Phase 5，调 spec-evaluator | 独立 agent 按报告模板写 spec-review；缺输入须报 BLOCK；通过 gate 5 后才能推进 |
| 3.9 | 在终端运行 `bin/reinsdev doctor` | 当前平台各护栏的落实层与下表一致 |

各平台调度 agent 的方式（3.8）：

| 平台 | 做法 |
| --- | --- |
| Claude Code | 模型用 Agent 工具调用 `reins:spec-evaluator`；也可以直接说「用 reins:spec-evaluator 评审 proposal.md」 |
| Codex | 必须**明确要求**派生 agent，例如「派生 spec-evaluator 子 agent 评审 proposal.md」；没装 agents 时总控会请用户运行 `reinsdev setup codex` |
| OpenCode | 输入 `@spec-evaluator 评审 proposal.md`，或由模型调用 task 工具 |

### 3.1 需要人工确认的平台行为

以下几点依赖平台自身行为，单测覆盖不到，`doctor` 会标为「待实测」。验证时顺带确认并记下结果：

| 平台 | 验证点 | 方法 |
| --- | --- | --- |
| Claude Code / Codex | UserPromptSubmit hook 是否收到用户每条输入（放行授权依赖它） | 在会话里输入任意一句话，看 `hooks.jsonl` 末尾是否有对应的 `prompt-submit` 记录 |
| OpenCode | 用户在主会话里输入口令能否签发授权，子 agent 会话能否被拒 | 制造一个拦截后输入「确认放行 <change> <gate> <检查项>」，看 `$REINS_HOME/grants/` 是否出现文件；再让模型用 task 派子 agent，在提示里写同一句口令，确认不会出现授权文件 |
| OpenCode | 子 agent 的工具调用是否被 hook 拦截 | 用 `@spec-evaluator` 让子 agent 执行 `touch d.reins-probe-block`，看是否被拦截 |
| 全部 | 评审 agent 的写权限是否受限 | 让 spec-evaluator 修改 `proposal.md`，预期被工具权限或 hook 拒绝 |

---

## 4. 清理

| 加载方式 | 清理 |
| --- | --- |
| Claude Code 方式 A | 退出会话即可 |
| Claude Code 方式 B | `claude plugin uninstall reins@reinsdev` + `claude plugin marketplace remove reinsdev` |
| Codex 方式 B | `codex plugin remove reins@reinsdev` + `codex plugin marketplace remove reinsdev`，再 `bin/reinsdev uninstall --target codex` 删除 agent |
| OpenCode 方式 A | 删除示例项目里的 `.opencode/plugins/reins.js` |
| 安装脚本（Claude Code 方式 C、Codex 方式 A、OpenCode 方式 B） | `bin/reinsdev uninstall [--target claude\|codex\|opencode]`，按 `~/.reins/installed.json` 精确撤销 |

确认保留证据后，只清理本次生成的临时示例目录和临时 `REINS_HOME`。不要为了联调删除真实 `~/.reins/`。

想让验证完全不碰默认目录，可以在执行 `install` / `uninstall` / hook 前设置 `REINS_HOME=/tmp/reins-home`，构建产物、安装记录和 hook 日志都会写到那里。

---

## 5. 常见问题

| 现象 | 原因与处理 |
| --- | --- |
| 会话里看不到 `/spec` | 插件 skill 可能带命名空间，试 `/reins:spec`；装在缓存里的旧版本要按 §2 刷新；Codex 上入口是 `$spec` |
| 改了文件但行为没变 | 本地 marketplace 安装会复制到平台缓存：按 §2 对应方式刷新；`--plugin-dir` 和 OpenCode 转引只需重开会话 |
| hook 没拦截探针 | 先跑 §1 的探针命令排除 CLI 问题；再看 `hooks.jsonl` 有没有记录——没有记录说明平台根本没调用 hook |
| hook 完全不触发（Windows，Claude Code） | 没装 Git for Windows，Claude Code 退回 cmd.exe；`doctor` 会报 `Git Bash 未找到` |
| hook 报 `os error 5`（Windows，Codex） | 选中了商店版 pwsh（openai/codex#47810）；装 MSI 版 PowerShell 7，或调整 PATH 顺序 |
| 启动器报找不到 Python | 安装 Python 3.8+；Windows 上避免只有商店版 `python3` 空壳 |
| `install` 拒绝覆盖某个文件 | 目标位置已有非 Reins 安装的同名文件；确认可覆盖后加 `--force` |
