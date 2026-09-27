# spec-driven 研发工作流完整指南



本文档面向第一次接触 Reins 规格驱动研发的人，一次性、完整地讲清楚这条工件链是怎么设计的、每一步做什么、为什么这么设计。读完这一份，就能上手用 `/spec` 或 `/bugfix` 跑通从需求到归档的整条研发流水线。

---

## 一、它解决什么问题

AI 写代码很快，但用 AI 一周后回头看 git 历史，常常答不出：

- "为什么加了这个服务？"
- "这个字段当初考虑了哪些场景？"
- "验收标准(AC)是什么？这段代码有没有偏离 AC？"

根因不是模型不够聪明，而是**过程没有留痕**——需求只活在对话里，设计只在脑子里，关掉窗口就没了，团队也没有统一标准，实现很容易偏离意图，最后只能返工。

spec-driven 的解法是强制研发过程产出一条**工件链(artifact chain)**：

```
proposal → design → spec → tasks → implementation → QA → review → (deploy) → acceptance → archive
```

每个工件是 markdown 文件，是下一阶段的输入；每个阶段有一道**机器验证门(gate)**，跳不过门不能进下一步；评审、QA 与 code review 由**独立的 agent** 完成，不让写代码的那个自己评自己。3 个月后回看，主 specs 就是项目当前的知识库，archive 就是历史决策日志。

一句话：**把"为什么这么做"沉淀成可追溯的文件，而不是只靠人脑和聊天记录。**

---

## 二、核心心智模型

### 2.1 工件链总图

| Phase | 名称 | 角色 | 产出 | 验证门 |
| --- | --- | --- | --- | --- |
| 0 | 启动 change | spec-driven-dev | `proposal.md` + `.meta.json` | gate-0 |
| 1 | 需求澄清 | requirements-clarify / bugfix | `proposal.md`(feature)或 `bugfix-analysis.md` + `proposal.md` | gate-1 |
| 2 | 技术方案 tradeoff(条件性) | tech-design-tradeoff | `design.md` | gate-2 |
| 3 | 接口与数据库设计(条件性) | api-design-rest + db-schema-design | 单个 `spec.md` | gate-3 |
| 4 | 任务拆分 | task-breakdown | `tasks.md` | gate-4 |
| 5 | 工件评审 | spec-evaluator(subagent) | `spec-review.md` | gate-5 |
| 6 | TDD 实现 | tdd-implement + implementation-generator(subagent) | 代码 commits + `implementation-log.md` | gate-6 / 6.5 / 6.7 |
| 7 | QA 验证 | qa-evaluator(subagent) | `qa-report.md` | gate-7 |
| 8 | Code Review | code-reviewer(subagent，按 tiered-code-review 规范) | `code-review.md` | gate-8 |
| 8.5 | 本地部署验收(可选) | local-deploy | `deploy-report.md` | gate-8.5 |
| 8.9 | 用户验收门 | 用户 | `.meta.json.uatAccepted` | gate-8.9 |
| 9 | 归档 | spec-driven-dev | `archive/<date>-<change>/` + 主 specs 同步 | gate-9 |

所有工件都落在项目根的 `.openspec/changes/<change-name>/` 目录下；归档时 delta-specs 合并回主 `.openspec/specs/`，change 目录移入 `archive`。

### 2.2 产物路由规则——只三条

每个 Phase 产出落到哪里，只有三条规则，消灭"该写成哪种 spec"的纠结：

| 你在写的是 | 去处 |
| --- | --- |
| 可观察行为(WHEN/THEN) | change 的单个 `spec.md` 的 REQ(H2)/ SC(H3) |
| 接口契约 / 数据模型细节 | 同一个 `spec.md` 文末的 `## 接口契约` / `## 数据模型` 汇总节(回指 SC) |
| 一次权衡 / 选型的"为什么" | ADR：`decisions/<NNNN>-*.md`(Phase 9 从 `design.md` 蒸馏) |
| 全局结构约束 / 层边界 | `architecture.md` §4 跨切不变量 |

> 一个 change 只有一个扁平 `spec.md`——没有 `specs/` 子文件夹，没有 `api.md` / `data-model.md` 剖面。归档时按 Capability ID 路由合并进主 `specs/<capability>.md`。

### 2.3 REQ / SC 结构——行为的最小可验证单位

能力 spec 用 **REQ(H2)/ SC(H3)** 结构，用 **WHEN/THEN** 描述场景：

- REQ = Requirement(需求)，H2 标题，一个粗粒度能力需求(如"批量审批")
- SC = Scenario(场景)，H3 标题，挂在某个 REQ 下，一条以 WHEN/THEN 写成、可被机器/评审/QA 共同验证的行为场景

```
# Capability: 政策审批 (`policy-approval`)

**Purpose**:让审批人对返利政策做单条/批量审批并留审批日志。

## REQ-policy-approval-001: 批量审批
系统应当允许审批人对一批 PENDING 政策一次性审批,单次上限 50 条。

### SC-policy-approval-001: 全部审批通过
WHEN POST /sales/rebate/policy/batch-approve 请求体含 N 条 policyId 且全部 PENDING
THEN 返回 RpcResult.success,所有 policy 状态变为 APPROVED
AND 写入 policy_approve_log,每条一行

### SC-policy-approval-002: 部分审批失败(状态不允许)
WHEN 请求体含 M 条状态非 PENDING
THEN 返回 RpcResult.partialSuccess(code=40005),data 含 successList/failedList
AND 整体事务回滚,数据库不变

### SC-policy-approval-E2: 单次批量超过上限
WHEN 请求体含 > 50 条 policyId
THEN 返回 RpcResult.fail(code=40010)
AND 数据库不变
```

**ID 规约**：`REQ-<capability>-<NNN>`、`SC-<capability>-<NNN>`；边界/异常场景常用 `E` 后缀(如 `SC-policy-approval-E2`)。整条链可追溯的最小单位就是 SC——Phase 4 的任务关联 SC(Phase 3 被跳过的 feature 关联 AC，bugfix 关联修改点)，Phase 7 的 QA 按 SC 逐条 PASS/FAIL。

### 2.4 复杂度分级——S/M/L 三通道

不是每个需求都要走全套流程，按复杂度分三档，80% 的简单需求只需 ≤4 个工件：

- **S(简单)**：跳过 Phase 2/3/5/7，默认轻量
- **M(中等)**：必走 Phase 5(评审)和 Phase 7(QA)，生成全套骨架
- **L(复杂)**：必走 ≥3 方案的 design，spec-evaluator 走 2 轮

档位在 Phase 1 末尾正式选定(`spec-driven complexity show` 给推荐档 + 理由，用户确认后 `set` 落定)；Phase 2、Phase 3 各有一次复杂度复评，且**只升不降**(工件已成型，降档会浪费沉没成本)。确需降档时，须由用户本人在对话里输入确认口令 `确认降档 <change 名> <档位>`，总控再执行 `complexity set --downgrade`，记入 retrospective.md「档位变更记录」。

### 2.5 Generator-Evaluator 分离——不让 AI 评自己

