---
name: tdd-implement
description: Reins Phase 6 的 implementation-generator 接到单个任务，需要执行 TDD、记录测试证据和提交任务代码时使用。
user-invocable: false
---

# 单任务 TDD 规范

本规范由 implementation-generator 读取。先读任务、行为依据、项目规约和状态中的基线，只改派发 scope 的源码、测试，并按 [implementation-log 模板](../spec-driven-dev/templates/implementation-log.md) 追加本任务记录。

## RED → GREEN → REFACTOR

1. **RED**：先写能暴露缺失行为或缺陷的测试，真实运行，确认失败原因是目标行为未实现，而非语法、环境或无测试执行。记录命令、退出码、运行数、失败断言及证据路径。
2. **GREEN**：写最小实现并重新运行。测试实际运行数必须大于 0，所有应跑测试通过。Maven/Gradle 的 skip 标志、surefire skip、零测试和只有编译结果都不能作为完成证据。
3. **REFACTOR**：在绿灯后整理结构，保持行为不变，再运行相关测试和项目要求的完整测试、构建。不得删测试、弱化断言、跳过失败测试或改构建配置来制造绿灯。
4. 记录增量覆盖率：以 baseCommit 以来改动行为为对象，保留 JaCoCo 报告、实际覆盖率、阈值和未覆盖行。覆盖率不够就补测试；用户放行由总控处理，不自行关闭检查。
5. 核对 diff 中的文件都属于任务范围。发现需求或规格有误时交总控回退，不修改 proposal、design、spec 或 tasks 的任务定义。

## 日志与提交

实现日志记录“变更范围、RED：失败测试、GREEN：通过测试、REFACTOR：重构、完整构建、增量覆盖率、提交记录”。数据来自实际执行；证据路径相对项目或 change，使用正斜杠。

每个任务完成提交带 `Task-Id: <task-id>` trailer。任务 ID 为 `T<数字>` 或 `T-regression`；总控按单个任务派发时，一次提交只包含该任务的实现。经总控明确安排的多任务提交，用逗号分隔 ID，例如 `Task-Id: T3, T4`，不得借此扩大 scope。

trailer 放在提交信息最后一段，与正文空一行，按 git interpret-trailers 规则解析。RED 提交必须同时带 `Task-Id` 和 `TDD-Phase: RED`；RED 证明先失败，不能算任务完成。GREEN、REFACTOR 提交建议分别带对应的 TDD-Phase，不可保留 RED 标记。完成依据是自 baseCommit 以来带该 Task-Id 的非 RED 提交。

```text
实现任务描述

Task-Id: T3
TDD-Phase: GREEN
```

提交前遵守用户已有的确认要求，未经要求的确认不得提交。禁止绕过 git hooks。未获提交确认时如实报告“实现已验证，待确认提交”，不能声称任务已完成。

不手动勾选 tasks.md，不写元数据、retrospective 或授权文件。并行任务只在总控明确划定独立 scope 时处理；不覆盖他人的改动。

交回总控，由总控跑 gate 6，并在全部任务结束后跑 gate 6.5 / 6.7。返回任务编号、commit hash（或待提交状态）、测试运行数及失败数、改动文件、日志路径和未决项。
