"""REQ-based spec merging and reversible archive publication. Owner: T7."""

import os
import re
import shutil
import tempfile
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Dict, List, Optional

from . import gitutil, mdparse, meta, retro
from .project import (BUGFIX_ANALYSIS, CODE_REVIEW, DEPLOY_REPORT, DESIGN,
                      IMPLEMENTATION_LOG, META, PROPOSAL, QA_REPORT,
                      RETROSPECTIVE, SPEC, SPEC_REVIEW, TASKS, Project)


class ArchiveError(ValueError):
    def __init__(self, reason, check="archive-complete", evidence=""):
        super().__init__(reason)
        self.check = check
        self.evidence = evidence or reason


@dataclass
class Capability:
    name: str
    prefix: str
    requirements: Dict[str, str]
    scenarios: Dict[str, str]
    summaries: Dict[str, str]


@dataclass
class Plan:
    project: Project
    change: str
    source: Path
    destination: Path
    writes: Dict[Path, str]
    architecture_notice: bool
    metadata: dict


def _read(path):
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise ArchiveError("无法读取 %s：%s" % (path.name, exc))


def _block(lines, section, end):
    return "\n".join(lines[section.line - 1:end]).strip() + "\n"


def parse_spec(text: str) -> Dict[str, Capability]:
    """Use the shared heading tree; preserve complete REQ subtrees."""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = text.splitlines()
    root = mdparse.parse(text)
    if not root.children:
        raise ArchiveError("spec.md 缺少 Capability 标题", "specs-synced")
    capabilities = {}
    for number, section in enumerate(root.children):
        match = re.fullmatch(r"Capability:\s*.+\(`([a-z][a-z0-9]*(?:-[a-z0-9]+)*)`\)", section.title)
        if section.level != 1 or not match:
            raise ArchiveError("无效的 Capability 标题：%s" % section.title, "specs-synced")
        name = match.group(1)
        if name in capabilities:
            raise ArchiveError("重复 Capability：%s" % name, "specs-synced", name)
        end = root.children[number + 1].line - 1 if number + 1 < len(root.children) else len(lines)
        first_child = section.children[0].line - 1 if section.children else end
        prefix = _block(lines, section, first_child)
        if number == 0 and root.body.strip():
            prefix = root.body.rstrip("\n") + "\n" + prefix
        requirements, scenarios, summaries = {}, {}, {}
        for index, child in enumerate(section.children):
            child_end = section.children[index + 1].line - 1 if index + 1 < len(section.children) else end
            block = _block(lines, child, child_end)
            ids = mdparse.ids(child.title, "REQ")
            if child.level != 2:
                raise ArchiveError("能力章节必须使用二级标题：%s" % child.title, "specs-synced")
            if not ids:
                if child.title.startswith(("REQ-", "SC-")):
                    raise ArchiveError("无效的需求标题：%s" % child.title, "specs-synced")
                if mdparse.find_all(child, mdparse.ID_PATTERNS["REQ"]) or mdparse.find_all(child, mdparse.ID_PATTERNS["SC"]):
                    raise ArchiveError("REQ/SC 必须位于能力的行为章节", "specs-synced")
                if child.title in summaries:
                    raise ArchiveError("重复汇总章节：%s" % child.title, "specs-synced")
                summaries[child.title] = block
                continue
            req = ids[0]
            if len(ids) != 1 or not child.title.startswith(req + ":") or not req.startswith("REQ-%s-" % name):
                raise ArchiveError("REQ 与 Capability 不一致：%s" % child.title, "specs-synced", child.title)
            if req.rsplit("-", 1)[0] != "REQ-%s" % name or req in requirements:
                raise ArchiveError("重复或错误的 REQ：%s" % req, "specs-synced", req)
            requirements[req] = block
            found = mdparse.find_all(child, mdparse.ID_PATTERNS["SC"])
            if not found:
                raise ArchiveError("REQ 缺少 SC：%s" % req, "specs-synced", req)
            for scenario in found:
                sc_ids = mdparse.ids(scenario.title, "SC")
                sc = sc_ids[0]
                if (len(sc_ids) != 1 or scenario.level != 3 or scenario not in child.children
                        or not scenario.title.startswith(sc + ":") or sc.rsplit("-", 1)[0] != "SC-%s" % name):
                    raise ArchiveError("无效的 SC：%s" % scenario.title, "specs-synced", scenario.title)
                if sc in scenarios:
                    raise ArchiveError("SC ID 冲突：%s" % sc, "specs-synced", sc)
                scenarios[sc] = req
            # Reject misplaced or malformed headings instead of silently dropping them.
            for descendant in mdparse.find_all(child, r"^(REQ-|SC-)"):
                if descendant is not child and descendant not in found:
                    raise ArchiveError("无效的 REQ/SC 层级：%s" % descendant.title, "specs-synced")
        if not requirements:
            raise ArchiveError("能力没有 REQ：%s" % name, "specs-synced", name)
        capabilities[name] = Capability(name, prefix, requirements, scenarios, summaries)
    return capabilities