来自 Anthropic Harness 设计的一个核心发现：**LLM 评审自己的工作时会自我宽容**——找到 bug 后会劝自己"问题不大"，跳过刻意苛刻的检查。

因此 spec-driven 把生成和评审拆成独立角色：

- `spec-evaluator` (Phase 5)：独立评审 spec，只读工具(不能改工件)
- `implementation-generator` (Phase 6)：按 TDD 节奏写码，可写，但有路径锁(禁改 spec、禁删测试)
- `qa-evaluator` (Phase 7)：按 SC 逐条验证实现，只读
- `code-reviewer` (Phase 8)：按 tiered-code-review 规范评审代码改动，只读

隔离靠三层：**角色**(不同 system prompt，评审者刻意苛刻)+ **工具**(evaluator 只读)+ **上下文**(工件走文件交接，evaluator 看不到 generator 的中间思考)。再加上机器标记兜底：评审报告首行必须带 `<!-- generated-by: xxx-subagent -->`，gate 校验该标记，subagent 失败重试一次，仍失败就 STOP 交人工——**禁止主线自己写评审报告当作通过**。

---

## 三、两种入口

工件链支持两种入口，在 Phase 0 由 `.meta.json` 的 `mode` 字段固化，后续 Phase 据此分支：

| 入口 | 触发 | mode | Phase 1 角色 |
| --- | --- | --- | --- |
| `/spec [name]` 或"新需求/新功能" | 用户给 PRD/需求 | `feature` | requirements-clarify |
| `/bugfix "<问题描述>"` 或"修 bug" | 用户描述问题 | `bugfix` | bugfix |

**mode 决定瘦身规则：**

- `feature` 模式：Phase 2、3 按档位决定，S 档跳过，M / L 档必走完整流程
- `bugfix` 模式：Phase 2、3 按改动范围可瘦身或跳过（`spec-driven scope set` 记录评估，见 §5.2）

bugfix 的缺陷信息由用户在对话中补全，不调用任何缺陷平台；`.meta.json` 的 `source` 字段为接入缺陷平台留位，默认 `null`。

---

## 四、Phase 0：启动新 change

| 项 | 值 |
| --- | --- |
| 输入 | 用户的需求描述或问题描述 |
| 角色 | spec-driven-dev skill 自身 |
| 产出 | `.openspec/changes/<change>/proposal.md` + `.meta.json` |
| 工具 | `spec-driven new`(下游 design/spec/tasks 由对应 skill 按 `templates/` 下的模板写出) |

**操作步骤(feature 模式)：**

1. 与用户对齐变更名(kebab-case，如 `batch-approve-policy`)
2. 检查项目根是否在 git 仓库内，如果不是，先提示 `git init`
3. `.openspec/` 不存在时由 `spec-driven new` 创建；项目首次接入时，经用户确认后先运行 `spec-driven quality setup`(接入 ArchUnit / Checkstyle / PMD / SpotBugs，会修改 pom 并可能需要联网)，再运行 `spec-driven init-config --java` 生成配置与静态质量基线
4. 调用 `spec-driven new <change-name> --mode feature`：落临时档位 provisional M / `tierConfirmed=false`，正式选档在 Phase 1 末尾；同时创建并切换到 `feat/<change>` 分支、安装 git hook，最后跑 gate-0
5. `.meta.json` 写入 `"mode": "feature"` + `"complexity": "M"` + `"tierConfirmed": false`

**操作步骤(bugfix 模式)：**

1. 从问题描述生成 change name = `fix-<YYYYMMDD>-<slug>`(slug 取描述首 3-5 个有效词，kebab-case)，与用户确认
2. 调用 `spec-driven new <change-name> --mode bugfix`(也可只给 `--slug`，由 CLI 生成名字；bugfix 的档位由 bugfix-analysis 复杂度判定接管，`tierConfirmed=true`)
3. `.meta.json` 写入 `"mode": "bugfix"` + `"source": null` + `"defect_code": null`

**验证门 0**

- [ ] 项目根(或上级目录)有 `pom.xml` / `build.gradle(.kts)`，否则提示「Reins 只支持 Java 项目」
- [ ] change name 是 kebab-case 且 ≥ 5 字符
- [ ] `.openspec/changes/<change>/` 已创建，且包含 `proposal.md`(惰性生成：下游工件进入对应 phase 时再生成)
- [ ] `.meta.json` 含 `mode` 字段，值为 `feature` 或 `bugfix`

**档位选择不在 Phase 0**：此处只落临时档位 provisional M。真正选档在 **Phase 1 末尾**——需求澄清完成后，AI 跑 `spec-driven complexity show` 拿推荐档 + 理由，用户确认后 `spec-driven complexity set <S|M|L>` 落定(写 `tierConfirmed=true` + 重算验证门)。

---

## 五、Phase 1：需求澄清

按 mode 分支。

### 5.1 feature 模式

| 项 | 值 |
| --- | --- |
| 输入 | 用户的需求描述 + 项目专属规约(若存在) |
| 角色 | requirements-clarify skill |
| 产出 | `.openspec/changes/<change>/proposal.md` |

**proposal.md 必须包含：**

1. **用户故事**(每个核心功能一条)：作为 X，我希望 Y，以便 Z
2. **验收标准 AC**：每个用户故事对应可测试的标准
3. **明确的 Out of Scope**：本次不做的事项清单
4. **歧义清单**：每条标注影响范围(性能/安全/合规/UI)
5. **隐含依赖**：依赖哪些已有功能/外部系统
6. **关键非功能性需求**：qps、延迟、并发、数据量级估算

### 5.2 bugfix 模式

| 项 | 值 |
| --- | --- |
| 输入 | 用户的问题描述 + 代码库 + 项目专属规约(**不调任何平台 API**) |
| 角色 | bugfix skill |
| 产出 | `.openspec/changes/fix-<date>-<slug>/bugfix-analysis.md`(根因 + 修复方案)+ `proposal.md` |

bugfix skill 先通过对话补全 5 项信息：复现步骤 / 期望 vs 实际 / 影响面 / 现场证据 / 发现源。

**bugfix-analysis.md 必须包含：**

1. 基本信息(报告时间、报告人、一句话描述、发现源)
2. 现场证据(用户提供的描述、请求样例、截图；可选 `log-search` 检索到的关联日志)
3. 根因分析(代码定位 + 时序图 + 关键调用链)
4. 修复方案(具体改动点、代码 diff 草稿、最小变更原则)
5. 影响范围(直接 + 间接 + 风险评估)

**proposal.md(自动起草)必须包含：**

1. 用户故事：作为 `<角色>`，我希望 `<bug 描述反推的能力>`，以便 `<恢复正常>`
2. **AC 由用户答出**："如何验证修好了？"，每条 AC 必含"验证步骤"字段
    - 至少额外补一条：`AC-regression: 新增自动化回归测试覆盖 <场景描述>，且不退化其它已有测试`
3. Out of Scope：写明本次只修该 bug，不顺手改其它发现的瑕疵(避免范围蔓延)
4. 歧义清单：bugfix skill 起草时未答的疑问，标注 ✅ 后才进 Phase 2
5. 草稿标志：文件顶部 `<!-- AUTO-DRAFTED by bugfix skill; 用户必须 review 并补全后才能通过验证门 1 -->`

