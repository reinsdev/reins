"""`spec-driven quality setup`. Owner: T16. Bring a Maven / Gradle project up to what gate 6.7
needs (ArchUnit test dependency and rules, Checkstyle / PMD / SpotBugs commands), so that
`init-config --java` can run the checks and build the baseline. See docs/dev/tasks.md T16."""

import json
import xml.etree.ElementTree as ET

from .. import java_setup
from ..errors import fail
from ..project import Project


def register(sub):
    p = sub.add_parser("quality", help="接入质量检查工具（ArchUnit、Checkstyle、PMD、SpotBugs）")
    p.add_argument("action", choices=["setup", "show"])
    p.add_argument("--dry-run", action="store_true", help="只列出将要做的修改")
    p.add_argument("--online", action="store_true", help="允许联网下载插件和依赖并预热本地仓库")
    p.add_argument("--base-package", help="用户明确确认的基础包（适用于选中的所有 Java 模块）")
    p.add_argument("--junit", choices=["4", "5"], help="无法自动识别时，用户明确确认的 JUnit 版本")


def run(a) -> int:
    root = Project.here().root
    try:
        if a.action == "show":
            print(json.dumps(java_setup.load_config(root).get("quality", {}), ensure_ascii=False, indent=2))
            return 0
        planned = java_setup.plan(root, a.base_package, a.junit)
        print(planned.render())
        if a.dry_run:
            print("只读预览完成，未写文件、未联网。")
            return 0
        java_setup.apply(planned, online=a.online)
        if not a.online:
            print("已写入接入文件，未联网、未验证完整依赖缓存。缺少依赖时需用户同意后执行 quality setup --online 预热，再 init-config --java 建基线。")
            return 2
        print("Maven 插件及依赖预热完成；尚未建立质量基线。下一步执行 init-config --java。")
        return 0
    except (OSError, ValueError, RuntimeError, ET.ParseError) as exc:
        fail("质量接入失败：%s" % exc)
