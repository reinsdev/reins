"""`spec-driven parallel plan | run | merge`. Owner: T19. Phase 6 multi-worker execution
(workflow §10.3). See docs/dev/tasks.md T19.

  plan   read-only: waves from tasks.md 依赖 / 范围, plus an honest gain estimate
  run    one branch + worktree per task of the next wave, cut from spec-parallel/<change>
  merge  merge the wave back one task at a time (abort on the first conflict, keep
         everything), then into the change branch; clean up; tasks-sync --apply; gate 6.5

run and merge need `parallel.enabled=true` in .openspec/.config.json.
"""

import argparse
import json
import re

from .. import config, gates, gitutil, locate, meta, parallel, taskstate
from .. import project as P
from ..errors import BLOCK, ERROR, OK, fail
from ..project import Project


def register(sub):
    p = sub.add_parser("parallel", help="Phase 6 多实现者并行：plan 预演 / run 建 worktree / merge 串行合回")
    p.add_argument("action", choices=["plan", "run", "merge"])
    p.add_argument("--change")
    p.add_argument("--json", action="store_true")


def _rel(project: Project, path) -> str:
    return path.relative_to(project.root).as_posix()


def _tasks_text(change_dir) -> str:
    path = change_dir / P.TASKS
    if not path.is_file():
        fail("还没有 tasks.md，先完成 Phase 4")
    return path.read_text(encoding="utf-8")


def _plan(project: Project, change_dir, m) -> parallel.Plan:
    if not m.get("baseCommit"):
        fail(".meta.json 缺少 baseCommit，无法按提交判定哪些任务已完成")
    return parallel.plan(_tasks_text(change_dir), taskstate.done_tasks(project, m))


def _refuse(p: parallel.Plan) -> int:
    print("无法规划并行：")
    for problem in p.problems:
        print("- %s" % problem)
    print("请回到 tasks.md 修正（Phase 4 已冻结时先 retry 4）后再预演")
    return ERROR


def _describe(task: parallel.Task) -> str:
    hours = "%g 小时" % task.hours if task.hours is not None else "预估未知"
    return "%s %s（%s；范围 %s）" % (task.id, task.title, hours, "、".join(task.scope))


def _plan_cmd(a, project, change, change_dir, m, cfg) -> int:
    p = _plan(project, change_dir, m)
    enabled = cfg.get("parallel", {}).get("enabled") is True
    if p.problems:
        if a.json:
            print(json.dumps({"change": change, "problems": p.problems}, ensure_ascii=False, indent=2))
        return _refuse(p)
    by_id = {t.id: t for t in p.tasks}
    est = parallel.estimate(p)
    if a.json:
        waves = [[{"id": i, "title": by_id[i].title, "hours": by_id[i].hours, "scope": by_id[i].scope}
                  for i in w] for w in p.waves]
        print(json.dumps({"change": change, "enabled": enabled, "done": p.done, "deferred": p.deferred,
                          "waves": waves, "estimate": est, "notes": p.notes}, ensure_ascii=False, indent=2))
        return OK
    print("%s 并行预演（只读，不建 worktree 和分支）" % change)
    print("已完成：%s；已延期：%s" % ("、".join(p.done) or "无", "、".join(p.deferred) or "无"))
    if not p.waves:
        print("没有待做的任务")
        return OK
    for n, wave in enumerate(p.waves, 1):
        print("第 %d 波：" % n)
        for i in wave:
            print("  - %s" % _describe(by_id[i]))
    for note in p.notes:
        print("注意：%s" % note)
    print("串行约 %g 小时，并行约 %g 小时（每波按最长的任务算）" % (est["serialHours"], est["parallelHours"]))
    print("结论：%s并行。%s" % (est["verdict"], est["reason"]))
    print("说明：平台不能同时运行多个 subagent 时，并行仍然正确，但不会更快；合并冲突要另花时间。")
    if not enabled:
        print("并行通道未开启（parallel.enabled=false）。要用，需由用户在 .openspec/.config.json 里设为 true。")
    return OK


def _prepare(project, change, change_dir, m, cfg):
    """Shared preconditions of run / merge; returns (work branch, tasks.md path relative to root)."""
    if cfg.get("parallel", {}).get("enabled") is not True:
        fail("并行通道未开启（parallel.enabled=false）；需要用户在 .openspec/.config.json 里设 "
             "\"parallel\": {\"enabled\": true}，否则按默认逐个任务实现")
    if m.get("phase") != "6":
        fail("并行只用于 Phase 6，%s 当前在 Phase %s" % (change, m.get("phase")))
    root = project.root
    if not gitutil.is_repo(root):
        fail("%s 不在 git 仓库里" % root)
    work = m.get("branch")
    if not work:
        fail("%s 没有绑定工作分支，无法确定合回哪里" % change)
    current = gitutil.current_branch(root)
    if current != work:
        fail("当前分支是 %s，%s 的工作分支是 %s；请在工作分支上运行" % (current or "（游离 HEAD）", change, work))
    tasks_rel = _rel(project, change_dir / P.TASKS)
    dirty = parallel.dirty(root, [tasks_rel])
    if dirty:
        fail("工作区有未提交改动：%s；worktree 只包含已提交的内容，请先提交" % "、".join(dirty[:5]))
    return work, tasks_rel


