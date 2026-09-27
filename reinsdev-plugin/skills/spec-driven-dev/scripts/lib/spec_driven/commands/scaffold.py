"""`spec-driven scaffold <artifact>`. Owner: T18. Copy the template of an artifact of the current
phase into the change directory (design, spec, tasks, bugfix-analysis, implementation-log,
deploy-report). See docs/dev/tasks.md T18.

Only the current phase's artifact may be generated: an earlier phase's file is frozen, a later
one would skip its gate. An existing file is never overwritten.
"""

import os
import tempfile
from pathlib import Path

from .. import locate, meta
from .. import project as P
from ..errors import OK, fail
from ..project import Project

ARTIFACTS = ["bugfix-analysis", "design", "spec", "tasks", "implementation-log", "deploy-report"]

TEMPLATES = Path(__file__).resolve().parents[4] / "templates"

# artifact -> (phase that writes it, file in the change directory)
PHASE_OF = {
    "bugfix-analysis": ("1", P.BUGFIX_ANALYSIS),
    "design": ("2", P.DESIGN),
    "spec": ("3", P.SPEC),
    "tasks": ("4", P.TASKS),
    "implementation-log": ("6", P.IMPLEMENTATION_LOG),
    "deploy-report": ("8.5", P.DEPLOY_REPORT),
}


def register(sub):
    p = sub.add_parser("scaffold", help="按模板生成当前 Phase 工件的骨架")
    p.add_argument("artifact", choices=ARTIFACTS)
    p.add_argument("--change")


def render(artifact: str, change: str) -> str:
    """Template text with the change name filled in, as `new` does for proposal.md."""
    tpl = TEMPLATES / PHASE_OF[artifact][1]
    try:
        text = tpl.read_text(encoding="utf-8")
    except OSError:
        fail("找不到模板 %s，插件安装可能不完整" % tpl.as_posix())
    return text.replace("<change-name>", change).replace("<change>", change)


def _write_new(path: Path, text: str) -> None:
    """Unique temp file + os.replace, so a reader never sees half a skeleton."""
    fd, tmp = tempfile.mkstemp(prefix="." + path.name + ".", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(text.encode("utf-8"))
        os.replace(tmp, str(path))
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def run(a) -> int:
    project = Project.here()
    change, change_dir, m = locate.load(project, a.change)
    phase, name = PHASE_OF[a.artifact]
    if a.artifact == "bugfix-analysis" and m["mode"] != "bugfix":
        fail("bugfix-analysis.md 只用于 bugfix 模式；%s 是 %s 模式" % (change, m["mode"]))
    if m["phase"] != phase:
        if meta.PHASES.index(m["phase"]) > meta.PHASES.index(phase):
            why = "Phase %s 的工件已冻结，要改请先 retry %s" % (phase, phase)
        else:
            why = "还没到 Phase %s，先通过前面的验证门" % phase
        fail("%s 属于 Phase %s，当前是 Phase %s：%s" % (name, phase, m["phase"], why))
    path = change_dir / name
    rel = path.relative_to(project.root).as_posix()
    text = render(a.artifact, change)
    # The change lock keeps two instances from both passing the existence check.
    with meta.lock(change_dir):
        if path.exists():
            fail("%s 已存在，不覆盖；直接在原文件上填写" % rel)
        _write_new(path, text)
    print("已生成 %s（模板 templates/%s），按模板填写占位内容" % (rel, name))
    return OK
