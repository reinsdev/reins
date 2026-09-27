"""`spec-driven tasks-sync`. Owner: T2. Render tasks.md checkboxes from Task-Id
trailers (workflow §10.5); prints the changes, writes only with --apply."""

from .. import locate, taskstate
from .. import project as P
from ..errors import OK, fail
from ..project import Project


def register(sub):
    p = sub.add_parser("tasks-sync", help="按 Task-Id trailer 同步 tasks.md 勾选")
    p.add_argument("--apply", action="store_true")
    p.add_argument("--change")


def run(a) -> int:
    project = Project.here()
    change, change_dir, m = locate.load(project, a.change)
    path = change_dir / P.TASKS
    if not path.is_file():
        fail("还没有 tasks.md")
    text = path.read_text(encoding="utf-8")
    done = taskstate.done_tasks(project, m)
    new = taskstate.render(text, done)
    changed = [(o, n) for o, n in zip(text.splitlines(), new.splitlines()) if o != n]
    for old, now in changed:
        print("- %s\n+ %s" % (old.strip(), now.strip()))
    open_ids = taskstate.open_tasks(text, done)
    print("完成 %d 个任务，未完成 %s" % (len(done), "、".join(open_ids) or "无"))
    if changed and a.apply:
        path.write_bytes(new.encode("utf-8"))
        print("已更新 tasks.md")
    elif changed:
        print("以上为预览，加 --apply 写入")
    return OK
