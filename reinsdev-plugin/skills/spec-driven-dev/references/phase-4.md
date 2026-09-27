# Phase 4：任务拆分

进入条件：Phase 3 已通过或由 CLI 记录跳过理由。调用 [task-breakdown](../../task-breakdown/SKILL.md)，输入 spec；瘦身 bugfix 输入 bugfix-analysis 的修改点和 proposal。

S 档 feature 若跳过 Phase 3 且没有有效 spec，先停止任务拆分。当前模板和 gate 4 只接受 SC 或 bugfix 修改点，缺少合法关联输入。向协调者报告，请 T0/T1 决定路由或任务关联契约；不要自行生成占位 spec / SC，也不要把 AC 当作 SC。契约补齐后再恢复。

skill 按 templates/tasks.md 写 tasks.md。任务分层有序、每项不超过 2 小时，每项带关联 SC 或修改点、依赖、预估和文件范围。bugfix 必含 T-regression。

本阶段只创建待办任务。后续完成勾选由 tasks-sync 根据提交证据写入，拆分者不能预先标记完成。

```text
<spec-driven-dev skill 目录>/scripts/spec-driven gate 4 --change <change>
```

结束：总控按 gate 4 结果处理。通过后 tasks 范围冻结；进入 Phase 5 或按 CLI 给出的已记录跳过进入 Phase 6。

工件不存在时，先由总控生成骨架，再交子流程按骨架填写；文件已存在时不覆盖，直接在原文件上填写：

```text
<spec-driven-dev skill 目录>/scripts/spec-driven scaffold tasks --change <change>
```
