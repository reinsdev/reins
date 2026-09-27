# Phase 3：行为规格、接口和数据

进入条件：上游 gate 通过，CLI 路由到 Phase 3。输入为 proposal 和 design；瘦身 bugfix 使用 bugfix-analysis。跳过只采纳 CLI 的非空理由，并运行 gate 3。

两个 skill 顺序共写一个 spec.md：

1. [api-design-rest](../../api-design-rest/SKILL.md) 先确定 Capability ID，建立 REQ(H2) / SC(H3) 行为主体及“接口契约”汇总节。
2. [db-schema-design](../../db-schema-design/SKILL.md) 接着写“数据模型”汇总节，并在现有 SC 补充数据库后置状态。保留接口章节、REQ/SC 编号及 API 行为。
3. feature 每条 AC 至少对应一个 SC，无接口或数据变更在相应节写“本次不变更”。bugfix 按实际 API/DDL 变更补充相关节，不能生成两个 spec 文件。
4. 如果约束或 AC 有误，经总控回退到来源 Phase。当前 skill 不修改上游工件。

```text
<spec-driven-dev skill 目录>/scripts/spec-driven complexity recheck --phase 3 --change <change>
<spec-driven-dev skill 目录>/scripts/spec-driven gate 3 --change <change>
```

复评升档先询问用户，确认后才对复评命令加 --apply。结束时按 gate 3 的真实结果返回主循环；通过后 spec 冻结。

工件不存在时，先由总控生成骨架，再交子流程按骨架填写；文件已存在时不覆盖，直接在原文件上填写：

```text
<spec-driven-dev skill 目录>/scripts/spec-driven scaffold spec --change <change>
```
