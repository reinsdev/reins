# Phase 8：代码评审

进入条件：上游门通过，CLI 路由到本阶段。按 [调度协议](subagent-protocol.md) 派 code-reviewer，读取 [tiered-code-review](../../tiered-code-review/SKILL.md)。

提供基线所在状态、全部工件、项目规约和 static-analysis-report 的路径。代理先消费静态报告，再评审设计意图、行为、边界、并发和可维护性，不重复列机器已定位的同一问题。

有效 code-review.md 返回后：BLOCK 回所属 Phase 修复或交用户发起 waive；每条 WARN 由总控经 CLI 追加待优化项。内容必须与“问题清单”表该行的“问题”原文完全相等，不拼接编号、位置、建议或改写摘要；这些信息保留在报告中。

```text
<spec-driven-dev skill 目录>/scripts/spec-driven retro add --source "code-review WARN" "<warn-text>" --change <change>
<spec-driven-dev skill 目录>/scripts/spec-driven gate 8 --change <change>
```

追加前先读已有待优化清单，避免同一 WARN 重复登记。CLI 写入失败就停止，不能手写 retrospective。openapi.enabled 启用时调可用的 openapi-check 比对本地契约，差异由评审者归类；缺少必需能力如实报告，不宣称一致。

结束：gate 8 通过后经 advance 进入部署询问；报告失败按调度协议处理。
