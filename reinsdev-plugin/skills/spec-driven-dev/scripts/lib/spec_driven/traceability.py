"""Requirement traceability (workflow §2.3). Owner: T18.

Follows one AC / REQ / SC / task id along the artifact chain:
proposal AC -> spec SC (and its REQ) -> tasks -> Task-Id commits -> qa-report SC results.
Skipped-Phase-3 changes link tasks to AC (feature) or to bugfix-analysis change points.

`trace()` is pure: the caller reads the artifacts and the commits. Markdown is parsed only
through mdparse. A link that cannot be found is listed as missing, never guessed.
"""

import re
from pathlib import Path
from typing import Dict, List, Optional

from . import mdparse
from .project import BUGFIX_ANALYSIS, PROPOSAL, QA_REPORT, SPEC, TASKS

FILES = (PROPOSAL, BUGFIX_ANALYSIS, SPEC, TASKS, QA_REPORT)

# Chain links in order; values are the user-facing labels.
LINKS = {"ac": "AC", "spec": "REQ / SC", "points": "修改点", "tasks": "任务",
         "commits": "提交", "qa": "QA"}

KINDS = ("AC", "REQ", "SC", "TASK")
_REGRESSION = "AC-regression"  # the one fixed non-numeric AC id (bugfix template)
_SPLIT = re.compile(r"[\s,，、;；:：]+")


def kind_of(ident: str) -> Optional[str]:
    """"AC" / "REQ" / "SC" / "TASK" by mdparse.ID_PATTERNS, or None."""
    if ident == _REGRESSION:
        return "AC"
    return next((k for k in KINDS if re.fullmatch(mdparse.ID_PATTERNS[k], ident)), None)


def read_artifacts(change_dir: Path) -> Dict[str, Optional[str]]:
    """File name -> text for the chain's artifacts; None when absent or unreadable."""
    texts = {}
    for name in FILES:
        try:
            texts[name] = (Path(change_dir) / name).read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            texts[name] = None
    return texts


def _acs(text):
    found = mdparse.ids(text, "AC")
    if _REGRESSION in _SPLIT.split(text):
        found.append(_REGRESSION)
    return found


def _rows(section):
    """(absolute line, row) for each table row directly under `section`."""
    for table in mdparse.tables(section.body):
        for i, row in enumerate(table.rows):
            yield section.line + table.line + 2 + i, row


def _fields(text):
    """`；key：value` fields of a task line, as in the tasks template."""
    fields = {}
    for part in text.replace(";", "；").split("；")[1:]:
        key, sep, value = part.replace(":", "：", 1).partition("：")
        if sep:
            fields.setdefault(key.strip(), value.strip())
    return fields


def _task_id(text):
    prefix = text.split(None, 1)[0].rstrip(".:：。") if text.strip() else ""
    return prefix if mdparse.ids(prefix, "TASK") == [prefix] else ""


def index(texts: Dict[str, Optional[str]], points_linked: bool) -> dict:
    """Everything the artifacts define, keyed by id in document order.
    `points_linked`: tasks link bugfix-analysis change points instead of SCs."""
    idx = {"acs": {}, "reqs": {}, "scs": {}, "points": {}, "tasks": {}, "qa": {}}
    text = texts.get(PROPOSAL)
    section = mdparse.find(mdparse.parse(text), "acceptance-criteria") if text else None
    if section:
        for line, row in _rows(section):
            ac = row.get("AC", "").strip()
            if kind_of(ac) == "AC":
                idx["acs"].setdefault(ac, {"id": ac, "line": line, "text": row.get("验收标准", "")})
        for ac in _acs(section.text()):
            idx["acs"].setdefault(ac, {"id": ac, "line": None, "text": ""})
    text = texts.get(SPEC)
    if text:
        root = mdparse.parse(text)
        reqs = [s for s in mdparse.find_all(root, mdparse.ID_PATTERNS["REQ"]) if s.level == 2]
        for req in reqs:
            rid = mdparse.ids(req.title, "REQ")[0]
            idx["reqs"].setdefault(rid, {"id": rid, "title": req.title, "line": req.line})
        for sc in mdparse.find_all(root, mdparse.ID_PATTERNS["SC"]):
            if sc.level != 3:
                continue
            sid = mdparse.ids(sc.title, "SC")[0]
            parent = next((r for r in reqs if sc in r.children), None)
            idx["scs"].setdefault(sid, {
                "id": sid, "title": sc.title, "line": sc.line, "acs": _acs(sc.text()),
                "req": mdparse.ids(parent.title, "REQ")[0] if parent else None})
    text = texts.get(BUGFIX_ANALYSIS)
    section = mdparse.find(mdparse.parse(text), "change-points") if text else None
    if section:
        for line, row in _rows(section):
            point = row.get("修改点", "").strip()
            if point and "<" not in point:
                idx["points"].setdefault(point, {"id": point, "line": line,
                                                 "path": row.get("项目相对路径", ""),
                                                 "acs": _acs(row.get("关联 AC", ""))})
    text = texts.get(TASKS)
    for box in mdparse.checkboxes(text or ""):
        tid = _task_id(box.text)
        if not tid or tid in idx["tasks"]:
            continue
        link = _fields(box.text).get("关联", "")
        scs, acs = mdparse.ids(link, "SC"), _acs(link)
        points = [v for v in re.split(r"[,，、]", link) if v.strip()] if points_linked else []
        points = [v.strip() for v in points if v.strip() not in scs + acs]
        idx["tasks"][tid] = {"id": tid, "line": box.line, "state": box.state, "text": box.text,
                             "scs": scs, "acs": acs, "points": points}
    text = texts.get(QA_REPORT)
    section = mdparse.find(mdparse.parse(text), "sc-results") if text else None
    idx["qaTable"] = section is not None
    if section:
        for line, row in _rows(section):
            sid = row.get("SC", "").strip()
            if sid:
                idx["qa"].setdefault(sid, {"sc": sid, "line": line, "result": row.get("结果", "").strip(),
                                           "evidence": row.get("证据", "").strip()})
    return idx