def _run_cmd(a, project, change, change_dir, m, cfg) -> int:
    root = project.root
    work, _ = _prepare(project, change, change_dir, m, cfg)
    meta_rel = _rel(project, change_dir / P.META)
    if not gitutil.git(["ls-files", "--", meta_rel], root):
        fail("%s 没有提交进 git：worktree 里看不到 change 状态，git hook 无法按 Phase 6 检查提交；"
             "请先提交 .openspec/" % meta_rel)
    pending = parallel.wave_branches(root, change)
    if pending:
        fail("上一波还没合回（%s）；先运行 parallel merge" % "、".join(pending))
    p = _plan(project, change_dir, m)
    if p.problems:
        return _refuse(p)
    if not p.waves:
        print("没有待做的任务，不需要并行")
        return OK
    wave = p.waves[0]
    integ = parallel.integration_branch(change)
    if parallel.branch_exists(root, integ):
        if integ in parallel.worktrees(root):
            fail("集成分支 %s 正被 worktree %s 占用：上次 merge 没有完成，先处理它"
                 % (integ, parallel.worktrees(root)[integ].as_posix()))
        if not parallel.is_ancestor(root, integ, "HEAD"):
            fail("集成分支 %s 有没合回 %s 的提交；先运行 parallel merge 或人工处理" % (integ, work))
        gitutil.git(["branch", "-f", integ, "HEAD"], root)
    else:
        gitutil.git(["branch", integ, "HEAD"], root)
    base = parallel.worktree_root(project, change)
    targets = [(i, parallel.task_branch(change, i), base / i) for i in wave]
    for tid, branch, path in targets:
        if path.exists():
            fail("%s 已存在：可能是上次留下的 worktree，确认没用后删除再运行" % path.as_posix())
        if parallel.branch_exists(root, branch):
            fail("分支 %s 已存在：可能是上次留下的，确认没用后删除再运行" % branch)
    base.mkdir(parents=True, exist_ok=True)
    for tid, branch, path in targets:
        gitutil.git(["worktree", "add", "-b", branch, str(path), integ], root)
    by_id = {t.id: t for t in p.tasks}
    rest = len(p.waves) - 1
    if a.json:
        print(json.dumps({"change": change, "integration": integ, "remainingWaves": rest,
                          "worktrees": [{"task": i, "branch": b, "path": path.as_posix(),
                                         "title": by_id[i].title, "scope": by_id[i].scope}
                                        for i, b, path in targets]}, ensure_ascii=False, indent=2))
        return OK
    print("已从集成分支 %s 建本波 %d 个 worktree：" % (integ, len(targets)))
    for tid, branch, path in targets:
        print("- %s：%s（分支 %s）" % (_describe(by_id[tid]), path.as_posix(), branch))
    print("把每个 worktree 和它的任务分别派给一个 implementation-generator：")
    print("只改自己范围内的文件，提交带 Task-Id，不写 tasks.md。")
    print("本波全部完成后运行 parallel merge。之后还有 %d 波。" % rest)
    return OK


def _task_done(cwd, base: str, tid: str) -> bool:
    for c in gitutil.commits(base, cwd):
        if taskstate.is_red(c):
            continue
        for value in c["trailers"].get("Task-Id", []):
            if tid in re.split(r"[,\s]+", value):
                return True
    return False


def _conflict(what: str, conflicts, out: str, kept) -> int:
    print("合并中止：%s" % what)
    if conflicts:
        print("冲突文件：%s" % "、".join(conflicts))
    elif out:
        print(out)
    print("已执行 git merge --abort，没有自动解决，也没有覆盖任何改动。")
    print("现场保留：")
    for line in kept:
        print("- %s" % line)
    print("交给用户或子 agent 在对应 worktree 里解决（例如把集成分支合进任务分支），然后重新运行 parallel merge；"
          "已合入的任务会自动跳过。")
    return BLOCK


