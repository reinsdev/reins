"""`spec-driven gate <id|all>`. Owner: T0. Loads the change and delegates to gates/.
`all` runs every gate up to the current phase and returns the worst exit code."""

from .. import config, gates, locate, meta
from ..errors import BLOCK, ERROR, OK, WARN
from ..project import Project


def register(sub):
    p = sub.add_parser("gate", help="运行验证门：0 放行 / 2 告警 / 3 拦截")
    p.add_argument("gate", help="门编号（%s）或 all" % " / ".join(meta.GATES))
    p.add_argument("--change")
    p.add_argument("--strict", action="store_true", help="WARN 也按 BLOCK 处理")
    p.add_argument("--json", action="store_true")
    p.add_argument("--task", help="gate 6：只检查这个任务")


def _worst(codes):
    for c in (ERROR, BLOCK, WARN):
        if c in codes:
            return c
    return OK


def run(a) -> int:
    project = Project.here()
    change = locate.resolve(project, a.change)
    change_dir = project.change_dir(change)
    m = meta.load(change_dir)
    ctx = gates.GateContext(project, change, change_dir, m, config.load(project), a.strict,
                            {"task": a.task} if a.task else {})
    if a.gate == "all":
        current = meta.GATES.index(m["phase"]) if m.get("phase") in meta.GATES else 0
        ids = meta.GATES[:current + 1]
    elif a.gate in meta.GATES:
        ids = [a.gate]
    else:
        print("reins: 没有 gate %s（可选 %s、all）" % (a.gate, " / ".join(meta.GATES)))
        return ERROR
    codes = []
    for g in ids:
        try:
            findings, code = gates.evaluate(g, ctx)
        except NotImplementedError:
            print("reins: gate-%s 尚未实现（该能力不可用）" % g)
            codes.append(ERROR)
            continue
        print(gates.to_json(g, findings, code) if a.json else gates.render(g, findings, code))
        codes.append(code)
    return _worst(codes)
