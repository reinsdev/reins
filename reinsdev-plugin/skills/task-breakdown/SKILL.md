---
name: task-breakdown
description: Reins 总控进入 Phase 4，需要把行为规格或瘦身 bugfix 修改点拆成可实现任务时使用。
user-invocable: false
---

# 任务拆分

输入：冻结的 spec.md；Phase 3 合法跳过的 bugfix 使用 bugfix-analysis.md 和 proposal.md。只写 tasks.md，读取 [tasks 模板](../spec-driven-dev/templates/tasks.md)。

S 档 feature 若跳过 Phase 3 且没有有效 spec，交回总控并停止拆分。现有契约没有可用的 SC 或 bugfix 修改点，请 T0/T1 确定路由或关联规则。不得自行补造 spec / SC、把 AC 当作 SC，或省略任务关联。

1. 保持分层顺序：`Foundation(底层依赖,必须先做)` → `Domain Layer` → `Application Layer` → `Adapter Layer` → `Test`。
2. 每项不超过 2 小时，过大继续拆。任务编号用唯一的 T 加数字；描述清楚可验证交付物。
3. 每项写明“关联、依赖、预估、范围”。关联至少一个 SC；瘦身 bugfix 关联分析中的具体修改点。依赖用任务编号或“无”，scope 用实际项目相对文件路径，避免“相关文件”这种开放范围。
4. 先排基础依赖，再排依赖它的任务。禁止循环依赖；测试覆盖正常、异常和边界场景，测试任务同样关联行为依据。
5. bugfix 必须保留 `T-regression`，写明缺陷场景、验证步骤、关联修改点或 SC、依赖及测试文件范围。不能因修复很小就省略。
6. 初始状态使用 `- [ ]`。完成状态后续由 tasks-sync 根据提交证据同步；没有完成证据不预先勾选，不把未完成项隐藏成延期。
7. 与用户确认范围和必要的拆分取舍。需要改上游行为时交总控回退；任务拆分不扩大已确认需求。

交回总控，由总控跑 gate 4。返回 tasks 路径、依赖顺序、SC/修改点覆盖及未决范围问题，不自行推进状态。
