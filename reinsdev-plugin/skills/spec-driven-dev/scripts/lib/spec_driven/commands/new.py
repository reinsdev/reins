"""`spec-driven new`. Owner: T2. Phase 0 (design doc §7): check the git repo, create
.openspec/ and changes/<change>/, write .meta.json, invariants.json and the proposal
skeleton, create and bind the branch, install git hooks, then run gate-0."""

import datetime
import json
import re
from pathlib import Path

from .. import config, gates, gitutil, meta
from .. import project as P
from ..errors import ERROR, OK, fail
from ..project import Project

KEBAB = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
MIN_NAME = 5
TEMPLATES = Path(__file__).resolve().parents[4] / "templates"
PROPOSAL_TEMPLATE = {"feature": "proposal.md", "bugfix": "proposal-bugfix.md"}


def register(sub):
    p = sub.add_parser("new", help="Phase 0：建 change")
    p.add_argument("change", nargs="?", help="feature：用户确认的 kebab-case 名；bugfix：留空时生成 fix-<YYYYMMDD>-<slug>")
    p.add_argument("--mode", choices=["feature", "bugfix"], default="feature")
    p.add_argument("--slug", help="bugfix 的简短英文描述，用于生成名字")
    p.add_argument("--no-branch", action="store_true", help="不创建 / 切换分支")


def slugify(text: str, words: int = 5) -> str:
    parts = [p for p in re.split(r"[^a-z0-9]+", text.lower()) if p]
    return "-".join(parts[:words])


def change_name(a) -> str:
    if a.change:
        return a.change
    if a.mode != "bugfix":
        fail("feature 模式需要给出 change 名（kebab-case，≥%d 字符）" % MIN_NAME)
    slug = slugify(a.slug or "")
    if not slug:
        fail("bugfix 需要 --slug（问题的简短英文描述，如 login-500-after-redirect）")
    return "fix-%s-%s" % (datetime.date.today().strftime("%Y%m%d"), slug)


def proposal_skeleton(change: str, mode: str) -> str:
    tpl = TEMPLATES / PROPOSAL_TEMPLATE[mode]
    if not tpl.is_file():
        tpl = TEMPLATES / PROPOSAL_TEMPLATE["feature"]
    if tpl.is_file():
        text = tpl.read_text(encoding="utf-8")
        return text.replace("<change-name>", change).replace("<change>", change)
    return "# Proposal: %s\n" % change


def _bind_branch(root: Path, change: str, mode: str, create: bool) -> str:
    current = gitutil.current_branch(root)
    if not create:
        return current or ""
    want = "%s/%s" % ("fix" if mode == "bugfix" else "feat", change)
    if current == want:
        return want
    exists = gitutil.git(["branch", "--list", want], root)
    gitutil.git(["switch", want] if exists else ["switch", "-c", want], root)
    return want


def _install_git_hooks(root: Path) -> None:
    from . import githook
    install = getattr(githook, "install", None)
    if install is None:
        print("提示：git hook 尚未实现，本次未安装（护栏第 2 层暂缺）")
        return
    for f in install(root):
        print("已安装 git hook %s" % f)


def run(a) -> int:
    project = Project.here()
    if not gitutil.is_repo(project.root):
        fail("%s 不在 git 仓库里，请先 git init 并提交一次" % project.root)
    if not gitutil.git(["rev-parse", "--verify", "--quiet", "HEAD"], project.root, check=False):
        fail("仓库还没有任何提交，请先提交一次再开始")
    change = change_name(a)
    if not KEBAB.match(change) or len(change) < MIN_NAME:
        fail("change 名「%s」必须是 kebab-case（小写字母、数字、连字符）且至少 %d 个字符" % (change, MIN_NAME))
    change_dir = project.change_dir(change)
    if change_dir.exists():
        fail("change「%s」已存在；继续它用 resume，或换一个名字" % change)

    base = gitutil.head(project.root)
    branch = _bind_branch(project.root, change, a.mode, not a.no_branch)
    for d in (project.changes_dir, project.specs_dir, project.decisions_dir):
        d.mkdir(parents=True, exist_ok=True)
    change_dir.mkdir()
    m = meta.new(change, a.mode, branch, base)
    if a.mode == "bugfix":
        m["tierConfirmed"] = True  # bugfix-analysis assesses scope; see workflow §4
    with meta.lock(change_dir):
        meta.save(change_dir, m)
    (change_dir / P.INVARIANTS).write_bytes(b"{}\n")
    (change_dir / P.PROPOSAL).write_bytes(proposal_skeleton(change, a.mode).encode("utf-8"))
    print("已创建 change %s（mode=%s，分支 %s，基线 %s）" % (change, a.mode, branch or "未绑定", base[:7]))
    _install_git_hooks(project.root)

    ctx = gates.GateContext(project, change, change_dir, m, config.load(project))
    try:
        findings, code = gates.evaluate("0", ctx)
    except NotImplementedError:
        print("提示：gate-0 尚未实现，未校验")
        return OK
    print(gates.render("0", findings, code))
    return code if code != ERROR else ERROR
