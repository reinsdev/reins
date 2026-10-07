"""Check Phase 4 task breakdown. Owner: T3.

Checks:
- tasks-readable: require a readable task artifact.
- tasks-present: require at least one checkbox task.
- task-identifiers: require unique valid task IDs.
- task-estimate: require a positive estimate no greater than two hours.
- task-order: require layer order and dependencies on earlier tasks.
- task-link: require existing SCs, skipped-feature ACs or bugfix change points.
- task-sources: require readable, populated link targets.
- ac-covered: require every skipped-feature AC to be covered by a task.
- bugfix-regression: require the dedicated automated regression task.
"""

import json
import re
from typing import List

from . import Finding, GateContext
from .. import mdparse
from ..project import BUGFIX_ANALYSIS, PROPOSAL, SPEC, TASKS


def _sections(root):
    yield root
    for child in root.children:
        yield from _sections(child)


def _fields(text):
    fields = {}
    for part in text.replace(";", "；").split("；")[1:]:
        key, sep, value = part.replace(":", "：", 1).partition("：")
        if sep:
            fields.setdefault(key.strip(), []).append(value.strip())
    return {key: values[0] if len(values) == 1 else "" for key, values in fields.items()}


def _task_id(text):
    prefix = text.split(None, 1)[0].rstrip(".:：。") if text.strip() else ""
    return prefix if mdparse.ids(prefix, "TASK") == [prefix] else ""


def check(ctx: GateContext) -> List[Finding]:
    findings = []

    def add(name, reason, evidence, line=None, file=TASKS, fix="按 tasks.md 模板补全任务及其依赖和关联"):
        findings.append(Finding(
            "BLOCK", name, reason, file + (":%d" % line if line else ""), fix,
            json.dumps(evidence, ensure_ascii=False, sort_keys=True)))

    try:
        root = mdparse.parse((ctx.change_dir / TASKS).read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValueError) as exc:
        add("tasks-readable", "无法读取或解析 tasks.md", type(exc).__name__)
        return findings
    layers = ("foundation", "domain-layer", "application-layer", "adapter-layer", "test-layer")
    layer_sections = [mdparse.find(root, key) for key in layers]
    records = []
    seen = set()
    last_layer = -1
    for section in _sections(root):
        layer = next((i for i, s in enumerate(layer_sections) if s is section), None)
        for box in mdparse.checkboxes(section.body):
            identifier = _task_id(box.text)
            line = section.line + box.line
            fields = _fields(box.text)
            records.append((identifier, fields, box.text))
            if not identifier or identifier in seen:
                add("task-identifiers", "每个任务须有唯一 T 编号或 T-regression",
                    box.text, line)
            estimate = fields.get("预估", "")
            number = re.fullmatch(r"([0-9]+(?:\.[0-9]+)?)\s*(小时|h|H|分钟|min)?", estimate)
            hours = float(number.group(1)) if number else 0
            if number and number.group(2) in ("分钟", "min"):
                hours /= 60
            if not number or not 0 < hours <= 2:
                add("task-estimate", "任务须填写大于 0 且不超过 2 小时的预估",
                    {"task": identifier or box.text, "estimate": estimate}, line)
            dependency = fields.get("依赖", "")
            dep_ids = mdparse.ids(dependency, "TASK")
            residue = dependency
            for dep in sorted(dep_ids, key=len, reverse=True):
                residue = residue.replace(dep, "")
            valid_deps = (dependency == "无" or (
                bool(dep_ids) and not residue.strip(" ,，、")
                and set(dep_ids).issubset(seen) and identifier not in dep_ids))
            if layer is None or layer < last_layer or not valid_deps:
                add("task-order", "任务须按 Foundation → Domain → App → Adapter → Test 排列，依赖须指向先前任务",
                    {"task": identifier or box.text, "layer": section.title, "dependencies": dependency}, line)
            if layer is not None:
                last_layer = max(last_layer, layer)
            if identifier:
                seen.add(identifier)
    if not records:
        add("tasks-present", "tasks.md 至少须有一个任务", "no-tasks")

    skipped_spec = bool((ctx.meta.get("skipped") or {}).get("3"))
    bugfix_links = ctx.meta.get("mode") == "bugfix" and skipped_spec
    ac_links = ctx.meta.get("mode") == "feature" and skipped_spec
    source = BUGFIX_ANALYSIS if bugfix_links else PROPOSAL if ac_links else SPEC
    try:
        source_root = mdparse.parse((ctx.change_dir / source).read_text(encoding="utf-8"))
        if bugfix_links:
            section = mdparse.find(source_root, "change-points")
            targets = {r.get("修改点", "").strip() for table in mdparse.tables(section.body if section else "")
                       for r in table.rows if r.get("修改点", "").strip()
                       and "<" not in r.get("修改点", "")}
        elif ac_links:
            sections = [section for section in _sections(source_root)
                        if mdparse.find(section, "acceptance-criteria") is section]
            ac_ids = [r.get("AC", "").strip() for section in sections for table in mdparse.tables(section.text())
                      for r in table.rows]
            if len(sections) != 1:
                add("task-sources", "proposal.md 验收标准须有且仅有一个章节",
                    {"sections": [section.title for section in sections], "acs": ac_ids}, file=source)
            targets = {identifier for identifier in ac_ids if mdparse.ids(identifier, "AC") == [identifier]}
            if len(targets) != len(ac_ids):
                add("task-sources", "proposal.md 验收标准须使用有效且唯一的 AC 编号", ac_ids, file=source)
        else:
            targets = {identifier for section in mdparse.find_all(source_root, mdparse.ID_PATTERNS["SC"])
                       for identifier in mdparse.ids(section.title, "SC") if section.level == 3}
        if not targets:
            reason = "proposal.md 验收标准没有可用的 AC" if ac_links else "任务关联来源没有可用的 SC 或修改点"
            add("task-sources", reason, source, file=source)
    except (OSError, UnicodeError, ValueError) as exc:
        targets = set()
        add("task-sources", "无法读取或解析任务关联来源", [source, type(exc).__name__], file=source)
    covered = set()
    for identifier, fields, text in records:
        value = fields.get("关联", "")
        if bugfix_links:
            links = [v.strip() for v in value.replace("、", ",").replace("，", ",").split(",") if v.strip()]
        else:
            links = mdparse.ids(value, "AC" if ac_links else "SC")
        valid_value = True
        if ac_links:
            residue = value
            for link in sorted(links, key=len, reverse=True):
                residue = residue.replace(link, "")
            valid_value = not residue.strip(" ,，、\t")
        covered.update(links)
        if not links or not valid_value or not set(links).issubset(targets):
            reason = ("每个任务须关联 proposal.md 验收标准中已定义的 AC" if ac_links
                      else "每个任务须关联已定义的 SC；bugfix 跳过 spec 时关联修改点")
            add("task-link", reason,
                {"task": identifier or text, "links": value, "unknown": sorted(set(links) - targets)})
    if ac_links and targets - covered:
        add("ac-covered", "proposal.md 每条 AC 至少须被一个任务覆盖", sorted(targets - covered),
            fix="为未覆盖的 AC 增加任务或补全任务关联")
    if ctx.meta.get("mode") == "bugfix" and not any(
            identifier == "T-regression" and "自动化回归测试" in text
            for identifier, fields, text in records):
        add("bugfix-regression", "bugfix 必须有 T-regression 自动化回归测试任务",
            "missing-T-regression", fix="增加 T-regression 并写明要覆盖的场景")
    return findings
