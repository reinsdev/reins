# T13 端到端联调报告

执行者：Json。日期：2026-09-27。开发分支：`task/T13-Json`。实测插件基线：`26c14ed20b39394618c42c81c348b98397d23f94`。交付前已 rebase 到 `97d5a75`；新增的是任务书与 T8 skill 说明，CLI 脚本和工件模板与实测基线相同。

## 结论

**B、C 符合预期；A 尚不能无额外放行走通。** A 在 gate 4 被卡住；诊断放行后，真实 RED/GREEN、gate 6、gate 6.5、code review 格式、部署跳过、用户验收/拒绝、归档均已执行。gate 6.7 因质量工具前提不满足而拦截。另复现了 git hook 拒绝 CLI 合法更新 tasks.md 的问题。

没有修改 T1–T11 的代码。没有手写 Surefire、JaCoCo 或静态分析报告，没有编辑 `.meta.json`、`retrospective.md`，没有关闭 git hook。所有用户口令都是用户授权的临时项目联调模拟，经 UserPromptSubmit JSON stdin 进入 CLI。评审报告是协议样例，不是实际 AI 独立评审结论。

## 环境与复跑

| 项 | 实测 |
| --- | --- |
| 系统 | macOS 26.4 / arm64 |
| Python | 3.9.6；脚本仅用 Python 3.8 标准库与语法 |
| JDK | OpenJDK 17.0.19 |
| Maven | 3.9.15 |
| 测试依赖 | JUnit 5.12.2、Surefire 3.5.4、JaCoCo 0.8.12 |
| 项目 | 一个 Points 业务类、一个 PointsTest 单测；真实 Maven POM |
| AI 平台 | 未启动；仅执行已安装的 `claude plugin validate` 清单校验 |
| Windows | 延后 |
| Linux / Python 3.8 解释器 | 本轮未实测 |

本机最初缺少 JaCoCo 缓存。用户明确授权联网后，用真实 `mvn -B verify` 下载 JaCoCo 及其依赖并成功构建。正式记录使用离线模式；默认质量命令本身也带 `-o`，没有在线下载质量工具。

```sh
# 在本分支仓库根目录执行
python3 tools/e2e/run.py                 # 原始路径；A 卡在 gate 4，仍继续 B/C；退出 1
python3 tools/e2e/run.py --diagnose      # 记录阻塞并诊断推进 A；最终仍退出 1
python3 tools/e2e/run.py --flows B C     # 独立运行 B/C
```

依赖尚未缓存时，可显式加 `--online`；离线仓库可用 `--maven-repo <路径>`。缺 JDK/Maven 会停止，不以假报告替代。

- [脚本及说明](../../tools/e2e/README.md)
- [168 步命令、退出码、关键输出、预期对照](../../tools/e2e/evidence/2026-09-27.md)
- 诊断运行完整证据：`/var/folders/yf/z2wzgghd0s329mrdskwdbm9h0000gn/T/reins-e2e-bko4ms3s`。
- 严格运行完整证据：`/var/folders/yf/z2wzgghd0s329mrdskwdbm9h0000gn/T/reins-e2e-yv9ynq50`。

每个证据目录保留 `steps.json`、`steps.md`、`summary.json` 和三个 git 项目。诊断目录还保存 RED/GREEN 原始 Surefire XML 和 JaCoCo XML。`REINS_HOME` 在证据目录内。仓库内证据表使用 `$REPO`、`$RUN`、`$M2` 代替本机路径，其余关键输出来自实际运行。

## 各流程结果

| 流程 | 实际结果 |
| --- | --- |
| A：S feature | new 后处于 0，advance 到 1；选 S 后 advance 跳过 2/3 到 4。gate 4 拦截，见 E2E-01。仅诊断模式放行 task-link/task-sources 后进入 6、跳过 5。 |
| A：TDD 与 hook | RED 真实运行 1 个测试、失败 1；GREEN 运行 1、失败 0、错误 0、跳过 0，完整构建成功。缺 Task-Id 提交被拒，补齐 trailer 成功。RED 不勾选，GREEN 经 tasks-sync --apply 勾选。保存勾选被 hook 拒绝，见 E2E-02。 |
| A：实现门 | 改动的 Points.java 第 5 行有真实 JaCoCo 指令覆盖，增量覆盖率 100%；gate 6 和 6.5 返回 0。init-config 返回 1，gate 6.7 返回 3，见 E2E-03。 |
| A：收尾 | 仅诊断模式放行 quality-baseline/quality-config 后进入 8、跳过 7。报告格式过门进入 8.5；deploy skip 进入 8.9。未授权 uat accept 返回 1，口令授权后成功。uat reject --phase 8 撤销验收；重新评审保留部署跳过决定，直接回到 8.9。再次授权验收后 advance 到 9，archive --dry-run/正式归档及归档提交成功。 |
| B：M feature | 真实 CLI 依次走 0→1→2→3→4→5；design set 与最终选择一致，spec 的 SC 关联 AC，tasks 关联 SC。预设一条 BLOCK 使 gate 5 和 advance 返回 3、阶段保持 5。无授权 waive 返回 1；prompt-submit 授权后 waive/gate 5 返回 0、显示 WAIVED，再 advance 到 6。 |
| C：bugfix | new --mode bugfix 后 advance 到 1；scope set --files 3 --public-api 时 2/3 不跳过；改为 --files 2、无跨服务/DDL/API 时 advance 到 4，2/3 有跳过理由。离开 Phase 1 再 scope set 返回 1。 |

A 归档目录为 `.openspec/changes/archive/2026-09-27-points-a/`，归档后 `status` 输出没有进行中的 change。S 未生成 spec/design，因此这里只验证了无 delta 的归档及 specs 索引生成；没有声称验证 M/L 的 delta 合并或 ADR 蒸馏。