def _table_text(table, rows):
    lines = ["| %s |" % " | ".join(table.header),
             "| %s |" % " | ".join("---" for _ in table.header)]
    lines.extend("| %s |" % " | ".join(row[key] for key in table.header) for row in rows)
    return "\n".join(lines)


def _merge_prose(old, new, title):
    if not new or old == new:
        return old
    if not old:
        return new
    raise ArchiveError("汇总文字无法安全自动合并：%s" % title, "specs-synced", title)


def _table_context(body, table):
    lines = body.splitlines()
    start = table.line - 1
    end = start + 2 + len(table.rows)
    return "\n".join(lines[:start]).strip(), "\n".join(lines[end:]).strip()


def _merge_summary(old, new, replaced):
    """Keep unaffected SC rows; reject prose merges that would lose information."""
    if old.strip() == new.strip():
        return old
    old_tree, new_tree = mdparse.parse(old), mdparse.parse(new)
    left, right = old_tree.children[0], new_tree.children[0]
    if not right.children and right.body.strip().rstrip("。.") == "本次不变更":
        return old
    old_tables, new_tables = mdparse.tables(left.body), mdparse.tables(right.body)
    if old_tables or new_tables:
        if len(old_tables) != 1 or len(new_tables) != 1 or old_tables[0].header != new_tables[0].header:
            raise ArchiveError("汇总表结构不一致：%s" % left.title, "specs-synced", left.title)
        table, incoming = old_tables[0], new_tables[0]
        if "关联 SC" not in table.header:
            raise ArchiveError("汇总表缺少关联 SC：%s" % left.title, "specs-synced", left.title)
        rows = []
        for row in table.rows:
            related = set(mdparse.ids(row["关联 SC"], "SC"))
            if related & replaced:
                if related - replaced and row not in incoming.rows:
                    raise ArchiveError("汇总行涉及未替换的 SC，需人工拆分：%s" % row["关联 SC"], "specs-synced")
            else:
                rows.append(row)
        rows.extend(row for row in incoming.rows if row not in rows)
        left_before, left_after = _table_context(left.body, table)
        right_before, right_after = _table_context(right.body, incoming)
        before = _merge_prose(left_before, right_before, left.title)
        after = _merge_prose(left_after, right_after, left.title)
        body = "\n\n".join(part for part in (before, _table_text(table, rows), after) if part)
    elif left.body.strip() == right.body.strip():
        body = left.body.strip()
    elif not left.body.strip() or left.body.strip().rstrip("。.") == "本次不变更":
        body = right.body.strip()
    elif not right.body.strip():
        body = left.body.strip()
    else:
        raise ArchiveError("汇总文字无法安全自动合并：%s" % left.title, "specs-synced", left.title)
    children = {child.title: child for child in left.children}
    for child in right.children:
        if child.title in children:
            previous = children[child.title]
            old_text = "#" * previous.level + " " + previous.title + "\n" + previous.text()
            new_text = "#" * child.level + " " + child.title + "\n" + child.text()
            children[child.title] = _merge_summary(old_text, new_text, replaced)
        else:
            children[child.title] = child
    parts = ["#" * left.level + " " + left.title]
    if body:
        parts.append(body)
    for child in children.values():
        parts.append(child.strip() if isinstance(child, str) else
                     ("#" * child.level + " " + child.title + "\n" + child.text()).strip())
    return "\n\n".join(parts) + "\n"


def merge_specs(existing: Dict[str, str], delta: str) -> Dict[str, str]:
    """Return changed capability files, replacing equal REQs and appending new ones."""
    changes = parse_spec(delta)
    merged = {}
    for name, incoming in changes.items():
        if name not in existing:
            merged[name] = "\n".join([incoming.prefix] + list(incoming.requirements.values()) + list(incoming.summaries.values()))
            continue
        parsed = parse_spec(existing[name])
        if set(parsed) != {name}:
            raise ArchiveError("主 spec 的 Capability 与文件名不一致：%s" % name, "specs-synced", name)
        previous = parsed[name]
        for sc, owner in incoming.scenarios.items():
            if sc in previous.scenarios and previous.scenarios[sc] != owner:
                raise ArchiveError("SC ID 冲突：%s（%s / %s）" % (sc, previous.scenarios[sc], owner), "specs-synced", sc)
        replaced = {sc for sc, owner in previous.scenarios.items() if owner in incoming.requirements}
        requirements = dict(previous.requirements)
        requirements.update(incoming.requirements)
        summaries = dict(previous.summaries)
        for title, block in incoming.summaries.items():
            summaries[title] = _merge_summary(summaries[title], block, replaced) if title in summaries else block
        text = "\n".join([previous.prefix] + list(requirements.values()) + list(summaries.values()))
        parse_spec(text)
        merged[name] = text
    return merged


