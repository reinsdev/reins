"""`spec-driven waive`. Owner: T6. 人工放行（§6.6）：重跑 gate 取当前指纹，grants.consume 成功才写 retro.append_waiver；无授权时拒绝并说明口令。没有提示词 hook 的平台退回 TTY 确认（输入 change 名）。"""

from ..errors import unavailable


def register(sub):
    p = sub.add_parser("waive", help="人工放行一次拦截（需用户本人确认）")
    p.add_argument("gate")
    p.add_argument("check")
    p.add_argument("--reason", required=True)
    p.add_argument("--change")


def run(a) -> int:
    return unavailable("waive")
