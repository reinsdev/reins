# Bugfix Analysis: <change-name>

## 基本信息

| 报告时间 | 报告人 | 一句话描述 | 发现源 |
| --- | --- | --- | --- |
| 联调运行时 | Json | 少增加一分 | 联调样例 |

## 现场证据

| 复现步骤 | 期望行为 | 实际行为 | 请求样例、截图或本地日志位置 |
| --- | --- | --- | --- |
| total(1) | 2 | 1 | src/main/java/demo/Points.java |

## 根因分析

Points.total 的 return 直接返回输入。调用链：PointsTest → Points.total → return amount。

## 修复方案

仅将 return amount 改为 return amount + 1。

### 修改点

| 修改点 | 项目相对路径 | 具体改动 | 关联 AC |
| --- | --- | --- | --- |
| FIX-1 | src/main/java/demo/Points.java | 返回值加一 | AC-1、AC-regression |

## 影响范围

| 直接影响 | 间接影响 | 风险评估 | 回归验证 |
| --- | --- | --- | --- |
| 积分 | 无 | 低 | PointsTest |

### 复杂度判定

| 修改文件数 | 是否跨服务 | 是否修改 DDL | 是否修改公开 API 签名或参数语义 | 建议与依据 | 用户确认 |
| --- | --- | --- | --- | --- | --- |
| 2 | 否 | 否 | 否 | 单类和测试 | 联调预设范围 |

不改接口签名 + 不改 DDL。