**AC 保护**：AC 写的是期望的正常行为，不是 bug 现象本身，防止把 bug 固化为验收标准。

**记录改动范围**：用户确认 bugfix-analysis.md 后，仍在 Phase 1，由总控执行 `spec-driven scope set --files N [--cross-service] [--ddl] [--public-api]`，数值来自分析里已确认的影响范围；再用 `spec-driven scope show` 告诉用户 Phase 2、3 是否跳过及原因。离开 Phase 1 后要改，须先回退到 Phase 1。

### 5.3 验证门 1(进入 Phase 2 的前提)

- [ ] 至少 1 条用户故事，每条至少 1 条 AC
- [ ] Out of Scope 不为空(可以写"无"，但必须显式声明)
- [ ] 歧义清单中所有问题都已得到用户回答(标注 ✅)；未回答的问题不存在
- [ ] **业务取值不可自填过门**(gate-1 BLOCK)：歧义每条标类型(业务取值/安全默认)+ 来源；类型=业务取值 的行，来源必须 = 用户(标 推断/默认/模型/未答 → BLOCK)。只有"安全默认"类(命名/非功能默认)允许模型给默认值继续
  - 设计动机：模型用"合理默认值"自填 `oemCode` 这类业务取值过门，会导致整链 + 实现 + 归档全返工。模型猜不到的业务取值(固定常量、字段映射、格式)不允许蒙混。
- [ ] **字段映射确认表**(gate-1 BLOCK)：命中字段映射/文件格式/转换器/固定值等关键词时，proposal 第 5.1 节字段映射确认表必填且每行来源 = 用户确认(否则显式声明"本次无字段映射")
- [ ] 影响的现有模块列表已列出
- [ ] **bugfix 模式额外**：`bugfix-analysis.md` 存在且包含 5 大节；`proposal.md` 中 AUTO-DRAFTED 标记已被用户删除(表示已 review)；每条 AC 含"验证步骤"字段
- [ ] **档位选择(Phase 1 末尾)**：provisional 档位(`tierConfirmed=false`)需在此正式选档：
    - AI 跑 `spec-driven complexity show` 基于 proposal.md 给出推荐档 + 理由
    - 用户确认(默认=推荐档)后 `spec-driven complexity set <S|M|L>` 落定(写 `tierConfirmed=true` + 重算验证门)
    - **不自动降档**：档位确认后，gate-1 只在复评不一致时给提示，尊重用户决定

不通过时：feature 模式回到 requirements-clarify；bugfix 模式回到 bugfix skill。

---

## 六、Phase 2：技术方案 tradeoff(条件性)

按 mode 判定是否必走：

| mode | 复杂度判定 | 行为 |
| --- | --- | --- |
| `feature` | 不论复杂度 | **必走**，产出 `design.md` |
| `bugfix` | 满足任一条件：跨 ≥3 文件 / 跨服务 / 改数据库 DDL / 改公开 API 签名 | **必走**，产出 `design.md` |
| `bugfix` | 不满足 | **跳过**，`bugfix-analysis.md` 视为本阶段产出 |

复杂度判定在 bugfix skill 输出 `bugfix-analysis.md` 时同时给出建议(基于 grep 命中的文件数 + 是否触达 DDL/API 定义)，由本 skill 与用户确认。

### 6.1 走完整流程时

| 项 | 值 |
| --- | --- |
| 输入 | `proposal.md` + 现有代码库结构 + (bugfix 模式)`bugfix-analysis.md` |
| 角色 | tech-design-tradeoff skill |
| 产出 | `.openspec/changes/<change>/design.md` |

> **上游冻结**：本 phase **只写 `design.md`**，`proposal.md` 是只读输入(gate-1 通过后即冻结)。若发现 proposal 的 AC/范围有误，**回 Phase 1 改 + 重过 gate-1**，不得在 Design 阶段直接编辑 `proposal.md`。

**design.md 必须包含：**

1. **背景与目标**：解决什么问题，可量化的成功标准
2. **现有系统分析**：相关模块、约束、改动影响面(列出文件路径)
3. **方案对比**：至少 2 个方案，每个方案有：核心思路、复杂度、优点、缺点、适用场景
4. **推荐方案与最终决策**：`**AI 推荐**` + `**最终选择**` 两行(均可机械解析)，有具体理由(禁止"视情况而定")；用户改选时最终选择行必须改成所选方案
5. **详细设计**：模块结构、核心数据流、关键接口签名(草稿)、数据库变更概要
6. **风险与缓解**：风险表格(风险 / 概率 / 影响 / 缓解措施)
7. **压力测试自检**：并发 10 倍 / 下游挂掉 / 3 个月后扩展 / 新人接手 四个场景
8. **实施计划**：工期估算、阶段拆解、上线风险等级

### 6.2 验证门 2(进入 Phase 3 前自动触发)

- [ ] (走完整流程)至少 2 个方案，每个方案有完整 6 字段(思路/复杂度/优点/缺点/工作量/适用场景)
- [ ] (走完整流程)推荐方案有明确理由
- [ ] **改选即回写**(gate-2 硬校验)：用户在 Gate 2 改选方案后，必须 `spec-driven design set <方案>` 落盘 + 把 `design.md` `**最终选择**` 行回写成该方案。`.meta.json.designDecision` 与 `design.md` `**最终选择**` 不一致 / 未回写 → BLOCK(进不了 Phase 3)。这样"用户决策只活在对话里"的漂移在 Phase 2 就被拦住，不会拖到 Phase 5
- [ ] (走完整流程)影响面列出了具体文件路径
- [ ] (走完整流程)4 个压测场景都有回答
- [ ] (跳过)`.meta.json` 的 `skipped.2` 写明跳过理由
- [ ] **复杂度复评**(gate-2 自动执行)：扫 proposal.md + design.md 重新打分：
    - **只升不降**：design.md 已成型，降级会浪费沉没成本，降档建议被自动忽略
    - **升档建议**(如 M→L)：gate-2 输出 WARN，**不自动改**。用户确认后由总控执行 `spec-driven complexity recheck --phase 2 --apply` 写入
    - S 通道默认跳过 Phase 2，gate-2 也不触发

---

## 七、Phase 3：接口与数据库设计(条件性)

并行进行。bugfix 模式下，若 `bugfix-analysis.md` 明确"不改接口签名 + 不改 DDL"，可整体跳过。

> **单文件布局**：两个 skill 共建**同一个** `spec.md`——`api-design-rest` 主笔 REQ/SC 行为脊柱 + 文末 `## 接口契约` 汇总节，`db-schema-design` 主笔文末 `## 数据模型` 汇总节 + 补全 SC 的 DB 后置状态。先按 `capability-conventions.md` 判定能力归属(决定 Capability ID / ID 前缀，进而决定归档路由)。

| mode | 触发 spec 产出的条件 |
| --- | --- |
| `feature` | 不论是否新增接口/表都必走(没新增就在对应汇总节写"本次不变更") |
| `bugfix` | 改了 API 签名或参数语义 → 补 SC + `## 接口契约` 节；改了 DDL → 补 `## 数据模型` 节；两者都没动 → 跳过 |

