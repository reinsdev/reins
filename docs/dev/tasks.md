# 并行开发任务书

每个任务交给一个 agent（或一个开发）独立完成。开工前必读：[AGENTS.md](../../AGENTS.md)（规约）→ [architecture.md](architecture.md)（架构与契约）→ 本文你的任务一节。

契约层（T0）已经就位：所有模块的文件、函数签名、CLI 命令、gate 框架、hook 判定链都已存在，未实现的部分是桩代码（`raise NotImplementedError` 或返回「该能力不可用」）。**每个任务只把自己名下的桩填实**，不新增跨任务的公共文件。

## 如何领取任务

协调者只会告诉你两件事：**你的名字**和**任务编号**。其余全部在本仓库里：

1. 读 [AGENTS.md](../../AGENTS.md)（规约）和 [architecture.md](architecture.md)（架构与契约）。
2. 读本文你的任务一节：拥有哪些文件、要做什么、怎样算完成。
3. 从 `feature/dev_0.1` 最新提交拉出 `task/T<n>-<名字>`，在单独的 git worktree 里开发。
4. 按 AGENTS.md §6 交付：提交信息以名字开头（`<名字>: T<n>: <做了什么>`）；运行测试时加 `set -o pipefail`，Python 3.8 和 3.12 全部通过；推送分支到远端；交付说明写四项。

任务之间「拥有的文件」互不重叠。发现需要改别人的文件、或契约不对，停下来写进交付说明，由协调者处理。

## 总览

| 任务 | 内容 | 依赖 | 状态 |
| --- | --- | --- | --- |
| T1 | markdown 解析 + 工件模板 | — | ✅ 已合入 |
| T2 | 状态与生命周期命令 | — | ✅ 已合入 |
| T3 | gate 0–4 | T1、T2 | ✅ 已合入 |
| T4 | gate 5、7、8、8.5、8.9 | T1、T2 | ✅ 已合入 |
| T5 | gate 6、6.5、6.7 + `init-config` | T1、T2 | ✅ 已合入 |
| T6 | 护栏：hook 规则、放行授权、留痕、git hook | T2 | ✅ 已合入 |
| T7 | 归档：`archive` + gate 9 | T1、T2 | ✅ 已合入 |
| T8 | 总控细则 + 主链 skill + bugfix 变种（含接入 T11 命令） | T1 | ✅ 已合入 |
| T9 | 4 个 agent + 评审报告填写说明 | T1 | ✅ 已合入 |
| T10 | 8 个横切 skill | T8 | ✅ 已合入 |
| T11 | 用户决策命令：uat / scope / deploy skip | T2、T6 | ✅ 已合入 |
| T12 | 排查偶发的测试失败 | — | 📋 待领取 |
| T13 | 端到端联调 + 更新 README 与验证手册 | T1–T11 | ✅ 已完成（Json）；文档与联调脚本已合入 |
| T14 | 多实例安全（CLI 状态层，含追加：hook 放行 tasks-sync 的勾选） | — | 📋 待领取 |
| T15 | gate 6.7 质量检查的并发保护 | — | ✅ 已合入（追加的「初始化报错可定位」转入 T20） |
| T16 | Java 质量工具接入：ArchUnit 自动接入，Checkstyle / PMD / SpotBugs 可直接运行 | T5 | 📋 待领取（建议 Json） |
| T17 | S 档任务关联 AC（联调问题 E2E-01） | T1、T3、T8 | 📋 待领取（建议 Codex） |
| T18 | 工件骨架生成 `scaffold` + 需求链追溯 `trace` | — | 📋 待领取 |
| T19 | Phase 6 多实现者并行 `parallel` | T14 | 📋 待领取（优先级低，T14 合入后开工） |
| T20 | SQL 检查完善（动态 SQL、占位符、`${}`、告警级规则、按数量比较违规、报错可定位） | T15 | 📋 待领取（建议 John，可以开工） |

T12、T14–T17 可以同时开工，拥有的文件互不重叠。联调报告的问题编号（E2E-01 至 E2E-04）见各任务说明。

## 待办与延后

| 事项 | 类别 | 负责 | 状态 |
| --- | --- | --- | --- |
| T9 本地分支 rebase 到最新 feature 分支，保留 implementation-generator「允许追加 implementation-log.md」的修正（26c14ed） | 小事项 | T9 | ✅ 已完成（快进到 8b173f1） |
| 删除 T8 早期草稿 worktree `codex_dev/reins-T8-Codex-draft-3caa86c` 及分支 `task/T8-Codex-draft-3caa86c`（正式版已完整覆盖） | 小事项 | T8 或用户 | ✅ 已删除 |
| Windows 真实环境验证：`install.ps1`、Git Bash 下的 hook、Codex 经 PowerShell 的 hook | 验证 | 待定 | 延后到 T13 之后 |
| gate 1「复评结果与已确认档位不一致时给提示」（workflow §5.3） | 小功能 | T3 | 延后 |
| gate 6 集成测试 `auto` 模式依赖 `.meta.json` 的 `qa_mode`，目前无命令写入 | 缺口 | 协调者 | 延后 |
| E2E-04：`spec-driven-workflow.md` 与现状不一致（旧脚本名、`tasks-sync --write` 应为 `--apply`、验收写状态方式、feature 不分档必走 2/3） | 文档 | 协调者 | ✅ 已完成 |

---

## T1 markdown 解析 + 工件模板

**目标**：所有 gate 都靠它读工件；所有写工件的 skill 都按它的模板写。它是格式的唯一来源。

**拥有的文件**
- `lib/spec_driven/mdparse.py`
- `skills/spec-driven-dev/templates/*.md`（新建）
- `tests/test_mdparse.py`、`tests/fixtures/t1/`

**要做的**
1. 按 `spec-driven-workflow.md` 写出全部工件模板：`proposal.md`（feature / bugfix 两版）、`bugfix-analysis.md`、`design.md`、`spec.md`、`tasks.md`、`implementation-log.md`、`deploy-report.md`。模板只含标题、表头、占位说明，占位用 `<…>`，不要用 `{{ }}`（插件测试禁止）。
2. 填 `ALIASES`：模板里每个会被 gate 查找的章节一个键（如 `out-of-scope`、`user-stories`、`ambiguities`、`field-mapping`、`interface-contract`、`data-model`、`final-choice`…）。每个键的第一个变体必须和模板标题完全一致；兼容中英文和常见写法。
3. 实现 `parse / find / find_all / ids / tables / checkboxes` 和 `Section.text()`，行为以 docstring 为准。忽略围栏代码块里的标题和 ID；兼容 CRLF；表格支持转义竖线。
4. 在本文件末尾的「别名索引」一节列出所有键和对应模板标题（这是本任务唯一允许改的 docs 文件段落）。
5. 补充：`bugfix-analysis.md`、`proposal-bugfix.md` 标题里的占位符改为 `<change-name>`（`new` 只替换它）。评审报告相关的 6 个 ALIASES 键、`templates/reports/` 骨架和别名索引已由协调者按契约加好。

