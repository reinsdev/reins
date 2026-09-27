# Phase 8.5：本地部署验收

进入条件：gate 8 通过。所有档位都要问用户：“评审已通过。是否在本地启动应用做部署验收？y / n / skip。”用户未答前不启动或跳过。

- y：由当前已实现的 CLI 留存选择，再调用 local-deploy。输入本地启动配置与当前分支，按 T1 的 templates/deploy-report.md 产出报告，交用户人工验收。只操作本机。
- n / skip：由 CLI 留存选择，并在 retrospective 中记录 DEPLOY-VERIFIED: NO；记录成功才可继续。

当前 CLI 没有部署选择和跳过留痕入口，见 [CLI 边界](cli-boundaries.md)。在入口补齐前，向用户说明无法记录并停下；不能手改状态或把记录塞进待优化清单。

能力可用并产出真实证据后，由总控运行：

```text
<spec-driven-dev skill 目录>/scripts/spec-driven gate 8.5 --change <change>
```

启动失败必须保留 failed 和错误日志，回 Phase 6 修复、重过受影响的门，再部署。即使时间紧张或用户提出改成 skip，也不能把一次已失败的启动当作未选择部署。

结束：gate 8.5 放行后经 advance 进入用户验收。人工反馈发现本次功能问题时回来源 Phase；已归档后发现问题则开启新的 bugfix。
