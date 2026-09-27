---
name: waive
description: 人工放行一次验证门拦截（Reins）。用户输入 /waive，或在 gate 拦截后说「放行」「跳过这个拦截」「先不管这个问题」「接受当前覆盖率」时使用。只有用户本人能放行，模型不得主动发起。
argument-hint: "[<gate> <检查项>]"
---

用户想放行一次验证门拦截。你只负责把放行需要的信息摆到用户面前、按用户的确认执行命令，**确认必须由用户本人在对话里输入**。

1. 从当前会话确认 change 名；有歧义时请用户指定，不能按当前分支猜测。执行 `<spec-driven-dev skill 目录>/scripts/spec-driven status --change <change>`，找出当前 change 处于 BLOCK 的检查项。没有 BLOCK 时告诉用户「当前没有需要放行的拦截」并停下。
2. 用户附带了 `<gate> <检查项>` 就用它；否则把所有 BLOCK 项列出来，让用户选一项。每项原样给出：gate、检查项、拦截内容、指纹。
3. 请用户给出放行理由。理由只能来自用户，不得代写或补全。
4. 请用户**原样输入**确认口令：

   ```
   确认放行 <change 名> <gate> <检查项>
   ```

   只有这句口令由用户本人发出时，平台的 UserPromptSubmit hook 才会签发一次性的放行授权。用户说「放行」「可以」「同意」都不算确认，继续请用户输入口令。
5. 用户输入口令后，执行 `<spec-driven-dev skill 目录>/scripts/spec-driven waive <gate> <检查项> --change <change> --reason "<用户给的理由>"`。命令消费授权，在 retrospective.md「人工确认记录」追加记录。命令报「没有有效授权」时，把原文告诉用户并停下，不要重试或绕过。
   - 用户已输入口令、命令仍报没有授权时（平台没把用户消息交给 Reins），若执行通道支持用户交互的真实终端，由你执行同一条带 `--change <change>` 的命令，请用户本人按终端提示输入 change 名确认。没有可用的交互终端时停下并说明原因。不得代填确认。
6. 执行 `<spec-driven-dev skill 目录>/scripts/spec-driven gate <gate> --change <change>`，确认该项显示 `[WAIVED]`，回到总控主循环。

用户表达的是「不要放行」「先别放行」，或者放行不是用户提出的，都不执行本 skill 的第 4、5 步。