def required_artifacts(metadata: dict) -> List[str]:
    required = [META, PROPOSAL, TASKS, IMPLEMENTATION_LOG, CODE_REVIEW]
    for phase, name in (("2", DESIGN), ("3", SPEC), ("5", SPEC_REVIEW), ("7", QA_REPORT), ("8.5", DEPLOY_REPORT)):
        if metadata.get("phaseStatus", {}).get(phase) != "skipped":
            required.append(name)
    if metadata.get("mode") == "bugfix":
        required.append(BUGFIX_ANALYSIS)
    return required


def _adr(project, change, source, destination):
    design = source / DESIGN
    if not design.is_file():
        return None, False
    text = _read(design)
    choice = mdparse.find(mdparse.parse(text), "final-choice")
    if choice is None or not choice.text().strip() or re.search(r"<[^<>\n]+>", choice.text()) or "待确认" in choice.text():
        raise ArchiveError("design.md 缺少已确认的最终选择与理由")
    numbers = []
    for path in project.decisions_dir.glob("*.md"):
        prefix = path.name.split("-", 1)[0]
        if prefix.isdigit():
            numbers.append(int(prefix))
    target = project.decisions_dir / ("%04d-%s.md" % (max(numbers, default=0) + 1, change))
    link = "../changes/archive/%s/%s" % (destination.name, DESIGN)
    content = "# ADR %04d: %s\n\n来源：[design.md](%s)\n\n## 推荐方案与最终决策\n\n%s\n" % (
        max(numbers, default=0) + 1, change, link, choice.text().strip())
    notice = any(word in text for word in ("层边界", "依赖方向", "只依赖", "禁止依赖"))
    return (target, content), notice


def build_plan(project: Project, change: str, source: Path, metadata: dict,
               day: Optional[date] = None) -> Plan:
    """Build a read-only plan; all validation precedes publication."""
    if not re.fullmatch(r"[a-z][a-z0-9]*(?:-[a-z0-9]+)*", change):
        raise ArchiveError("无效的 change 名称")
    if source != project.change_dir(change) or not source.is_dir():
        raise ArchiveError("活动 change 不存在：%s" % change)
    if metadata.get("change") != change:
        raise ArchiveError("change 与元数据不一致")
    destination = project.archive_dir / ("%s-%s" % ((day or date.today()).isoformat(), change))
    if destination.exists():
        raise ArchiveError("归档目录已存在：%s" % destination.name)
    missing = [name for name in required_artifacts(metadata) if not (source / name).is_file()]
    if missing:
        raise ArchiveError("归档工件缺失：%s" % "、".join(missing))
    if not retro.verify(source):
        raise ArchiveError("retrospective.md 校验失败，请恢复 CLI 记录")
    writes = {}
    if (source / SPEC).is_file():
        delta = _read(source / SPEC)
        names = parse_spec(delta)
        existing = {name: _read(project.specs_dir / (name + ".md"))
                    for name in names if (project.specs_dir / (name + ".md")).exists()}
        for name, text in merge_specs(existing, delta).items():
            writes[project.specs_dir / (name + ".md")] = text
    adr, notice = _adr(project, change, source, destination)
    if adr:
        writes[adr[0]] = adr[1]
    names = {path.stem for path in project.specs_dir.glob("*.md") if path.name != "README.md"}
    names.update(path.stem for path in writes if path.parent == project.specs_dir)
    writes[project.specs_dir / "README.md"] = "# Specs\n\n" + "".join(
        "- [%s](%s.md)\n" % (name, name) for name in sorted(names))
    plan = Plan(project, change, source, destination, writes, notice, metadata)
    _retrospective(plan)
    _index_state(project)
    return plan


def _retrospective(plan):
    path = plan.source / RETROSPECTIVE
    prior = _read(path) if path.exists() else "# Retrospective: %s\n" % plan.change
    if plan.metadata.get("phaseStatus", {}).get("8.5") == "skipped":
        deployment = "本次跳过本地部署。"
    else:
        section = mdparse.find(mdparse.parse(_read(plan.source / DEPLOY_REPORT)), "conclusion")
        if section is None or not section.text().strip():
            raise ArchiveError("deploy-report.md 缺少部署结论")
        deployment = section.text().strip()
    return prior + "\n## 部署结论\n\n%s\n\n## 复盘小结\n\nchange %s 已归档；规格和决策已同步。\n原有人工确认记录、档位变更记录和待优化清单已保留。\n" % (deployment, plan.change)


