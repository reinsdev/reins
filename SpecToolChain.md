# Spec-Driven 研发工件链 PRD

Sep 26, 2026 · @Ronnie

Spec-Driven 研发工件链（Reins）是一套运行在 Claude Code、Codex、OpenCode 上的规格驱动研发插件：以 Phase 主链、独立评审 agent、机器验证门和 hook 护栏，把需求到归档的全流程变成可校验、可追溯的工件链。适用于 Java 项目（Maven / Gradle）。

## 1. 复杂度分级与产物路由

每个 change 按 S/M/L 三通道走不同深度的流程，档位在 Phase 1 末尾正式选定。

| 档位 | 流程要求 |
| --- | --- |
| S | 默认跳过 Phase 2/3/5/7；约 80% 的简单需求，工件不超过 4 个 |
| M | 必走 Phase 5/7，使用全套骨架 |
| L | 必须给出 ≥3 个方案的 design；spec-evaluator 评审 2 轮 |

- 通过 `spec-driven complexity show/set` 选定档位。
- Phase 2、Phase 3 各对复杂度做一次复评，规则为「只升不降」。
- 降档只能由用户本人在对话里输入确认口令后执行，记入 retrospective.md「档位变更记录」。

### 产物路由规则（三平面沉淀）

| 写的内容 | 去处 |
| --- | --- |
| 可观察行为（WHEN/THEN） | change 的单个 spec.md 的 REQ/SC |
| 接口契约 / 数据模型 | 同一 spec.md 文末两节（回指 SC） |
| 一次权衡/选型的「为什么」 | ADR：decisions/\<NNNN>-\*.md（归档时从 design 蒸馏） |
| 全局结构约束/层边界 | architecture.md |

一个 change 只产出一个扁平 spec.md，归档时按 Capability ID 路由合并进主 specs/\<capability>.md。

## 2. Generator-Evaluator 分离的 agent

生成与评审分给独立 agent，评审角色只读，避免主线自己给自己打分。

| Agent | 职责 | 工具隔离 |
| --- | --- | --- |
| spec-evaluator | Phase 5 独立评审 spec 工件，刻意苛刻，支持 bugfix 变种 | 只读，只能写自己的 spec-review.md |
| implementation-generator | Phase 6 按 TDD 节奏写码，每任务一提交 | 可写，但路径锁（禁改 `.openspec/` / 删测试），branch 绑定 |
| qa-evaluator | Phase 7 按 WHEN/THEN scenario 逐条验证实现，PASS/FAIL 带证据 | 只读 + 可跑测试，只能写自己的 qa-report.md |
| code-reviewer | Phase 8 按 tiered-code-review 规范评审代码改动 | 只读 + 可跑 git / 测试，只能写自己的 code-review.md |

隔离边界由四层构成：

- 角色：不同 system prompt。
- 工具：评审者只读，只能写自己的报告。
- 上下文：工件走文件交接。
- 机器标记兜底：报告首行必须带 `generated-by: <agent>-subagent`，gate 校验该标记。

agent 失败重试一次，仍失败则 STOP 交人工，禁止主线自写评审报告当通过。

## 3. Skills 清单（17 个）

### 3.1 主链 skill

| Skill | Phase | 职责 |
| --- | --- | --- |
| spec-driven-dev | 总控 | 建 change、Phase 路由、复杂度通道、跑 gate、调度 agent、Phase 8.9 验收、Phase 9 归档（含 ADR 蒸馏） |
| requirements-clarify | 1 | 歧义识别 + AC 提取（含代码现状扫描） |
| tech-design-tradeoff | 2 | 强制 ≥2 备选方案 + tradeoff + 明确推荐 |
| api-design-rest | 3a | REST/RPC 接口规范，产 spec.md 行为脊柱 + ## 接口契约 |
| db-schema-design | 3b | DDL/索引/迁移，产 ## 数据模型 节 + 补 SC 的 DB 后置状态 |
| task-breakdown | 4 | spec → tasks.md，按层拆分，关联 SC |
| tdd-implement | 6 | RED-GREEN-REFACTOR 规范，由 implementation-generator 执行 |
| tiered-code-review | 8 | BLOCK/WARN/INFO 三档分级规范，由 code-reviewer 执行 |

