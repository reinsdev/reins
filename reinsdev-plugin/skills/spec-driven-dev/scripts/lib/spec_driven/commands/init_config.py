"""`spec-driven init-config`. Owner: T5. 首次接入（§6.5）：生成 .openspec/.config.json 的 quality 块，跑全部检查生成 quality-baseline.json。"""

from ..errors import unavailable


def register(sub):
    p = sub.add_parser("init-config", help="生成质量门配置与存量基线")
    p.add_argument("--java", action="store_true", required=True)
    p.add_argument("--dry-run", action="store_true")


def run(a) -> int:
    return unavailable("init-config")
