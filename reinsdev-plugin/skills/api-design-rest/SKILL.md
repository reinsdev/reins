---
name: api-design-rest
description: Reins 总控进入 Phase 3，需要将 AC 写成行为场景或设计 REST 接口契约时使用。
user-invocable: false
---

# 行为与接口规格

输入：proposal、design 或 bugfix-analysis、项目规约。只编辑当前 change 的单个 spec.md。读取 [spec 模板](../spec-driven-dev/templates/spec.md)，保留已有数据库章节；不得另建一份接口 spec。

1. 根据项目现有能力归属确定 Capability ID，小写 kebab-case。已有能力沿用 ID；歧义交用户确认，不自行重命名导致归档路由改变。
2. 把每条 AC 映射到至少一个 SC。REQ 使用 H2，格式 `REQ-<capability>-<NNN>`；SC 使用 H3，格式 `SC-<capability>-<NNN>`，边界/异常可用 `SC-<capability>-E<数字>`。编号唯一，不因排序随意改号。
3. 每个 SC 写“关联 AC”，并完整写 WHEN、THEN，必要时加 AND。说明前置条件、输入、可观察结果、失败行为和数据副作用；不把实现过程当作验收行为。
4. 文末保留“接口契约”汇总节，填模板列：Method、Path、请求字段、响应字段、错误码、幂等性、限流、关联 SC。字段给出类型、必填性和约束，错误码对应实际失败场景。
5. 没有接口变更仍保留该节并写“本次不变更”。如果有数据库影响，在 SC 中明确待补的 DB 后置状态并交 db-schema-design 完成，不能为省事删除这些条件。
6. 将同一 spec 路径和需要补充数据约束的 SC 编号交回总控，再顺序调用 db-schema-design；交接通过文件，保持既有 REQ/SC 身份。

可选 OpenAPI 草稿仅在配置启用且对应本地生成、校验能力可用时产出。能力未提供时明确报告，不发明脚本或宣称验证通过。

交回总控，由总控在数据库部分完成后跑 gate 3。返回 spec 路径、AC→SC 对应关系和待补的数据状态；不自行修改冻结的 proposal/design。