| 项 | 值 |
| --- | --- |
| 输入 | `design.md` 或 `bugfix-analysis.md` |
| 角色 | api-design-rest skill + db-schema-design skill |
| 产出 | `.openspec/changes/<change>/spec.md`(单文件：REQ/SC + 文末 `## 接口契约` / `## 数据模型`) |

能力 spec 用 REQ(H2)/ SC(H3)结构，WHEN/THEN 描述场景(完整示例见 §2.3)。

> 接口契约细节进文末 `## 接口契约` 节，表结构进文末 `## 数据模型` 节，均标注"关联 SC"引用上面的场景。

> **可选：生成 `openapi.draft.json`** 若 `.openspec/.config.json` 的 `openapi.enabled=true`，api-design-rest 在写完 `## 接口契约` 后(Step 3.5)按映射表额外产出 `openapi.draft.json`(设计意图骨架，字段级 schema 多为占位)。默认 `openapi.enabled=false`，不影响未配置项目。

### 7.1 验证门 3(进入 Phase 4 前自动触发)

- [ ] (走完整流程)proposal.md 中每个 AC，至少映射到一个 SC(scenario)
- [ ] (走完整流程)每个 SC 是 H3、所属 REQ 是 H2，有完整 WHEN / THEN(/ AND)
- [ ] (走完整流程)`## 接口契约` 节包含：Method+Path、请求/响应字段、错误码、幂等性、限流(均引用 SC)
- [ ] (走完整流程)`## 数据模型` 节包含：表结构、索引、约束、迁移脚本(含回滚)
- [ ] (整体跳过)`.meta.json` 的 `skipped.3` 写明跳过理由
- [ ] (若 `openapi.enabled=true`)`openapi.draft.json` 通过 `validate_openapi.py` 无 BLOCK(`gate_on_draft` 默认 `warn`，不阻断)
- [ ] **复杂度复评**(gate-3 自动执行)：扫 proposal+design+spec.md 重新打分：
    - **只升不降**：spec.md 已成型，降级会浪费，降档建议被自动忽略
    - **升档建议**(如 M→L)：gate-3 输出 WARN，**不自动改**。用户确认后由总控执行 `spec-driven complexity recheck --phase 3 --apply` 写入
    - S 通道 / Phase 3 已跳过时，gate-3 只检查跳过理由

---

## 八、Phase 4：任务拆分

| 项 | 值 |
| --- | --- |
| 输入 | spec.md(单文件) |
| 角色 | task-breakdown skill |
| 产出 | `.openspec/changes/<change>/tasks.md` |

**tasks.md 格式**(按层组织，与能力 spec 正交，在"任务关联 SC"处汇合)：

```
# Tasks: <change-name>

## Foundation(底层依赖,必须先做)
- [ ] T1. 新增数据库表 policy_approve_log(DDL + 回滚 DDL)
- [ ] T2. 新增 RebatePolicyEventEnum.BATCH_APPROVE 状态机事件

## Domain Layer
- [ ] T3. 新增 BatchApproveCmd(client/dto/cmd/)
- [ ] T4. 在 PolicyApproveLogGateway 增加 batchInsert 方法

## Application Layer
- [ ] T5. 实现 BatchApproveCmdExe(对应 spec scenario 1-3)

## Adapter Layer
- [ ] T6. 在 RebatePolicyController 增加 POST /batch-approve 接口

## Test
- [ ] T7. BatchApproveCmdExeTest(覆盖 scenario 1-3 + 边界值)
- [ ] T8. RebatePolicyControllerTest(集成测试,使用 MockMvc)
```

### 8.1 验证门 4

- [ ] 每个任务粒度 ≤ 2 小时(粒度过大要再拆)
- [ ] 任务有清晰的依赖顺序(Foundation → Domain → App → Adapter → Test)
- [ ] 每个任务都关联到至少一个 spec scenario；Phase 3 被跳过时，feature 关联 proposal.md 的 AC(每条 AC 至少被一个任务覆盖)，bugfix 关联 bugfix-analysis.md 中的"修改点"
- [ ] **bugfix 模式额外**：tasks.md 必须有一条 `T-regression: 为 <场景描述> 编写自动化回归测试`，缺失即 BLOCK

---

## 九、Phase 5：工件评审(Generator-Evaluator 分离)

这一步由 **subagent** 独立完成，不是让生成工件的同一个 agent 评审自己。

| 项 | 值 |
| --- | --- |
| 输入(feature) | proposal.md + design.md + spec.md(单文件)+ tasks.md |
| 输入(bugfix 完整) | proposal.md + bugfix-analysis.md + design.md + spec.md(单文件)+ tasks.md |
| 输入(bugfix 瘦身) | proposal.md + bugfix-analysis.md + tasks.md |
| 角色 | spec-evaluator subagent |
| 产出 | `.openspec/changes/<change>/spec-review.md` |

输出格式：见 `references/review-template.md`，分 **BLOCK / WARN / INFO** 三档。

bugfix 模式下，spec-evaluator 把 `bugfix-analysis.md` 视为 `design.md` 的等价物评审同样的 9 大维度，并额外检查：

- 根因是否定位到具体代码行(不能只到"模块")
- 回归测试任务是否覆盖缺陷场景
- 复杂度判定是否合理(是否漏标"实际需要 design.md")

### 9.1 验证门 5

- [ ] spec-review.md 由独立 spec-evaluator subagent 产出(首行含 `<!-- generated-by: spec-evaluator-subagent -->`，无主线自评/降级痕迹)。subagent 没产出 → 重试一次 → 仍失败 STOP 交人工
- [ ] spec-review.md 中 BLOCK 数量 = 0
- [ ] 所有 BLOCK 已修复或在 review 中显式标注"已确认接受风险，继续"
- [ ] bugfix 模式：spec-evaluator 未标注"应升级为完整 design 流程"。

---

## 十、Phase 6：TDD 实现

| 项 | 值 |
| --- | --- |
| 输入 | tasks.md(已通过 spec-review)+ 项目专属规约 |
| 角色 | tdd-implement skill + implementation-generator subagent |
| 产出 | 代码 commits(GREEN/REFACTOR 带 `Task-Id` trailer)+ tasks.md 由 `tasks-sync` 单点渲染勾选 + `implementation-log.md` |

执行规则见 `tdd-implement` skill。节奏是 **RED → GREEN → REFACTOR**：先写失败测试，再写实现让它通过，再重构；每个任务一次提交。

### 10.1 上下文卫生：重活下沉 subagent

工件链在单条长会话里跑完 Phase 0-9 时，主线会反复全量读 600-700 行大文件、吞大段 diff，导致反复触发上下文压缩，每次压缩后重读、重验、甚至重新引入已修过的 bug。根因是**重活留在主线**。

因此 Phase 3 代码现状扫描、Phase 6 实现，**主线不亲自啃大文件**，而是下沉到 subagent，主线只保留"结论摘要 + `file:line` 指针"：

