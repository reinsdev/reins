# Phase 5：工件评审

进入条件：gate 4 通过；CLI 判定本阶段需执行。S 档跳过仅采纳 CLI 已记录的理由，不补造评审报告。

按 [调度协议](subagent-protocol.md) 派 spec-evaluator。feature 提供 proposal、design、spec、tasks；bugfix 加 bugfix-analysis。被合法跳过的工件不伪造，传入实际替代工件及状态路径。

M 档一轮；L 档两轮独立评审。第一轮问题经所属 Phase 回退修复并重新过门后，再启动第二轮；不能把同一报告复制成第二轮。每轮都检查报告标记并运行 gate 5，第二轮成功后才能结束本阶段。

```text
<spec-driven-dev skill 目录>/scripts/spec-driven gate 5 --change <change>
```

BLOCK 回到问题所属 Phase 修复；例如 AC 错误回 Phase 1，接口规格错误回 Phase 3。bugfix 被评为需要完整 design 时，交用户确认并由 CLI 重算路由，不让评审者自行创建 design 或修改状态。人工接受风险走 waive，不能只改报告计数。

结束：全部所需轮次通过后交回主循环，经 advance 推进。代理失败沿调度协议重试一次后停止。
