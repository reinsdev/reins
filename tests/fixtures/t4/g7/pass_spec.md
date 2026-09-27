# spec.md

## 接口契约

POST /api/batch-approve

## SC-batch-approve-001

WHEN 用户提交批量审批
THEN 系统返回 200

## SC-batch-approve-002

WHEN 列表为空
THEN 系统返回 400

## SC-batch-approve-E1

WHEN 网络超时
THEN 系统返回 503