**验收**
- 每个模板经 `parse()` 后，`ALIASES` 里的每个键都能 `find()` 到。
- 覆盖：嵌套标题、同名标题、代码块里的假标题、中文编号标题（「一、」「1.」）、空表格、单元格含 `|`、三种复选框状态、ID 去重保序、`SC-x-E2` 这类异常场景 ID。

---

## T2 状态与生命周期命令

**目标**：让总控能建 change、知道当前在哪、下一步去哪、能回退、能选档。

**拥有的文件**
- `lib/spec_driven/meta.py`、`router.py`、`locate.py`、`gitutil.py`、`taskstate.py`
- `commands/new.py`、`status.py`、`resume.py`、`retry.py`、`complexity.py`、`design.py`、`tasks_sync.py`
- `tests/test_meta.py`、`test_router.py`、`test_locate.py`、`test_gitutil.py`、`test_lifecycle.py`，`tests/fixtures/t2/`

**要做的**
1. `meta`：按设计文档 §3.2 生成与校验；`lock()` 用 `O_CREAT|O_EXCL` 锁文件，超时和过期清理；`save()` 原子写。
2. `router`：设计文档 §3.3 的跳过规则表（含 bugfix 的额外规则，bugfix 的判定依据先读 `meta` 里的字段，缺少时视为「走」）；`next_phase()` stale 优先。
3. `locate.resolve()`、`gitutil` 全部函数。
4. 命令：
   - `new`：设计文档 §7 Phase 0 的 6 步。bugfix 名字按 `fix-<YYYYMMDD>-<slug>`。最后一步调用 `commands.githook` 的安装（T6 实现；未实现时跳过并提示），再跑 gate-0（T3 实现；未实现时提示）。
   - `status`：在现有输出上加「下一步」（`router.next_phase`）和 `--json` 的 `next` 字段，保留「尚未启用 Reins」的原文。
   - `resume`：设计文档 §8 的一屏输出。
   - `retry`：设计文档 §8 的 4 件事。
   - `complexity`：`show` 的推荐档规则写在代码常量里并有理由输出；`set` 经 `retro.append_tier_change` 留痕；`--downgrade` 必须 `grants.consume(..., "downgrade", tier, "")` 成功，否则拒绝并说明口令；`recheck` 只升不降。
   - `design`：`show` / `set`，读 design.md 用 `mdparse`。
   - `tasks-sync`：计算逻辑放在 `taskstate`（gate 6.5 也用），命令只负责打印差异，`--apply` 才写 tasks.md。

**验收**
- 两个进程同时 `meta.update()` 不丢写（用 `multiprocessing` 测）。
- 跳过规则表每一格都有测试。
- 在临时 git 仓库里：`new` → `status` → `retry 1` → `resume` 全流程测试。

---

## T3 gate 0–4

**目标**：Phase 0–4 的产出能被机械校验。

**拥有的文件**：`gates/g0.py`–`g4.py`，`tests/test_gates_0_4.py`，`tests/fixtures/t3/`

**要做的**：按设计文档 §6.2 表格和 `spec-driven-workflow.md` 对应的「验证门」小节，逐条实现为 `Finding`。每条规则一个稳定的 `check` 编号，写在模块顶部的列表里并附一句说明。「业务取值来源必须是用户」「tierConfirmed」这类防自欺检查设 `locked=True`。复杂度复评只出 WARN，不改 meta。

**验收**：每个 `check` 一组合格 / 不合格 fixture；fixture 基于 T1 模板填写；`spec-driven gate <n>` 在 fixture 项目里输出与预期一致。

---

## T4 gate 5、7、8、8.5、8.9

**拥有的文件**：`gates/g5.py`、`g7.py`、`g8.py`、`g8_5.py`、`g8_9.py`，`tests/test_gates_review.py`，`tests/fixtures/t4/`

**要做的**
- 报告类 gate（5、7、8）：首行 generated-by 标记（`locked=True`）；扫描「主线自评」「直接根据代码验证」等降级措辞（`locked=True`）；报告格式严格按 architecture.md §4.2 解析（结论表、问题清单、SC 验证结果、bugfix 升级判定），缺失或不合法一律 BLOCK。
- gate 7：spec.md 的每个 SC 在 qa-report 里都是 PASS。
- gate 8：问题清单里每条 WARN 的「问题」原文都在 `retro.todos()` 里（完全相等，见 architecture.md §4.2），不要自己解析 retrospective.md。
- gate 8.5、8.9：按设计文档 §6.2；8.9 的 `uatAccepted` 检查 `locked=True`。

**验收**：同 T3。

---

## T5 gate 6、6.5、6.7 + init-config

**目标**：测试真跑、任务真完成、新代码合规。这是 Java 相关逻辑最集中的任务。

**拥有的文件**：`gates/g6.py`、`g6_5.py`、`g6_7.py`，`commands/init_config.py`，新建 `lib/spec_driven/java.py`（Maven / Gradle 与报告解析，只供本任务的 gate 用），`tests/test_gates_impl.py`、`test_java.py`，`tests/fixtures/t5/`

**要做的**
- gate 6：新增或改动了 `src/test/java` 下的文件；surefire / Gradle 测试报告里运行数 > 0；识别 `-DskipTests`、`-Dmaven.test.skip`、`-x test`、pom 里的 surefire `<skip>`；implementation-log.md 存在；JaCoCo 增量覆盖率（只算 `baseCommit` 以来改动的行）低于 `test.coverage.diff_threshold` 时 BLOCK，`evidence` 放覆盖率数值和未覆盖行清单（不含行号以外的易变内容）。
- gate 6.5：用 `taskstate.done_tasks()` + `open_tasks()` 判定，不读复选框原样；S 档 WARN，其余 BLOCK。
- gate 6.7：设计文档 §6.5 全部；所有 Finding `locked=True`；产出 `static-analysis-report.md`（格式见 architecture.md §4.4）是本 gate 唯一允许的写文件操作（在模块顶部注释说明这个例外）。
- gate 6 读提交 trailer 按 architecture.md §4.3（RED 先于 GREEN、Task-Id）。
- `init-config --java`：写 `.config.json` 的 `quality` 块，跑检查生成 `quality-baseline.json`。

**验收**：fixture 里放真实格式的 surefire XML、JaCoCo XML、Checkstyle / PMD / SpotBugs XML、SQLFluff JSON 样本（手写小样本即可，不需要真跑 Maven）。

---

## T6 护栏：hook 规则、放行授权、留痕、git hook

**目标**：设计文档 §2.4 的第 2、3 层，以及 §6.6 的放行机制。

