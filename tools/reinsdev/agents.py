"""`reinsdev setup codex`: install the Reins agents for Codex.

Codex plugins cannot bundle agents, so the plugin ships them once, as the
shared agents/*.md, and this command converts each to a Codex custom-agent
TOML in ~/.codex/agents/ (or the project's .codex/agents/ with --project)."""

import json
from pathlib import Path

from spec_driven import frontmatter

from . import PLUGIN
from .platforms import codex_home


def sandbox_mode(access) -> str:
    return "workspace-write" if {"write", "write-own-report"} & set(access) else "read-only"


def _toml_str(s: str) -> str:
    # JSON string escapes are a subset of TOML basic-string escapes.
    return json.dumps(s, ensure_ascii=False)


def codex_agent(md: Path) -> str:
    """Translate one shared agent file into Codex custom-agent TOML."""
    meta, body = frontmatter.parse(md.read_text(encoding="utf-8"))
    access = meta.get("access") or []
    lines = [
        "name = %s" % _toml_str(meta["name"]),
        "description = %s" % _toml_str(meta["description"]),
        "sandbox_mode = %s" % _toml_str(sandbox_mode(access)),
    ]
    if meta.get("model"):
        lines.append("model = %s" % _toml_str(meta["model"]))
    lines.append("developer_instructions = %s" % _toml_str(body.strip()))
    return "\n".join(lines) + "\n"


def install_agents(dest: Path, force: bool, known=()) -> list:
    """Write one TOML per agent; refuse up front if a same-named file differs and is not ours."""
    pairs = [(dest / (md.stem + ".toml"), codex_agent(md))
             for md in sorted((PLUGIN / "agents").glob("*.md"))]
    foreign = [str(d) for d, text in pairs
               if d.exists() and str(d) not in known and d.read_text(encoding="utf-8") != text]
    if foreign and not force:
        raise SystemExit("reins: 以下文件已存在且内容不同，拒绝覆盖（确认无误可加 --force）：\n  " + "\n  ".join(foreign))
    dest.mkdir(parents=True, exist_ok=True)
    for d, text in pairs:
        d.write_bytes(text.encode("utf-8"))
    return [str(d) for d, _ in pairs]

