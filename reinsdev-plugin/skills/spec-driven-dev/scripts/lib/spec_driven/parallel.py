"""Phase 6 multi-worker lane (workflow §10.3). Owner: T19.

`plan()` turns tasks.md into waves: a task joins a wave once all its dependencies
finished in earlier waves, and only if its scope does not overlap a task already in
that wave. The git side keeps one integration branch `spec-parallel/<change>` and one
branch + worktree per task of the current wave. Worktrees live under REINS_HOME, never
inside the project, so the coordinator's working tree stays clean.

Task branches are `spec-parallel/<change>-<task>`: git cannot hold both a ref and a
directory named `spec-parallel/<change>`.
"""

import hashlib
import re
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Dict, List, Optional

from . import gitutil, mdparse, paths
from .project import Project

PREFIX = "spec-parallel/"
INTEGRATION_DIR = "_integration"
_GLOB = re.compile(r"[*?\[]")


@dataclass
class Task:
    id: str
    title: str
    state: str                      # " " | "x" | "~" as in tasks.md
    deps: List[str] = field(default_factory=list)
    scope: List[str] = field(default_factory=list)
    hours: Optional[float] = None   # None when 预估 is missing or unreadable


@dataclass
class Plan:
    tasks: List[Task]
    done: List[str]                 # finished per Task-Id commits, not scheduled
    deferred: List[str]             # "- [~]", not scheduled
    waves: List[List[str]]
    problems: List[str]
    notes: List[str]


def _fields(text: str) -> Dict[str, str]:
    """`key：value` parts after the task title, split on "；" (same reading as gate 4)."""
    out = {}
    for part in text.replace(";", "；").split("；")[1:]:
        key, sep, value = part.replace(":", "：", 1).partition("：")
        if sep:
            out.setdefault(key.strip(), value.strip())
    return out


def _task_id(text: str) -> str:
    prefix = text.split(None, 1)[0].rstrip(".:：。") if text.strip() else ""
    return prefix if mdparse.ids(prefix, "TASK") == [prefix] else ""


def _hours(value: str) -> Optional[float]:
    m = re.fullmatch(r"\s*([0-9]+(?:\.[0-9]+)?)\s*(小时|h|H|分钟|min)?\s*", value or "")
    if not m:
        return None
    n = float(m.group(1))
    return n / 60 if m.group(2) in ("分钟", "min") else n


def _scope(value: str) -> List[str]:
    """Normalized scope paths; raises ValueError for absolute, `..` or placeholder paths."""
    out = []
    for item in re.split(r"[,，、]", value):
        p = item.strip().strip("`").replace("\\", "/").rstrip("/")
        if p.startswith("./"):
            p = p[2:]
        if not p:
            continue
        if PurePosixPath(p).is_absolute() or ".." in PurePosixPath(p).parts or "<" in p:
            raise ValueError(p)
        out.append(p)
    return out


def _base(path: str) -> str:
    """Directory part before the first glob character; a plain path is itself."""
    m = _GLOB.search(path)
    return path if not m else path[:m.start()].rsplit("/", 1)[0] if "/" in path[:m.start()] else ""


def overlaps(a: str, b: str) -> bool:
    """Two scope entries touch the same files: equal, or one is a directory holding the other.
    Globs are compared by their directory part, so they overlap conservatively."""
    a, b = _base(a), _base(b)
    if not a or not b:
        return True
    return a == b or a.startswith(b + "/") or b.startswith(a + "/")


def parse_tasks(text: str):
    """(tasks, problems) from tasks.md text."""
    tasks, problems, seen = [], [], set()
    for box in mdparse.checkboxes(text):
        tid = _task_id(box.text)
        if not tid:
            problems.append("任务缺少有效编号：%s" % box.text)
            continue
        if tid in seen:
            problems.append("任务编号重复：%s" % tid)
            continue
        seen.add(tid)
        fields = _fields(box.text)
        title = box.text.split("；", 1)[0][len(tid):].lstrip(".:：。 ").strip()
        task = Task(tid, title, box.state, hours=_hours(fields.get("预估", "")))
        dep = fields.get("依赖")
        if dep is None or not dep.strip():
            problems.append("%s 缺少「依赖」（没有依赖写「无」）" % tid)
        elif dep.strip() != "无":
            task.deps = mdparse.ids(dep, "TASK")
            if not task.deps:
                problems.append("%s 的依赖「%s」不是任务编号" % (tid, dep))
        try:
            task.scope = _scope(fields.get("范围", ""))
        except ValueError as e:
            problems.append("%s 的范围含无效路径：%s" % (tid, e))
        else:
            if not task.scope:
                problems.append("%s 缺少「范围」，无法判断能否与其他任务同批" % tid)
        tasks.append(task)
    if not tasks and not problems:
        problems.append("tasks.md 里没有任务")
    return tasks, problems


def _cycle(pending: Dict[str, Task]) -> List[str]:
    """One dependency cycle among `pending` (ids in order), for the error message."""
    start = sorted(pending)[0]
    path, at = [], start
    while at not in path:
        path.append(at)
        at = next(d for d in pending[at].deps if d in pending)
    return path[path.index(at):] + [at]