**拥有的文件**
- `policies/spec_gate.py`、`bash_guard.py`、`waive_grant.py`、`gate_router.py`
- `lib/spec_driven/retro.py`、`grants.py`
- `commands/waive.py`、`retro.py`、`githook.py`
- `skills/waive/SKILL.md`（已有初稿，按实现核对）
- `hook.py` 的 `normalize()`：只允许追加字段
- `tests/test_policies.py`、`test_grants.py`、`test_retro.py`、`test_githook.py`，`tests/fixtures/t6/`

**要做的**
1. `retro`：三张表的读写；`waivers()` 解析「人工确认记录」，`todos()` 读待优化清单（T4 的 gate 8 用）。
2. `grants`：口令匹配、签发（绑定项目、change、动作、键、指纹、过期时间）、原子消费（重命名占用，防止并发重复消费）。
3. `policies`：各模块 docstring 里列的规则。先查清三个平台 hook payload 里子 agent 身份的字段（Claude Code、Codex 的官方文档），追加到 `normalize()`；拿不到身份的平台在交付说明里写明降级方式。
4. `waive` 命令：重跑对应 gate 拿当前指纹 → `grants.consume()` → `retro.append_waiver()`。没有授权时拒绝，并把口令格式告诉用户。无提示词 hook 的平台（OpenCode）退回 TTY 输入 change 名确认。
5. `githook`：`install` 写入 `.git/hooks/pre-commit`、`commit-msg`（已有他人 hook 时链式调用，不覆盖）；`pre-commit` 拒绝当前 Phase gate 未过、冻结工件与 retrospective.md 的非 CLI 改动；`commit-msg` 在 Phase 6 校验 `Task-Id` trailer。
6. `gate_router`：按关键字跑当前 Phase 的 gate，结果作为提示返回。

**验收**
- policy：每条规则拦截 / 放行 / 异常输入三类测试，包括 `sh -c "..."`、`&&`、引号、Windows 反斜杠路径。
- 授权：口令大小写与空格、过期、重复消费、跨项目、跨 change、指纹变化，全部拒绝。
- 端到端：模拟 prompt-submit 输入口令 → `waive` 成功；不输入口令 → `waive` 失败。

---

## T7 归档

**拥有的文件**：`commands/archive.py`，`gates/g9.py`，新建 `lib/spec_driven/archive.py`（合并与 ADR 逻辑），`tests/test_archive.py`，`tests/fixtures/t7/`

**要做的**：设计文档 §7 Phase 9 的 7 步。spec 合并按 REQ 粒度：同 ID 替换、新 ID 追加、SC ID 冲突 BLOCK；ADR 编号取现有最大值 +1；`--dry-run` 只打印计划；迁移用 `gitutil.git(["mv", ...])`。

**验收**：设计文档要求的 4 类合并场景（新能力、已有能力追加 REQ、同 REQ 覆盖、SC 冲突）各有 fixture；归档后 gate 9 通过；中途失败不留半迁移状态（先在临时位置组装，最后一步再移动）。

---

## T8 总控细则 + 主链 skill + bugfix 变种

**目标**：模型按什么步骤、和用户怎么对话、产出什么工件。纯 markdown 任务。

**拥有的文件**
- `skills/spec-driven-dev/SKILL.md`、`skills/spec-driven-dev/references/*`（新建）
- `skills/requirements-clarify/`、`tech-design-tradeoff/`、`api-design-rest/`、`db-schema-design/`、`task-breakdown/`、`tdd-implement/`、`tiered-code-review/`（新建）
- `skills/bugfix/SKILL.md`（入口保留，变种流程写在总控 references 或独立 skill 中，二选一并说明）
- `skills/spec/SKILL.md`

**要做的**
1. 总控 `references/`：每个 Phase 一份细则（进入条件、调用谁、结束时跑哪个 gate）；`subagent-protocol.md`（设计文档 §5 的调度模板，只传路径）。SKILL.md 主体保持精简，细节下沉 references，按 Phase 读取。
2. 7 个主链 skill：各自 Phase 的对话步骤和工件写法，严格按 T1 模板；每个 skill 结尾写明「交回总控，由总控跑 gate」。
3. bugfix 变种：写 bugfix-analysis.md 与 proposal.md，Phase 2/3 条件性瘦身。
4. `tdd-implement`、`tiered-code-review` 是给 agent 读的规范（RED→GREEN→REFACTOR；提交 trailer 严格按 architecture.md §4.3；分级规则与检查清单）。
5. 总控 Phase 8 细则：code-review 的每条 WARN 用 `retro add --source "code-review WARN" "<问题原文>"` 记入待优化清单（architecture.md §4.2）。
6. 用户决策一律经 architecture.md §4.5 的命令落盘：Phase 8.9 通过走 `uat accept`（先请用户输入「确认验收 <change 名>」），要修改走 `uat reject`；Phase 8.5 用户选跳过走 `deploy skip`；bugfix skill 在用户确认 bugfix-analysis 后执行 `scope set`。

**验收**
- 每个 skill 的 frontmatter 能被 `frontmatter.parse()` 解析，`name` 与目录同名（补进 `tests/test_plugin.py` 的检查由协调者做，你在交付说明里列出新 skill）。
- 没有任何一处让模型直接编辑 `.meta.json` / `retrospective.md`，或替用户做放行、降档、验收决定。
- 用 T1 模板人工走一遍：skill 指示写出的工件能被对应 gate 的别名找到。

---

## T9 4 个 agent + 评审报告模板

**拥有的文件**：`agents/*.md`，`skills/spec-driven-dev/templates/reports/spec-review.md`、`qa-report.md`、`code-review.md`（骨架已由协调者按契约建好，只能补说明文字，不能改标题和表头）

**要做的**
- 每个 agent：角色、输入（只有路径）、必须遵守的约束（只写自己的报告、不改代码 / 工件、失败时怎么报告）、检查清单、报告格式。
- 报告模板：在已有骨架上补充填写说明，结构（标题、表头）不能改；agent 的输出要求逐条对应该节（首行标记、结论表、问题清单、SC 验证结果、bugfix 升级判定）。code-reviewer 先读 static-analysis-report.md（§4.4）。
- implementation-generator：读 `tdd-implement` 规范（T8），提交 trailer 按 architecture.md §4.3，只改任务 scope 内的文件。
- 保持 `tools` 与 `access` 一致（`tests/test_plugin.py` 会查）。

**验收**：`test_plugin.py` 通过；每个 agent 的约束能对应到 T6 的 policy 或 T4 的 gate 检查（在交付说明里列对应关系）。

---

## T10 8 个横切 skill

**拥有的文件**：`skills/root-cause-analysis/`、`incident-analysis/`、`code-quality-optimize/`、`codegraph/`、`log-search/`、`local-deploy/`、`openapi-check/`、`safety-check/`

**要做的**：按设计文档 §1.1 横切 skill 表。全部本地化：日志读本地文件、部署在本机、接口比对读本地 Swagger，不接外部服务。`local-deploy` 产出的 `deploy-report.md` 按 T1 模板；`safety-check` 在平台 hook 不可用时显式调用 CLI 的判定（需要 CLI 入口时向协调者提）。