## E2E-01：S 跳过 spec，但 gate 4 仍强制 SC

- **判断归属：T3 为主，T1/T8 协同。阻断正常流程。**
- 现象：S 路由正确跳过 2/3，未产生 spec.md；tasks.md 用已有 AC-1 关联时，gate 4 报 `task-sources` 和 `task-link`。模板也只描述 SC 和 bugfix 修改点，没有 S feature 的 AC 关联约定。
- 复现：`python3 tools/e2e/run.py --flows A`。填写 proposal，`complexity set S`，`advance` 到 4，填 tasks，再 `advance`。退出 3。
- 关键输出：`spec.md 无法读取或解析任务关联来源`；`每个任务须关联已定义的 SC；bugfix 跳过 spec 时关联修改点`。
- 证据：逐步记录第 26 步。B 使用真实 spec/SC 的相同任务结构可通过，说明冲突位于 S 路由与任务来源要求之间。
- 建议协调：明确 S feature 的关联来源，统一 T3 gate 与 T1 模板、T8 总控说明。T13 不擅自修改契约或用虚构 SC 过门。

## E2E-02：git hook 拒绝 tasks-sync 产生的合法勾选

- **判断归属：T6 为主，与 T2 tasks-sync 接口衔接。阻断正常提交。**
- 现象：GREEN 提交带 `Task-Id: T1` 后，`tasks-sync --apply` 正确把 T1 改为 `[x]`；仍在 Phase 6 时，仅暂存 `.openspec` 并提交，pre-commit 却按 Phase 4 冻结规则拒绝 tasks.md。
- 复现：`python3 tools/e2e/run.py --flows A --diagnose`。第 49–52 步为同步、核对、暂存、提交。git 调用经 gitutil，包装器退出 1。
- 关键输出：`tasks.md 属于 Phase 4，已冻结（当前 Phase 6）；要改请先回退`。
- 判断依据：tasks.md 的变化由 CLI 从真实 GREEN trailer 生成，没有手动勾选。另一次在 Phase 9 保存同一更新也被拒绝；问题不是缺少 Task-Id。
- 建议协调：让冻结校验识别合法的机器勾选更新，同时保留对任务正文篡改的保护。诊断只保留失败的暂存内容继续探查；未使用 `--no-verify` 或移除 hook。最后归档后提交成功不代表此问题修复。

## E2E-03：最小 Maven 项目不能直接完成质量初始化

- **判断归属：T5 初始化前提/诊断信息，T8 接入说明协同。属于环境前提与文档承诺缺口，不认定 fail-closed 本身是 bug。**
- 现象：`init-config --java --dry-run` 返回 0、未写配置；正式命令返回 1、没有写有效基线。随后的 advance 中 gate 6/6.5 通过，6.7 以 quality-baseline/quality-config 拦截。
- 复现：诊断脚本第 55–63 步。项目已经能真实执行 Surefire/JaCoCo，但没有 ArchUnit 测试，也没有 Checkstyle/PMD/SpotBugs 的项目配置和完整离线缓存。
- 对预览给出的命令单独重跑，得到：`mvn -o -q test '-Dtest=*Arch*' ...` 无匹配测试；`checkstyle:checkstyle`、`pmd:pmd` 无可解析插件版本；`spotbugs:spotbugs` 无可解析前缀。均退出 1。
- 影响：只配置 Surefire/JaCoCo 不足以让 6.7 通过。`--online` 可下载示例构建依赖，但不替项目编写 ArchUnit 规则，且 CLI 默认质量命令带 `-o`。
- 建议协调：给出完整质量接入前提、规则/插件版本配置示例，以及能定位到原始命令日志的初始化错误提示。README/验证手册已据实说明。没有用普通单测冒充 ArchUnit，也没有填空 XML 冒充质量结果。
- 诊断时只模拟放行缺失配置/基线以检查后续状态转换；静态报告仍明确列出“执行失败”。**本轮未验证真实静态质量工具全通过、基线初始化成功和质量债务比较。**

## E2E-04：文档与现有 CLI 不一致

- **判断归属：T8 总控说明协调，公共工作流文档由协调者维护。**
- 已更新 README.md、docs/verification.md：删除建 change 不可用、hook 只有探针、内部 CLI 只有 status/hook、放行只能终端确认等过时说法；补齐 advance、用户决策、完整口令、git hook、报告表格、init-config 前提和复跑方式。
- 仍需协调者更新 `spec-driven-workflow.md`：旧 `new-change.sh` / `archive-change.sh` 等脚本入口、`tasks-sync --write`（实际为 `--apply`）、验收直接写状态、feature 不分档必走 2/3 等内容。T13 未修改该任务未授权的共享文档。

## 交付检查与边界

- `python3 -m unittest discover -s tests -t .`：346 项通过，Python 3.9.6。
- `claude plugin validate reinsdev-plugin`：Validation passed。
- 严格脚本：退出 1，A 在原始 gate 4 拦截；B/C 完成。
- 诊断脚本：168 步，A/B/C 都走到设定终点，4 个原始非预期步骤，最终退出 1。两个产品衔接问题和一个质量接入前提未被掩盖。
- 未完成：A 无额外放行的全链通过；真实静态质量初始化成功；AI 平台会话/独立 agent 行为；Windows 验证延后。
- 契约或共享文件待改：S 任务关联契约；T6 与 T2 的合法勾选更新识别；由协调者分派修复，T13 未改插件代码。
- 需要更新的文档：README 与验证手册已完成；公共 `spec-driven-workflow.md` 的剩余漂移见 E2E-04。最新任务书提到协调者将转交 T14 多实例说明，本轮尚未收到该文字，未把未验证的多实例行为写成保证。
