# Capability: batch-approve (`batch-approve`)

**Purpose**：批量审批能力。

## REQ-batch-approve-001: 正常审批流程

正常审批请求须通过所有校验后落库。

### SC-batch-approve-001: 正常批量审批成功

关联 AC：AC-1

WHEN 用户提交包含有效 ID 列表的批量审批请求
THEN 系统返回 200，所有记录状态变为「已审批」
AND 审批时间戳写入数据库

### SC-batch-approve-002: 空列表拒绝

关联 AC：AC-2

WHEN 用户提交空的 ID 列表
THEN 系统返回 400，提示「列表不能为空」
AND 数据库无变更

### SC-batch-approve-E1: 网络超时重试

关联 AC：AC-3

WHEN 下游服务在 5 秒内无响应
THEN 系统返回 503，提示「服务暂时不可用」
AND 事务回滚，无脏数据

## 接口契约

| Method | Path | 请求字段 | 响应字段 | 错误码 | 幂等性 | 限流 | 关联 SC |
| --- | --- | --- | --- | --- | --- | --- | --- |
| POST | /api/batch-approve | ids: List[Long] | approved: int | 400, 503 | 是 | 100/s | SC-batch-approve-001 |