**验收**：frontmatter 合法；每个 skill 写明推荐调用点和「只分析不修改」等边界。

---

## T11 用户决策命令：uat / scope / deploy skip

**目标**：让用户的验收、跳过部署验收、bugfix 范围评估有命令可落盘，并防止模型代替用户验收。接口见 architecture.md §4.5。

**拥有的文件**
- `commands/uat.py`、`scope.py`、`deploy.py`（新建）
- `grants.py`、`policies/waive_grant.py`、`retro.py`：只追加，不改已有行为
- `commands/retry.py`：只允许把回退逻辑抽成可复用函数，行为不变
- `tests/test_user_decisions.py`

**要做的**
1. `grants`：新增口令 `确认验收 <change 名>`，以及计算验收指纹的函数（spec.md + qa-report.md 的内容哈希）。
2. `waive_grant`：只在该 change 处于 Phase 8.9、尚未验收时签发 `uat` 授权。
3. `retro`：新增「用户验收记录」「部署验收记录」两张表的追加函数，同样记签名。
4. 三个命令按 §4.5 实现；`uat reject` 复用 `retry` 的回退逻辑。

**验收**
- `uat accept`：没有授权拒绝；授权后 spec.md 或 qa-report.md 变化则拒绝；非 Phase 8.9 拒绝；成功后 gate 8.9 通过。
- 模型经子 agent 或非用户消息无法签发 `uat` 授权（沿用 T6 的判定链）。
- `scope set` 后 `advance` 按评估跳过或保留 Phase 2 / 3；非 bugfix 或非 Phase 1 拒绝。
- `deploy skip` 后 Phase 8.5 为 skipped、当前 Phase 为 8.9，gate 8.5 放行。

---

## T12 排查偶发的测试失败

**目标**：全量测试偶发失败、重跑又通过，要找到根因并修掉，否则 CI 会随机变红。

**已知现象**
- 第 1 次：Python 3.8，紧接在一轮 3.12 全量测试之后运行，`FAILED (errors=5, skipped=1)`，时间约 09-27 00:10（刚过零点）。
- 第 2 次：Python 3.12，在临时 worktree 里运行，`FAILED (errors=1)`。
- 之后单独重跑二十多次未复现，两次都没留下报错详情。当时有多个 agent 在不同 worktree 里同时跑测试。

**拥有的文件**
- `tests/` 下已有的测试文件（只为修复不稳定性而改）
- `tools/flaky/`（新建：复现脚本，不进插件）

**要做的**
1. 写复现脚本：并发起多个测试进程、在较高负载下反复运行，保存每次失败的完整报错，把问题稳定复现出来。
2. 逐个验证这些方向，不要只凭推测下结论：
   - 有测试没把 `REINS_HOME` 指到临时目录，读写了真实的 `~/.reins`（日志、grants），或依赖 `HOME`、全局 git 配置；
   - 与日期时间相关：如 `tests/test_lifecycle.py` 的 bugfix 名字含当天日期，测试和被测代码各取一次日期，跨零点会不一致；授权有效期、锁超时；
   - `tests/test_meta.py` 的 spawn 多进程并发写入、`meta.lock` 的超时与过期清理；
   - 真实 `git commit` 会触发 git hook（`test_githook.py`、`test_user_decisions.py` 等），hook 调用的 CLI 路径和环境变量是否受外部影响；
   - 多个 worktree 同时跑测试时共用的固定路径或同名文件。
3. 问题在测试本身时直接修；问题在产品代码时不要改，写清复现步骤交给协调者。

**验收**
- 交付说明写明根因：哪个测试、为什么失败。
- 修复后用复现脚本并发 4 个进程、共 50 轮，Python 3.8 和 3.12 都零失败。

---

## T13 端到端联调 + 更新 README 与验证手册

**目标**：T1–T11 都已合入，但还没有人把整条工件链从头走通。在真实的示例 Java 项目里完整走一遍，找出模块之间对不上的地方，并把文档更新到和代码一致。

**拥有的文件**
- `tools/e2e/`（新建：可重复运行的联调脚本，不进插件）
- `docs/dev/e2e-report.md`（新建：联调报告）
- `README.md`、`docs/verification.md`

**要做的**
1. 在临时目录建最小 Maven 示例项目：一个业务类、一个单元测试，配置 surefire 和 jacoco。机器上没有 JDK / Maven 时先停下告诉协调者，不要用手写的测试报告冒充真实运行结果。
2. 不启动任何 AI 平台，用 CLI（`reinsdev-plugin/skills/spec-driven-dev/scripts/spec-driven`）模拟总控每一步。工件按 `templates/`、评审报告按 `templates/reports/` 填写：
   - **流程 A（S 档 feature）**：`new` → 填 proposal → `complexity set S` → `advance`（应跳过 2、3、5、7）→ tasks → 按 TDD 节奏提交（RED 带 `TDD-Phase: RED`，GREEN 带 `Task-Id`）→ `tasks-sync` → `init-config --java` → `advance` 过 6 / 6.5 / 6.7 → code-review → `deploy skip` → 模拟用户输入「确认验收 <change>」→ `uat accept` → `archive`。
   - **流程 B（M 档 feature，至少到 Phase 5）**：写 design、spec、spec-review，并演练一次 gate 拦截 → 模拟用户输入「确认放行 …」→ `waive`。
   - **流程 C（bugfix）**：`new --mode bugfix` → `scope set` → 核对 Phase 2 / 3 的跳过。
   - 模拟用户输入口令：把 UserPromptSubmit 形状的 JSON 经 stdin 交给 `spec-driven hook prompt-submit --runtime claude`，形状见 `tests/test_policies.py`。
3. 每一步记录命令、退出码、关键输出、是否符合预期；整个过程做成 `tools/e2e/` 下可重复运行的脚本。
4. 发现的问题写进 `docs/dev/e2e-report.md`：现象、复现命令、判断属于哪个任务。不要改其他任务的代码。
5. 按实际行为更新 README.md 和 docs/verification.md，至少覆盖：`advance`、用户决策命令、放行与验收口令、git hook、评审报告格式、`init-config`；删掉过时写法。Windows 相关只标注「延后」。
6. 协调者会转交 T14 给出的文档文字（「一个实例对应一个 git worktree」、授权不绑定实例），一并写进 README。

**验收**
- 流程 A、C 完整走通，流程 B 走到 Phase 5；联调脚本可重复运行。
- 联调报告列出所有偏差及其归属；README 和验证手册与代码一致。

---

## T14 多实例安全（CLI 状态层）

**目标**：用户会同时开多个 Claude / Codex / OpenCode 实例使用本插件。CLI 每次调用都是独立进程，进程内没有全局变量；但多个实例共用磁盘文件和同一个 git 工作区，会互相干扰。修掉下面 5 个问题，每个问题先写能复现的测试再修。

