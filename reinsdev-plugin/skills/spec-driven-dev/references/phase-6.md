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
