"""`spec-driven scope set | show`. Owner: T11. bugfix scope assessment (architecture.md §4.5).

Written in Phase 1 after the user confirmed bugfix-analysis; router.skip_reason reads it
to skip Phase 2 / 3. To change it later, roll back to Phase 1 first.
"""

from .. import locate, meta, router
from ..errors import OK, fail
from ..project import Project


def register(sub):
    p = sub.add_parser("scope", help="bugfix 改动范围评估，决定 Phase 2 / 3 是否跳过")
    p.add_argument("action", choices=["set", "show"])
    p.add_argument("--files", type=int, help="预计改动的文件数")
    p.add_argument("--cross-service", action="store_true")
    p.add_argument("--ddl", action="store_true")
    p.add_argument("--public-api", action="store_true")
    p.add_argument("--change")


def _describe(m: dict) -> None:
    scope = m.get("bugfixScope")
    if not isinstance(scope, dict):
        print("尚未评估改动范围：Phase 2、3 都会执行")
        return
    print("改动范围：%d 个文件%s%s%s" % (scope.get("files") or 0, "，跨服务" if scope.get("crossService") else "",
          "，改 DDL" if scope.get("ddl") else "", "，改公开 API" if scope.get("publicApi") else ""))
    for phase in ("2", "3"):
        reason = router.skip_reason(phase, m)
        print("Phase %s：%s" % (phase, "跳过（%s）" % reason if reason else "执行"))


def run(a) -> int:
    project = Project.here()
    change, change_dir, m = locate.load(project, a.change)
    if a.action == "show":
        _describe(m)
        return OK
    if m["mode"] != "bugfix":
        fail("改动范围评估只用于 bugfix 模式")
    if m["phase"] != "1":
        fail("改动范围只能在 Phase 1 评估，当前在 Phase %s；要修改请先回退到 Phase 1" % m["phase"])
    if a.files is None or a.files < 0:
        fail("scope set 需要 --files <预计改动的文件数>")
    scope = {"files": a.files, "crossService": a.cross_service, "ddl": a.ddl, "publicApi": a.public_api}
    m = meta.update(change_dir, lambda md: md.__setitem__("bugfixScope", scope))
    _describe(m)
    return OK
