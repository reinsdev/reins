---
name: bugfix
description: 用规格驱动工件链修复一个缺陷（Reins）。仅在用户输入 /bugfix 或 $bugfix 时使用。
argument-hint: "<问题描述>"
disable-model-invocation: true
---

使用 spec-driven-dev skill，以 bugfix 模式开始一个新 change。缺陷信息由用户描述，不调用任何缺陷平台。

用户调用本 skill 时附带的文本就是问题描述；没有附带文本时，先请用户描述问题。

将原始问题交给 [总控](../spec-driven-dev/SKILL.md)。总控完成启动后，在 Phase 1 读取 [bugfix 变种](../spec-driven-dev/references/bugfix-flow.md)。本入口不直接修代码、不编造 AC、不删除用户 review 标志，也不决定跳过阶段。
