"""Tier recommendation (workflow §2.4). Owner: T2.

A transparent point score over the artifacts written so far, so `complexity show`
can explain itself and gates 2 / 3 can recheck with the same rules. Only a
recommendation: the user decides, and a confirmed tier is never lowered here.
"""

import re
from pathlib import Path
from typing import List, Tuple

from . import mdparse
from . import project as P

# (points, reason, pattern). Patterns run case-insensitively over the artifact text.
KEYWORD_RULES = [
    (1, "涉及表结构或数据迁移", r"DDL|建表|新增表|加字段|索引|迁移|flyway|alter\s+table"),
    (1, "涉及新增或修改接口", r"接口|API|endpoint|controller|\bPOST\b|\bPUT\b|\bDELETE\b"),
    (2, "涉及跨服务、消息或分布式一致性", r"跨服务|微服务|消息队列|\bMQ\b|kafka|rocketmq|分布式|最终一致|分布式事务"),
    (1, "涉及并发、幂等或状态机", r"并发|幂等|加锁|状态机|竞态"),
]
AC_THRESHOLDS = [(8, 2, "验收标准 ≥8 条"), (4, 1, "验收标准 ≥4 条")]
FILE_THRESHOLDS = [(8, 2, "影响 ≥8 个文件"), (3, 1, "影响 ≥3 个文件")]
TIER_BY_SCORE = [(4, "L"), (2, "M"), (0, "S")]

_FILE_PATH = re.compile(r"[\w.-]+(?:/[\w.-]+)+\.(?:java|kt|xml|sql|yml|yaml|properties|json|ts|js|py)\b")

# Artifacts each recheck point reads.
SOURCES = {"1": [P.PROPOSAL, P.BUGFIX_ANALYSIS],
           "2": [P.PROPOSAL, P.BUGFIX_ANALYSIS, P.DESIGN],
           "3": [P.PROPOSAL, P.BUGFIX_ANALYSIS, P.DESIGN, P.SPEC]}


def score_text(text: str) -> Tuple[str, int, List[str]]:
    """(tier, points, reasons) for the given artifact text."""
    points, reasons = 0, []
    acs = len(set(mdparse.id_re("AC").findall(text)))
    for limit, pts, why in AC_THRESHOLDS:
        if acs >= limit:
            points += pts
            reasons.append("%s（%d 条）" % (why, acs))
            break
    files = len(set(_FILE_PATH.findall(text)))
    for limit, pts, why in FILE_THRESHOLDS:
        if files >= limit:
            points += pts
            reasons.append("%s（%d 个）" % (why, files))
            break
    for pts, why, pattern in KEYWORD_RULES:
        if re.search(pattern, text, re.I):
            points += pts
            reasons.append(why)
    tier = next(t for floor, t in TIER_BY_SCORE if points >= floor)
    if not reasons:
        reasons.append("没有发现接口、表结构、跨服务等复杂度信号，改动面小")
    return tier, points, reasons


def recommend(change_dir: Path, phase: str = "1") -> Tuple[str, int, List[str]]:
    """Score the artifacts available at `phase` ("1", "2" or "3")."""
    texts = []
    for name in SOURCES[phase]:
        path = Path(change_dir) / name
        if path.is_file():
            texts.append(path.read_text(encoding="utf-8"))
    return score_text("\n".join(texts))