**拥有的文件**
- `commands/new.py`、`commands/status.py`、`commands/advance.py`、`commands/githook.py`
- `meta.py`、`retro.py`、`hook.py`、`policies/gate_router.py`
- `skills/waive/SKILL.md`
- `tests/test_multi_instance.py`（新建；不改已有测试文件，T12 正在处理它们）

**要做的**
1. **【高】共用工作区时 `new` 切换分支会影响其他实例；按分支定位 change 会选错**
   - `new`：工作区有未提交改动时拒绝切换分支，提示为这个 change 新建 git worktree 或加 `--no-branch`；工作区干净时行为不变。
   - `gate_router`：同一项目有多个进行中的 change 时不按分支猜，直接不给提示；只有一个时行为不变。
   - waive skill：所有 spec-driven 调用都带 `--change <change>`。
   - `locate.resolve()` 规则不变，但 docstring 写明：多实例场景下调用方必须显式传 change。
2. **【低～中】retrospective.md 不是原子写入，签名分开写**：正文和 `.retro.sha256` 都改为「唯一文件名的临时文件 + `os.replace`」；`retro.verify()` 签名对不上时短暂等待后重读一次再下结论。表格格式、签名算法、公开函数签名不变。
3. **【低～中】git hook 写死了插件版本的绝对路径，插件升级后静默跳过**：hook 找不到 CLI 时输出醒目提示（这次没有执行 Reins 检查、怎么修复），仍不拦截提交；新增一个函数检查已安装 hook 的 CLI 路径是否仍有效且是当前 CLI，不是则重装（保留别人的 hook），在 `status` 和 `advance` 里调用，出错只提示、不影响命令结果。
4. **【低】过期锁被清理后，原持有者释放时误删新持有者的锁**：`meta.lock()` 在锁文件里写唯一标识（pid + 随机值），释放前核对是自己的才删除，参照 `archive.archive_lock`。
6. **【追加，E2E-02，高】pre-commit 拒绝 `tasks-sync` 合法勾选后的 tasks.md**：Phase 6 时 tasks.md 属于已冻结的 Phase 4 工件，CLI 按 `Task-Id` 自动勾选后提交被拒。修法：冻结检查遇到 tasks.md 时，若暂存内容与 HEAD 相比只有复选框状态变化，且等于 `taskstate.render(HEAD 内容, taskstate.done_tasks(...))` 的结果，就放行；任务正文、编号、增删行的改动仍按冻结拦截。联调复现步骤见 T13 联调脚本流程 A 的「同步、核对、暂存、提交」四步。
5. **【低】所有实例共用 `~/.reins/logs/hooks.jsonl`**：每条记录用一次 `os.write` 在 O_APPEND 下追加，不经缓冲；超过 5 MB 轮转为 `hooks.jsonl.1`（只留一份），轮转失败不影响 hook；日志仍不能包含用户原文。

**验收**
- 测试覆盖：tasks-sync 勾选后的 tasks.md 能在 Phase 6 提交、手改任务正文仍被拒；工作区有改动时 `new` 拒绝切换；两个进行中的 change 时 gate_router 不给提示；多进程并发 `retro.add_todo` 后行数完整且签名通过；旧 hook 路径被自动刷新；过期锁被清理后原持有者不误删新锁；多进程并发写日志后每行都是合法 JSON；日志轮转。多进程测试用 spawn，`REINS_HOME` 指向临时目录。
- README.md 和总控 SKILL.md 不在本任务范围。交付说明里给出要补的文字，由协调者转交 T13 / T8，至少包括：「一个实例对应一个 git worktree」的使用建议；放行授权不绑定具体实例（同一 change 的同一检查项，任何实例都可能消费用户签发的授权）。

---

## T15 gate 6.7 质量检查的并发保护

**目标**：两个实例同时对同一项目执行 `advance` 经过 gate 6.7 时，`java.run_quality()` 会在同一目录里同时跑 Maven 和质量检查，互相覆盖 `target/` 和报告；gate 6.7 写 `static-analysis-report.md` 不是原子写入，code-reviewer 可能读到写了一半的报告。

**拥有的文件**
- `java.py`、`gates/g6_7.py`、`commands/init_config.py`
- `tests/test_quality_concurrency.py`（新建；不改已有测试文件）

**要做的**
1. 在 `java.py` 加项目级质量检查锁（如 `.openspec/.quality.lock`，`O_CREAT|O_EXCL` 创建），包住 `run_quality()` 全程：
   - 锁文件写唯一标识，释放前核对是自己的才删除（参照 `archive.archive_lock`）；
   - 等锁有超时，默认取所有检查超时之和再加余量；超时给 BLOCK，原因写明「另一个实例正在跑质量检查」，不能当作通过；
   - 过期判定要长于最长的检查时间，避免清理掉正在运行的检查的锁；
   - `init-config` 也调用 `run_quality`，必须经过同一把锁。
2. gate 6.7 写 `static-analysis-report.md` 改为「唯一文件名的临时文件 + `os.replace`」，格式严格按 architecture.md §4.4 不变。
3. 保持现有行为：所有 Finding 仍然 `locked=True`；拿不准、执行失败或拿不到锁时一律拦截。需要新配置项时按 AGENTS.md §2 追加到 `config.DEFAULTS` 并在交付说明列出。
4. **【已转入 T20 第 8 条】初始化失败时报错要能定位**：`init-config --java` 和 gate 6.7 某项检查失败时，输出实际执行的完整命令、退出码、stderr 的最后若干行，并把完整输出写到 `.openspec/logs/quality-<检查>.log`（新建目录，路径写进报错）。联调中「插件无法解析」「没有匹配的 ArchUnit 测试」都只报了退出码 1，无法定位。
5. 与 T16 的衔接：T16 会通过 `.config.json` 的 `quality.<检查>.command` 写入带完整坐标的插件命令；`init-config` 已有「用户配置覆盖默认值」的合并逻辑，保持不变即可，不要为 T16 改默认命令。

**验收**
- 测试覆盖：两个进程同时调用 `run_quality` 时串行执行（用会 sleep 的假命令证明不重叠）；等锁超时返回 BLOCK；持锁进程异常退出后锁按过期规则回收；报告写入过程中读取方读不到不完整的文件。
- 不依赖真实 Maven，用配置里的假命令或小脚本代替。
- 检查失败时，报错里包含完整命令、退出码和日志路径，日志文件内容完整。

---

## T16 Java 质量工具接入：ArchUnit 自动接入，Checkstyle / PMD / SpotBugs 可直接运行

**目标**：联调（E2E-03）发现，一个能正常跑测试的 Maven 项目，`init-config --java` 仍然失败：
- ArchUnit：项目里没有依赖，也没有类名含 `Arch` 的测试，`-Dtest=*Arch*` 匹配不到任何测试；
- Checkstyle / PMD / SpotBugs：默认命令用 `checkstyle:checkstyle` 这类插件简写，pom 里没声明插件时 Maven 无法解析。

