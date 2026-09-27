"""`spec-driven status`. Owner: T2. Where each change stands: phase, status and next step.
T2 extends the output with router.next_phase(); the no-.openspec message stays as is."""

import json

from ..project import META, Project


def register(sub):
    s = sub.add_parser("status", help="查看各 change 的进度")
    s.add_argument("--json", action="store_true")


def run(a) -> int:
    project = Project.here()
    changes = []
    for name in project.active_changes():
        try:
            data = json.loads((project.change_dir(name) / META).read_text(encoding="utf-8"))
        except ValueError:
            data = {"error": "无法解析 .meta.json"}
        changes.append({"change": name, **data})
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
        print("%-40s mode=%-8s 档位=%-2s phase=%s" % (
            c["change"], c.get("mode", "?"), c.get("complexity", "?"), c.get("phase", "?")))
    return 0