def plan(text: str, done: Dict[str, List[str]]) -> Plan:
    """Waves for the tasks not yet done. Pure function of tasks.md and done_tasks()."""
    tasks, problems = parse_tasks(text)
    known = {t.id for t in tasks}
    for t in tasks:
        for d in t.deps:
            if d == t.id:
                problems.append("%s 依赖自己" % t.id)
            elif d not in known:
                problems.append("%s 依赖不存在的任务 %s" % (t.id, d))
    finished = [t.id for t in tasks if t.id in done]
    deferred = [t.id for t in tasks if t.state == "~" and t.id not in done]
    notes = []
    pending = {t.id: t for t in tasks if t.id not in finished and t.id not in deferred}
    for t in pending.values():
        for d in t.deps:
            if d in deferred:
                notes.append("%s 依赖已延期的 %s，按已满足处理；请确认它不需要 %s 的产出" % (t.id, d, d))
    waves = []
    if problems:
        return Plan(tasks, finished, deferred, waves, problems, notes)
    order = [t.id for t in tasks]
    while pending:
        ready = [i for i in order if i in pending and not any(d in pending for d in pending[i].deps)]
        if not ready:
            problems.append("依赖有环：%s" % " → ".join(_cycle(pending)))
            break
        wave = []
        for i in ready:
            if not any(overlaps(a, b) for j in wave for a in pending[i].scope for b in pending[j].scope):
                wave.append(i)
        for i in wave:
            del pending[i]
        waves.append(wave)
    return Plan(tasks, finished, deferred, waves, problems, notes)


def estimate(p: Plan) -> dict:
    """Honest numbers: serial hours vs. the sum of each wave's longest task."""
    by_id = {t.id: t for t in p.tasks}
    scheduled = [i for w in p.waves for i in w]
    unknown = [i for i in scheduled if by_id[i].hours is None]
    serial = sum(by_id[i].hours or 0 for i in scheduled)
    parallel = sum(max(by_id[i].hours or 0 for i in w) for w in p.waves)
    widest = max((len(w) for w in p.waves), default=0)
    if widest < 2:
        verdict, why = "不建议", "没有能同批的任务，并行只会多出建 worktree 和合并的开销"
    elif unknown:
        verdict, why = "无法判断", "%s 没有可读的预估" % "、".join(unknown)
    elif serial and parallel <= serial * 0.75:
        verdict, why = "建议", "预计节省 %.1f 小时（%d%%）" % (serial - parallel, round(100 * (1 - parallel / serial)))
    else:
        verdict, why = "不建议", "节省不到 25%%，抵不过合并和冲突处理的成本"
    return {"serialHours": serial, "parallelHours": parallel, "widestWave": widest,
            "verdict": verdict, "reason": why}


# ---- git side ---------------------------------------------------------------

def integration_branch(change: str) -> str:
    return PREFIX + change


def task_branch(change: str, task: str) -> str:
    return "%s%s-%s" % (PREFIX, change, task)


def worktree_root(project: Project, change: str) -> Path:
    """REINS_HOME/worktrees/<project>-<hash>/<change>: outside the repo, one per project."""
    key = hashlib.sha1(str(project.root.resolve()).encode("utf-8")).hexdigest()[:8]
    return paths.reins_home() / "worktrees" / ("%s-%s" % (project.root.name, key)) / change


def worktrees(root: Path) -> Dict[str, Path]:
    """Branch name -> worktree path for every worktree that has a branch checked out."""
    out, path = {}, None
    for line in gitutil.git(["worktree", "list", "--porcelain"], root).splitlines():
        if line.startswith("worktree "):
            path = Path(line[len("worktree "):])
        elif line.startswith("branch refs/heads/") and path is not None:
            out[line[len("branch refs/heads/"):]] = path
    return out


def wave_branches(root: Path, change: str) -> List[str]:
    """Existing task branches of the current wave."""
    prefix = task_branch(change, "")
    names = gitutil.git(["for-each-ref", "--format=%(refname:short)", "refs/heads/" + PREFIX], root)
    return [n for n in names.splitlines() if n.startswith(prefix) and mdparse.ids(n[len(prefix):], "TASK")]


def branch_exists(root: Path, name: str) -> bool:
    return bool(gitutil.git(["rev-parse", "--verify", "--quiet", "refs/heads/" + name], root, check=False))


def is_ancestor(root: Path, a: str, b: str) -> bool:
    """True when commit `a` is reachable from `b` (gitutil.git hides exit codes, so compare
    the merge base with `a` instead of using --is-ancestor)."""
    tip = gitutil.git(["rev-parse", "--verify", "--quiet", a], root, check=False)
    return bool(tip) and gitutil.git(["merge-base", a, b], root, check=False) == tip


def dirty(root: Path, allow: Optional[List[str]] = None) -> List[str]:
    """Uncommitted paths (staged, unstaged or untracked), except those listed in `allow`."""
    allow = set(allow or [])
    return [p for p in gitutil.changed_files("HEAD", root) if p not in allow]


def merge(cwd: Path, branch: str, message: List[str]):
    """Merge `branch` into the branch checked out at `cwd`. On failure, abort the merge and
    return (False, conflicted paths, git output); never resolves or overwrites anything."""
    args = ["merge", "--no-ff", "--no-edit"]
    for m in message:
        args += ["-m", m]
    out = gitutil.git(args + [branch], cwd, check=False)
    if gitutil.git(["rev-parse", "-q", "--verify", "MERGE_HEAD"], cwd, check=False):
        conflicts = [p for p in gitutil.git(["diff", "--name-only", "--diff-filter=U"], cwd,
                                            check=False).splitlines() if p]
        gitutil.git(["merge", "--abort"], cwd, check=False)
        return False, conflicts, out
    if not is_ancestor(cwd, branch, "HEAD"):
        return False, [], out
    return True, [], out