### 3.2 变种入口

| Skill | 职责 |
| --- | --- |
| bugfix | 以 `/bugfix "<问题描述>"` 启动，对话补全缺陷信息，起草 bugfix-analysis + proposal，Phase 2/3 条件性瘦身 |

### 3.3 横切 skill（不进 phase，任意调用）

| Skill | 用途 | 推荐调用点 |
| --- | --- | --- |
| root-cause-analysis | bug/联调/测试失败根因分析，只分析不修 | Phase 1/6/7 |
| incident-analysis | 线上事故/告警分析，只给建议不操作生产 | incident |
| code-quality-optimize | 横切质量分析：早期返回/N+1/圈复杂度/命名/重复/嵌套 | 任意，实现后或 review 前 |
| codegraph | 用 CodeGraph 代码知识图谱一次拿符号源码 + 调用链 + 影响半径，替代 grep/Read；探测到才启用，否则静默回退 | Phase 2/3/6/8 |
| log-search | 读本地日志文件，按时间范围 + 关键字检索，脱敏 | Phase 1/6/7 |
| local-deploy | 本地启动应用，产出 deploy-report.md，交给人工验收 | Phase 8.5 |
| openapi-check | 读本地 Swagger 端点，与 spec.md ## 接口契约 比对 | Phase 6 实现后 / Phase 8 |
| safety-check | 平台 hook 不可用时，显式调用 bash-guard/spec-gate/gate 护栏 | 平台 hook 不可用时 |

## 4. 机器验证门（Gates）

每个 Phase 由 `spec-driven gate <phase>` 机械校验，总控主循环显式调用，gate-router（UserPromptSubmit hook）也会按用户输入关键字触发。退出码 0 放行、2 WARN、3 BLOCK。任何 BLOCK 都可由用户本人确认放行并留痕：输入 `/waive` 或说「放行」，再输入确认口令。

| Gate | 校验内容 |
| --- | --- |
| gate-0 | Java 构建文件存在 + change 名规范 + `.meta.json` mode 合法 |
| gate-1 | proposal 完整性 + 业务取值不可自填过门 + 字段映射确认表（来源必须=用户）+ 档位落定 |
| gate-2 | design ≥ 2 方案 + 改选即回写硬校验（.meta.json.designDecision 与 design.md 最终选择一致）+ 复杂度复评（只升不降） |
| gate-3 | AC→SC 映射完整 + 接口契约 / 数据模型节完整 + 复杂度复评 |
| gate-4 | tasks 完整性 + 分层顺序 + bugfix 必有 T-regression |
| gate-5 | spec-review 无 BLOCK + subagent 标记（防主线降级自评） |
| gate-6 | 测试文件存在 + 测试真跑（0 测试 / surefire skip / -DskipTests → BLOCK）+ RED commit 先于 GREEN + JaCoCo 增量覆盖率 |
| gate-6.5 | 任务完成靠 git Task-Id trailer 证据（tasks-sync 单点补勾），拦裸 - \[ \] |
| gate-6.7 | 静态质量门：ArchUnit / Checkstyle / SpotBugs / PMD / SQLFluff（覆盖 MyBatis mapper XML / Flyway 脚本）；以基线区分存量违规，新增违规 BLOCK |
| gate-7 | qa-report 无 FAIL + subagent 标记 |
| gate-8 | code review 无 BLOCK + subagent 标记 |
| gate-8.5 | 选择部署验收时 deploy-report 结论为 passed |
| gate-8.9 | 用户验收通过（uatAccepted） |
| gate-9 | 归档完整 + 主 specs 已合并 + retrospective 存在 |

## 5. 护栏 hook 全景

各平台的 hook 配置都转调 `spec-driven hook`，由它统一判定：