@contextmanager
def archive_lock(project):
    """Serialize archives across changes sharing the same spec and ADR namespace."""
    path = project.openspec / ".archive.lock"
    try:
        descriptor = os.open(str(path), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError:
        raise ArchiveError("另一个归档正在进行，请稍后重试")
    try:
        os.close(descriptor)
        yield
    finally:
        path.unlink()


def _file_snapshot(directory):
    return {path.relative_to(directory): path.read_bytes() for path in directory.rglob("*") if path.is_file()}


def _index_state(project):
    visible = set(gitutil.git(["diff", "--cached", "--name-only", "-z", "--ita-visible-in-index"], project.root).split("\0"))
    ordinary = set(gitutil.git(["diff", "--cached", "--name-only", "-z", "--ita-invisible-in-index"], project.root).split("\0"))
    intent = sorted(visible - ordinary - {""})
    missing = [name for name in intent if not (project.root / name).exists()]
    if missing:
        raise ArchiveError("暂存区含已删除的 intent-to-add 文件，请先恢复或清理标记：%s" % "、".join(missing))
    flags = [entry for entry in gitutil.git(["ls-files", "-v", "-z"], project.root).split("\0") if entry]
    assumed = [entry[2:] for entry in flags if entry[0].islower()]
    skipped = [entry[2:] for entry in flags if entry[0].upper() == "S"]
    return intent, assumed, skipped


@contextmanager
def publish(plan: Plan):
    """Stage complete outputs, then publish; restore files and index on failure."""
    source, project = plan.source, plan.project
    original = _file_snapshot(source)
    original_dirs = [path.relative_to(source) for path in source.rglob("*") if path.is_dir()]
    before = {path: path.read_bytes() if path.is_file() else None for path in plan.writes}
    created_dirs = []
    with tempfile.TemporaryDirectory(prefix=".archive-", dir=str(project.openspec)) as temp:
        temporary = Path(temp)
        staged = temporary / "change"
        shutil.copytree(str(source), str(staged))
        retrospective = _retrospective(plan)
        (staged / RETROSPECTIVE).write_text(retrospective, encoding="utf-8")
        (staged / retro.SIG_FILE).write_text(retro.signature(retrospective) + "\n", encoding="utf-8")
        def completed(data):
            data["phase"] = "9"
            data["phaseStatus"]["9"] = "passed"
        meta.update(staged, completed)
        outputs = dict(plan.writes)
        for name in (RETROSPECTIVE, retro.SIG_FILE, META):
            outputs[source / name] = _read(staged / name)
        prepared = {}
        for index, (target, text) in enumerate(outputs.items()):
            location = temporary / ("output-%d" % index)
            location.write_text(text, encoding="utf-8")
            prepared[target] = location
        if original != _file_snapshot(source) or any(
                (path.read_bytes() if path.is_file() else None) != old for path, old in before.items()):
            raise ArchiveError("归档输入已变化，请重试")
        intent, assumed, skipped = _index_state(project)
        index_tree = gitutil.git(["write-tree"], project.root)
        try:
            for target, location in prepared.items():
                parent = target.parent
                while not parent.exists():
                    created_dirs.append(parent)
                    parent = parent.parent
                target.parent.mkdir(parents=True, exist_ok=True)
                os.replace(str(location), str(target))
            if not project.archive_dir.exists():
                project.archive_dir.mkdir(parents=True)
                created_dirs.append(project.archive_dir)
            gitutil.git(["mv", "--", source.relative_to(project.root).as_posix(),
                         plan.destination.relative_to(project.root).as_posix()], project.root)
            yield plan.destination
        except BaseException:
            # git mv can fail after moving some entries; restore the exact source snapshot.
            if plan.destination.exists():
                shutil.rmtree(str(plan.destination))
            source.mkdir(parents=True, exist_ok=True)
            for relative in original_dirs:
                (source / relative).mkdir(parents=True, exist_ok=True)
            for path in source.rglob("*"):
                if path.is_file() and path.relative_to(source) not in original:
                    path.unlink()
            for relative, content in original.items():
                path = source / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(content)
            for path, content in before.items():
                if content is None:
                    if path.exists():
                        path.unlink()
                else:
                    path.write_bytes(content)
            gitutil.git(["read-tree", index_tree], project.root)
            if intent:
                gitutil.git(["add", "-f", "-N", "--"] + intent, project.root)
            if assumed:
                gitutil.git(["update-index", "--assume-unchanged", "--"] + assumed, project.root)
            if skipped:
                gitutil.git(["update-index", "--skip-worktree", "--"] + skipped, project.root)
            for directory in sorted(set(created_dirs), key=lambda p: len(p.parts), reverse=True):
                if directory.is_dir() and not any(directory.iterdir()):
                    directory.rmdir()
            raise
