---
name: spec-driven-dev
description: 用户输入 /spec、/bugfix，或提出新需求、新功能、修 bug、继续 change、恢复规格驱动流程时使用。
user-invocable: false
---

# spec-driven-dev

你是 Reins 工件链总控。负责定位 change、调度、运行验证门和呈报用户决定。工件由对应 skill 编写，代码和评审由对应独立 agent 产出。

## 先恢复状态

新会话先恢复，随后读取状态。已有明确 change 时传给 resume；没有时按用户指定、分支绑定、唯一活跃 change 的顺序定位。仍不唯一才请用户选择。

```text
<spec-driven-dev skill 目录>/scripts/spec-driven resume <change>
<spec-driven-dev skill 目录>/scripts/spec-driven status --json
```

状态读取失败时不能推测下一步。首次启动、尚无 change 时读取 [Phase 0](references/phase-0.md)。每条支持 `--change` 的命令都显式传当前 change；`status` 没有此参数，读取后按 change 筛选结果。

CLI 随 skill 打包。macOS、Linux、Git Bash 使用上面的启动器；PowerShell、cmd 使用同目录的 `scripts/spec-driven.cmd`。命令参数以当前 `--help` 为准，详见 [CLI 边界](references/cli-boundaries.md)。

## 硬规则

1. `.meta.json`、`retrospective.md`、授权文件只由 CLI 写入。模型不得用编辑器、shell、Python 或直接调用内部模块代写。
2. 上游工件冻结。发现上游错误，先通过 `retry` 回到对应 Phase，再修改并重过受影响的下游 gate。Phase 8.9 用户要求修改时由 `uat reject` 完成记录与回退，不再单独调用 retry。
3. 固定业务值、字段映射、格式来自用户。来源不明就保留问题，不得以推断或默认值填成已确认。
4. 评审报告只能由对应独立 agent 写。按 [调度协议](references/subagent-protocol.md) 验证首行标记；失败重试一次，仍失败就停下交人工。
5. 完成实现需要测试实际运行并通过，以及带 `Task-Id` trailer 的提交。任务勾选由 CLI 同步。
6. 放行和降档由用户本人决定。用户提出放行时交给 waive skill；降档按 [CLI 授权步骤](references/cli-boundaries.md) 执行。不得主动提议替用户放行，不得代写理由、口令或授权，不得绕过或修改验证门。gate 的 BLOCK、WARN 都按下面的退出码处理。
7. 部署选择和用户验收都要实际询问。用户确认后仍须由已实现的 CLI 留存；无法落盘就停止。未经 gate 8.9 放行，不执行归档。

## 主循环

每次只读取当前 Phase 的细则。CLI 给出的 next_phase、档位、跳过原因和 stale 状态是路由依据；不凭工件存在或对话记忆推进。

| Phase | 读取 | 调用者或产出者 |
| --- | --- | --- |
| 0 | [启动](references/phase-0.md) | 总控调用 CLI |
| 1 | [需求](references/phase-1.md) | requirements-clarify；bugfix 变种见该节 |
| 2 | [方案](references/phase-2.md) | tech-design-tradeoff |
| 3 | [规格](references/phase-3.md) | api-design-rest → db-schema-design |
| 4 | [任务](references/phase-4.md) | task-breakdown |
| 5 | [工件评审](references/phase-5.md) | spec-evaluator |
| 6 | [实现](references/phase-6.md) | implementation-generator；含 gate 6.5 / 6.7 |
| 7 | [QA](references/phase-7.md) | qa-evaluator |
| 8 | [代码评审](references/phase-8.md) | code-reviewer |
| 8.5 | [本地部署](references/phase-8.5.md) | 用户决定；local-deploy |
| 8.9 | [用户验收](references/phase-8.9.md) | 总控呈报，用户决定 |
| 9 | [归档](references/phase-9.md) | 总控调用 CLI |

子 skill 返回工件路径、待确认项和影响范围。总控运行该节指定的 gate，并检查进程退出码：

| 退出码 | 下一步 |
| --- | --- |
| 0 | 按本 Phase 细则完成全部工作后，经 advance 推进，再重读状态 |
| 1 | 命令错误或能力不可用；保留错误原文，停止当前动作，不能当作 WARN 或通过 |
| 2 | 向用户呈报告警原文，由用户选择继续或修正；确认继续后才使用 advance --ack-warn |
| 3 | 呈报 BLOCK 的原因、位置和修复建议，留在当前 Phase；用户可选择修正或发起放行 |

gate 负责诊断，advance 重新过门并持久化阶段推进。只在 Phase 细则声明全部结束时执行，单任务 gate 6 通过不推进整阶段。

```text
<spec-driven-dev skill 目录>/scripts/spec-driven advance --change <change>
```

用户明确接受当前告警后才加 --ack-warn。new、archive 或 deploy skip 已推进状态时不重复 advance；先读 status。advance 失败或状态仍未推进时，按 [CLI 边界](references/cli-boundaries.md) 停止处理。条件跳过由 CLI 写入非空原因；S/M/L 和 bugfix 条件由路由器决定。

每完成 1–2 个 Phase 或上下文紧张时，告知当前 change、Phase、工件路径和未决事项。新会话经 resume 恢复；是否提交 checkpoint 遵守用户已有授权。
