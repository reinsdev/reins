# Implementation Log: demo-change

## T1: 更新值

### 变更范围

| 关联 SC 或修改点 | 改动文件 | 测试文件 |
| --- | --- | --- |
| SC-demo-001 | src/main/java/demo/A.java | src/test/java/demo/ATest.java |

### RED：失败测试

| 命令 | 退出码 | 运行数 | 失败数 | 失败原因 | 证据位置 |
| --- | --- | --- | --- | --- | --- |
| mvn -o test | 1 | 1 | 1 | 断言值不相等 | RED commit |

### GREEN：通过测试

| 命令 | 退出码 | 运行数 | 失败数 | 跳过数 | 证据位置 |
| --- | --- | --- | --- | --- | --- |
| mvn -o test | 0 | 1 | 0 | 0 | target/surefire-reports/TEST-demo.ATest.xml |

### 完整构建

| 命令 | 退出码 | 结果 | 证据位置 |
| --- | --- | --- | --- |
| mvn -o verify | 0 | PASS | target/build.log |
