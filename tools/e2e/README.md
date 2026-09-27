# CLI 联调脚本

从仓库根目录运行 `python3 tools/e2e/run.py`。需要 Python 3.8+、JDK 17、Maven。每次创建独立临时项目和 `REINS_HOME`，不启动 AI 平台，不改真实项目，不编辑 `.meta.json` 或 `retrospective.md`。

```sh
python3 tools/e2e/run.py --flows B C
python3 tools/e2e/run.py --online
python3 tools/e2e/run.py --maven-repo /path/to/offline-repository
python3 tools/e2e/run.py --diagnose
python3 tools/e2e/run.py --flows Q Q4 --online
python3 tools/e2e/check_sqlfluff.py --sqlfluff /path/to/sqlfluff
```

- 默认离线。POM 锁定 Surefire 3.5.4、JaCoCo 0.8.12、JUnit 5.12.2（Q4 使用 JUnit 4.13.2）。`--online` 允许下载 Maven 依赖。默认仍运行 A/B/C；Q/Q4 专门验证质量接入。
- Q/Q4 先预览并执行 `quality setup`，验证重复执行文件不变，再初始化基线，检查 gate 6.7 通过、新增 Checkstyle 违规拦截、恢复后通过、新增分层依赖违规拦截。ArchUnit、Checkstyle、PMD、SpotBugs 的 XML 都由真实工具生成；插件版本和属性见 [T16 验证记录](T16-evidence.md)。
- `check_sqlfluff.py` 使用单独安装的 SQLFluff，在临时目录验证模板参数、CP01、AM04、RF02、LT05 告警和隐式别名；不自动安装依赖。
- 缺 JDK/Maven 时停止；依赖缺失、真实构建失败时记录失败。某一流程失败后继续另外两条独立流程。
- 默认遇到非预期结果即停止该流程，最终退出 1；全部符合预期才退出 0。
- `--diagnose` 仅作用于脚本新建的 A 项目。记录原始失败后，模拟 UserPromptSubmit 口令并调用 waive，以探查后续阶段。任何诊断偏差都会让最终退出码保持 1。B 中的放行则是用例本身的预期行为。
- 报告按插件 `templates/reports/` 生成协议测试输入，明确标注“不是独立 agent 实际评审结果”。测试、构建和覆盖率报告由 Maven/Surefire/JaCoCo 真实产生。
- `fixtures/` 中的 markdown 是插件模板填写后的具体样例。implementation-log 的固定测试数量与覆盖率在写入前由脚本核对真实 XML；模板变动时需要同步这些样例。

脚本打印证据目录，保留 `steps.json`（完整输出和 stdin）、`steps.md`（逐步关键输出）、`summary.json`、真实 RED/GREEN 测试 XML、JaCoCo XML，以及三个 git 项目。git 统一经 `gitutil.git()`，记录的失败码是包装器的 1，诊断中保留 git hook 的拒绝原因。

每次运行的完整证据保存在脚本打印的临时目录里，不提交进仓库。联调发现的问题已转为任务，见 [任务书](../../docs/dev/tasks.md)。Windows 验证延后，Linux 尚未实测。
