"""gate-9: verify archived artifacts and the merged master specs. Owner: T7."""

from typing import List

from .. import archive, mdparse, meta
from ..project import DESIGN, META, RETROSPECTIVE, SPEC
from . import Finding, GateContext, evaluate


def check(ctx: GateContext) -> List[Finding]:
    findings = []
    def block(check_id, reason, evidence, location="", locked=False):
        findings.append(Finding("BLOCK", check_id, reason, location=location,
                                evidence=evidence, locked=locked))

    # The framework applies gate-8.9's fingerprint-bound waiver before this result.
    try:
        uat, code = evaluate("8.9", ctx)
    except (NotImplementedError, OSError, UnicodeError, ValueError):
        uat, code = [], 3
        block("uat", "用户验收门不可用或无法解析", "gate-8.9-unavailable", locked=True)
    if code == 3:
        for item in uat:
            if item.level == "BLOCK" and not item.waived:
                block("uat", "用户验收门未通过：%s" % item.reason, item.evidence or item.reason, locked=True)
    if ctx.project.change_dir(ctx.change).exists():
        block("change-moved", "活动 change 目录仍存在", ctx.change)
    directory = ctx.change_dir
    if directory.parent != ctx.project.archive_dir or not directory.is_dir():
        block("archive-complete", "change 尚未迁入归档目录", ctx.change)
        return findings
    suffix = "-" + ctx.change
    if not directory.name.endswith(suffix):
        block("archive-complete", "归档目录与 change 名称不一致", ctx.change)
    missing = [name for name in archive.required_artifacts(ctx.meta) if not (directory / name).is_file()]
    if missing:
        block("archive-complete", "归档工件缺失：%s" % "、".join(missing), ",".join(sorted(missing)))
    try:
        stored = meta.load(directory)
        if stored.get("change") != ctx.change or stored.get("phase") != "9":
            block("archive-complete", "归档元数据与 change 或 Phase 不一致", ctx.change, META)
    except (SystemExit, OSError, ValueError):
        block("archive-complete", "归档元数据缺失或无法解析", META, META)
    if not (directory / RETROSPECTIVE).is_file():
        block("retrospective", "归档缺少 retrospective.md", RETROSPECTIVE, RETROSPECTIVE)
    if (directory / DESIGN).is_file():
        try:
            choice = mdparse.find(mdparse.parse((directory / DESIGN).read_text(encoding="utf-8")), "final-choice")
            link = "../changes/archive/%s/%s" % (directory.name, DESIGN)
            records = [path.read_text(encoding="utf-8") for path in ctx.project.decisions_dir.glob("*-" + ctx.change + ".md")]
            if choice is None or not any(link in record and choice.text().strip() in record for record in records):
                block("archive-complete", "归档缺少对应的 ADR 决策记录", DESIGN)
        except (OSError, UnicodeError, ValueError):
            block("archive-complete", "ADR 决策记录无法读取", DESIGN)
    if (directory / SPEC).is_file():
        try:
            delta = (directory / SPEC).read_text(encoding="utf-8")
            changes = archive.parse_spec(delta)
            for name, incoming in changes.items():
                target = ctx.project.specs_dir / (name + ".md")
                master = target.read_text(encoding="utf-8")
                parsed = archive.parse_spec(master)
                if set(parsed) != {name}:
                    raise archive.ArchiveError("主 spec Capability 与文件名不一致：%s" % name)
                expected = archive.parse_spec(archive.merge_specs({name: master}, delta)[name])[name]
                if expected.summaries != parsed[name].summaries:
                    block("specs-synced", "主 spec 汇总节尚未同步：%s" % name, name)
                for req, text in incoming.requirements.items():
                    if parsed[name].requirements.get(req) != text:
                        block("specs-synced", "主 spec 尚未同步 %s" % req, req,
                              target.relative_to(ctx.project.root).as_posix())
            index = (ctx.project.specs_dir / "README.md").read_text(encoding="utf-8")
            for name in changes:
                if "(%s.md)" % name not in index:
                    block("specs-synced", "specs 索引缺少 %s" % name, name)
        except (archive.ArchiveError, OSError, UnicodeError, ValueError) as exc:
            block("specs-synced", "主 specs 同步校验失败：%s" % exc, str(exc))
    return findings
