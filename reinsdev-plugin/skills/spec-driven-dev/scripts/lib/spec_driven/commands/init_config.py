"""Initialize Java quality commands and a one-time debt baseline."""

import json
import os
from pathlib import Path
import tempfile

from .. import java
from ..errors import fail, OK
from ..project import Project


def register(sub):
    p = sub.add_parser("init-config", help="生成质量门配置与存量基线")
    p.add_argument("--java", action="store_true", required=True)
    p.add_argument("--dry-run", action="store_true")


def _json(path):
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("配置必须是 JSON 对象")
    return data


def _write(path, data):
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=str(path.parent),
                                         prefix=".quality-", suffix=".tmp", delete=False) as handle:
            temporary = Path(handle.name)
            json.dump(data, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
        os.replace(str(temporary), str(path))
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()


def run(a) -> int:
    project = Project.here()
    try:
        defaults = java.quality_defaults(project.root)
        config = _json(project.config_path) if project.config_path.exists() else {}
        quality = config.get("quality", {})
        if not isinstance(quality, dict):
            raise ValueError("quality 配置必须是对象")
        merged = dict(defaults)
        for name, value in quality.items():
            if name in defaults:
                if not isinstance(value, dict):
                    raise ValueError("quality.%s 必须是对象" % name)
                merged[name] = dict(defaults[name])
                merged[name].update(value)
                if name == "sqlfluff" and "command" in value and "source" not in value:
                    merged[name].pop("source", None)
            else:
                merged[name] = value
        config["quality"] = merged
        exists = project.quality_baseline.exists()
        if "quality_baseline_initialized" in config and config["quality_baseline_initialized"] is not True:
            raise ValueError("质量基线初始化标记无效")
        if config.get("quality_baseline_initialized") and not exists:
            raise ValueError("已初始化的质量基线被删除，请从版本库恢复，不能重新吸收新增违规")
        previous = java.load_baseline(project.quality_baseline) if exists else []
        if a.dry_run:
            print("将写入 .openspec/.config.json 并%s质量基线；预览不会运行检查。" % ("保留" if exists else "生成"))
            print(json.dumps(config, ensure_ascii=False, indent=2, sort_keys=True))
            return OK
        current, errors = java.run_quality(project.root, merged, initialize=not exists)
        if errors:
            raise ValueError("；".join("%s：%s" % item for item in sorted(errors.items())))
        new, unused, repaid = java.compare_quality(current, previous)
        if exists and any(not entry.warning for entry in new):
            raise ValueError("检测到新增违规，不能用重新初始化扩大已有基线")
        config["quality_baseline_initialized"] = True
        project.openspec.mkdir(parents=True, exist_ok=True)
        if not exists:
            baseline = {"version": 1, "violations": [entry.to_dict() for entry in
                        sorted(current, key=lambda item: (item.fingerprint, item.line))]}
            _write(project.quality_baseline, baseline)
        try:
            _write(project.config_path, config)
        except OSError:
            if not exists:
                project.quality_baseline.unlink()
            raise
    except (ValueError, OSError, TypeError, KeyError) as exc:
        fail("Java 质量配置初始化失败：%s" % exc)
    print("已写入 .openspec/.config.json，%s .openspec/quality-baseline.json。" % ("保留" if exists else "已生成"))
    return OK
