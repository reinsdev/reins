# CLI 联调脚本

从仓库根目录运行 `python3 tools/e2e/run.py`。需要 Python 3.8+、JDK 17、Maven。每次创建独立临时项目和 `REINS_HOME`，不启动 AI 平台，不改真实项目，不编辑 `.meta.json` 或 `retrospective.md`。

```sh
python3 tools/e2e/run.py --flows B C
python3 tools/e2e/run.py --online
python3 tools/e2e/run.py --maven-repo /path/to/offline-repository
python3 tools/e2e/run.py --diagnose
```

- 默认离线。POM 锁定 Surefire 3.5.4、JaCoCo 0.8.12、JUnit 5.12.2。`--online` 允许下载 Maven 依赖，不会给项目编写 ArchUnit 规则或安装其他质量工具。
- 缺 JDK/Maven 时停止；依赖缺失、真实构建失败时记录失败。某一流程失败后继续另外两条独立流程。
- 默认遇到非预期结果即停止该流程，最终退出 1；全部符合预期才退出 0。
- `--diagnose` 仅作用于脚本新建的 A 项目。记录原始失败后，模拟 UserPromptSubmit 口令并调用 waive，以探查后续阶段。任何诊断偏差都会让最终退出码保持 1。B 中的放行则是用例本身的预期行为。
- 报告按插件 `templates/reports/` 生成协议测试输入，明确标注“不是独立 agent 实际评审结果”。测试、构建和覆盖率报告由 Maven/Surefire/JaCoCo 真实产生。
- `fixtures/` 中的 markdown 是插件模板填写后的具体样例。implementation-log 的固定测试数量与覆盖率在写入前由脚本核对真实 XML；模板变动时需要同步这些样例。

脚本打印证据目录，保留 `steps.json`（完整输出和 stdin）、`steps.md`（逐步关键输出）、`summary.json`、真实 RED/GREEN 测试 XML、JaCoCo XML，以及三个 git 项目。git 统一经 `gitutil.git()`，记录的失败码是包装器的 1，诊断中保留 git hook 的拒绝原因。

本次实测摘要在 [evidence/2026-09-27.md](evidence/2026-09-27.md)，问题分析在 [联调报告](../../docs/dev/e2e-report.md)。Windows 验证延后，Linux 本轮未实测。
