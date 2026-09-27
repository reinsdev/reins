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
| 用户验收通过 | `uat accept --change <change>`；先请用户本人原样输入“确认验收 <change 名>” |
| 用户要求修改 | `uat reject --phase N --reason "<用户原话>" --change <change>`；已含回退，不再单独调用 retry |
| bugfix 范围 | `scope set --files N [--cross-service] [--ddl] [--public-api] --change <change>`；Phase 1 用户确认分析后执行 |
| 范围与跳过判定 | `scope show --change <change>`；将 Phase 2、3 是否跳过及原因告诉用户 |
| 跳过部署验收 | `deploy skip --reason "<用户原话>" --change <change>`；用户选 n / skip 后执行，成功即进入 Phase 8.9 |
| 回退 | `retry <phase> --reason "<reason>" --change <change>` |
| 归档 | `archive --dry-run --change <change>`；去掉 `--dry-run` 才执行 |

用户决策命令的 `--reason` 只用用户原话。`uat accept` 报“没有有效授权”时，原文呈报后停止，不替用户输入口令或创建授权。验收授权绑定 spec.md 与 qa-report.md，内容变化后须重新确认。`deploy skip` 已推进状态时先读 status，不重复 advance。范围参数来自用户确认的 bugfix-analysis，方括号表示可选参数，不原样传入。

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

- S 档 feature：Phase 3 被跳过且没有有效 spec 时，Phase 4 缺少 SC 输入。现有任务契约只接受 SC 或 bugfix 修改点；停止并请 T0/T1 确定路由或关联契约，不能自行造 SC 或把 AC 当作 SC。

阶段推进已有 advance 入口；gate 自身不负责推进。advance 同时验证 Phase 6 的 6 / 6.5 / 6.7，并按档位和 mode 记录条件跳过。执行失败或状态异常时停止，不能直接调用 meta.update() 或编辑 JSON。

这些缺口交协调者维护契约；skill 在缺口处停止，不修改 CLI、gate 或共享模块。入口补齐后，以实际帮助和状态输出为准恢复。

## 回退与恢复

Phase 8.9 用户要求修改时按上面的 `uat reject` 流程执行，不再单独调用 retry。其它需要修改上游的情况，向用户说明原因与受影响范围，再执行：

```text
<spec-driven-dev skill 目录>/scripts/spec-driven retry <phase> --reason "<reason>" --change <change>
<spec-driven-dev skill 目录>/scripts/spec-driven resume <change>
```

确认目标 Phase 可写后才委派修改。CLI 负责修订标记、解除冻结和下游 stale；所有受影响的下游工件重新生成或评审，并重新过门。已归档 change 不回退，新缺陷重新走 bugfix。

## 质量工具首次接入

总控调用 `<spec-driven-dev skill 目录>/scripts/spec-driven quality setup --dry-run` 展示具体改动。用户同意改 pom 后才能执行 `quality setup`，用户同意联网后才能加 `--online`；已有明确授权不重复询问。默认离线只写接入文件并返回 2，联网预热成功返回 0，随后仍需 `init-config --java` 建基线。不得把预热成功当作 gate 通过。

`--base-package`、`--junit`、`--sql-dialect` 传递用户确认的选择。有 SQL 时展示 JDBC 方言候选，生成 `.sqlfluff`；已有文件只显示差异，不覆盖。`quality show` 只读显示团队配置。Gradle 自动接入暂不支持，不绕过检查或伪造报告。
