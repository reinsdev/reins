"""`spec-driven complexity`. Owner: T2. The tier channel (workflow §2.4, design doc §3.2):
  show      recommended tier with reasons (tiering.recommend)
  set       select (first time) or raise the tier; lowering needs --downgrade and a grant
            the user issued by typing 「确认降档 <change> <档位>」
  recheck   Phase 2 / 3 re-score: only ever raises; --apply writes the raise
Every change of tier is recorded in retrospective.md via retro.append_tier_change."""

from .. import gitutil, grants, locate, meta, retro, tiering
from ..errors import OK, WARN, fail
from ..project import Project


def register(sub):
    p = sub.add_parser("complexity", help="档位：show / set / recheck")
    p.add_argument("action", choices=["show", "set", "recheck"])
    p.add_argument("tier", nargs="?", choices=["S", "M", "L"])
    p.add_argument("--phase", choices=["2", "3"])
    p.add_argument("--apply", action="store_true")
    p.add_argument("--downgrade", action="store_true")
    p.add_argument("--reason")
    p.add_argument("--change")


def _print_recommendation(tier, points, reasons):
    print("推荐档位 %s（%d 分）" % (tier, points))
    for r in reasons:
        print("  - %s" % r)


def _record(project, change_dir, m, old, new, kind, reason):
    try:
        retro.append_tier_change(change_dir, m["phase"], "%s → %s" % (old, new), kind, reason,
                                 gitutil.user_name(project.root))
    except NotImplementedError:
        fail("retrospective 留痕尚未实现（该能力不可用），档位未修改")


def _set(project, change, change_dir, m, tier, kind, reason):
    _record(project, change_dir, m, m["complexity"], tier, kind, reason)

    def apply(md):
        md["complexity"] = tier
        md["tierConfirmed"] = True
    meta.update(change_dir, apply)
    print("档位已%s：%s → %s" % (kind, m["complexity"], tier))


def _cmd_set(a, project, change, change_dir, m):
    if not a.tier:
        fail("用法：complexity set <S|M|L>")
    old = m["complexity"]
    lower = meta.tier_rank(a.tier) < meta.tier_rank(old)
    if not m["tierConfirmed"]:
        rec = tiering.recommend(change_dir)[0]
        reason = a.reason or ("推荐档，用户确认" if a.tier == rec else "用户选择（推荐 %s）" % rec)
        _set(project, change, change_dir, m, a.tier, "选定", reason)
        return OK
    if a.tier == old:
        print("档位已是 %s，无需修改" % old)
        return OK
    if not lower:
        if a.downgrade:
            fail("%s → %s 是升档，不要加 --downgrade" % (old, a.tier))
        _set(project, change, change_dir, m, a.tier, "升档", a.reason or "用户确认升档")
        return OK
    if not a.downgrade:
        fail("%s → %s 是降档：档位确认后只升不降。确需降档，请用户本人输入「确认降档 %s %s」后，再加 --downgrade --reason 执行"
             % (old, a.tier, change, a.tier))
    if not (a.reason or "").strip():
        fail("降档必须给出 --reason")
    try:
        granted = grants.consume(project.root, change, "downgrade", a.tier, "")
    except NotImplementedError:
        fail("降档授权尚未实现（该能力不可用）")
    if not granted:
        fail("没有有效的降档授权：请用户本人在对话里原样输入「确认降档 %s %s」（10 分钟内有效）" % (change, a.tier))
    _set(project, change, change_dir, m, a.tier, "降档", a.reason)
    return OK


def _cmd_recheck(a, project, change, change_dir, m):
    if not a.phase:
        fail("用法：complexity recheck --phase <2|3> [--apply]")
    tier, points, reasons = tiering.recommend(change_dir, a.phase)
    _print_recommendation(tier, points, reasons)
    old = m["complexity"]
    if meta.tier_rank(tier) <= meta.tier_rank(old):
        if tier != old:
            print("复评建议 %s，按只升不降保持 %s" % (tier, old))
        return OK
    if not a.apply:
        print("升档建议：%s → %s。用户确认后加 --apply 写入" % (old, tier))
        return WARN
    _set(project, change, change_dir, m, tier, "升档", "Phase %s 复评：%s" % (a.phase, "；".join(reasons)))
    return OK


def run(a) -> int:
    project = Project.here()
    change, change_dir, m = locate.load(project, a.change)
    if a.action == "show":
        _print_recommendation(*tiering.recommend(change_dir, a.phase or "1"))
        print("当前档位 %s（%s）" % (m["complexity"], "已确认" if m["tierConfirmed"] else "临时"))
        return OK
    if a.action == "set":
        return _cmd_set(a, project, change, change_dir, m)
    return _cmd_recheck(a, project, change, change_dir, m)
