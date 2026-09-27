# CLI 边界与恢复

命令入口统一为 `<spec-driven-dev skill 目录>/scripts/spec-driven`。用户只需通过 `/spec`、`/bugfix`、`/waive` 或自然语言交流，内部命令由总控执行。

## 已有命令契约

| 目的 | 命令和参数 |
| --- | --- |
| 恢复与查看 | `resume <change>`；`status --json` |
| 建 change | `new <change> --mode feature`；`new <change> --mode bugfix` |
| 推进 | `advance --change <change>`；用户确认接受告警后加 `--ack-warn` |
| 验证门 | `gate <phase> --change <change>`；gate 6 可加 `--task <task>` |
| 档位 | `complexity show --change <change>`；`complexity set <tier> --reason "<reason>" --change <change>` |
| 复评 | `complexity recheck --phase 2 --change <change>`；用户确认升档后同命令加 `--apply`；Phase 3 同理 |
| 决策 | `design show --change <change>`；`design set "<choice>" --change <change>` |
| 任务状态 | `tasks-sync --change <change>` 预览；加 `--apply` 才写 |
| 待优化项 | `retro add --source "code-review WARN" "<问题原文>" --change <change>`；内容与 WARN 行的“问题”完全相等 |
| 回退 | `retry <phase> --reason "<reason>" --change <change>` |
| 归档 | `archive --dry-run --change <change>`；去掉 `--dry-run` 才执行 |

子命令已注册不表示实现已经可用。若返回“该能力不可用”、错误码 1、无法解析的输出或缺少必要状态，停止并呈报，不另写脚本代替。不要使用旧文档中的 `new-change.sh`、`scaffold-artifact.sh`、`archive-change.sh`、`tasks-sync --write`、`gate --soft` 或未注册的 parallel / trace 命令。

## 用户主动要求降档

复杂度复评只升不降。用户主动要求降低已确认档位时，先呈报当前档位、目标档位和影响，并取得用户本人的理由。普通确认不能代替降档授权。

请用户本人在对话里完整输入 `确认降档 <change 名> <档位>`，用实际 change 名和目标 S / M / L 替换占位符。只有真实用户消息经授权 hook 签发的授权有效；不得模拟用户消息、代写口令或创建授权文件。拿不到有效授权就停止，不假定降档支持终端 TTY 确认。

收到用户口令后，由总控调用 CLI 消费授权，理由使用用户提供的原意：

```text
<spec-driven-dev skill 目录>/scripts/spec-driven complexity set <tier> --downgrade --reason "<reason>" --change <change>
<spec-driven-dev skill 目录>/scripts/spec-driven status --json
```

CLI 负责写入档位和 retrospective 的档位变更记录。确认命令成功，并重读当前 change 的档位、记录和路由；失败时保留错误并停止，不能改用普通 set 绕过授权。

## 当前需协调者补齐的入口

- 用户验收：当前命令契约没有写入 uatAccepted / uatAcceptedAt 的入口。用户说通过后仍不能归档，不能发明 accept 或 uat 命令。
- 部署选择与跳过留痕：当前没有专用入口记录用户选择和 DEPLOY-VERIFIED: NO。retro add 仅写待优化清单，不能冒充部署选择记录。
- S 档 feature：Phase 3 被跳过且没有有效 spec 时，Phase 4 缺少 SC 输入。现有任务契约只接受 SC 或 bugfix 修改点；停止并请 T0/T1 确定路由或关联契约，不能自行造 SC 或把 AC 当作 SC。

阶段推进已有 advance 入口；gate 自身不负责推进。advance 同时验证 Phase 6 的 6 / 6.5 / 6.7，并按档位和 mode 记录条件跳过。执行失败或状态异常时停止，不能直接调用 meta.update() 或编辑 JSON。

这些缺口交协调者维护契约；skill 在缺口处停止，不修改 CLI、gate 或共享模块。入口补齐后，以实际帮助和状态输出为准恢复。

## 回退与恢复

需要修改上游时，向用户说明原因与受影响范围，再执行：

```text
<spec-driven-dev skill 目录>/scripts/spec-driven retry <phase> --reason "<reason>" --change <change>
<spec-driven-dev skill 目录>/scripts/spec-driven resume <change>
```

确认目标 Phase 可写后才委派修改。CLI 负责修订标记、解除冻结和下游 stale；所有受影响的下游工件重新生成或评审，并重新过门。已归档 change 不回退，新缺陷重新走 bugfix。
