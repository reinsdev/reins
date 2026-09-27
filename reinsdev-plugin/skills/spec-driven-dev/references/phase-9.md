# Phase 9：归档

进入条件：gate 8.9 放行，当前 change 尚未归档。主线调用 CLI，不直接合并 spec、生成状态或搬运工件。

```text
<spec-driven-dev skill 目录>/scripts/spec-driven archive --dry-run --change <change>
```

检查计划中 REQ 合并目标、SC 冲突、ADR 编号和归档目录。CLI 按同 REQ 替换、新 REQ 追加处理；SC 冲突必须先解决，不静默覆盖。涉及层边界或依赖方向时呈报 architecture.md 的更新建议，由用户决定。

用户的归档意图已明确、计划无冲突且前置门仍通过时执行：

```text
<spec-driven-dev skill 目录>/scripts/spec-driven archive --change <change>
```

CLI 负责主 specs、ADR、retrospective、git mv、能力索引及最后的 gate 9。读取 archive 的 gate 9 结果，确认迁移完整；命令未实现、失败或缺少 gate 9 结果都不能声称完成。需要补跑时必须使用 CLI 能定位归档 change 的方式，不能再按原活跃目录猜测路径。

结束：呈报归档位置、主规格更新及仍需更新的文档。归档后不再回头改原 change；新增问题走新的 bugfix。