新增 `spec-driven quality setup`，把项目补齐到 gate 6.7 能运行的状态，然后用户再执行 `init-config --java` 建基线。命令已登记（`commands/quality.py` 为桩），参数见 `spec-driven quality --help`。

**拥有的文件**
- `commands/quality.py`（填实）、`java_setup.py`（新建，放接入逻辑）
- `skills/spec-driven-dev/templates/quality/`（新建：ArchUnit 测试类模板、需要时的规则文件）
- `skills/spec-driven-dev/references/phase-0.md`、`references/cli-boundaries.md`：只追加 `quality setup` 的调用说明（T8 已完成，本任务可以改这两处）
- `tools/e2e/`、`README.md`、`docs/verification.md`：接入完成后更新联调脚本和文档
- `tests/test_quality_setup.py`（新建）

**不能改的文件**：`java.py`、`commands/init_config.py`、`gates/g6_7.py`（T15 正在改）。需要它们配合时，写进交付说明由协调者处理。`java.quality_defaults()`、`java.detect_build()` 可以只读调用。

**要做的**
1. **Checkstyle / PMD / SpotBugs：优先不改 pom**
   - 在 `.openspec/.config.json` 的 `quality.<检查>.command` 里写入带完整坐标、锁定版本的插件命令（例如 `org.apache.maven.plugins:maven-checkstyle-plugin:<版本>:checkstyle`），`report_path` 与 `java.quality_defaults()` 的报告路径保持一致。`init-config` 会用这里的配置覆盖默认值。
   - 规则集优先用插件自带的（如 Checkstyle 的 `google_checks.xml` 或 `sun_checks.xml`、PMD 的内置 category 规则），通过 `-D` 属性指定。每个属性都要用锁定的版本实测确认生效。
   - 工具不能因为发现违规而让构建失败（failOnViolation 等设为 false）：gate 6.7 自己解析报告来判定。
   - 只有某项确实无法用命令行完成时，才退回到修改 pom 的插件配置，并在交付说明里写明原因。
2. **ArchUnit：自动接入**
   - 依据 JUnit 版本（5 或 4）在 pom 的 `<dependencies>` 里加入对应的 ArchUnit 测试依赖（锁定版本，test scope）。只做最小的文本插入，保留原有格式和注释；已有同名依赖时不重复添加。
   - 生成架构测试类，例如 `src/test/java/<基础包>/architecture/ReinsArchTest.java`，类名必须含 `Arch`，与 `-Dtest=*Arch*` 对应。规则按「Foundation → Domain → Application → Adapter」的分层和依赖方向生成（包名按项目实际目录识别，识别不出时列出候选请用户确认）。所有规则用 FreezingArchRule 包装，只拦截新增违规。
   - freeze 存储位置、系统属性名要和 `java.py` 的 `FREEZE_KEYS` 以及 `quality_defaults()` 里的 ArchUnit 命令一致。发现不一致时不要改 `java.py`，写进交付说明。
   - 类和规则已存在时不覆盖，只报告。
3. **离线与联网**：默认只写配置、不联网。`--online` 时执行一次预热（把用到的插件和依赖下载进本地仓库），之后 `init-config` 的离线命令（带 `-o`）才能运行。没有 `--online` 且本地缺依赖时，明确提示需要预热，不要假装成功。
4. **安全要求**：
   - `--dry-run` 列出将要修改的文件和具体改动（pom 片段、新文件路径、config 键），不写任何东西；
   - 改 pom 前备份为 `pom.xml.reins-bak`，任何一步失败都恢复；
   - 多次执行结果相同（幂等）；
   - 多模块 Maven 项目：列出各模块，只处理含 `src/main/java` 的模块；判断不了时停下来说明，不要猜。
5. **Gradle**：第二优先级。能做就同样处理（Gradle 自带 checkstyle、pmd 插件，SpotBugs 需 `com.github.spotbugs` 插件）；来不及时，`quality setup` 对 Gradle 项目明确回报「暂不支持」和手工步骤，不能静默跳过。
6. **SQLFluff**（追加：生成团队默认配置，替代原来「给出配置示例」）
   - 检测 `sqlfluff` 是否可用；不可用时给出安装方式。项目里没有 SQL 文件时说明可以不装、不生成配置。
   - 在项目根生成 `.sqlfluff`（已存在时不覆盖，只列出差异）：
     - 方言：按 pom / Gradle 里的 JDBC 驱动推断（mysql、postgres、oracle、tsql 等），推断结果请用户确认；推断不出时停下询问。
     - 参数占位：使用 SQLFluff 的 `placeholder` 模板，把 MyBatis 的 `#{…}` 当作问号占位符（与 T20 的提取方式对应）。
     - 启用的规则：关键字大写（CP01），标识符、函数名、字面量写法一致（CP02–CP04），禁止 `SELECT *`（AM04），多表连接时字段带表名或别名前缀（RF02）。
     - **不要求**显式写 `AS`：关闭 AL01、AL02。
     - 行长度：LT05 上限 120 字符，**列入 `warnings`（告警级，不拦截）**。
     - 从 mapper 提取的 SQL 的缩进来自 XML 排版，关闭缩进类规则（LT02）。
   - 生成的规则集写进交付说明和 README，便于团队按需调整。
7. **串起来验证**：用 T13 的联调脚本（`tools/e2e/run.py`）在真实的最小 Maven 项目里跑：`quality setup --online` → `init-config --java` 成功生成基线 → gate 6.7 通过；再故意引入一处新违规，gate 6.7 必须拦截。流程 A 在 E2E-01、E2E-02 修好之前仍需 `--diagnose`，这不影响本任务的验收。
8. `phase-0.md`、`cli-boundaries.md` 里补上「首次接入：先 `quality setup`（需用户同意改 pom、同意联网），再 `init-config --java`」；README 和验证手册同步。

**验收**
- 真实 Maven 项目上：`quality setup --online` 之后 `init-config --java` 返回 0 并写出基线；gate 6.7 通过；新增一处违规后 gate 6.7 拦截。
- `--dry-run` 不写任何文件；重复执行结果相同；pom 修改失败时恢复原样。
- 单元测试不依赖真实 Maven：用固定的 pom 样本验证插入结果、幂等、备份恢复、多模块识别。

---

## T17 S 档任务关联 AC（联调问题 E2E-01）

**目标**：S 档会跳过 Phase 3，不产生 spec.md，但 gate 4 仍要求每个任务关联一个已定义的 SC，所以 S 档 feature 正常走下去必然卡在 Phase 4。