| 重活 | 下沉到 | 主线保留 |
| --- | --- | --- |
| 读 > 200 行的大文件、跨文件追代码现状 | `Explore` subagent | 命中位置 `file:line` + 一句话结论 |
| Phase 6 写测试 / 写实现 / 跑构建 | `implementation-generator` subagent | 每个任务的 commit hash + 测试结果 + 改动文件清单 |
| 多文件批量 grep 摸清调用链 | `Explore` / `general-purpose` subagent | 调用链摘要 |

主线职责回归"**调度 + 验证门 + 决策**"，不把源码正文堆进主上下文。需要具体某段代码时，用 Grep 定向取行，而非 Read 整文件。这样压缩频率显著下降。`invariants.json`(含 `field_mappings` / `env_notes`)在每次调度时注入，跨压缩也不丢关键事实。

### 10.2 会话分段：别把全链塞进一条会话

工件链 phase 边界天然干净(输入工件 → 输出工件)，状态全在磁盘(`.meta.json` + `invariants.json` + 工件)。所以**一条会话只承载 1~2 个 phase**：跑完落盘(+ 必要时 `git commit` 做 checkpoint)，上下文紧张就 `/clear`，下个 phase 用 `spec-driven resume` 从磁盘冷启动(一屏给出当前 phase / 下一步 / invariants 摘要 / 该读哪些工件)，而不是硬撑在同一条会话里等自动压缩。把"线性增长的单条长会话"换成"多段短会话 + 磁盘交接"。

### 10.3 可选：多 Agent 并行通道

> **规划中，当前 CLI 尚未提供**：下面描述的 `spec-driven parallel plan / run` 还没有实现，Phase 6 目前只能单线程逐个做任务。

默认 Phase 6 仍是单线程逐个做任务(上面的"重活下沉"只下沉给一个 `implementation-generator`)。若 `.openspec/.config.json` 的 `parallel.enabled=true`(默认关闭，仅建议 L 档 / 任务数较多的大型 change)，可切换为多 worker 并行：

1. 主 skill(此时充当协调者)运行 `spec-driven parallel plan` 只读预演：读 `tasks.md` 的 `depends_on`/`scope` 元数据构建 DAG，按依赖分层成"波次"，波内 `scope` 不重叠的任务同批，给出诚实的收益预估(不创建任何 worktree/分支)。
2. 若预估"建议并行"，运行 `spec-driven parallel run` 确认后执行：为本波每个任务建独立 `git worktree`(从 `spec-parallel/<change>` 集成分支切出)，把每个 worktree + 单个任务分派给一个 `implementation-generator` worker(worker 只改自己 scope 内文件、绝不写 `tasks.md`)。
3. 本波 worker 全部完成后，协调者**串行** merge 回集成分支(遇冲突 abort，交人工/子 agent 修复，不静默覆盖)，随后单点跑 `tasks-sync` + `gate-6.5`(与单 agent 场景完全一致的完成判定机制)。
4. 全部波次完成后，集成分支合回原工作分支，进入正常的 Phase 6 验证门 / Phase 7。

真并行度取决于 harness 是否支持并发 subagent；不支持时仍受益于 worktree 隔离与干净合并(**正确但不提速**)。

### 10.4 验证门 6(每个任务完成后)

- [ ] 测试**实际跑绿** PASS(编译通过 ≠ 测试通过 ≠ 完成；`mvn compile -DskipTests` 不得替代 `mvn test`)
- [ ] 本 change 有新增/改动的测试文件(`src/test/java`)(gate-6 / commit-guard git 校验；无测试在 M/L/bugfix 档 BLOCK，S 档或 `test.require_tests=false` 降 WARN)
- [ ] 测试实际运行数 > 0(防 surefire `<skip>true</skip>` / `-DskipTests` 绿灯过门；`test.command` 含跳过参数同样 BLOCK)
- [ ] 集成测试按 `test.integration` 校验：`required=true` 缺集成测试文件 → BLOCK(要求 Phase 6 由 implementation-generator 生成)；`auto` 且 `qa_mode=full` → 缺则 WARN；`false`/其他 → skip
- [ ] 完整构建通过
- [ ] 有"先红后绿"证据，implementation-log 记录测试运行结果(非仅编译记录)；gate-6 检测不到 RED commit 出 WARN
- [ ] `git diff --stat` 无 scope 外文件
- [ ] GREEN/REFACTOR commit 带 `Task-Id` trailer；勾选由 `tasks-sync` 据 commit 单点渲染(实现者不手动勾)
- [ ] JaCoCo **增量**覆盖率(只算本次 change 改动的行)达到 `test.coverage.diff_threshold`(默认 80%)；不达标 BLOCK，直到用户本人确认放行(`/waive` 或说「放行」，再输入确认口令)，由 `spec-driven waive 6 coverage` 留痕

> 反例警示：把 `mvn compile -DskipTests` 通过 当任务完成、宣称"实现完成"，测试实际未跑，靠用户追问"任务完成了吗？"才补——把"能编译"误当"已完成"。

### 10.5 完成记录：勿手动勾选

实现者只产出带 `Task-Id` trailer 的 GREEN/REFACTOR commit；`tasks.md` 的勾选由 `spec-driven tasks-sync [--apply]` 据 commit 证据单点渲染(不带 `--apply` 只预览)(完成的真相是"非 RED commit 带 `Task-Id` + 测试跑绿"，不是手动打的勾)。本次 change 不做的任务用 `- [~]` 显式延期，不要留裸 `- [ ]`。

### 10.6 验证门 6.5 — 任务完成门(Phase 6→7 之间)

进入 Phase 7 前，gate-6.5(由 `spec-driven advance` 在离开 Phase 6 时随 gate-6 一起运行)会：

- [ ] 先跑 `tasks-sync` 据 commit `Task-Id` trailer 自动补勾(避免"活干完了忘打勾"被误挡)
- [ ] 再校验 tasks.md **无裸** `- [ ]`：仍有未完成任务 → M/L/bugfix 档 **BLOCK**、S 档 WARN(`tasks.completion_gate=off` 可关闭)
- [ ] `- [~]` 显式延期默认放行(`tasks.allow_deferred=false` 时连延期也拦)

> 设计动机：手动勾选没有机器门、处在流程末位、压缩后容易丢，常出现"任务做完没打勾"。完成判定证据化(commit trailer)+ 勾选单点渲染(tasks-sync)+ 完成门(gate-6.5)，让单 agent 与多 agent 并行使用同一套完成判定。

### 10.7 验证门 6.7 — 静态质量门(Phase 6→7 之间)

进入 Phase 7 前，gate-6.7(由 `spec-driven advance` 在离开 Phase 6 时随 gate-6 / gate-6.5 一起运行)按 `.openspec/.config.json` 的 `quality` 块跑 ArchUnit / Checkstyle / SpotBugs / PMD / SQLFluff。定位属"提交代码前"门禁，在 QA / 人工 review 之前 fail-fast。原则是**新代码必须合规，历史债务不强制本次偿还**。

