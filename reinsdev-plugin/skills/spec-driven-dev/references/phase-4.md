# Phase 4：任务拆分

进入条件：Phase 3 已通过或由 CLI 记录跳过理由。调用 [task-breakdown](../../task-breakdown/SKILL.md)，按 mode 和 `skipped.3` 选择输入与关联：

- Phase 3 未跳过：feature 和 bugfix 都输入 spec.md，每项关联至少一个已定义的 SC。
- feature 且 `skipped.3` 非空：输入 proposal.md，每项关联验收标准中至少一个 AC（如 `AC-1`），每条 AC 至少被一个任务覆盖。无需生成 spec.md 或 SC。
- bugfix 且 `skipped.3` 非空：输入 bugfix-analysis.md 和 proposal.md，每项关联分析中的具体修改点。

skill 按 templates/tasks.md 写 tasks.md。任务分层有序、每项不超过 2 小时，每项带关联 SC、AC 或修改点、依赖、预估和文件范围。bugfix 必含 T-regression。缺少关联来源或引用不存在的编号时，回退到来源阶段补全。

本阶段只创建待办任务。后续完成勾选由 tasks-sync 根据提交证据写入，拆分者不能预先标记完成。

```text
<spec-driven-dev skill 目录>/scripts/spec-driven gate 4 --change <change>
```

结束：总控按 gate 4 结果处理。通过后 tasks 范围冻结；进入 Phase 5 或按 CLI 给出的已记录跳过进入 Phase 6。
