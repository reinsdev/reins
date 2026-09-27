"""waive-grant: issue a one-time grant when the user's prompt is exactly a
confirmation phrase (grants.WAIVE_PHRASE / DOWNGRADE_PHRASE). Owner: T6.

A phrase only issues a grant for something live: a current, un-waived BLOCK of that
gate and check (the grant binds its fingerprints, so a changed finding needs a new
confirmation), or a tier below the confirmed one. The note returned goes to the model
as context and says what to run next; nothing is issued otherwise.
"""

from typing import Optional

from .. import config, gates, grants
from ..meta import GATES, TIERS
from .common import project_of, read_meta


def _waive(project, change_dir, m, change, gate, check) -> str:
    if gate not in GATES:
        return "没有 gate-%s，未签发放行授权" % gate
    ctx = gates.GateContext(project, change, change_dir, m, config.load(project))
    try:
        findings, _ = gates.evaluate(gate, ctx)
    except NotImplementedError:
        return "gate-%s 尚未实现，无法确认拦截内容，未签发放行授权" % gate
    live = sorted({f.fingerprint for f in findings if f.level == "BLOCK" and not f.waived and f.check == check})
    if not live:
        return "gate-%s 当前没有检查项 %s 的拦截（可能已修复或已放行），未签发放行授权" % (gate, check)
    grants.issue(project.root, change, "waive", "%s %s" % (gate, check), ",".join(live))
    return ("用户已确认放行 %s 的 gate-%s / %s（%d 项，%d 分钟内有效）。按 waive skill 执行 "
            "spec-driven waive %s %s --reason \"<用户给的理由>\"，理由只能用用户的原话。"
            % (change, gate, check, len(live), grants.TTL // 60, gate, check))


def _downgrade(project, m, change, tier) -> str:
    current = m.get("complexity")
    if current not in TIERS or not m.get("tierConfirmed") or TIERS.index(tier) >= TIERS.index(current):
        return "%s 当前档位是 %s，%s 不是降档，未签发降档授权" % (change, current, tier)
    grants.issue(project.root, change, "downgrade", tier, "")
    return ("用户已确认把 %s 从 %s 降到 %s（%d 分钟内有效）。请用户给出理由后执行 "
            "spec-driven complexity set %s --downgrade --reason \"<用户给的理由>\"。"
            % (change, current, tier, grants.TTL // 60, tier))


def prompt(ev: dict) -> Optional[str]:
    phrase = grants.match_phrase(ev.get("prompt") or "")
    if not phrase:
        return None
    project = project_of(ev)
    if project is None:
        return "Reins：当前目录不是启用 Reins 的项目，未签发授权"
    change = phrase["change"]
    if change not in project.active_changes():
        return "Reins：没有进行中的 change「%s」，未签发授权" % change
    change_dir = project.change_dir(change)
    m = read_meta(change_dir)
    if m is None:
        return "Reins：%s 的 .meta.json 无法读取，未签发授权" % change
    try:
        if phrase["action"] == "waive":
            note = _waive(project, change_dir, m, change, phrase["gate"], phrase["check"])
        else:
            note = _downgrade(project, m, change, phrase["tier"])
    except SystemExit as e:  # config / gate reported a user-facing error
        note = "%s；未签发授权" % e.code
    return "Reins：" + note