- [ ] **命令驱动**：每个检查配置 `command`(`spec-driven quality setup` 写入带完整坐标、锁定版本的插件命令；ArchUnit 为类名含 `Arch` 的测试类；`sqlfluff lint`)和 `report_path`；Checkstyle / PMD / SpotBugs 的 XML 报告和 SQLFluff 的 JSON 输出解析出逐条违规。MyBatis mapper XML 里的 SQL 由 CLI 提取后交给 SQLFluff
- [ ] **基线**：项目首次接入时由 `spec-driven init-config --java` 生成配置，并把现有违规记为基线 `.openspec/quality-baseline.json`(提交进仓库)。指纹为"文件 + 规则 + 规范化消息"，不含行号；ArchUnit 用 `FreezingArchRule` 冻结存量
- [ ] **判定**：本次 change 引入、基线里没有的违规 → **BLOCK**；基线里已有的 → 不拦截，列为"存量"；本次修掉的存量 → 列为"已偿还"，归档时从基线移除，基线只减不增
- [ ] **不按档位降级**：所有档位一致，也不能在配置里关闭；确实无法修复的新增违规，由用户本人确认放行，经 `spec-driven waive 6.7 <检查名>` 留痕
- [ ] **始终产出报告**：无论通过与否，都写 `static-analysis-report.md`(change 目录)，分"新增 / 存量 / 已偿还"三栏，供 Phase 8 code-reviewer 消费
- [ ] coverage 不在此：覆盖率由 gate-6 负责；本门只做架构 / 风格 / 坏味道 / SQL 反模式
- [ ] **commit 时不介入**：静态分析(尤其 SpotBugs 需字节码)是重活，只在 Phase 6 出口单点跑；commit-guard 不跑它

> ArchUnit 规则是 `architecture.md` §4 跨切不变量(层边界 / 依赖方向)的机器编码：设计阶段写下的分层约束，Phase 6 用 ArchUnit 落成测试，gate-6.7 强制。手动复跑：`spec-driven gate 6.7`。

---

## 十一、Phase 7：QA 验证

| 项 | 值 |
| --- | --- |
| 输入 | 已实现的代码 + spec.md(单文件，SC scenarios) |
| 角色 | qa-evaluator subagent |
| 产出 | `.openspec/changes/<change>/qa-report.md` |

qa-evaluator 按 spec 中的每个 scenario 实际执行(运行测试、调用接口、查数据库状态)，判定 PASS/FAIL 并给出证据。

### 评审者失败 = 硬门失败，禁止降级自评

如果 qa-evaluator subagent 没产出报告文件，主线"直接根据代码验证"自写 qa-report 全 PASS——Generator-Evaluator 分离就被悄悄降级成自评，错误的字段映射会跟着一路放行到归档。处理协议：

1. qa-evaluator subagent **没产出** `qa-report.md` 或产出为空 → **重试一次**(可换 model，见 `agents.qa-evaluator.model`)。
2. 重试仍失败 → **STOP**，告知用户"独立 QA 未完成，需人工介入"，**不允许主线自己写 qa-report 当作通过**。
3. qa-report.md **首行必须带机器标记** `<!-- generated-by: qa-evaluator-subagent -->`；gate-7 校验该标记 + "主线自评/降级"反例措辞，命中即 BLOCK。

### 11.1 验证门 7

- [ ] qa-report.md 由独立 qa-evaluator subagent 产出(含 `generated-by: qa-evaluator-subagent` 标记，无主线自评痕迹)
- [ ] 所有 scenario 状态为 PASS
- [ ] FAIL 的 scenario 已回到 Phase 6 修复

---

## 十二、Phase 8：Code Review

| 项 | 值 |
| --- | --- |
| 输入 | 基线 commit..HEAD 的代码改动 + 全部工件 + `static-analysis-report.md` + 项目专属规约 |
| 角色 | code-reviewer subagent(按 tiered-code-review 规范) |
| 产出 | `.openspec/changes/<change>/code-review.md` |

按 BLOCK/WARN/INFO 三档输出，见 `tiered-code-review` skill。与 Phase 5、7 一样，code-review.md 首行必须带 `<!-- generated-by: code-reviewer-subagent -->`，agent 失败重试一次，仍失败 STOP 交人工。

> **消费静态分析报告(gate-6.7 产出)**：code-reviewer **先读** `static-analysis-report.md`，不重复标记机器已抓到的问题(人工评审聚焦机器抓不到的：设计意图、命名语义、边界与并发、可读性)。避免"人机重复劳动 + 报告打架"。

> **可选：接口契约一致性校验** 若 `openapi.enabled=true`，Phase 6 收尾 / Phase 8 由 `openapi-check` skill 读取本地应用暴露的 Swagger / OpenAPI 端点(code-first，权威真值)，与 spec.md `## 接口契约` 及 `openapi.draft.json`(若有)比对，不一致提示"设计与实现漂移"，破坏性变更记入报告。

### 12.1 验证门 8

- [ ] code-review.md 由独立 code-reviewer subagent 产出(首行标记)
- [ ] BLOCK 数 = 0
- [ ] WARN 已记录在 retrospective.md 的"待优化清单"中
- [ ] (若 `openapi.enabled=true`)接口契约与 Swagger 一致，或差异已处理

---

## 十三、Phase 8.5：本地部署验收(可选)

code review 通过后，主 skill 必须显式问用户：

> "code review 已通过。是否在本地启动应用做部署验收？(y / n / skip)"

| 用户回应 | 行为 |
| --- | --- |
| y | 调用 `local-deploy` skill 在本机启动应用，产出 `deploy-report.md`，交用户人工验收 |
| n 或 skip | 请用户给出理由，由总控执行 `spec-driven deploy skip --reason "<用户原话>"`：Phase 8.5 标为跳过、理由记入 retrospective.md「部署验收记录」，直接进入 Phase 8.9 |

| 项 | 值 |
| --- | --- |
| 输入 | `.openspec/.config.json` 中的本地启动命令 + 当前 git 分支 |
| 角色 | local-deploy skill |
| 产出 | `.openspec/changes/<change>/deploy-report.md` |

**deploy-report.md 必须包含：**

- 启动时间 / 分支 / 启动命令
- 启动结果(passed / failed)+ 耗时
- 失败时：错误摘要 + 日志位置(让 Phase 6 修复时有锚点)
- 推荐附：`log-search` 在启动后检索到的关键错误(如有)
- 用户人工验收结论

local-deploy 只在本机启动应用，不操作任何远程环境。

### 13.1 验证门 8.5

- [ ] (用户选 y)deploy-report.md 存在且结论 = `passed`
- [ ] (用户选 y，结论 = `failed`)→ **不通过**，回 Phase 6 修复，**禁止跳过**
- [ ] (用户选 n/skip)已由 `deploy skip` 标为跳过，gate 8.5 直接放行

### 13.2 部署验收 / 归档后发现 bug 的处理路径

按 bug 发现时机走不同路径，**核心规则：已归档的 change 不再改动。**

| bug 发现节点 | 是否回退 feat-X | 走 bugfix? | 操作 |
| --- | --- | --- | --- |
| Phase 6/7 抓到 | ✅ 回退 | 否 | `spec-driven retry 6/7`，在 feat-X 内修 |
| Phase 8.5 启动失败 | ✅ 回退 | 否 | deploy-report.md 结论 = failed，Phase 6 修 → 重 Phase 7 → 重 Phase 8.5 |
| Phase 8.5 / 8.9 人工验收发现功能 bug | ✅ 回退 | 否 | 指出问题所在 Phase，`spec-driven retry <phase>` 走回退流程 |
| 发现与 feat-X 无关的 bug(老功能) | n/a | ✅ | 先把 feat-X 归档(Phase 9)，再 `/bugfix` 起 fix-X，避免 spec 合并冲突 |
| feat-X 已归档后发现 bug | ❌ 不能回退 | ✅ | `/bugfix` 起 fix-X，现场证据用 `log-search` 检索 |