def _merge_cmd(a, project, change, change_dir, m, cfg) -> int:
    root = project.root
    work, tasks_rel = _prepare(project, change, change_dir, m, cfg)
    branches = parallel.wave_branches(root, change)
    if not branches:
        fail("没有进行中的波次；先运行 parallel run")
    integ = parallel.integration_branch(change)
    if not parallel.branch_exists(root, integ):
        fail("集成分支 %s 不存在，无法合回；请人工检查分支 %s" % (integ, "、".join(branches)))
    prefix = parallel.task_branch(change, "")
    order = [t.id for t in parallel.parse_tasks(_tasks_text(change_dir))[0]]
    wave = sorted((b[len(prefix):] for b in branches),
                  key=lambda i: (order.index(i) if i in order else len(order), i))
    trees = parallel.worktrees(root)
    problems = []
    for tid in wave:
        branch = parallel.task_branch(change, tid)
        path = trees.get(branch)
        if path is None:
            problems.append("%s 的 worktree 不见了（分支 %s 还在）" % (tid, branch))
        elif parallel.dirty(path):
            problems.append("%s 的 worktree 有未提交改动：%s" % (tid, path.as_posix()))
        # Count from the work branch, not the integration branch: a worker with no commits
        # sits at the wave base, which is already "contained" in the integration branch.
        elif not _task_done(path, work, tid):
            problems.append("%s 还没有带 Task-Id: %s 的非 RED 提交" % (tid, tid))
        # Hooks can be skipped with --no-verify; tasks.md is only ever rendered by tasks-sync.
        elif tasks_rel in gitutil.git(["diff", "--name-only", "%s...%s" % (work, branch)], root).splitlines():
            problems.append("%s 的提交改了 tasks.md：worker 不能写 tasks.md，请撤销该改动" % tid)
    if problems:
        print("本波还没全部完成，暂不合并：")
        for problem in problems:
            print("- %s" % problem)
        return ERROR

    ipath = trees.get(integ)
    if ipath is None:
        ipath = parallel.worktree_root(project, change) / parallel.INTEGRATION_DIR
        if ipath.exists():
            fail("%s 已存在但不是集成分支的 worktree；确认没用后删除再运行" % ipath.as_posix())
        gitutil.git(["worktree", "add", str(ipath), integ], root)
    elif parallel.dirty(ipath):
        fail("集成分支的 worktree %s 有未提交改动，请先人工处理" % ipath.as_posix())

    kept = ["集成分支 %s：%s" % (integ, ipath.as_posix())] + [
        "%s：%s" % (tid, trees[parallel.task_branch(change, tid)].as_posix())
        for tid in wave if parallel.task_branch(change, tid) in trees]
    merged = []
    for tid in wave:
        branch = parallel.task_branch(change, tid)
        if parallel.is_ancestor(root, branch, integ):
            print("%s 已在集成分支上，跳过" % tid)
            continue
        ok, conflicts, out = parallel.merge(
            ipath, branch, ["Merge %s into %s" % (branch, integ), "Task-Id: %s" % tid])
        if not ok:
            done = "、".join(merged) or "无"
            return _conflict("%s 合入集成分支失败（本次已合入：%s）" % (tid, done), conflicts, out, kept)
        merged.append(tid)
        print("已合入 %s" % tid)

    ok, conflicts, out = parallel.merge(
        root, integ, ["Merge %s into %s" % (integ, work), "Task-Id: %s" % ", ".join(wave)])
    if not ok:
        return _conflict("集成分支合回 %s 失败" % work, conflicts, out, kept)
    print("集成分支已合回 %s" % work)

    for tid in wave:
        branch = parallel.task_branch(change, tid)
        if branch in trees:
            gitutil.git(["worktree", "remove", str(trees[branch])], root, check=False)
        gitutil.git(["branch", "-d", branch], root, check=False)
    gitutil.git(["worktree", "remove", str(ipath)], root, check=False)
    gitutil.git(["branch", "-d", integ], root, check=False)
    gitutil.git(["worktree", "prune"], root, check=False)
    left = [p.as_posix() for p in [trees.get(parallel.task_branch(change, t)) for t in wave] + [ipath]
            if p is not None and p.exists()]
    left += [b for b in parallel.wave_branches(root, change)]
    if left:
        print("以下没能清理，请人工检查后删除：%s" % "、".join(left))
    else:
        print("已清理本波 worktree 和分支")

    from . import tasks_sync
    tasks_sync.run(argparse.Namespace(apply=True, change=change))
    m = meta.load(change_dir)
    ctx = gates.GateContext(project, change, change_dir, m, cfg)
    findings, code = gates.evaluate("6.5", ctx)
    print(gates.render("6.5", findings, code))
    rest = _plan(project, change_dir, m)
    if rest.waves:
        print("还有 %d 波待做（下一波：%s）：再运行 parallel run。gate-6.5 现在拦截是预期的。"
              % (len(rest.waves), "、".join(rest.waves[0])))
        return OK
    return code


def run(a) -> int:
    project = Project.here()
    change, change_dir, m = locate.load(project, a.change)
    cfg = config.load(project)
    handler = {"plan": _plan_cmd, "run": _run_cmd, "merge": _merge_cmd}[a.action]
    return handler(a, project, change, change_dir, m, cfg)
