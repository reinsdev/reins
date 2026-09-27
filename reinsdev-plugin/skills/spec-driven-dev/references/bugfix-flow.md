# bugfix 变种

本细则由总控在 Phase 1 以 bugfix 模式读取。入口 skill 保持轻量，变种流程集中在此。开始前已由 CLI 创建并定位 change；只写 bugfix-analysis.md 与 proposal.md。

## 先取得事实

逐步询问五项信息：复现步骤、期望与实际、影响面、现场证据、发现源。证据来自用户和本地源码、请求样例、截图或日志，不调用缺陷平台。业务固定值仍由用户提供。

按 [bugfix-analysis 模板](../templates/bugfix-analysis.md) 填写：

1. 基本信息：报告时间、报告人、描述和发现源。
2. 现场证据：复现条件与操作、期望/实际、证据路径。区分已验证和待验证结论。
3. 根因分析：具体文件、符号及位置、时序图和关键调用链。证据不足时保留假设，不直接修代码。
4. 修复方案：最小改动、diff 草稿；“修改点”表写编号、文件、改动及 AC。
5. 影响范围：直接、间接影响及风险；“复杂度判定”记录修改文件数、跨服务、DDL、公开 API 签名或参数语义变化及依据。

## 由用户给出验收

询问“如何验证修好了？”，按 [proposal-bugfix 模板](../templates/proposal-bugfix.md) 写入 change 的 proposal.md。

- 保留用户故事、AC、Out of Scope、歧义、依赖、字段映射、非功能要求和影响模块等模板章节。
- AC 描述正常行为，每条有验证步骤；保留 AC-regression 及自动化回归和已有测试不退化的要求。
- 业务歧义来源只能是用户；字段映射实际确认后才能标“用户确认”。未答不标 ✅。
- Out of Scope 明确只修本次缺陷。其它瑕疵另行记录，不混入修复范围。
- 文件首行保留 AUTO-DRAFTED 标志，交用户 review、补全并删除；模型不代删。

## 确认并记录影响范围

请用户确认 bugfix-analysis.md。确认后，仍在 Phase 1，由总控执行：

`<spec-driven-dev skill 目录>/scripts/spec-driven scope set --files N [--cross-service] [--ddl] [--public-api] --change <change>`

成功后查看跳过判定：

```text
<spec-driven-dev skill 目录>/scripts/spec-driven scope show --change <change>
```

N 来自已确认分析的“影响范围 / 复杂度判定”中的修改文件数。跨服务时加 `--cross-service`，修改 DDL 时加 `--ddl`，修改公开 API 签名或参数语义时加 `--public-api`。方括号表示可选参数，实际调用不带方括号。依据未明确时先请用户补全并确认，不把未知当作否。

`scope set` 成功后，用 `scope show` 的结果告诉用户 Phase 2、3 是否跳过及原因。任一命令失败时呈报原文并停止，不自行补写状态。影响范围变更后须重新确认并在 Phase 1 更新 scope。

## 条件性瘦身

将证据交回总控，以 scope show、complexity 和 advance 的真实结果确定路由，不直接写 bugfixScope、skipped 或 tierConfirmed。scope set 只记录范围，不代替选档、gate 1 或阶段推进。

| 条件 | 后续 |
| --- | --- |
| 跨至少 3 个文件、跨服务、修改 DDL、修改公开 API 签名或参数语义任一命中 | 需要完整 Phase 2 方案依据，按当前档位和 CLI 路由处理 |
| 改 API 签名或参数语义，或改 DDL | 进入相应 Phase 3 规格设计 |
| 不改接口签名/参数语义，且不改 DDL | 明确写出事实与依据，由 CLI 记录 Phase 3 跳过原因 |

跳过 Phase 3 时，任务关联分析中的“修改点”；任务中仍必须有 T-regression。需要升级完整 design 时先呈报给用户，不自行降档或省略必要工件。

交回总控，由总控跑 gate 1。返回两个工件路径、待用户回答的问题、复杂度依据；不自行推进 Phase。
