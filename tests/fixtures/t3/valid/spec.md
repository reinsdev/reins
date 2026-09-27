# Capability: 批量审批 (`approval`)

**Purpose**：审批所选记录。

## REQ-approval-001: 批量审批

审批结果全部更新。

### SC-approval-001: 审批成功

关联 AC：AC-1

WHEN 审批人提交两条待审批记录
THEN 两条记录均变成已通过
AND 保留审批日志

## 接口契约

| Method | Path | 请求字段 | 响应字段 | 错误码 | 幂等性 | 限流 | 关联 SC |
| --- | --- | --- | --- | --- | --- | --- | --- |
| POST | /approvals | ids: 必填数组，最多 20 条 | count: 整数 | 400: 无效编号 | 重复请求不重复审批 | 每秒 10 次，超限 429 | SC-approval-001 |

## 数据模型

### 表结构

| 表 | 字段 | 类型 | 可空 | 默认值 | 含义 | 关联 SC |
| --- | --- | --- | --- | --- | --- | --- |
| approval | status | VARCHAR(20) | 否 | pending | 审批状态 | SC-approval-001 |

### 索引

| 表 | 索引 | 字段顺序 | 唯一性 | 用途 | 关联 SC |
| --- | --- | --- | --- | --- | --- |
| approval | idx_status | status | 否 | 状态查询 | SC-approval-001 |

### 约束

| 表 | 约束 | 规则 | 关联 SC |
| --- | --- | --- | --- |
| approval | 主键 | id 不可重复 | SC-approval-001 |

### 迁移与回滚

| 迁移脚本 | 回滚脚本 | 执行顺序 | 数据兼容与风险 | 关联 SC |
| --- | --- | --- | --- | --- |
| db/V2.sql: 增加 status | db/U2.sql: 删除 status | 先迁移再发布 | 保留已有记录 | SC-approval-001 |