**为什么归档后发现的 bug 必须新建 change：**

- feat-X 已产出全部评审证据(spec-review.md / qa-report.md / code-review.md)和用户验收记录
- 回头改 spec/tasks 等于事后改写"那个时刻评审通过了"的审计证据
- 主 specs 已合并 feat-X 的 delta，改 feat-X 会让合并结果不一致
- bugfix 模式的 `T-regression` 任务挂在 fix-X 上，才能精确绑定这次缺陷

---

## 十四、Phase 8.9：用户验收门(归档前强制)

归档事故的典型形态：Phase 7 降级成自评、Phase 8 也是 agent 自评，**全程无人类确认输出是否正确**，archive 就执行了；随后用户给出大量字段映射修正，只能在"已归档 + 已合并主 specs"状态上返工。根因——**自评链一路绿灯，但没有任何"业务真值正确"的人类背书就归档。**

因此 Phase 9 归档前**必须**插入用户验收：

| 项 | 值 |
| --- | --- |
| 输入 | proposal §5.1 字段映射确认表 + 关键行为(SC)摘要 + qa-report 结论 |
| 角色 | spec-driven-dev skill(向用户呈报)+ 用户(验收) |
| 产出 | 经 `spec-driven uat accept` 写入 `uatAccepted: true` + `uatAcceptedAt`，并记入 retrospective.md「用户验收记录」 |

**操作：**

1. 主 skill 把"字段映射确认表(源→目标→取值规则)+ 本次关键行为 + qa-report 结论"整理成一屏摘要交用户。
2. 显式问："以上字段取值/行为是否符合预期？验收通过请确认(y)，需要改请指出。"
3. 用户确认通过 → 请用户本人原样输入 `确认验收 <change 名>`，平台 hook 据此签发一次性授权，总控再执行 `spec-driven uat accept`。授权绑定当时 spec.md 与 qa-report.md 的内容，之后二者变化须重新确认；模型不能代替用户输入口令，也不能直接写 `.meta.json`。
4. 用户指出问题 → 总控执行 `spec-driven uat reject --phase <N> --reason "<用户原话>"`：记入「用户验收记录」并回退到该 Phase 修正(不许归档)。

### 14.1 验证门 8.9

- [ ] `.meta.json.uatAccepted == true`(`spec-driven archive` 先跑 gate 8.9，未通过时 **拒绝归档**)

例外：用户主动选择跳过验收 → 由用户本人确认放行，经 `spec-driven waive 8.9 g8_9-uat-accepted` 记入 retrospective.md「人工确认记录」后才能归档。

---

## 十五、Phase 9：归档

| 项 | 值 |
| --- | --- |
| 输入 | `.openspec/changes/<change>/` 全套工件 |
| 角色 | spec-driven-dev skill 自身 |
| 产出 | `.openspec/changes/archive/<date>-<change>/` + 主 specs 同步 |
| 工具 | `spec-driven archive`(可先加 `--dry-run` 只看计划) |

执行 `spec-driven archive` 完成迁移与合并：先跑 gate 8.9；spec.md 按 `Capability ID` 路由，按 REQ 粒度合并进主 `specs/<capability>.md`(同 ID 替换、新 ID 追加、SC ID 冲突即拦截)；决策从 `design.md` 蒸馏进 `decisions/<NNNN>-*.md` ADR(编号取现有最大值 +1)；补全 retrospective.md；`git mv` 到 `archive/<date>-<change>/`；最后在迁移后的目录上跑 gate 9。整个过程按事务处理，任一步失败都恢复原工件和 git 暂存区。

### 15.1 验证门 9

- [ ] Phase 8.9 用户验收已通过(`.meta.json.uatAccepted=true`，或有用户本人的放行记录)
- [ ] `.openspec/changes/<change>/` 已不存在(已迁移)
- [ ] `.openspec/changes/archive/<date>-<change>/` 完整
- [ ] 主 `.openspec/specs/` 已同步 delta
- [ ] 已生成 retrospective.md

---

## 十六、阶段间回退机制

允许的回退：Phase N 发现 Phase M(M < N)工件有错时，可以回到 Phase M。

回退时**必须**：

1. 在原工件顶部追加修订记录：`<!-- revised at <date>: <reason> -->`
2. 重新过一次该 phase 的验证门
3. 后续所有 phase 的工件标记为"待重新评审"
4. 至少重做被影响的下游 phase

禁止"偷偷改 proposal.md 但不重过 spec-evaluator"这种行为。上游冻结规则保证进入某 phase 后，其输入工件只读，要改输入必须回上游 + 重过那道门。

---

## 十七、横切 skills(任意 Phase 可调用，不进工件链主目录)

横切 skill 不属于某个固定 Phase，可在任意 Phase 按需调用，且**不创建** `.openspec/changes/<change>/<新文件>`。关键发现手动摘录回主工件的对应章节(如 bugfix-analysis.md 的"现场证据"节、retrospective.md 引用段)，保持工件链单一来源。

| 横切 skill | 用途 | 推荐调用点 | 输出去处 |
| --- | --- | --- | --- |
| `log-search` | 读本地日志文件，按时间范围 + 关键字检索，脱敏 | Phase 1(bugfix 现场诊断)/ Phase 7(QA 后排错)/ Phase 8.5(启动后看日志)/ 任意 incident | 终端输出，关键发现摘录到 bugfix-analysis.md 或 retrospective.md 引用段 |
| `root-cause-analysis` | 5 Whys / fishbone 结构化根因 | Phase 1-2 排障 / Phase 7 验证失败 | 终端输出，结论挪到 bugfix-analysis.md "根因分析"节 |
| `code-quality-optimize` | 代码质量、可读性、性能 | Phase 6 refactor 后 / Phase 8 前 | 直接改代码，review 时写到 code-review.md INFO |
| `incident-analysis` | 线上事故复盘(只分析、给建议，绝不操作生产) | 紧急(跨工件链) | `incidents/<date>-<topic>.md`，事故平息后回到工件链 |
| `local-deploy` | 本地启动应用，交人工验收 | Phase 8.5 | `deploy-report.md` |
| `openapi-check` | 读本地 Swagger 端点，与 `## 接口契约` 比对 | Phase 6 实现后 / Phase 8 | 终端输出，差异摘录进 code-review.md |
| `codegraph` | 用 CodeGraph 代码知识图谱一次拿到"相关符号源码 + 调用链 + 影响半径"，替代 grep/glob/逐文件 Read(探测到 `codegraph` 在 PATH 且项目有 `.codegraph/` 才启用，否则静默回退 Grep/Read) | Phase 2/3 现状扫描与影响面 / Phase 6 取被调方法上下文 / Phase 8 review 取被改方法+影响面 | 中间检索结果 `file:line` + 结论摘录进 design/architecture/review；主 agent 走 MCP，subagent 走 CLI |

