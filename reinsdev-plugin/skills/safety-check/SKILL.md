---
name: safety-check
description: 在平台工具前 hook 不可用或覆盖不到当前操作时使用，需要显式执行 CLI 护栏与阶段验证门。
---

# 显式护栏检查

## 推荐调用点与输入

平台 hook 不可用或对子 agent 操作不生效时，在每次 shell / 编辑操作之前调用。
推进 Phase 时另跑 gate。输入为项目根、当前 change/Phase、真实工具名、完整参数和已知的执行者身份。
只判定不执行待检查操作，不自行改写护栏规则。

## 工具前判定

使用已有 CLI 入口，不直接 import policy，不假设存在 bash-guard 或 spec-gate 子命令：

`<spec-driven-dev skill 目录>/scripts/spec-driven hook pre-tool --runtime <claude|codex|opencode>`

用于本次判定的这次 hook CLI 调用不再递归做同一预检；这不豁免待检查操作或其他 shell 调用。
通过 stdin 传合法 JSON 对象，不能把待检查命令拼入 shell 管道来执行。
对象使用平台事件格式，至少提供 `cwd`、`tool_name`、`tool_input`；不要直接传 normalize 后的 `kind/paths/command`。
例如 shell 事件：

```json
{"cwd":"<项目绝对路径>","tool_name":"Bash","tool_input":{"command":"<待执行的完整命令>"}}
```

编辑事件使用实际工具及参数：Edit/Write 的 `file_path`，apply_patch 的完整补丁文本，或多文件编辑的 `edits`。
检查覆盖所有写入路径；不能只检查第一条命令或第一个文件。
仅在平台确实提供身份时带 `agent_type`，不伪造独立评审者身份来获得权限。
当前链路会执行 bash-guard 和 spec-gate 等已注册判定；调用 hook 本身不执行上述命令或编辑。

| CLI 结果 | 处理 |
| --- | --- |
| Claude/Codex exit 0 且 JSON 的 hookSpecificOutput.permissionDecision 为 deny | 拒绝操作，原样呈报 permissionDecisionReason |
| OpenCode exit 2，stderr 为原因 | 拒绝操作，呈报原因 |
| 正常完成且没有拒绝 | 仅本次、同一参数的操作可继续；仍受任务 scope 和其他护栏约束 |
| 无法调用、异常输出、已知解析或 policy 错误 | 报告判定不可用或已降级，不宣称安全检查通过 |

hook 的 fail open 契约保留：异常会记录后放行，exit 0 不能证明所有 policy 都已完成。
显式检查失败时保留待执行操作，交回总控处理缺失能力，不改 hook 为 fail closed，也不把失败伪装成授权。
命令、补丁、路径或执行上下文改变后重新检查。

## 阶段判定与边界

由总控从状态确定当前门，再显式运行：

`<spec-driven-dev skill 目录>/scripts/spec-driven gate <当前门> --change <change>`

gate 6 检查单任务时追加 `--task <任务 ID>`。不以工具前判定代替阶段验证。
gate 退出码 0 放行，1 为错误或能力不可用，2 为告警，3 为拦截。
1/3 时不推进 Phase；2 呈报告警并交回总控。gate 的告警不撤销工具前 deny。
BLOCK 的修复、放行、降档交回总控；用户需要放行时走 /waive，不伪造 prompt-submit 或授权口令。

只用本地 CLI，不连接外部服务，不执行被拒绝操作，不更改 gate 配置。
不创建额外 change 工件，不直接编辑 .meta.json 或 retrospective.md，不代替用户验收。
输出本次检查的工具/路径摘要、判定与原因、gate 结果和降级限制。
显式调用不能保证拦住绕过本 skill 的操作，不能冒充平台自动强制拦截。
