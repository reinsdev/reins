# Phase 7：QA

进入条件：Phase 6 的 6 / 6.5 / 6.7 已通过，CLI 路由到本阶段。S 档按 CLI 已记录的跳过处理，不生成虚假的 PASS 报告。

按 [调度协议](subagent-protocol.md) 派 qa-evaluator。提供 spec、实现日志、项目规约与测试配置路径；代理对每个 SC 的 WHEN/THEN 实际验证，写出 PASS/FAIL 与证据。

瘦身 bugfix 没有 spec 时提供 proposal、bugfix-analysis、tasks 和状态，由代理按已有 AC、修改点及回归任务核验。角色定义不支持这种输入时停止，交协调者补契约，不能主线代写 QA。

```text
<spec-driven-dev skill 目录>/scripts/spec-driven gate 7 --change <change>
```

FAIL 回 Phase 6 修实现；若行为要求本身有误，回相应上游 Phase。修复后重跑受影响的验证与 QA，旧报告不能直接改成 PASS。报告不存在或无合法标记，重试一次后仍失败就交人工。

结束：真实 gate 7 通过后交回主循环，经 advance 推进。