**关键原则**：横切 skill 不创建 `.openspec/changes/<change>/<新文件>`。如果横切发现"动摇了主工件结论"(如 log-search 发现 bug 影响面比 bugfix-analysis.md 写的大)，必须回到对应 Phase 重过验证门，不能只在聊天里提一句就继续。

### 17.1 CodeGraph 在各 Phase 的用法接线(探测到才用)

前提：`command -v codegraph` 存在 + 项目有 `.codegraph/` 索引(跑过 `codegraph init`)。探测不到 → 静默走现有 Grep/Read，以下全部不生效。**主会话 agent 走 MCP** `codegraph_explore`；**subagent(收不到 MCP 引导)走 CLI**。

| Phase | 用法 | 替代了什么 | 结论去处 |
| --- | --- | --- | --- |
| Phase 2/3 现状扫描 | `codegraph explore "X 怎么跑通 / X 怎么到 Y"` 一次拿相关符号源码 + 调用链 | Explore subagent 逐文件 Read 拼调用关系 | `design.md` 现状节 / `architecture.md`，只留 `file:line` + 结论 |
| Phase 3 影响面 | `codegraph impact <symbol> --json` 列影响半径 | 人工估影响范围 | `design.md` "影响面"节 |
| Phase 6 实现 | `implementation-generator` 用 `codegraph node <symbol>` 取被调方法上下文(CLI) | subagent Read 相关文件找被调方 | 不落工件，只为写对代码 |
| Phase 8 review | `code-reviewer` 用 `codegraph node/impact` 取被改方法上下文 + 影响面 | 整文件 Read | `code-review.md`，与 log 驱动取证协议对接 |

**纪律**：CodeGraph 返回的源码**视为已读**，不要再 grep/Read 复核同一处(否则抵消收益)；它是**检索不是判定**，impact 结果供参考，不自动变成验证门 pass/fail，关键结论仍按横切 skill 惯例摘录进主工件。可选：`codegraph affected` 接 gate-6 只跑受影响测试(`.openspec/.config.json` 的 `codegraph.affected_tests`，默认关，推荐先用 `warn` 观察)。

---

## 十八、验证门总表(一图速查)

所有 gate 由 `spec-driven gate <phase>` 执行：总控主循环显式调用，gate-router(UserPromptSubmit hook)也按用户输入关键字触发，返回 0 放行 / 2 WARN / 3 BLOCK。任何 BLOCK 都可由用户本人确认放行：输入 `/waive` 或说「放行」触发，再在对话里输入确认口令 `确认放行 <change 名> <gate> <检查项>`，由 UserPromptSubmit hook 签发一次性授权后执行 `spec-driven waive`，记入 retrospective.md「人工确认记录」；防自欺类检查和 gate-6.7 不能在配置里关闭。

| Gate | 触发时机 | 校验内容 | 阻断档位 |
| --- | --- | --- | --- |
| gate-0 | Phase 0 → 1 | Java 构建文件存在；change name kebab-case ≥5 字符；目录已建含 proposal.md；`.meta.json` 含 mode | BLOCK |
| gate-1 | Phase 1 → 2 | 用户故事/AC 完整；Out of Scope 显式声明；歧义全 ✅；业务取值来源必须=用户；字段映射确认表；档位落定 | BLOCK(业务取值自填) |
| gate-2 | Phase 2 → 3 | ≥2 方案 6 字段；推荐有理由；改选即回写(`.meta.json.designDecision` 与 design.md 一致)；影响面到文件路径；4 压测场景；复杂度复评(只升不降) | BLOCK(改选未回写) |
| gate-3 | Phase 3 → 4 | 每 AC 映射到 SC；SC 是 H3/REQ 是 H2、WHEN/THEN 完整；接口契约节完整；数据模型节完整；复杂度复评 | BLOCK |
| gate-4 | Phase 4 → 5 | 任务粒度 ≤2h；依赖顺序清晰；每任务关联 SC(跳过 Phase 3 的 feature 关联 AC，bugfix 关联修改点)；bugfix 必有 T-regression | BLOCK(缺 T-regression) |
| gate-5 | Phase 5 → 6 | spec-review.md 由独立 subagent 产出(首行标记)；BLOCK=0；bugfix 未标"应升级 design" | BLOCK(主线自评) |
| gate-6 | Phase 6 每任务 | 测试实际跑绿；有新增测试文件；测试运行数>0；集成测试按 `test.integration`；RED 先于 GREEN；无 scope 外文件；Task-Id trailer；JaCoCo 增量覆盖率 | BLOCK(0 测试 / skip / 覆盖率不达标) |
| gate-6.5 | Phase 6 → 7 | `tasks-sync` 据 commit 补勾；tasks.md 无裸 `- [ ]`；`- [~]` 延期放行 | M/L/bugfix BLOCK、S WARN |
| gate-6.7 | Phase 6 → 7 | ArchUnit/Checkstyle/SpotBugs/PMD/SQLFluff 命令驱动；基线区分存量违规；产出 `static-analysis-report.md` | 新增违规 BLOCK，所有档位一致 |
| gate-7 | Phase 7 → 8 | qa-report.md 由独立 subagent 产出(首行标记)；所有 scenario PASS | BLOCK(主线自评) |
| gate-8 | Phase 8 → 8.5 | code-review.md 由独立 subagent 产出(首行标记)；BLOCK=0；WARN 入 retrospective 待优化清单 | BLOCK(主线自评) |
| gate-8.5 | Phase 8.5 | (选 y)deploy-report 结论=passed；(失败)回 Phase 6；(选 n/skip)已由 `deploy skip` 标为跳过 | BLOCK(启动失败) |
| gate-8.9 | Phase 8.9 → 9 | `.meta.json.uatAccepted==true`(经用户口令授权后由 `uat accept` 写入) | 拒绝归档 |
| gate-9 | Phase 9 | 8.9 通过；change 目录已迁移；archive 完整；主 specs 同步；retrospective 已生成 | 拒绝归档 |

---

## 十九、上手第一步

1. 在 Java 项目根目录输入 `/spec <需求一句话>` 或 `/bugfix "<问题描述>"`(Codex 上用 `$spec` / `$bugfix`)
2. AI 会建议一个 change name(kebab-case)，确认后创建 `.openspec/changes/<change>/` 骨架
3. Phase 1 需求澄清，AI 整理出歧义清单，等你逐条回答后进 Phase 2
4. 之后按 `proposal → design → spec → tasks → 实现 → QA → review → (本地部署) → 验收 → 归档` 顺序走，每阶段一道门，门不过就回上游修
5. 任何时候想知道当前进度，直接问 AI「现在进度如何」；新开会话时说「继续上次的 change」，总控会先恢复上下文

> 工件链开箱即用：首次接入时，总控会在你同意后接入质量检查工具并生成默认配置和基线，之后不需要改任何东西。只有用到本地集成(日志检索 / 本地部署 / Swagger 比对 / CodeGraph)时才需要按 `.openspec/.config.json` 配置，用不到就跳过。
