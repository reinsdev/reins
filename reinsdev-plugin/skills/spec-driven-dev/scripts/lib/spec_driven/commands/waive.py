"""`spec-driven waive`. Owner: T6. Manual waiver of a gate BLOCK (design doc §6.6).

Re-runs the gate to get the live findings of that check, consumes the grant the user
issued by typing 「确认放行 <change> <gate> <检查项>」 (bound to those fingerprints),
then records one row per finding in retrospective.md. Without a grant it refuses and
says the phrase. In a real terminal (TTY) the user may instead confirm by typing the
change name: the fallback for runtimes without a prompt hook.
"""

import sys

from .. import config, gates, gitutil, grants, locate, retro
from ..errors import OK, fail, unavailable
from ..meta import GATES
from ..project import Project


def register(sub):
    p = sub.add_parser("waive", help="人工放行一次拦截（需用户本人确认）")
    p.add_argument("gate")
    p.add_argument("check")
    p.add_argument("--reason", required=True)
    p.add_argument("--change")


def _tty_confirm(change: str) -> bool:
    if not (sys.stdin and sys.stdin.isatty()):
        return False
    try:
        return input("请输入 change 名「%s」确认放行：" % change).strip() == change
    except EOFError:
        return False


def run(a) -> int:
    project = Project.here()
    change, change_dir, m = locate.load(project, a.change)
    if a.gate not in GATES:
        fail("没有 gate %s（可选 %s）" % (a.gate, " / ".join(GATES)))
    if not a.reason.strip():
        fail("--reason 不能为空：理由只能来自用户")
    ctx = gates.GateContext(project, change, change_dir, m, config.load(project))
    try:
        findings, _ = gates.evaluate(a.gate, ctx)
    except NotImplementedError:
        return unavailable("gate-%s" % a.gate)
    live = [f for f in findings if f.level == "BLOCK" and not f.waived and f.check == a.check]
    if not live:
        fail("gate-%s 当前没有检查项 %s 的拦截（可能已修复或已放行）" % (a.gate, a.check))
    key = "%s %s" % (a.gate, a.check)
    fingerprint = ",".join(sorted({f.fingerprint for f in live}))
    if not grants.consume(project.root, change, "waive", key, fingerprint) and not _tty_confirm(change):
        fail("没有有效的放行授权：请用户本人在对话里原样输入「确认放行 %s %s %s」（%d 分钟内有效），再执行本命令"
             % (change, a.gate, a.check, grants.TTL // 60))
    confirmer = gitutil.user_name(project.root)
    for f in live:
        content = ("%s %s" % (f.location, f.reason)).strip()
        retro.append_waiver(change_dir, retro.Waiver(retro.now(), a.gate, a.check, content,
                                                     a.reason.strip(), confirmer, f.fingerprint))
    print("已放行 gate-%s / %s 共 %d 项，记入 retrospective.md「人工确认记录」" % (a.gate, a.check, len(live)))
    findings, code = gates.evaluate(a.gate, gates.GateContext(project, change, change_dir, m, config.load(project)))
    print(gates.render(a.gate, findings, code))
    return OK
