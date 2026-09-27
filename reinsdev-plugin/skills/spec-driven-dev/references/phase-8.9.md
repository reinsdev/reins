# Phase 8.9：用户验收

进入条件：上游门已经通过或有有效放行，当前变更尚未归档。总控整理一屏摘要：proposal 的“5.1 字段映射确认表”、关键 SC、独立 QA 结论和部署结果。合法跳过的工件如实列出跳过原因，不编造 PASS。

询问：“以上字段取值和行为是否符合预期？验收通过请确认，需要修改请指出。”决定必须来自用户本人。

## 用户确认通过

请用户本人原样输入 `确认验收 <change 名>`，将占位符替换为当前 change 名。不得替用户输入口令、模拟用户消息或创建授权文件。收到真实用户口令后，由总控执行：

```text
<spec-driven-dev skill 目录>/scripts/spec-driven uat accept --change <change>
<spec-driven-dev skill 目录>/scripts/spec-driven status --json
```

命令报“没有有效授权”时，把错误原文告诉用户后停下。其它错误同样保留原文并停止。成功后再读取状态，确认验收已记录。授权绑定 spec.md 与 qa-report.md 的内容；内容变化后须重新请用户确认。

## 用户要求修改

确定问题所属 Phase，用其编号替换 `<phase>`，由总控执行，`<reason>` 只填用户原话：

```text
<spec-driven-dev skill 目录>/scripts/spec-driven uat reject --phase <phase> --reason "<reason>" --change <change>
<spec-driven-dev skill 目录>/scripts/spec-driven resume <change>
```

`uat reject` 已记录验收意见并回退，不要再单独调用 retry。确认目标 Phase 可写后修正，重新验证受影响的下游工件。命令失败时停止，不继续修改或推进。

用户主动要求放行时交给 waive skill，由用户本人完成授权。所有验收记录和状态只由 CLI 写入，不直接编辑 `.meta.json` 或 `retrospective.md`。

具备真实 CLI 验收记录或有效用户授权后，由总控运行：

```text
<spec-driven-dev skill 目录>/scripts/spec-driven gate 8.9 --change <change>
```

结束：只有 gate 8.9 放行，才能经 advance 进入 Phase 9；用户沉默或测试全绿均不等于验收通过。
