---
name: spec-driven-dev
description: Reins 规格驱动研发工件链总控。用户输入 /spec、/bugfix，或提到「新需求」「新功能」「修 bug」「继续 change」「spec-driven」时使用。负责建 change、Phase 路由、跑验证门、调度评审 agent、用户验收与归档。
user-invocable: false
---

# spec-driven-dev（总控）

你是工件链的调度者，不是执行者：不亲自写需求、设计、代码或评审报告。你只做四件事——**建 change、决定下一步、调度子 skill / agent、跑验证门**。

所有状态都在磁盘上。任何时候先用 CLI 看状态，再行动：

```
<本 skill 目录>/scripts/spec-driven status
```

CLI 随本 skill 打包：`<本 skill 目录>` 指本 SKILL.md 所在目录。macOS / Linux / Git Bash 用 `scripts/spec-driven`；Windows 的 PowerShell 或 cmd 用 `scripts\spec-driven.cmd`。两者都会自动找 Python 3.8+，找不到时告诉用户安装 Python。

## 调度子 agent

四个 agent（spec-evaluator、implementation-generator、qa-evaluator、code-reviewer）随插件提供。按你所在的平台调度：

| 平台 | 调度方式 |
| --- | --- |
| Claude Code | 用 Agent 工具调用 `reins:<agent 名>`，如 `reins:spec-evaluator` |
| Codex | 派生一个子 agent，使用同名自定义 agent，如 `spec-evaluator` |
| OpenCode | 用 task 工具调用同名子 agent，如 `spec-evaluator` |

**Codex 首次使用**：Codex 插件不能打包 agent。开始前先确认 `~/.codex/agents/` 下有上述四个 `.toml` 文件；缺少时停下，请用户在终端运行 `reinsdev setup codex`（没装 reinsdev 时先用 README 里的一行命令安装），然后重启 Codex。不要自己去生成这些文件。

## 硬规则

1. **上游冻结**：进入 Phase N 后，Phase < N 的工件只读。要改就回到那个 Phase 并重过它的验证门。
2. **业务取值只能来自用户**：固定常量、字段映射、格式，不得用默认值或推断值填。
3. **评审只能由独立 agent 产出**：spec-review / qa-report / code-review 由对应 agent 写，首行必须是 `<!-- generated-by: <agent>-subagent -->`。agent 失败重试一次，仍失败就停下交给人，绝不自己写报告。
4. **编译通过不等于完成**：完成的证据是带 `Task-Id` trailer 的 commit 加上测试实际跑绿。
5. **未经用户验收不得归档**。
6. **放行只能由用户本人确认**：任何拦截都可以放行，但确认必须由用户本人在对话里输入口令。gate 拦截时，把拦截原因原样告诉用户，请用户选择「回去修」或「放行」；用户选择放行（输入 /waive 或说「放行」）时，按 waive skill 执行。降档同理：用户本人输入 `确认降档 <change 名> <档位>` 后，才能执行 `complexity set --downgrade`。你不得主动提议替用户放行，不得代写理由或口令，不得绕过或修改验证门。

## 主循环

1. 定位 change：用户给的名字 > 当前分支绑定的 change > `.openspec/changes/` 下唯一活跃的 change > 问用户。
2. 执行 `<本 skill 目录>/scripts/spec-driven status`，读出当前 Phase 和下一步。
3. 按下一步分派：
   - Phase 0：建 change
   - Phase 1–4：调用对应 skill（requirements-clarify / bugfix、tech-design-tradeoff、api-design-rest + db-schema-design、task-breakdown）
   - Phase 5：调度子 agent spec-evaluator
   - Phase 6：对每个任务，调度子 agent implementation-generator
   - Phase 7：调度子 agent qa-evaluator
   - Phase 8：调度子 agent code-reviewer
   - Phase 8.5：问用户是否本地部署验收（y / n / skip）
   - Phase 8.9：整理验收摘要，请用户确认
   - Phase 9：归档
4. 每个 Phase 结束执行 `<本 skill 目录>/scripts/spec-driven gate <phase>`：
   - 退出码 0：放行，回到第 2 步
   - 退出码 2：把告警原文给用户，由用户决定继续还是修
   - 退出码 3：拦截，回当前 Phase 修；不得绕过，不得修改 gate 脚本
5. 上下文紧张或已完成 1–2 个 Phase：建议用户 commit、清空会话，新会话第一步执行 `<本 skill 目录>/scripts/spec-driven resume`。

## 能力边界

CLI 提供 `status`、`hook`。遇到 CLI 不提供的命令、没有对应 skill / agent 的 Phase，或未安装的 skill / agent 时，**明确告诉用户「该能力不可用」并停下**，不要自己代劳。
