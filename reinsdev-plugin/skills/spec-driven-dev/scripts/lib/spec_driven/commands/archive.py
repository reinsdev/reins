"""`spec-driven archive`: prepare, publish and verify Phase 9. Owner: T7."""

from .. import archive, config, gates, locate, meta
from ..errors import BLOCK, OK, fail, unavailable
from ..project import Project


def register(sub):
    p = sub.add_parser("archive", help="Phase 9：归档 change")
    p.add_argument("--change")
    p.add_argument("--dry-run", action="store_true")


class _Rejected(Exception):
    pass


def _context(project, change, directory):
    return gates.GateContext(project, change, directory, meta.load(directory), config.load(project))


def _plan_output(plan):
    print("归档计划：%s" % plan.change)
    for path in plan.writes:
        print("  更新 %s" % path.relative_to(plan.project.root).as_posix())
    print("  补全部署结论与复盘小结，保留已有人工确认和待优化记录")
    print("  git mv %s → %s" % (plan.source.relative_to(plan.project.root).as_posix(),
                                 plan.destination.relative_to(plan.project.root).as_posix()))
    if plan.architecture_notice:
        print("提示：design.md 含层边界或依赖方向约束，请确认是否更新 architecture.md §4。")


def run(a) -> int:
    project = Project.here()
    change, source, metadata = locate.load(project, a.change)
    try:
        ctx = _context(project, change, source)
        findings, code = gates.evaluate("8.9", ctx)
        print(gates.render("8.9", findings, code))
        if code == BLOCK:
            return BLOCK
        if a.dry_run:
            plan = archive.build_plan(project, change, source, metadata)
            _plan_output(plan)
            print("只读预览完成，未写入文件。")
            return OK
        with archive.archive_lock(project):
            plan = archive.build_plan(project, change, source, meta.load(source))
            _plan_output(plan)
            try:
                with archive.publish(plan) as destination:
                    findings, code = gates.evaluate("9", _context(project, change, destination))
                    print(gates.render("9", findings, code))
                    if code == BLOCK:
                        raise _Rejected()
            except _Rejected:
                print("归档校验未通过，已恢复原工件与暂存区。")
                return BLOCK
        print("已归档：%s" % plan.destination.relative_to(project.root).as_posix())
        return code
    except NotImplementedError:
        return unavailable("gate-8.9")
    except archive.ArchiveError as exc:
        finding = gates.Finding("BLOCK", exc.check, str(exc), evidence=exc.evidence)
        print(gates.render("9", [finding], BLOCK))
        return BLOCK
    except (OSError, UnicodeError, ValueError) as exc:
        fail("归档失败：%s" % exc)
