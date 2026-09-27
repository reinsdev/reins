"""`spec-driven deploy skip`. Owner: T11. Phase 8.5 skipped by user choice (architecture.md §4.5).
No grant: deployment acceptance is optional by design (the controller asks y / n / skip)."""

from .. import gitutil, locate, meta, retro, router
from ..errors import OK, fail
from ..project import Project


def register(sub):
    p = sub.add_parser("deploy", help="Phase 8.5 部署验收：用户选择跳过")
    p.add_argument("action", choices=["skip"])
    p.add_argument("--reason", required=True, help="用户的理由（用户原话）")
    p.add_argument("--change")


def run(a) -> int:
    project = Project.here()
    change, change_dir, m = locate.load(project, a.change)
    if m["phase"] != "8.5":
        fail("只能在 Phase 8.5 跳过部署验收，当前在 Phase %s" % m["phase"])
    reason = a.reason.strip()
    if not reason:
        fail("--reason 不能为空：理由只能来自用户")
    retro.append_deploy(change_dir, "跳过", reason, gitutil.user_name(project.root))
    moved = {}

    def apply(md):
        md["phaseStatus"]["8.5"] = "skipped"
        md["skipped"]["8.5"] = "用户选择跳过部署验收：%s" % reason
        nxt = router.next_phase(md, {})
        if nxt:
            md["phase"] = nxt
            md["phaseStatus"][nxt] = "in_progress"
        moved["next"] = nxt

    meta.update(change_dir, apply)
    print("已跳过部署验收，记入 retrospective。下一步 Phase %s：%s" % (moved["next"], router.ACTIONS.get(moved["next"], "")))
    return OK
