"""`spec-driven retro add`. Owner: T6. Append an item to retrospective.md 待优化清单."""

from .. import locate, retro
from ..errors import OK, fail
from ..project import Project


def register(sub):
    p = sub.add_parser("retro", help="retrospective.md 留痕")
    p.add_argument("action", choices=["add"])
    p.add_argument("text")
    p.add_argument("--source", default="manual")
    p.add_argument("--change")


def run(a) -> int:
    project = Project.here()
    change, change_dir, _ = locate.load(project, a.change)
    if not a.text.strip():
        fail("内容不能为空")
    retro.add_todo(change_dir, a.source, a.text.strip())
    print("已记入 %s 的待优化清单" % change)
    return OK
