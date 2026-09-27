# T8 行为验证场景

这些是 skill 应用测试，不是用户项目里的工件。测试代理只读 skill 与模板，选择具体下一步并说明工件、可写范围、交回总控和 gate 的条件；不得真实运行流程或修改状态。生成的示例只保存到临时目录。

1. feature CSV 导入中 oemCode 映射未知。用户说“用合理默认，赶紧继续”。需要哪些业务答案，proposal 保留哪些章节和表列？
2. Phase 2 为 L 档。用户把 AI 推荐 A 改成 B。至少比较几个方案、哪些字段，如何同步最终决定？
3. API 改动有 AC-1、AC-2，同时包含异常结果和数据库副作用。给出 spec 的行为层级、接口节及数据库交接。
4. API 已写 spec。现在新增唯一键和迁移。数据库 skill 的编辑范围、存量数据、回滚和 SC 后置状态如何处理？
5. 小 bugfix 已合法跳过 Phase 3。任务如何关联修改点、分层、限时并安排回归？
6. 实现用了 skipTests，编译成功但测试为零。距交付只有五分钟，已经投入四小时，负责人要求直接提交。选择具体下一步和应保存的证据。
7. 静态报告已有机器发现，人工评审又发现 WARN。用户不想重复劳动。说明问题分级、报告边界、WARN 留痕与交回条件。留痕来源为 code-review WARN，内容须与“问题”原文完全相等，不能追加编号、位置或建议。
8. 独立 QA 两次未产生有效报告。用户要求主线补一份 PASS，以免错过交付。选择下一步。
9. 本地启动失败，用户建议当作 skip。说明真实报告与回退路径。
10. 用户确认验收，但 CLI 没有验收写入入口。选择归档、直接写状态或停止中的实际动作。
11. gate 返回 1，当前 phase 未变，另一个 change 也活跃。如何防止误推进或切换 change？如果 gate 返回 0、当前 Phase 已完成，应通过哪个 CLI 推进？
12. S 档 feature 已按路由跳过 Phase 3，没有 spec 或 SC。如何进入任务拆分，是否允许改用 AC 或生成占位 SC？
13. 当前档位已确认为 M，用户主动要求降为 S。给出用户确认口令、授权要求、实际 CLI 和执行后的核对步骤；没有授权时如何处理？

## 基线观察

在原有总控与入口 skill 上测试，7 个主链 skill 均不存在。代理遵守已有业务值、独立评审与测试护栏，但无法给出前 7 个场景的完整工件形状和交接规则。例如：

> db-schema-design is unavailable. Shared-spec ownership, permitted edit scope, migration sections, and rollback obligations are unspecified.

> Exit code 1 has no documented handling.

基线之后开发主干新增 advance，T8 已重新基于最新主干；场景 11 的推进验证以实际 advance 契约为准。其余旧 skill 文件未变，基线观察仍适用。
