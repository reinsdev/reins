"""`spec-driven trace <id>`. Owner: T18. Follow an AC / REQ / SC / task id through proposal,
spec, tasks, commits and QA results. See docs/dev/tasks.md T18.

Read-only. The current change by default; `--change` also finds an archived change under
changes/archive/<date>-<change>/. Exit 0 when every link is found, 2 when some link is
missing (listed, never guessed), 1 when the id appears nowhere in the change.
"""

import json
import re
from pathlib import Path
from typing import List, Optional, Tuple

from .. import gitutil, locate, meta, mdparse, taskstate, traceability
from ..errors import OK, WARN, fail
from ..project import META, Project


def register(sub):
    p = sub.add_parser("trace", help="按 AC / REQ / SC / 任务编号追溯需求到测试的链路")
    p.add_argument("id")
    p.add_argument("--change")
    p.add_argument("--json", action="store_true")


def _archived(project: Project, name: str) -> List[Path]:
    """Archive directories of `name`: the exact directory name, or <YYYY-MM-DD>-<name>."""
    if not project.archive_dir.is_dir():
        return []
    pattern = re.compile(r"\d{4}-\d{2}-\d{2}-%s" % re.escape(name))
    return [d for d in sorted(project.archive_dir.iterdir())
            if d.is_dir() and (d / META).is_file() and (d.name == name or pattern.fullmatch(d.name))]


def resolve(project: Project, name: Optional[str]) -> Tuple[str, Path, bool]:
    """(change, change dir, archived). Active changes win over archived ones of the same name."""
    if not name or not project.enabled or name in project.active_changes():
        change = locate.resolve(project, name)
        return change, project.change_dir(change), False
    found = _archived(project, name)
    if len(found) > 1:
        fail("「%s」有多个归档，请用归档目录名指定：%s" % (name, "、".join(d.name for d in found)))
    if not found:
        fail("没有进行中或已归档的 change「%s」；进行中：%s" % (name, "、".join(project.active_changes()) or "无"))
    return name, found[0], True


def _verified(root: Path, rev: str) -> str:
    return gitutil.git(["rev-parse", "--verify", "--quiet", rev + "^{commit}"], root, check=False)


def history(project: Project, change_dir: Path, m: dict, archived: bool):
    """(commits since baseCommit with "red" set, error). An archived change stops at the
    commit that archived it, so later changes reusing the same task ids do not leak in."""
    if not gitutil.is_repo(project.root):
        return None, "%s 不是 git 仓库，查不到提交" % project.root.as_posix()
    base = m.get("baseCommit") or ""
    if not base or not _verified(project.root, base):
        return None, "baseCommit %s 在 git 历史里不存在" % (base or "（空）")
    commits = gitutil.commits(base, project.root)
    if archived:
        rel = (change_dir / META).relative_to(project.root).as_posix()
        added = gitutil.git(["log", "--reverse", "--diff-filter=A", "--format=%H", "--", rel],
                            project.root, check=False).split()
        if added:
            keep = set(gitutil.git(["rev-list", "%s..%s" % (base, added[0])], project.root).split())
            commits = [c for c in commits if c["hash"] in keep]
    for c in commits:
        c["red"] = taskstate.is_red(c)
    return commits, ""


def _where(name, line):
    return "%s:%d" % (name, line) if line else name


def render(result: dict, change: str, archived: bool, m: dict) -> str:
    state = "已归档" if archived else "Phase %s" % m["phase"]
    out = ["追溯 %s（change：%s，%s）" % (result["id"], change, state)]
    rows = {
        "ac": ["%s  %s  %s" % (a["id"], _where("proposal.md", a.get("line")), a.get("text", ""))
               for a in result["acs"] if a["defined"]],
        "spec": ["%s  %s" % (r["id"], _where("spec.md", r["line"])) for r in result["reqs"] if r["defined"]]
                + ["%s  所属 %s  %s  关联 %s" % (s["id"], s["req"] or "（无 REQ）", _where("spec.md", s["line"]),
                                              "、".join(s["acs"]) or "（无）")
                   for s in result["scs"] if s["defined"]],
        "points": ["%s  %s  %s  关联 %s" % (p["id"], _where("bugfix-analysis.md", p["line"]), p["path"],
                                          "、".join(p["acs"]) or "（无）")
                   for p in result["points"] if p["defined"]],
        "tasks": ["%s  [%s]  %s  关联 %s" % (t["id"], t["state"], _where("tasks.md", t["line"]),
                                           "、".join(t["scs"] + t["acs"] + t["points"]) or "（无）")
                  for t in result["tasks"] if t["defined"]],
        "commits": ["%s  %-8s  %s  %s" % (c["task"], c["phase"], c["hash"][:7], c["subject"])
                    for c in result["commits"]],
        "qa": ["%s  %s  %s" % (q["sc"], q["result"], q["evidence"]) for q in result["qa"]],
    }
    notes = {}
    for entry in result["skipped"]:
        notes.setdefault(entry["link"], []).append("跳过：" + entry["reason"])
    for entry in result["missing"]:
        notes.setdefault(entry["link"], []).append("缺失：" + entry["reason"])
    for link, label in traceability.LINKS.items():
        if rows[link] or notes.get(link):
            out.append(label)
            out.extend("  " + line.rstrip() for line in rows[link] + notes.get(link, []))
    if result["missing"]:
        out.append("链路不完整：缺失 %d 处" % len(result["missing"]))
    else:
        out.append("链路完整")
    return "\n".join(out)


def run(a) -> int:
    ident = a.id.strip()
    if not traceability.kind_of(ident):
        fail("「%s」不是 AC / REQ / SC / 任务编号；格式：%s" % (
            ident, "，".join("%s %s" % (k, mdparse.ID_PATTERNS[k]) for k in traceability.KINDS)))
    project = Project.here()
    change, change_dir, archived = resolve(project, a.change)
    m = meta.load(change_dir)
    commits, error = history(project, change_dir, m, archived)
    result = traceability.trace(ident, traceability.read_artifacts(change_dir), m, commits, error)
    if result is None:
        fail("change %s 的工件和提交里都没有 %s" % (change, ident))
    if a.json:
        result = dict(result, change=change, archived=archived,
                      changeDir=change_dir.relative_to(project.root).as_posix(), phase=m["phase"])
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(render(result, change, archived, m))
    return OK if result["complete"] else WARN
