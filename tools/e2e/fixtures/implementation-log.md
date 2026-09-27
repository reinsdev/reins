# Implementation Log: <change-name>

## T1: 增加积分

### 变更范围

| 关联 SC 或修改点 | 改动文件 | 测试文件 |
| --- | --- | --- |
| AC-1 | src/main/java/demo/Points.java | src/test/java/demo/PointsTest.java |

### RED：失败测试

| 命令 | 退出码 | 运行数 | 失败数 | 失败原因 | 证据位置 |
| --- | --- | --- | --- | --- | --- |
| mvn -B test | 1 | 1 | 1 | expected 2 but was 1 | <red> |

### GREEN：通过测试

| 命令 | 退出码 | 运行数 | 失败数 | 跳过数 | 证据位置 |
| --- | --- | --- | --- | --- | --- |
| mvn -B verify | 0 | 1 | 0 | 0 | target/surefire-reports/TEST-demo.PointsTest.xml |

### REFACTOR：重构

无。本次修改只有一个表达式。

### 完整构建

| 命令 | 退出码 | 结果 | 证据位置 |
| --- | --- | --- | --- |
| mvn -B verify | 0 | BUILD SUCCESS | target/reins-e2e-1.0-SNAPSHOT.jar |

### 增量覆盖率

| 基线 commit | 改动行数 | 已覆盖行数 | 增量覆盖率 | 配置阈值 | 未覆盖行 | 报告位置 |
| --- | --- | --- | --- | --- | --- | --- |
| <base> | 1 | 1 | 100% | 80% | 无 | target/site/jacoco/jacoco.xml |

### 提交记录

| Commit | 阶段 | Task-Id | 范围核对 |
| --- | --- | --- | --- |
| <green> | GREEN | T1 | Points.java 与 PointsTest.java；另含 CLI 工件 |
