# Capability: 政策审批 (`demo`)

**Purpose**：批量审批。

## REQ-demo-001: 批量审批

系统允许一次审批多条政策。

### SC-demo-001: 全部通过

关联 AC：AC-1

WHEN 提交 3 条 PENDING 政策
THEN 全部变为 APPROVED

### SC-demo-E1: 含非 PENDING 政策

关联 AC：AC-1

WHEN 提交的政策含 APPROVED 状态
THEN 返回部分失败

## REQ-demo-002: 批量上限

系统限制单次条数。

### SC-demo-002: 超过上限

关联 AC：AC-2

WHEN 提交 51 条
THEN 返回错误码 40010

## 接口契约

本次不变更

## 数据模型

本次不变更