def _unique(values):
    seen, out = set(), []
    for v in values:
        if v and v not in seen:
            seen.add(v)
            out.append(v)
    return out


def commit_phase(commit: dict) -> str:
    """RED for red commits (caller sets "red"); otherwise the TDD-Phase trailer or GREEN."""
    if commit.get("red"):
        return "RED"
    phases = [v.upper() for v in commit.get("trailers", {}).get("TDD-Phase", [])]
    return next((p for p in phases if p in ("GREEN", "REFACTOR")), "GREEN")


def commit_tasks(commit: dict) -> List[str]:
    return [t for v in commit.get("trailers", {}).get("Task-Id", []) for t in re.split(r"[,\s]+", v) if t]


def trace(ident: str, texts: Dict[str, Optional[str]], meta: dict,
          commits: Optional[List[dict]], commit_error: str = "") -> Optional[dict]:
    """The chain through `ident`, or None when the id appears nowhere in the change.

    `commits`: gitutil.commits() records of this change, each with "red": bool added;
    None when git history is unavailable (`commit_error` says why).
    Result keys: id, kind, acs, reqs, scs, points, tasks, commits, qa (lists of dicts, each
    with "defined" where it applies), missing / skipped ([{"link", "id", "reason"}]), complete.
    """
    kind = kind_of(ident)
    if not kind:
        raise ValueError(ident)
    skipped = meta.get("skipped") or {}
    no_spec = bool(skipped.get("3"))
    points_linked = no_spec and meta.get("mode") == "bugfix"
    idx = index(texts, points_linked)
    tasks_all = idx["tasks"]

    def linking(scs=(), acs=(), points=()):
        return [t["id"] for t in tasks_all.values()
                if set(t["scs"]) & set(scs) or set(t["acs"]) & set(acs) or set(t["points"]) & set(points)]

    acs, reqs, scs, points, tasks = [], [], [], [], []
    if kind == "AC":
        acs = [ident]
        scs = [s["id"] for s in idx["scs"].values() if ident in s["acs"]]
        points = [p["id"] for p in idx["points"].values() if ident in p["acs"]]
        tasks = linking(scs, [ident], points)
    elif kind == "REQ":
        reqs = [ident]
        scs = [s["id"] for s in idx["scs"].values() if s["req"] == ident]
        tasks = linking(scs)
    elif kind == "SC":
        scs = [ident]
        tasks = linking(scs)
    else:
        tasks = [ident]
        task = tasks_all.get(ident)
        if task:
            scs, points = list(task["scs"]), list(task["points"])
            acs = list(task["acs"])
    if kind != "AC":
        acs = _unique(acs + [a for s in scs for a in idx["scs"].get(s, {}).get("acs", [])]
                      + [a for p in points for a in idx["points"].get(p, {}).get("acs", [])])
    if kind != "REQ":
        reqs = _unique([idx["scs"][s]["req"] for s in scs if s in idx["scs"]])

    home = {"AC": idx["acs"], "REQ": idx["reqs"], "SC": idx["scs"], "TASK": tasks_all}[kind]
    qa_rows = [s for s in scs if s in idx["qa"]]
    mentioned = {"AC": bool(scs or points or tasks), "REQ": False, "SC": bool(tasks or qa_rows),
                 "TASK": any(ident in commit_tasks(c) for c in commits or [])}[kind]
    if ident not in home and not mentioned:
        return None

    missing, skip = [], []

    def miss(link, reason, item=""):
        missing.append({"link": link, "id": item, "reason": reason})

    # AC
    if texts.get(PROPOSAL) is None:
        miss("ac", "没有 proposal.md")
    for ac in acs:
        if ac not in idx["acs"]:
            miss("ac", "proposal.md 的验收标准里没有 %s" % ac, ac)
    # REQ / SC, or the change points that replace them in a slim bugfix
    if no_spec:
        skip.append({"link": "spec", "id": "", "reason": "Phase 3 已跳过：%s" % skipped["3"]})
        if points_linked:
            if texts.get(BUGFIX_ANALYSIS) is None:
                miss("points", "没有 bugfix-analysis.md")
            elif kind == "AC" and not points:
                miss("points", "bugfix-analysis.md 的修改点没有关联 %s" % ident, ident)
            for p in points:
                if p not in idx["points"]:
                    miss("points", "bugfix-analysis.md 的修改点里没有「%s」" % p, p)
    elif texts.get(SPEC) is None:
        miss("spec", "还没有 spec.md")
    else:
        if kind == "AC" and not scs:
            miss("spec", "spec.md 里没有 SC 关联 %s" % ident, ident)
        if kind == "REQ" and ident not in idx["reqs"]:
            miss("spec", "spec.md 里没有 %s" % ident, ident)
        elif kind == "REQ" and not scs:
            miss("spec", "%s 下没有 SC" % ident, ident)
        for s in scs:
            if s not in idx["scs"]:
                miss("spec", "spec.md 里没有 %s" % s, s)
                continue
            if not idx["scs"][s]["acs"]:
                miss("ac", "%s 没有写关联 AC" % s, s)
            if not idx["scs"][s]["req"]:
                miss("spec", "%s 不在任何 REQ 下" % s, s)
    # tasks
    if texts.get(TASKS) is None:
        miss("tasks", "还没有 tasks.md")
    elif kind == "TASK":
        if ident not in tasks_all:
            miss("tasks", "tasks.md 里没有任务 %s" % ident, ident)
        elif not (scs or acs or points):
            miss("tasks", "%s 没有写关联" % ident, ident)
    else:
        targets = points if points_linked else (acs if no_spec else scs)
        for target in targets:
            if not linking([target], [target], [target]):
                miss("tasks", "没有任务关联 %s" % target, target)
        if not tasks and not targets:
            miss("tasks", "没有任务关联 %s" % ident, ident)
    # commits
    chain_commits = []
    if commits is None:
        miss("commits", commit_error or "读不到提交记录")
    else:
        for tid in tasks:
            task = tasks_all.get(tid, {})
            mine = [c for c in commits if tid in commit_tasks(c)]
            for c in mine:
                chain_commits.append({"task": tid, "hash": c["hash"], "subject": c["subject"],
                                      "phase": commit_phase(c)})
            if task.get("state") == "~":
                skip.append({"link": "commits", "id": tid, "reason": "%s 已延期（[~]）" % tid})
            elif not mine:
                miss("commits", "没有带 Task-Id: %s 的提交" % tid, tid)
            elif all(c.get("red") for c in mine):
                miss("commits", "%s 只有 RED 提交，还没有 GREEN" % tid, tid)
    # QA
    if skipped.get("7"):
        skip.append({"link": "qa", "id": "", "reason": "Phase 7 已跳过：%s" % skipped["7"]})
    elif not scs:
        if no_spec:
            skip.append({"link": "qa", "id": "", "reason": "没有 SC，QA 按 SC 记录结论，本链不适用"})
    elif texts.get(QA_REPORT) is None:
        miss("qa", "还没有 qa-report.md")
    elif not idx["qaTable"]:
        miss("qa", "qa-report.md 没有「SC 验证结果」")
    else:
        for s in scs:
            if s not in idx["qa"]:
                miss("qa", "qa-report.md 的 SC 验证结果里没有 %s" % s, s)

    def entries(ids, table):
        return [dict(table.get(i) or {"id": i}, defined=i in table) for i in ids]

    return {
        "id": ident, "kind": kind,
        "acs": entries(acs, idx["acs"]),
        "reqs": entries(reqs, idx["reqs"]),
        "scs": entries(scs, idx["scs"]),
        "points": entries(points, idx["points"]),
        "tasks": entries(tasks, tasks_all),
        "commits": chain_commits,
        "qa": [idx["qa"][s] for s in qa_rows],
        "missing": missing,
        "skipped": skip,
        "complete": not missing,
    }
