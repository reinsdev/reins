"""`reinsdev doctor`: environment check plus, per runtime, which layer
actually enforces each guardrail (design doc §2.4). A guardrail left with
only the CLI layer is printed loudly, never silently."""

import json
import os
import platform
import shutil
import subprocess
import sys

from pathlib import Path

from spec_driven import VERSION
from spec_driven.paths import reins_home

from . import PLUGIN
from .platforms import find_cli

# Per runtime: guardrail -> (enforcing layer, note). "待实测" marks behaviour
# that has to be confirmed by hand in a live session.
GUARDRAILS = {
    "claude": {
        "验证门": ("CLI + git + 平台 hook", ""),
        "路径锁 / 上游冻结": ("平台 hook（PreToolUse）", ""),
        "只有用户能放行": ("对话口令 + UserPromptSubmit 授权", ""),
        "评审者隔离": ("子 agent + tools 白名单", ""),
        "Windows hook": ("Git Bash 执行 sh 启动器，JSON deny", "没有 Git Bash 时退回 cmd.exe，hook 失效"),
    },
    "codex": {
        "验证门": ("CLI + git + 平台 hook", ""),
        "路径锁 / 上游冻结": ("平台 hook（PreToolUse 覆盖 apply_patch）", ""),
        "只有用户能放行": ("对话口令 + UserPromptSubmit 授权", ""),
        "评审者隔离": ("子 agent + workspace-write 沙箱 + hook 路径锁", "agents 需 reinsdev setup codex"),
        "Windows hook": ("commandWindows 经 PowerShell 调 .cmd 启动器，JSON deny", "商店版 pwsh 会导致 hook 失效（openai/codex#47810）"),
    },
    "opencode": {
        "验证门": ("CLI + git + 平台 hook", ""),
        "路径锁 / 上游冻结": ("JS 插件 tool.execute.before", "子 agent 调用是否被拦（#5894）：待实测"),
        "只有用户能放行": ("终端 TTY 确认（退回方案）", "插件能否拿到用户消息以签发授权：待实测"),
        "评审者隔离": ("子 agent + permission", ""),
        "Windows hook": ("JS 插件直接调用 Python", ""),
    },
}


def _version(cmd):
    exe = find_cli(cmd)
    if not exe:
        return None
    try:
        r = subprocess.run([exe, "--version"], capture_output=True, encoding="utf-8",
                           errors="replace", timeout=20)
        return (r.stdout or r.stderr).strip().splitlines()[0] if r.returncode == 0 else "（--version 失败）"
    except (OSError, subprocess.TimeoutExpired, IndexError):
        return "（--version 失败）"


def _windows_checks() -> bool:
    """Windows-only: the two environment conditions that make hooks fail open."""
    ok = True
    git = shutil.which("git")
    # git.exe lives in <Git>\cmd\ or <Git>\mingw64\bin\; bash.exe in <Git>\bin\.
    candidates = [Path(git).resolve().parents[i] / "bin" / "bash.exe" for i in (1, 2)] if git else []
    bash = next((c for c in candidates if c.is_file()), None)
    if bash:
        print("Git Bash %s" % bash)
    else:
        print("Git Bash 未找到  ✗  Claude Code 会退回 cmd.exe 执行 hook，护栏失效；请安装 Git for Windows")
        ok = False
    pwsh = shutil.which("pwsh")
    if pwsh and "WindowsApps" in pwsh:
        print("pwsh     %s  ⚠ 商店版 PowerShell 会让 Codex hook 报 os error 5 而失效（openai/codex#47810）；"
              "请安装 MSI 版 PowerShell 7，或让 PATH 里 C:\\Windows\\System32\\WindowsPowerShell\\v1.0 排在前面" % pwsh)
    return ok


def run() -> int:
    ok = True
    print("Reins    %s" % VERSION)
    print("python   %s" % sys.version.split()[0])
    git = _version("git")
    print("git      %s" % (git or "未安装  ✗"))
    ok &= bool(git)

    print("系统     %s" % platform.platform())
    print("插件位置 %s" % PLUGIN)
    home = reins_home()
    manifest = {}
    if (home / "installed.json").is_file():
        manifest = json.loads((home / "installed.json").read_text(encoding="utf-8"))

    if os.name == "nt":
        ok &= _windows_checks()

    for name in GUARDRAILS:
        v = _version(name)
        if not v:
            print("\n[%s] 未检测到（PATH 和默认安装目录里都没有），跳过" % name)
            continue
        print("\n[%s] %s%s" % (name, v, "（已由 reinsdev 安装）" if name in manifest else ""))
        for rail, (layer, note) in GUARDRAILS[name].items():
            print("  %-18s %s%s" % (rail, layer, ("  ⚠ " + note) if note else ""))
    return 0 if ok else 1
