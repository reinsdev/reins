# 独立 agent 调度协议

每次派发使用独立上下文。输入由路径组成，任务编号是定位 tasks.md 的唯一额外标识。代理自行读文件；主线不粘贴工件全文、代码、diff 或自己的推理。

## 平台接线

| 平台 | 调度 |
| --- | --- |
| Claude Code | Agent 工具调用 `reins:<agent 名>` |
| Codex | 派生使用同名自定义角色的子 agent |
| OpenCode | task 工具调用同名子 agent |

Codex 使用前确认四个自定义 agent 已安装；缺少时请用户运行 `reinsdev setup codex` 并重启会话，不自行生成安装文件。平台不提供独立执行能力、报告模板缺失或权限配置不够时，说明“该能力不可用”并停止。主线程自评不能替代独立评审。

## 派发载荷

按角色选定固定指令，再填路径。路径可为绝对路径或相对项目根的正斜杠路径，必须唯一指向当前 change。

```text
读取给定路径，按角色定义及规范执行。只在允许范围写入，完成后返回证据摘要。
项目根：<project-path>
角色定义：<agent-definition-path>
项目规约：<instructions-path>
状态与基线：<change-path>/.meta.json
输入工件：<input-paths>
不变量：<change-path>/invariants.json
执行规范：<skill-path>
报告模板：<report-template-path>
允许写入：<allowed-output-paths>
```

只传存在且需要的可选文件；不变量缺失如实标明，不让模型推断补造。实施任务另传 `任务：<task-id>`，范围来自 tasks.md，不随派发扩大。

| 角色 | 输入工件 | 规范与输出边界 |
| --- | --- | --- |
| spec-evaluator | proposal、tasks；存在时加 design、spec、bugfix-analysis | 只写 spec-review.md；模板 templates/reports/spec-review.md |
| implementation-generator | tasks、spec，或瘦身 bugfix-analysis、proposal | 读 tdd-implement；只改任务 scope 的源码、测试并追加 implementation-log.md |
| qa-evaluator | spec、implementation-log、测试配置；瘦身流程加 proposal、bugfix-analysis | 只写 qa-report.md；模板 templates/reports/qa-report.md；可跑验证，不改源码和预期 |
| code-reviewer | 全部工件、static-analysis-report、测试配置 | 读 tiered-code-review；只写 code-review.md；模板 templates/reports/code-review.md |

报告骨架由协调者维护，T9 只补说明，不改标题和表头。模板路径相对 spec-driven-dev 目录；角色定义在插件 agents/ 下。基线 commit 从只读状态读取，不能改基线来缩小评审范围。

报告结构遵守共享契约：

- “结论”只有一张 `BLOCK | WARN | INFO` 表，一行非负整数，计数与问题清单一致。
- “问题清单”只有一张 `级别 | 位置 | 问题 | 建议` 表，级别仅 BLOCK / WARN / INFO，位置为 `文件:行` 或 `-`。无问题时只保留表头，不写数据行。
- QA 的“SC 验证结果”表头为 `SC | 结果 | 证据`，每个 SC 一行，SC 列只写 ID，结果仅 PASS / FAIL。
- bugfix 的 spec-review 另有“bugfix 升级判定”，第一个非空行只能是 `保持 bugfix` 或 `应升级 design`。
- 多轮 spec 评审逐轮覆盖同一报告，gate 检查最新一轮。证据等补充说明可另加小节，不改上述结构。

## 返回与失败

评审者只返回报告路径、结论、BLOCK/WARN 数量和证据位置。实现者返回任务编号、commit hash、测试实际运行数/失败数、改动文件和日志路径。正文留在工件中。

总控先检查报告存在、非空且首行对应角色：

- `<!-- generated-by: spec-evaluator-subagent -->`
- `<!-- generated-by: qa-evaluator-subagent -->`
- `<!-- generated-by: code-reviewer-subagent -->`

缺文件、空报告、错误标记或代理异常：独立重试一次。仍失败就报告“独立评审未完成，需人工介入”，不推进、不代写报告、不补签标记。有效报告里的 BLOCK 属于评审结果，进入修正流程，不靠重复派发掩盖。

Claude Code 的 hook 可识别 agent_type；当前 Codex、OpenCode 的工具事件没有同等身份字段。仍按角色与输出范围调度，由现有沙箱、平台权限、CLI 和 git 护栏共同约束；不得声称单个 hook 已验证评审者身份。
