"""`spec-driven resume`. Owner: T2. Cold start (design doc §8): one screen with the
change, mode, tier, current phase and next step, invariants and the files to read."""

import json

from .. import config, locate, router
from .. import project as P
from ..project import Project

MAX_INVARIANT_LINES = 12


def register(sub):
    p = sub.add_parser("resume", help="新会话第一步：恢复当前 change 的上下文")
    p.add_argument("change", nargs="?")


def _invariants(change_dir):
    path = change_dir / P.INVARIANTS
    try:
        data = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}
    except ValueError:
        return ["invariants.json 无法解析，请检查"]
    lines = []
    for k, v in data.items():
        lines.append("  %s: %s" % (k, json.dumps(v, ensure_ascii=False)))
    if len(lines) > MAX_INVARIANT_LINES:
        lines = lines[:MAX_INVARIANT_LINES] + ["  …（共 %d 项，详见 invariants.json）" % len(data)]
    return lines or ["  （无）"]


def run(a) -> int:
    project = Project.here()
    change, change_dir, m = locate.load(project, a.change)
    s = router.summary(m, config.load(project))
    tier = "%s（%s）" % (m["complexity"], "已确认" if m["tierConfirmed"] else "临时，Phase 1 末尾选定")
    print("change   %s" % change)
    print("mode     %s    档位 %s" % (m["mode"], tier))
    print("分支     %s    基线 %s" % (m["branch"] or "未绑定", (m["baseCommit"] or "")[:7]))
    print("当前     Phase %s（%s）" % (s["phase"], s["phaseStatus"]))
    print("下一步   Phase %s：%s" % (s["next"], s["action"]) if s["next"] else "下一步   %s" % s["action"])
    if s["stale"]:
        print("待重审   Phase %s（上游改过，需要重新过门）" % "、".join(s["stale"]))
    skipped = ["%s（%s）" % (p, r) for p, r in (m.get("skipped") or {}).items() if r]
    if skipped:
        print("已跳过   %s" % "；".join(skipped))
    print("业务取值与映射（invariants.json）")
    print("\n".join(_invariants(change_dir)))
    reads = [f for f in router.INPUTS.get(s["next"] or "9", []) if (change_dir / f).is_file()]
    rel = change_dir.relative_to(project.root).as_posix()
    print("本 Phase 先读")
    print("\n".join("  %s/%s" % (rel, f) for f in reads) or "  （无）")
    return 0
