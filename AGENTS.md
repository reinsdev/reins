# Reins 开发规约

本文件是所有参与开发的 agent（Claude Code、Codex 等）必须遵守的规约。开工前先读完本文件和你的任务书（`docs/dev/tasks.md` 中你的任务一节），再读 `docs/dev/architecture.md`（整体架构与接口契约）。

## 1. 先弄清三件事

- **你是哪个任务**：`T1`…`T10`，见 `docs/dev/tasks.md`。只做任务书范围内的事。
- **你拥有哪些文件**：任务书的「拥有的文件」列表。**只改这些文件**，外加你新建的测试和 fixture。
- **你依赖哪些接口**：函数签名和 docstring 就是契约，写在各模块里，汇总在 `docs/dev/architecture.md`。按契约编程，不要去读或改别的任务的实现细节。

## 2. 文件归属与共享文件

- **T0（契约层，协调者维护）的文件不许改**：`cli.py`、`commands/__init__.py`、`gates/__init__.py`、`policies/__init__.py`、`errors.py`、`project.py`、`config.py`、`tests/test_contracts.py`、`AGENTS.md`、`CLAUDE.md`、`docs/dev/*`。需要改契约时：**停下来**，在交付说明里写明要改什么、为什么，由协调者改。
- 例外，只允许追加、不许改已有内容：
  - `config.py` 的 `DEFAULTS`：新增配置键和默认值，并在交付说明里列出。
  - `project.py`：新增工件文件名常量。
  - `hook.py` 的 `normalize()`：T6 可以新增事件字段（如子 agent 身份）。
- 别的任务拥有的文件，哪怕只改一个字也不行。发现别人的 bug：在交付说明里写清楚复现方法，不要顺手修。
- README、验证手册、设计文档由协调者统一更新。你的改动需要更新文档时，在交付说明里写「需要更新的文档」。

## 3. Python 代码

- **只用 Python 3.8 标准库**，不引入任何第三方包。CI 在 3.8 上跑，以下 3.9+ 写法一律不用：`list[str]` / `dict[str, int]` 这类内置泛型（用 `typing.List` 等）、`X | Y` 联合类型、`str.removeprefix`、`match` 语句、`zoneinfo`。
- 风格照抄现有代码：字符串格式化用 `%`；docstring 和注释用英文，简短，说「为什么」；用户可见的输出用中文。
- 文件读写一律显式 `encoding="utf-8"`；读时兼容 CRLF；写出的路径用正斜杠、相对项目根或 change 目录。
- 路径用 `pathlib`；子进程用参数列表，禁止 `shell=True`；**git 只经 `gitutil.git()` 调用**。
- 预期内的失败用 `errors.fail("...")`，不许把 traceback 抛给用户。未实现的能力返回 `errors.unavailable(name)`。
- 不访问网络。只写这些位置：项目的 `.openspec/`、项目源码（仅 T2 建分支、T7 `git mv` 等任务书明确的操作）、`REINS_HOME`（默认 `~/.reins`）。
- 两条失败方向不能反：
  - **gate 失败即拦截（fail closed）**：拿不准、解析失败、文件缺失 → BLOCK，并写清原因。
  - **hook 失败即放行（fail open）**：policy 抛异常由链路记录后放行，不能把用户锁死。
- gate 模块只返回 `Finding` 列表：**不打印、不退出、不写文件、不读 retrospective.md 和 .config.json**（框架负责）。`Finding.check` 用稳定的 kebab-case 编号；`evidence` 只放决定是否同一问题的内容，**不含行号**。
- 解析 markdown 一律调用 `mdparse`，不许在 gate 里自己写正则找标题或 ID。需要新的章节别名，向 T1 提（交付说明里写），期间在测试里用 T1 模板中的标题。

## 4. Markdown 工件、skill 与 agent

- 工件格式（标题、ID、表格列名）的唯一来源：`spec-driven-workflow.md` 和 T1 维护的 `reinsdev-plugin/skills/spec-driven-dev/templates/`。不许自创格式；写 skill 的任务（T8、T9）和写 gate 的任务（T3–T5、T7）都以模板为准。
- skill / agent 的 frontmatter 只用 `frontmatter.py` 支持的子集（`key: 标量`、`key: [a, b]`、块列表）。
- skill 里让模型调用 CLI 时写 `<spec-driven-dev skill 目录>/scripts/spec-driven <命令>`。**永远不要让模型直接编辑 `.meta.json`、`retrospective.md`**，也不要让模型代替用户做放行、降档、验收决定。
- 用户在会话里只接触 `/spec`、`/bugfix`、`/waive`；skill 的对话文案里不要让用户去敲 `spec-driven`。安装相关的事只提 `reinsdev`。
- 文案用中文，短句，一句一个意思。

## 5. 测试

- 用 `unittest`，放在 `tests/test_<你的模块>.py`；fixture 放在 `tests/fixtures/<任务编号小写>/`（如 `tests/fixtures/t3/`）。
- 测试在临时目录里建项目，**不依赖真实的 claude / codex / opencode，不联网，不改 `~/.reins`**（设置 `REINS_HOME` 到临时目录）。需要 git 时在临时目录 `git init`，并设 `user.name` / `user.email`。
- 每个 gate 的每个 `check` 至少一组「合格 / 不合格」fixture；每个 policy 至少覆盖「拦截 / 放行 / 异常输入」。
- 必须在 macOS、Linux、Windows 上都能过：不用符号链接，不依赖文件权限位，不假设路径分隔符。

## 6. 交付

- 在自己的分支上开发：`task/T<n>-<简短英文名>`，建议每个任务一个 git worktree，避免互相踩文件。
- 提交信息：**第一行以你的 agent 名字开头**，格式 `<agent 名字>: T<n>: <做了什么>`，例如 `Claude: T0: 新增 gate 框架`。agent 名字由协调者分配，开工时会告诉你；不知道自己的名字就先问，不要自己起。一次提交一件事。
- 交付前必须全部通过：
  ```sh
  python3 -m unittest discover -s tests -t .
  claude plugin validate reinsdev-plugin   # 装了 claude 时
  ```
- 交付前 rebase 到最新的开发主干（`feature/dev_0.1`），解决冲突时**只保留自己文件的改动**。
- 交付说明（PR 描述或最后一条消息）写四项：完成了什么、没完成什么、契约或共享文件需要的改动、需要更新的文档。
