---
name: spec
description: 用规格驱动工件链开始一个新需求（Reins）。仅在用户输入 /spec 或 $spec 时使用。
argument-hint: <需求一句话或 change 名>
disable-model-invocation: true
---

使用 spec-driven-dev skill，以 feature 模式开始一个新 change。

用户调用本 skill 时附带的文本就是需求描述或 change 名；没有附带文本时，先请用户描述需求。
