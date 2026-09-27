"""`spec-driven hook`. Owner: T0 (plumbing); decisions: policies/ (T6)."""


TARGETS = ["claude", "codex", "opencode"]


def register(sub):
    h = sub.add_parser("hook", help="供各平台 hook 调用（从 stdin 读事件）")
    h.add_argument("event", choices=["pre-tool", "prompt-submit"])
    h.add_argument("--runtime", required=True, choices=TARGETS)


def run(a) -> int:
    from .. import hook
    return hook.run(a.event, a.runtime)
