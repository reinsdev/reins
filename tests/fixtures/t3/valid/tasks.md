# Tasks: batch-approve

## Foundation(底层依赖,必须先做)

- [ ] T1. 增加状态列；关联：SC-approval-001；依赖：无；预估：0.5 小时；范围：db/V2.sql

## Domain Layer

- [ ] T2. 补充状态类型；关联：SC-approval-001；依赖：T1；预估：1 小时；范围：src/main/java/Status.java

## Application Layer

- [ ] T3. 实现批量审批；关联：SC-approval-001；依赖：T2；预估：2 小时；范围：src/main/java/Approval.java

## Adapter Layer

- [ ] T4. 接入接口；关联：SC-approval-001；依赖：T3；预估：1 小时；范围：src/main/java/Controller.java

## Test

- [ ] T5. 验证批量审批；关联：SC-approval-001；依赖：T4；预估：1 小时；范围：src/test/java/ApprovalTest.java