| 时机 | hook | 作用 |
| --- | --- | --- |
| PreToolUse（Bash） | bash-guard | 拦截危险命令，拦截对放行授权文件 `~/.reins/grants/` 的写入 |
| PreToolUse（Bash） | commit-guard | 验证门 + 编译前置 |
| PreToolUse（Edit/Write） | spec-gate | 上游冻结 + 路径锁 + branch 绑定 + 禁改 retrospective.md |
| PostToolUse | audit-log | 脱敏审计 |
| PostToolUse | archive-on-merge | 提示归档 |
| PostToolUse | cost-tracker | token + model 校验 |
| Stop | commit-draft | 生成 commit message 草稿 |
| UserPromptSubmit | gate-router | 按关键字触发 gate |
| UserPromptSubmit | phase-router | 复杂度通道感知 |
| UserPromptSubmit | waive-grant | 用户原样输入确认口令时签发一次性放行 / 降档授权 |

## 6. 旗舰能力

以下能力均为可选增强，默认关闭或仅告警，不影响主链。

### 6.1 多 Agent 并行执行器

`spec-driven parallel` 子命令：

- plan：只读预演，DAG + scope 重叠分析 + 波次分层 + 诚实收益预估。
- run：每任务独立 git worktree（项目外隔离）；协调者串行 merge（冲突 abort + BLOCK，不自动覆盖）；单点 tasks-sync/gate-6.5；波内可并发，真并发度取决于 harness，不支持则隔离串行仍正确。
- status / clean。
- 默认关（parallel.enabled=false），仅建议 L 档/大型 change 使用。

### 6.2 CodeGraph 代码知识图谱集成

- 横切 skill，探测到 codegraph CLI + .codegraph/ 索引才启用，否则静默回退 Grep/Read，零影响。
- 一次 `codegraph explore` 拿到符号源码 + 调用链（含动态分发）+ 影响半径，替代逐文件 Read。
- `codegraph affected` 可给 gate-6 提供「只跑受影响测试」（默认关，推荐先 warn 观察）。
- 使用阶段：Phase 2/3 现状扫描、Phase 6 取被调方法上下文、Phase 8 review 取被改方法 + 影响面。

### 6.3 测试质量硬化

- 严格 RED-先于-GREEN 时序校验。
- 弱测试启发式（空断言 / assertNotNull 兜底 / 反射测私有方法）。
- commit trailer 缺失兜底。
- 三项均默认开、只 WARN 不 BLOCK。

### 6.4 接口契约 ↔ OpenAPI 一致性

openapi-check skill + `spec-driven openapi` 子命令：

- Phase 3a 由 api-design-rest 可选产出 openapi.draft.json（设计意图骨架，spec-first）。
- Phase 6/8 读本地应用暴露的 Swagger / OpenAPI 端点（code-first，权威真值）。
- 与 spec.md ## 接口契约 及 draft 做一致性校验，破坏性变更出 diff 报告。
- 默认关（openapi.enabled=false）。

## 7. 抗自欺与抗压缩

### 7.1 防自欺

- 业务取值（固定常量/字段映射/格式）不允许用「默认值」蒙混过 gate-1。
- 评审/QA/code review 失败时禁止主线降级自评（gate-5/7/8 机器标记）。
- Phase 6 完成定义严格区分：编译 ≠ 测试 ≠ 完成。
- Phase 8.9 用户验收门。
- 放行与降档只能由用户本人在对话里输入确认口令，由 UserPromptSubmit hook 签发一次性授权，记入 retrospective.md。

### 7.2 抗压缩（长会话里反复压缩重学）

- invariants.json 记录 field\_mappings / env\_notes（业务取值 + 环境备忘）。
- 重活下沉 subagent（节省主线上下文）。
- spec-driven resume 冷启动恢复包：从磁盘拼最小上下文（下一步 + invariants 摘要）。
- 会话分段。

## 8. CLI

安装阶段的命令由 `reinsdev` 提供，用户可见；其余由插件内的 `spec-driven` 提供，只供总控和 hook 调用，用户看不到。

