# Phase 1：需求澄清

进入条件：gate 0 通过，CLI 当前阶段允许编写 proposal。只写本阶段工件。

| mode | 调用及输入 | 产出 |
| --- | --- | --- |
| feature | [requirements-clarify](../../requirements-clarify/SKILL.md)，用户需求与项目规约 | 按 templates/proposal.md 写 proposal.md |
| bugfix | [bugfix 变种](bugfix-flow.md)，用户描述与本地证据 | 按 T1 模板写 bugfix-analysis.md、proposal.md |

子流程返回后，列出仍需用户回答的业务值与映射。用户尚未回答时不能推进。bugfix 的 AUTO-DRAFTED 标志必须由用户 review 并删除，不能代删。

需求澄清完成后才进行选档：

```text
<spec-driven-dev skill 目录>/scripts/spec-driven complexity show --change <change>
<spec-driven-dev skill 目录>/scripts/spec-driven complexity set <tier> --reason "<reason>" --change <change>
```

先呈报推荐档和理由，等待用户确认，再运行 set。已确认的档位不自动降低；用户主动要求降档时遵循总控的授权规则。

```text
<spec-driven-dev skill 目录>/scripts/spec-driven gate 1 --change <change>
```

结束：gate 1 检查用户故事、AC、歧义来源、字段映射、影响模块与档位。返回 3 就回当前子流程补齐；需要业务答案仍交用户决定。通过后重读状态，proposal 冻结。
