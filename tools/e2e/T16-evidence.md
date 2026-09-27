# T16 质量工具接入验证

执行人 Json。环境：macOS、JDK 17.0.19、Maven 3.9.15。未启动 AI 平台；Java XML 报告均由真实 Maven 插件生成。Windows 验证延后；Linux 未实测。

## 可重复执行

```sh
python3 tools/e2e/run.py --flows Q Q4 --online
python3 tools/e2e/check_sqlfluff.py --sqlfluff /path/to/sqlfluff
```

Q 为 JUnit 5.12.2，Q4 为 JUnit 4.13.2。首次下载需联网；之后可去掉 `--online` 使用缓存。脚本输出独立临时目录，逐步记录命令、stdin、退出码和输出。

## 实测结果

| 步骤 | Q / Q4 结果 |
| --- | --- |
| `quality setup --dry-run` | 0，展示具体改动 |
| `quality setup --online` | 0，生成 ArchUnit 测试及完整坐标命令，实际预热四项工具 |
| 再次离线 setup | 2，pom、配置、测试字节相同；明确缓存未验证 |
| `init-config --java` | 0，生成真实质量基线 |
| `gate 6.7` | 0 |
| 新增 `Bad_variable` 后 `gate 6.7 --json` | 3，包含 Checkstyle BLOCK |
| 恢复源码后 `gate 6.7` | 0 |
| Domain 调用 Adapter 后 `gate 6.7 --json` | 3，包含 ArchUnit BLOCK |

首次实测完整证据位于本机临时目录：Q 为 `reins-e2e-6kzlpdud`，Q4 为 `reins-e2e-zxfw9soj`。这两次执行均退出 0，无诊断放行；完整目录由运行输出给出，不作为跨机器依赖。

SQLFluff 3.4.2 真实验证：MyBatis `#{id,jdbcType=BIGINT}`、`?` 和不带 AS 的别名返回 0；CP01、AM04、RF02 示例返回 1；超过 120 字符只产生 `warning: true` 的 LT05，返回 0。证据目录 `reins-sqlfluff-ll3cqigr`。单元测试不安装或调用 SQLFluff。

## 版本和参数依据

| 工具 | 生成的配置 | 实测依据 |
| --- | --- | --- |
| ArchUnit 1.3.0 | test scope 的 archunit-junit4 / archunit-junit5 | 两套真实 JUnit 项目均通过基线及新增违规测试 |
| Checkstyle Maven 3.6.0 | 完整坐标 `:checkstyle`，`-Dcheckstyle.config.location=google_checks.xml` | 输出含 Google 规则违规的 XML，命令返回 0；gate 单独拦截新增违规 |
| PMD Maven 3.26.0 | 完整坐标 `:pmd`，插件内置规则 | 实际生成 `target/pmd.xml`，命令返回 0 |
| SpotBugs Maven 4.9.3.0 | `test-compile` 和完整坐标 `:spotbugs`，`-Dspotbugs.xmlOutput=true` | 实际生成 `target/spotbugsXml.xml`，命令返回 0 |

Checkstyle、PMD、SpotBugs 使用报告目标，默认不会因为报告中存在违规而终止构建；真实执行错误仍失败。没有传入不存在的 `-Dpmd.rulesets` 或把执行错误设为忽略。参考 [Checkstyle report goal](https://maven.apache.org/plugins/maven-checkstyle-plugin/checkstyle-mojo.html)、[PMD 3.26.0 report goal](https://maven.apache.org/plugins-archives/maven-pmd-plugin-3.26.0/pmd-mojo.html)、[SpotBugs report goal](https://spotbugs.github.io/spotbugs-maven-plugin/spotbugs-mojo.html)。

## 契约衔接与边界

现有 `java.FREEZE_KEYS` 使用 `archunit_freeze.*`，ArchUnit 本身识别 `archunit.freeze.*`。生成模板在测试内将前者映射到后者，默认全部 false；初始化时由现有 CLI 明确设置 true。冻结存储为 `.openspec/archunit-store/<模块>`。此兼容处理已由真实门验证，未修改 T15 的 `java.py`、`init_config.py`、`g6_7.py`。协调者可后续统一属性契约，届时应同步模板。参见 [ArchUnit 冻结规则文档](https://www.archunit.org/userguide/html/000_Index.html#_freezing_arch_rules)。

SQLFluff 规则集：CP01 大写；CP02–CP04 consistent；AM04、RF02；LT05 上限 120 且仅 warnings；关闭 AL01、AL02、LT02。使用 placeholder 自定义表达式同时识别 MyBatis 参数与提取后的问号，按位置替换为示例值。已有 `.sqlfluff` 仅列差异；无 SQL 不生成文件。SQL 提取、告警以及存量数量比较由 T20 完成，T16 没有改对应 gate。参考 [规则配置](https://docs.sqlfluff.com/en/stable/configuration/rule_configuration.html)及 [placeholder 配置](https://docs.sqlfluff.com/en/stable/configuration/templating/placeholder.html)。

Gradle 自动接入暂不支持，明确返回 1 并给出手工步骤。条件模块、包名或 JUnit 不确定会停止，不猜测。多模块依赖需要项目本身能被 Maven 正常构建；已有团队命令不会被替换。预热失败恢复本次管理的 pom、配置及新测试，保留构建输出和日志供定位。

完整 unittest 首轮：Python 3.8 与 3.12 各 370 项通过；插件 manifest 验证通过。T16 的 24 项测试覆盖插入、幂等、离线、失败恢复、确认参数、多模块及 SQL 配置。
