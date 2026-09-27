# Phase 0：启动

进入条件：用户明确提出新需求或缺陷，且已确认不是恢复现有 change。产出由 CLI 创建：change 目录、proposal 骨架、状态和分支绑定。

1. 确认项目是 Git 仓库，项目或上级有 Maven / Gradle 构建文件。非 Java 项目说明适用边界并停止。
2. feature 使用用户确认的 kebab-case 名称，至少 5 个字符；bugfix 使用 fix-<YYYYMMDD>-<slug> 并让用户确认。
3. 调用当前 mode 的命令；初始档位不替用户确认。

```text
<spec-driven-dev skill 目录>/scripts/spec-driven new <change> --mode feature
<spec-driven-dev skill 目录>/scripts/spec-driven new <change> --mode bugfix
```

两个命令择一执行。CLI 负责元数据、分支和 git hooks；失败不手工补造半套目录。用户已指定独立工作分支时可按 new --help 使用 --no-branch，保留已有分支。

4. 已有 Java 项目需质量基线时，先解释配置和基线用途，通过 CLI 的 init-config --java --dry-run 展示计划；用户同意接入后去掉 --dry-run。不可为通过后续门而扩大存量基线。
5. 读取 CLI 的 gate 0 结果；命令未返回明确结果时再执行以下命令。

```text
<spec-driven-dev skill 目录>/scripts/spec-driven gate 0 --change <change>
```

结束：按总控退出码表处理，重读状态后进入 Phase 1。

## 首次接入质量工具

首次接入先运行 `<spec-driven-dev skill 目录>/scripts/spec-driven quality setup --dry-run` 展示 pom、架构测试和配置差异。用户同意改 pom 后执行 `quality setup`；默认离线写入返回 2，表示依赖缓存尚未验证。用户也同意联网时执行 `quality setup --online` 预热，再执行 `init-config --java` 建基线。已有明确授权不重复询问。

包名和 JUnit 无法确定时，用用户确认的 `--base-package`、`--junit 4|5` 重试。有 SQL 时确认 JDBC 方言候选，再用 `--sql-dialect` 生成团队 `.sqlfluff`；已有配置只列差异。SQLFluff 未安装时解释安装方法，不擅自安装。Gradle 自动接入暂不支持，按 CLI 提示完成手工接入。
