# Phase 2：方案权衡

进入条件：gate 1 已通过，CLI 路由到本阶段。proposal 只读。若路由声明跳过，确认非空跳过理由并运行 gate 2，不自行生成 design 掩盖缺少状态。

1. 调用 [tech-design-tradeoff](../../tech-design-tradeoff/SKILL.md)，传入 proposal、项目规约和现有结构；bugfix 同时提供分析工件。
2. skill 按 templates/design.md 写 design.md，至少两个方案；L 档至少三个。
3. 向用户呈报推荐方案与理由。用户选择后由总控执行：

```text
<spec-driven-dev skill 目录>/scripts/spec-driven design set "<choice>" --change <change>
```

确认 CLI 决策落盘，再交 tech-design-tradeoff 将 **最终选择** 行和理由同步为用户所选方案；AI 推荐保留为原推荐。两处不一致时不进入下一阶段。

4. 运行复杂度复评并呈报。仅当用户确认升档时加 --apply；复评不自动降档。

```text
<spec-driven-dev skill 目录>/scripts/spec-driven complexity recheck --phase 2 --change <change>
<spec-driven-dev skill 目录>/scripts/spec-driven gate 2 --change <change>
```

结束：按 gate 2 结果处理。方案涉及修改需求时经总控 retry 回 Phase 1，不让设计 skill 改冻结的 proposal。
