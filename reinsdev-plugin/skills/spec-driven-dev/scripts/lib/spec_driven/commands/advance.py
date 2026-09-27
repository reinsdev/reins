"""`spec-driven advance`. Owner: T2. Close the current phase and move on: run the
phase's gates (6 also runs 6.5 and 6.7); on pass mark it passed, mark conditional
phases the tier / mode skips, and open the next phase. WARN needs --ack-warn,
given only after the user chose to continue."""

from .. import config, gates, locate, meta, router
from ..errors import BLOCK, ERROR, OK, WARN
from ..project import Project


def register(sub):
    p = sub.add_parser("advance", help="当前 Phase 过门后进入下一个 Phase")
    p.add_argument("--change")
    p.add_argument("--ack-warn", action="store_true", help="用户已确认接受告警")


def run(a) -> int:
    project = Project.here()
    change, change_dir, m = locate.load(project, a.change)
    cfg = config.load(project)
    current = m["phase"]
    worst = OK
    for g in router.gates_of(current):
        ctx = gates.GateContext(project, change, change_dir, m, cfg)
        try:
            findings, code = gates.evaluate(g, ctx)
        except NotImplementedError:
            print("reins: gate-%s 尚未实现（该能力不可用），不能推进" % g)
            return ERROR
        print(gates.render(g, findings, code))
        worst = max(worst, code)
    if worst == BLOCK:
        print("Phase %s 未通过，修完后再推进" % current)
        return BLOCK
    if worst == WARN and not a.ack_warn:
        print("Phase %s 有告警：把告警告诉用户，用户决定继续后加 --ack-warn 再推进" % current)
        return WARN

    moved = {}

    def apply(md):
        status = md["phaseStatus"]
        status[current] = "passed"
        skipped = []
        nxt = router.next_phase(md, cfg)
        while nxt and router.skip_reason(nxt, md):
            status[nxt] = "skipped"
            md["skipped"][nxt] = router.skip_reason(nxt, md)
            skipped.append(nxt)
            nxt = router.next_phase(md, cfg)
        if nxt:
            md["phase"] = nxt
            status[nxt] = "in_progress"
        if not router.stale_phases(md):
            md["staleFrom"] = None
        moved.update(next=nxt, skipped=skipped)

    m = meta.update(change_dir, apply)
    parts = ["Phase %s 通过" % current]
    if moved["skipped"]:
        parts.append("跳过 Phase %s" % "、".join("%s（%s）" % (p, m["skipped"][p]) for p in moved["skipped"]))
    parts.append("下一步 Phase %s：%s" % (moved["next"], router.ACTIONS[moved["next"]])
                 if moved["next"] else "全部完成")
    print("；".join(parts))
    return OK