**契约（协调者决定）**：Phase 3 被跳过（`skipped.3` 非空）的 feature，任务改为关联 proposal.md 里的 AC 编号（如 `AC-1`）；bugfix 仍关联修改点，未跳过 Phase 3 的仍关联 SC。gate 4 在这种情况下校验：每个任务至少关联一个 AC，所关联的 AC 都在 proposal 的验收标准里存在，且每条 AC 至少被一个任务覆盖。

**拥有的文件**
- `gates/g4.py`（T3）
- `skills/spec-driven-dev/templates/tasks.md`（T1）：「关联」字段的说明改为「SC 编号；Phase 3 跳过时写 AC 编号；bugfix 写修改点」
- `skills/task-breakdown/SKILL.md`、`skills/spec-driven-dev/references/phase-4.md`（T8）
- `tests/test_s_tier_links.py`（新建；不改已有测试文件）

**要做的**
1. 按上面的契约修改 gate 4，其他检查保持不变；bugfix 与未跳过 Phase 3 的 feature 行为不变。
2. 同步 tasks 模板和 T1 的模板一致性测试所依赖的标题（标题不变，只改占位说明）。
3. task-breakdown skill 和 Phase 4 细则写清三种情况各关联什么。

**验收**
- S 档 feature：任务关联 AC 时 gate 4 通过；关联不存在的 AC、有 AC 没被任何任务覆盖时拦截。
- M 档 feature、bugfix 的原有 gate 4 测试全部照旧通过。
- 用 T13 的联调脚本严格模式（不加 `--diagnose`）跑流程 A，能越过 gate 4（后续是否受 E2E-02 影响不在本任务验收内）。

---

## T18 工件骨架生成 `scaffold` + 需求链追溯 `trace`

**目标**：两个文档里承诺过、但 CLI 没有的小功能。命令已登记（`commands/scaffold.py`、`commands/trace.py` 为桩），参数见 `--help`。

**拥有的文件**
- `commands/scaffold.py`、`commands/trace.py`（填实）、`traceability.py`（新建，放追溯逻辑）
- `skills/spec-driven-dev/references/phase-1.md` 至 `phase-4.md`、`phase-6.md`、`phase-8.5.md`：只追加「先 `scaffold` 生成骨架再填写」的一句调用说明
- `tests/test_scaffold.py`、`tests/test_trace.py`（新建）

**要做的**
1. **scaffold**
   - 把 `templates/` 下对应模板复制到 change 目录，替换 `<change-name>`；bugfix 模式的 proposal 已由 `new` 生成，不在此列。
   - 只允许生成**当前 Phase** 的工件（例如 Phase 2 只能生成 design），其他 Phase 的工件拒绝并说明原因，避免绕过上游冻结。
   - 文件已存在时拒绝，不覆盖；写入用临时文件 + `os.replace`。
2. **trace**
   - 输入 AC / REQ / SC / 任务编号（格式按 `mdparse.ID_PATTERNS`），输出这条链：proposal 里的 AC → spec 里关联它的 SC 及所属 REQ → tasks 里关联它们的任务 → 带对应 `Task-Id` 的提交（区分 RED / GREEN）→ qa-report「SC 验证结果」里的结论。
   - 查不到的环节明确标「缺失」，不猜；`--json` 输出机器可读结果。
   - 解析一律经 `mdparse`；提交经 `taskstate` / `gitutil`；只读，不写任何文件。
   - 默认查当前 change；归档后的 change 可以用 `--change` 指定（从 archive 目录读取）。

**验收**
- scaffold：各工件按 Phase 限制生成；已存在时不覆盖；生成的骨架能被对应 gate 的别名找到所有章节。
- trace：从 AC、SC、任务编号三个方向都能查出完整链；缺环节时如实标出；S 档（无 spec）按 AC 直接关联任务。

---

## T19 Phase 6 多实现者并行 `parallel`

**目标**：实现 `spec-driven-workflow.md` §10.3 描述的并行通道。命令已登记（`commands/parallel.py` 为桩）。优先级低，**T14（多实例安全）合入后再开工**，因为并行会同时存在多个 worktree 和多个实现者。

**拥有的文件**
- `commands/parallel.py`（填实）、`parallel.py`（新建）
- `skills/spec-driven-dev/references/phase-6.md`：只追加并行通道的调用说明
- `tests/test_parallel.py`（新建）

**要做的**
1. `plan`：只读预演。读 tasks.md 每个任务的「依赖」和「范围」字段构建依赖图，按依赖分层成波次，同一波内范围不重叠的任务才能同批；输出每波的任务和诚实的收益预估。依赖有环、范围缺失时拒绝并列出问题。
2. `run`：用户确认后，从 `spec-parallel/<change>` 集成分支为本波每个任务建一个 git worktree，输出每个 worktree 的路径和任务，由总控分别派给 implementation-generator。只能在 `.openspec/.config.json` 的 `parallel.enabled=true` 时使用（新增配置项，默认 false，追加到 `config.DEFAULTS`）。
3. `merge`：本波全部完成后，按任务顺序串行合回集成分支；遇到冲突立即中止、保留现场并报告，不自动解决、不覆盖；全部合回后跑 `tasks-sync --apply` 和 gate 6.5；最后把集成分支合回 change 的工作分支，清理本波 worktree。
4. 每个 worktree 里 git hook 同样生效；worker 不得写 tasks.md（沿用 spec_gate 规则）。

**验收**
- 在临时仓库里：3 个任务（两个无依赖、一个依赖前者）分成两波；范围重叠的任务不会进同一波；有冲突时中止并保留现场；正常时合回后 gate 6.5 通过、worktree 被清理。
- `parallel.enabled=false` 时 `run` / `merge` 拒绝执行。

---

## T20 SQL 检查完善

**目标**：SQLFluff 已接入 gate 6.7，但对照代码发现以下问题，导致真实 MyBatis 项目基本过不了 gate 6.7，或者新增违规被漏掉。**T15 合入后开工**（同样改 `java.py`）；团队默认的 `.sqlfluff` 由 T16 生成，本任务按那份配置实现。

**拥有的文件**
- `java.py`、`gates/g6_7.py`、`commands/init_config.py`
- `tests/test_sql_quality.py`（新建；不改已有测试文件）

**要做的**
1. **动态 SQL 标签**：`<if>`、`<where>`、`<set>`、`<trim>`、`<choose>`/`<when>`/`<otherwise>`、`<foreach>`、`<bind>` 目前会让整个检查报错。改为展开成可检查的静态 SQL：
   - `<if>`、`<when>`、`<otherwise>` 的内容都保留（所有分支都展开，`<choose>` 的每个分支各生成一条变体，同一条语句的多个变体报出的相同违规只算一次）；
   - `<where>`、`<set>`、`<trim>` 按 MyBatis 的规则处理前缀、后缀和多余的 AND / OR / 逗号；
   - `<foreach>` 按展开一项处理，保留 open / close / separator；
   - 行号仍映射回原 XML。
