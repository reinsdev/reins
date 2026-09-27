# Proposal: <change-name>

## 用户故事

- US-1：作为示例使用者，我希望积分增加一分，以便验证一次完整变更。

## 验收标准 AC

| AC | 用户故事 | 验收标准 | 验证步骤 |
| --- | --- | --- | --- |
| AC-1 | US-1 | 输入 1 返回 2 | 运行 PointsTest，断言 total(1) 等于 2 |

## Out of Scope

不增加网络接口、数据库或部署环境。

## 歧义清单

无

## 隐含依赖

JDK 17、Maven、JUnit、Surefire 和 JaCoCo。

### 5.1 字段映射确认表

本次无字段映射

## 关键非功能性需求

| QPS | 延迟 | 并发 | 数据量级 | 来源 |
| --- | --- | --- | --- | --- |
| 不适用 | 不设性能门槛 | 单线程测试 | 一个整数 | 联调样例约定 |

## 影响的现有模块

| 模块 | 项目相对路径 | 影响说明 |
| --- | --- | --- |
| 积分 | src/main/java/demo/Points.java | 修改计算逻辑 |
| 测试 | src/test/java/demo/PointsTest.java | 验证增加一分 |
