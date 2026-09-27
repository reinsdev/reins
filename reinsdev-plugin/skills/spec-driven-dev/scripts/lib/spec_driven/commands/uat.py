"""`spec-driven uat accept | reject`. Owner: T11. Phase 8.9 user acceptance (architecture.md §4.5).

accept needs the grant the user issued by typing 「确认验收 <change>」; the grant is bound to
the content of spec.md and qa-report.md at that moment, so a later change needs a new
confirmation. In a real terminal (TTY) the user may instead type the change name.
reject needs no grant: it records the user's reason and rolls back like `retry`.
"""

import datetime

from .. import gitutil, grants, locate, meta, retro
from ..errors import OK, fail
from ..project import Project
from .retry import check_rollback, report, rollback
from .waive import _tty_confirm


def register(sub):
    p = sub.add_parser("uat", help="Phase 8.9 用户验收：accept 需用户输入口令授权；reject 回退修改")
    p.add_argument("action", choices=["accept", "reject"])
    p.add_argument("--phase", help="reject：回退到的 Phase")
    p.add_argument("--reason", help="reject：用户要修改的内容（用户原话）")
    p.add_argument("--change")


def run(a) -> int:
    project = Project.here()
    change, change_dir, m = locate.load(project, a.change)
    if m["phase"] != "8.9":
        fail("用户验收只在 Phase 8.9 进行，当前在 Phase %s" % m["phase"])
    confirmer = gitutil.user_name(project.root)
    if a.action == "reject":
        if not a.phase:
            fail("uat reject 需要 --phase：用户指出要回到哪个 Phase 修改")
        check_rollback(m, a.phase, a.reason)
        retro.append_uat(change_dir, "需要修改（回退到 Phase %s）" % a.phase, a.reason.strip(), confirmer)
        report(a.phase, rollback(change_dir, a.phase, a.reason))
        return OK
    if m.get("uatAccepted"):
        print("%s 已经验收通过（%s）" % (change, m.get("uatAcceptedAt")))
        return OK
    fingerprint = grants.uat_fingerprint(change_dir)
    if not grants.consume(project.root, change, "uat", "accept", fingerprint) and not _tty_confirm(change):
        fail("没有有效的验收授权：请用户本人在对话里原样输入「确认验收 %s」（%d 分钟内有效；"
             "确认后 spec.md、qa-report.md 若有改动需重新确认），再执行本命令" % (change, grants.TTL // 60))
    retro.append_uat(change_dir, "通过", "", confirmer)
    accepted_at = datetime.datetime.now().isoformat(timespec="seconds")
    meta.update(change_dir, lambda md: md.update(uatAccepted=True, uatAcceptedAt=accepted_at))
    print("已记录 %s 用户验收通过。下一步：advance 进入归档" % change)
    return OK