| 类别 | 子命令 |
| --- | --- |
| 安装与环境（由 `reinsdev` 提供） | install / update / uninstall / setup codex / doctor / version |
| 工件链 | status / resume / list / retry \<phase> / switch / diff / gate \<phase\|all> \[--strict\|--soft\] |
| 复杂度 | complexity \<show\|recheck\|set> |
| 设计 | design \<show\|set>（Gate 2 改选后必须 set） |
| 任务 | tasks-sync（据 commit Task-Id trailer 单点渲染勾选，默认 dry-run） |
| 放行与留痕 | waive \<gate> \<检查项> --reason / retro add |
| 能力 | index（刷新 specs/README 能力索引）/ capability \<list\|init> |
| OpenAPI | openapi \<draft\|check\|diff> |
| 并行 | parallel \<plan\|run\|status\|clean> |
| 配置 | init-config \[--java\] / config-sync \[--write\] |
| hook | hook \<pre-tool\|prompt-submit> --runtime \<claude\|codex\|opencode> |
| 可观测 | analytics（token/USD，按 agent/phase 分组）/ trace \<id>（AC/SC/T ID 反查 spec→tasks→test） |

## 9. 本地集成（配置了即开启，用不到就跳过）

| 集成 | 入口 | 配置 |
| --- | --- | --- |
| 本地日志 | log-search | `.openspec/.config.json` 中的日志路径 |
| 本地部署验收 | local-deploy | `.openspec/.config.json` 中的启动命令 |
| Swagger / OpenAPI | openapi-check | `.openspec/.config.json` 中的本地端点地址 |
| CodeGraph 代码图谱 | 横切 skill 自动用 | 无需 key，装 codegraph CLI + codegraph init |

所有集成只访问本机资源，不依赖外部平台。

## 10. 安全护栏原则

- 凭证一律走环境变量，配置文件禁止出现密钥字面量。
- audit-log 脱敏，不记录原始 prompt。
- .meta.json 并发锁。
- branch 绑定（git branch 必须与 change 绑定一致）。
- implementation-generator 路径锁（禁改 `.openspec/` / 删测试，bash-guard 拦测试目录删除）。
- spec-gate soft warning：无活跃 change 时放行但提醒先 /spec，保留用户判断权（避免逼用户 --no-verify 绕开整个护栏）。
- local-deploy 只在本机启动应用，不操作任何远程环境。
- 线上事故分析 skill 绝对不执行任何生产操作，所有建议人工确认后执行。

## 11. 安装与平台适配

| 平台 | skills | agents | 入口 | hooks |
| --- | --- | --- | --- | --- |
| Claude Code | ✓ | ✓ | `/spec`、`/bugfix` | ✓（PreToolUse / UserPromptSubmit 等） |
| Codex | ✓ | ✓（`reinsdev` 安装） | `$spec`、`$bugfix`（入口 skill） | ✓（PreToolUse / UserPromptSubmit） |
| OpenCode | ✓ | ✓ | `/spec`、`/bugfix` | ✓（JS 插件 `tool.execute.before`） |

### 安装方式

- 一行命令（推荐）：`curl -fsSL https://raw.githubusercontent.com/reinsdev/reins/main/install.sh | sh`（Windows 用 `install.ps1`），安装 `reinsdev` 并装好本机所有平台。
- Claude Code：`/plugin marketplace add reinsdev/reins` + `/plugin install reins@reinsdev`。
- Codex：`codex plugin marketplace add reinsdev/reins` + `codex plugin add reins@reinsdev`，再运行 `reinsdev setup codex` 安装 agents。
- OpenCode：`opencode plugin @reinsdev/opencode -g`，或写进 `opencode.json` 的 `plugin` 数组。

### 通用 skill + 项目专属规约分离

通用 skill 执行时自动加载 \<project>/.claude/skills/\*-conventions/SKILL.md，实现「通用骨架 + 项目方言」分离，每个项目的规约各自维护，互不影响。

### 跨平台运行

- CLI 只用 Python 3.8+ 标准库，随插件打包，不需要单独安装。
- 启动器 `spec-driven`（sh）和 `spec-driven.cmd` 自动寻找可用的 Python；Windows 上 Claude Code 靠 Git Bash 执行 hook。
- 所有文件读写与 hook 输出统一 UTF-8；没有 Python 时 hook 放行、其他命令失败。
