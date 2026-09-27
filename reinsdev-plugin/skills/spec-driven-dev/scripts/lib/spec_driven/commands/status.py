"""`spec-driven status`. Owner: T2. Where each change stands: phase, status and next step."""

import json

from .. import config, router
from ..project import META, Project


def register(sub):
    s = sub.add_parser("status", help="查看各 change 的进度")
    s.add_argument("--json", action="store_true")


def run(a) -> int:
    project = Project.here()
    cfg = config.load(project) if project.enabled else {}
    changes = []
    for name in project.active_changes():
        try:
            data = json.loads((project.change_dir(name) / META).read_text(encoding="utf-8"))
            nxt = router.summary(data, cfg)
        except (ValueError, KeyError):
            data, nxt = {"error": "无法解析 .meta.json"}, None
        changes.append(dict({"change": name}, **data, next=nxt))
    if a.json:
        print(json.dumps({"project": str(project.root), "enabled": project.enabled, "changes": changes},
                         ensure_ascii=False, indent=2))
        return 0
    if not project.enabled:
        print("项目 %s 尚未启用 Reins（没有 .openspec/）。用 /spec 开始第一个 change。" % project.root)
        return 0
    if not changes:
        print("没有进行中的 change。用 /spec 开始一个。")
        return 0
    for c in changes:
        if "error" in c:
            print("%-40s %s" % (c["change"], c["error"]))
            continue
        s = c["next"]
        print("%-40s mode=%-8s 档位=%s%s phase=%s(%s) 下一步=%s %s" % (
            c["change"], c["mode"], c["complexity"], "" if c["tierConfirmed"] else "(临时)",
            s["phase"], s["phaseStatus"], s["next"] or "-", s["action"]))
        if s["stale"]:
            print("%-40s 待重新过门：Phase %s" % ("", "、".join(s["stale"])))
    return 0
