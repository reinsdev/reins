# Phase 6：逐任务实现

进入条件：Phase 5 通过或由 CLI 合法跳过，任务范围已冻结。默认逐任务串行，按依赖顺序派 implementation-generator，读取 [tdd-implement](../../tdd-implement/SKILL.md) 并遵守 [调度协议](subagent-protocol.md)。

1. 先预览 tasks-sync，以提交证据识别未完成任务，不重做已有完成提交。
2. 每次只派一个任务编号、输入路径和 scope。实现者返回 commit、真实测试结果、文件列表及 implementation-log 路径。
3. 总控对该任务运行 gate 6；BLOCK 留在本任务修复。WARN 由用户决定，不能视为自动通过。

```text
<spec-driven-dev skill 目录>/scripts/spec-driven tasks-sync --change <change>
<spec-driven-dev skill 目录>/scripts/spec-driven gate 6 --task <task> --change <change>
```

所有任务完成后，总控单点同步并运行出口验证：

```text
<spec-driven-dev skill 目录>/scripts/spec-driven tasks-sync --apply --change <change>
<spec-driven-dev skill 目录>/scripts/spec-driven gate 6 --change <change>
<spec-driven-dev skill 目录>/scripts/spec-driven gate 6.5 --change <change>
<spec-driven-dev skill 目录>/scripts/spec-driven gate 6.7 --change <change>
```

gate 6.5 检查提交推导的任务状态；延期必须有明确范围决定，不能把没完成的任务改成已完成。gate 6.7 对所有档位检查静态质量，报告由 gate 产出，模型不伪造；新增违规修复或由用户本人发起放行，不能扩充基线抹去违规。

结束：全部出口门通过，用户已处理 WARN 后才经 advance 推进；advance 会再次检查 6 / 6.5 / 6.7。任务级 gate 通过不能提前进入 QA。测试为零、编译成功但未跑测试、覆盖率不足都不属于“完成”。

## 可选：多实现者并行

默认逐任务串行。只有 `.openspec/.config.json` 里 `parallel.enabled=true` 时才能并行。这个开关由用户决定，总控不替用户打开。

1. 先预演。它只读，不建分支和 worktree：

   ```text
   <spec-driven-dev skill 目录>/scripts/spec-driven parallel plan --change <change>
   ```

   把波次、预计用时和结论原样告诉用户。预演报出依赖有环或缺范围时，不能并行，按提示处理。结论不是「建议」时，默认继续串行。
2. 用户确认要并行后，为下一波建 worktree：

   ```text
   <spec-driven-dev skill 目录>/scripts/spec-driven parallel run --change <change> --json
   ```

   为输出里的每个 worktree 派一个 implementation-generator。每个只给一个任务编号、worktree 路径和范围。worker 只改自己范围内的文件，提交要带 Task-Id，不写 tasks.md。平台支持时可以同时派多个。
3. 本波全部返回后，串行合回：

   ```text
   <spec-driven-dev skill 目录>/scripts/spec-driven parallel merge --change <change>
   ```

   合并会自动做 tasks-sync --apply 和 gate 6.5。退出码 3 表示合并冲突。这时已经中止合并，现场全部保留。把冲突文件和 worktree 路径告诉用户，在对应 worktree 里解决后，再运行 merge。不要删 worktree，不要强行覆盖。退出码 1 表示本波还没做完，或者有 worker 改了 tasks.md，按提示处理。
4. 还有下一波时，回到第 2 步。全部波次合回后，按上文运行出口验证（gate 6 / 6.5 / 6.7）。
