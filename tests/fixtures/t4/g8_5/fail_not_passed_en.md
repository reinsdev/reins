# Deploy Report: test-change

## 启动信息

| 启动时间 | 分支 | 启动命令 |
| --- | --- | --- |
| 2026-01-01 10:00 | feature/test | mvn spring-boot:run |

## 启动结果

| 结果 | 耗时 | 验证证据 |
| --- | --- | --- |
| failed | 8s | health check returned 500 |

## 错误摘要与日志

| 错误摘要 | 日志位置 | 启动后关键错误 |
| --- | --- | --- |
| NullPointerException in startup | logs/app.log | NPE at ApplicationContext |

## 用户人工验收结论

| 验收人 | 验收时间 | 结论 | 反馈 |
| --- | --- | --- | --- |
| 待验收 | — | 待验收 | — |

## 结论

not passed
