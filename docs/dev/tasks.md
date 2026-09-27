# 并行开发任务书

每个任务交给一个 agent（或一个开发）独立完成。开工前必读：[AGENTS.md](../../AGENTS.md)（规约）→ [architecture.md](architecture.md)（架构与契约）→ 本文你的任务一节。

契约层（T0）已经就位：所有模块的文件、函数签名、CLI 命令、gate 框架、hook 判定链都已存在，未实现的部分是桩代码（`raise NotImplementedError` 或返回「该能力不可用」）。**每个任务只把自己名下的桩填实**，不新增跨任务的公共文件。

## 总览与开工顺序

| 任务 | 内容 | 依赖 | 批次 |
| --- | --- | --- | --- |
| T1 | markdown 解析 + 工件模板 | — | 第 1 批 |
| T2 | 状态与生命周期命令 | — | 第 1 批 |
| T6 | 护栏：hook 规则、放行授权、留痕、git hook | T2 的 meta / locate（先按契约写，联调在 T2 合入后） | 第 1 批 |
| T8 | 总控细则 + 主链 skill + bugfix 变种 | T1 的模板 | 第 1 批 |
| T9 | 4 个 agent + 评审报告模板 | T1 的模板 | 第 1 批 |
| T3 | gate 0–4 | T1、T2 合入 | 第 2 批 |
| T4 | gate 5、7、8、8.5、8.9 | T1、T2 合入 | 第 2 批 |
| T5 | gate 6、6.5、6.7 + `init-config` | T1、T2 合入 | 第 2 批 |
| T7 | 归档：`archive` + gate 9 | T1、T2 合入 | 第 2 批 |
| T10 | 8 个横切 skill | T8 合入 | 第 3 批 |

- **第 1 批 5 个任务可以同时开工**，彼此不改同一个文件。
- **T1、T2 要最先合入**，第 2 批都依赖 `mdparse` 和 `meta`。T1 建议先交付模板和 `ALIASES`（半天量），再做解析函数，这样 T8、T9 能尽早对齐格式。
- 第 2 批 4 个任务之间互不依赖，可以同时开。
- 全部合入后由协调者做一次端到端联调：在示例 Java 项目里用 S 档和 M 档各走通一遍，并更新 README 和验证手册。

每个任务的交付标准都包含 AGENTS.md §6 的通用要求，下文不再重复：提交信息以 agent 名字开头（`<agent 名字>: T<n>: <做了什么>`，名字由协调者分配）、测试全过、rebase、交付说明四项。

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
5. 补充（契约新增）：协调者已按 architecture.md §4.2、§4.4 在 ALIASES 里加了 `findings`、`sc-results`、`bugfix-upgrade`、`new-violations`、`baseline-violations`、`repaid-violations`（报告不是 T1 的模板，只需把它们补进别名索引，注明来源为评审报告 / 静态分析报告）；`bugfix-analysis.md`、`proposal-bugfix.md` 标题里的占位符改为 `<change-name>`（`new` 只替换它）。

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

**验收**
- 每个 skill 的 frontmatter 能被 `frontmatter.parse()` 解析，`name` 与目录同名（补进 `tests/test_plugin.py` 的检查由协调者做，你在交付说明里列出新 skill）。
- 没有任何一处让模型直接编辑 `.meta.json` / `retrospective.md`，或替用户做放行、降档、验收决定。
- 用 T1 模板人工走一遍：skill 指示写出的工件能被对应 gate 的别名找到。

---

## T9 4 个 agent + 评审报告模板

**拥有的文件**：`agents/*.md`，`skills/spec-driven-dev/templates/reports/*.md`（新建：spec-review、qa-report、code-review 三份报告模板）

**要做的**
- 每个 agent：角色、输入（只有路径）、必须遵守的约束（只写自己的报告、不改代码 / 工件、失败时怎么报告）、检查清单、报告格式。
- 报告模板：严格按 architecture.md §4.2 写 spec-review、qa-report、code-review 三份模板；agent 的输出要求逐条对应该节（首行标记、结论表、问题清单、SC 验证结果、bugfix 升级判定）。code-reviewer 先读 static-analysis-report.md（§4.4）。
- implementation-generator：读 `tdd-implement` 规范（T8），提交 trailer 按 architecture.md §4.3，只改任务 scope 内的文件。
- 保持 `tools` 与 `access` 一致（`tests/test_plugin.py` 会查）。

**验收**：`test_plugin.py` 通过；每个 agent 的约束能对应到 T6 的 policy 或 T4 的 gate 检查（在交付说明里列对应关系）。

---

## T10 8 个横切 skill

**拥有的文件**：`skills/root-cause-analysis/`、`incident-analysis/`、`code-quality-optimize/`、`codegraph/`、`log-search/`、`local-deploy/`、`openapi-check/`、`safety-check/`

**要做的**：按设计文档 §1.1 横切 skill 表。全部本地化：日志读本地文件、部署在本机、接口比对读本地 Swagger，不接外部服务。`local-deploy` 产出的 `deploy-report.md` 按 T1 模板；`safety-check` 在平台 hook 不可用时显式调用 CLI 的判定（需要 CLI 入口时向协调者提）。

**验收**：frontmatter 合法；每个 skill 写明推荐调用点和「只分析不修改」等边界。

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

REQ / SC、单任务日志等动态标题通过 `find_all()` 与 `ID_PATTERNS` 查找，不为每个编号新增别名。`ids()` 按契约只提取数字 AC；bugfix 的固定 `AC-regression` 保留在验收标准表的 `AC` 列，可经 `tables()` 读取。