2. **参数占位**：`#{…}` 不再替换成 `NULL`（会误触发「与 NULL 比较要用 IS」），改为问号占位符，配合 `.sqlfluff` 的 `placeholder` 模板。
3. **`${…}` 拼接**：不再让整个检查报错，改为报告一条违规（规则名如 `mybatis-dollar-substitution`，提示有 SQL 注入风险），参与新增 / 存量判定；展开时用一个中性标识符占位，让后面的 SQL 仍能被检查。
4. **一次调用**：所有语句写到一个临时目录，只调用一次 SQLFluff，再按文件把结果映射回原文件和行号；超时按整体计算。
5. **告警级规则**：读取 SQLFluff 输出里的告警标记（`.sqlfluff` 的 `warnings` 配置，如 LT05 行长度），按 architecture.md §4.4 处理：列在「新增违规」表里、说明以 `[WARN] ` 开头，gate 6.7 给 WARN 不拦截。
6. **按数量比较违规（所有检查通用）**：现在用指纹做字典去重，同一文件里同一规则、同样提示的违规只算一个，已有 1 处存量时新增 10 处也不会被拦截。改为按 architecture.md §4.4 的「按数量判定」：同一指纹当前数量多于基线时，多出的部分算新增。基线文件格式保持 `version: 1` 兼容（同一指纹多条记录即表示数量）。
8. **【从 T15 转入，E2E-03】初始化与检查失败时报错要能定位**：`init-config --java` 和 gate 6.7 某项检查失败时，输出实际执行的完整命令、退出码、stderr 的最后若干行，并把完整输出写到 `.openspec/logs/quality-<检查>.log`（新建目录，路径写进报错）。联调中「插件无法解析」「没有匹配的 ArchUnit 测试」都只报了退出码 1，无法定位。本条会改到 `commands/init_config.py`，归本任务所有。
7. 扫描范围补充：`src/main/resources` 以外、`.config.json` 里 `quality.sqlfluff.paths` 指定的目录（新增配置项，默认空，追加到 `config.DEFAULTS`）。写在 Java 注解里的 SQL（`@Select` 等）本任务不做，交付说明里标注。

**验收**
- 使用了全部动态标签的 mapper 能被检查，违规行号正确；`${}` 作为违规出现且其余 SQL 照常检查。
- `WHERE id = #{id}` 不再报「与 NULL 比较」。
- 同一文件在基线已有 1 处某违规时，再新增 1 处同样的违规会被拦截；修掉 1 处算已偿还。
- 行长度超限只出 WARN，不拦截；其他规则的新增违规拦截。
- 100 个 mapper 语句只启动一次 SQLFluff 进程（用计数的假命令验证）。
- 检查失败时，报错里包含完整命令、退出码和日志路径，日志文件内容完整。
- 不依赖真实 SQLFluff 的单元测试用假命令输出固定 JSON；另附一个装了 SQLFluff 时才运行的集成测试（未安装时跳过并说明）。

---

## 别名索引

模板目录：`reinsdev-plugin/skills/spec-driven-dev/templates/`。`proposal.md` 用于 feature；`proposal-bugfix.md` 用于 bugfix，生成时仍写入 change 的 `proposal.md`。

标题的编号、大小写和首尾空白由 `find()` 统一忽略。下表列出每个键的第一个变体，与模板标题完全一致；其它中英文写法见 `mdparse.ALIASES`。

| ALIASES 键 | 模板文件 | 模板标题 |
| --- | --- | --- |
| user-stories | proposal.md、proposal-bugfix.md | 用户故事 |
| acceptance-criteria | proposal.md、proposal-bugfix.md | 验收标准 AC |
| out-of-scope | proposal.md、proposal-bugfix.md | Out of Scope |
| ambiguities | proposal.md、proposal-bugfix.md | 歧义清单 |
| dependencies | proposal.md、proposal-bugfix.md | 隐含依赖 |
| field-mapping | proposal.md、proposal-bugfix.md | 5.1 字段映射确认表 |
| non-functional | proposal.md、proposal-bugfix.md | 关键非功能性需求 |
| affected-modules | proposal.md、proposal-bugfix.md | 影响的现有模块 |
| basic-info | bugfix-analysis.md | 基本信息 |
| evidence | bugfix-analysis.md | 现场证据 |
| root-cause | bugfix-analysis.md | 根因分析 |
| fix-plan | bugfix-analysis.md | 修复方案 |
| change-points | bugfix-analysis.md | 修改点 |
| impact | bugfix-analysis.md | 影响范围 |
| complexity-assessment | bugfix-analysis.md | 复杂度判定 |
| background | design.md | 背景与目标 |
| current-system | design.md | 现有系统分析 |
| alternatives | design.md | 方案对比 |
| final-choice | design.md | 推荐方案与最终决策 |
| detailed-design | design.md | 详细设计 |
| risks | design.md | 风险与缓解 |
| stress-test | design.md | 压力测试自检 |
| implementation-plan | design.md | 实施计划 |
| interface-contract | spec.md | 接口契约 |
| data-model | spec.md | 数据模型 |
| table-structure | spec.md | 表结构 |
| indexes | spec.md | 索引 |
| constraints | spec.md | 约束 |
| migrations | spec.md | 迁移与回滚 |
| foundation | tasks.md | Foundation(底层依赖,必须先做) |
| domain-layer | tasks.md | Domain Layer |
| application-layer | tasks.md | Application Layer |
| adapter-layer | tasks.md | Adapter Layer |
| test-layer | tasks.md | Test |
| change-scope | implementation-log.md | 变更范围 |
| red | implementation-log.md | RED：失败测试 |
| green | implementation-log.md | GREEN：通过测试 |
| refactor | implementation-log.md | REFACTOR：重构 |
| build | implementation-log.md | 完整构建 |
| coverage | implementation-log.md | 增量覆盖率 |
| commits | implementation-log.md | 提交记录 |
| deployment-info | deploy-report.md | 启动信息 |
| startup-result | deploy-report.md | 启动结果 |
| deployment-errors | deploy-report.md | 错误摘要与日志 |
| manual-acceptance | deploy-report.md | 用户人工验收结论 |
| conclusion | deploy-report.md | 结论 |
| findings | reports/spec-review.md、reports/qa-report.md、reports/code-review.md | 问题清单 |
| sc-results | reports/qa-report.md | SC 验证结果 |
| bugfix-upgrade | reports/spec-review.md | bugfix 升级判定 |
| new-violations | reports/static-analysis-report.md | 新增违规 |
| baseline-violations | reports/static-analysis-report.md | 存量违规 |
| repaid-violations | reports/static-analysis-report.md | 已偿还 |

REQ / SC、单任务日志等动态标题通过 `find_all()` 与 `ID_PATTERNS` 查找，不为每个编号新增别名。`ids()` 按契约只提取数字 AC；bugfix 的固定 `AC-regression` 保留在验收标准表的 `AC` 列，可经 `tables()` 读取。
