#!/usr/bin/env python3
"""Validate the shipped SQL defaults using a real, separately installed SQLFluff."""

import argparse
import json
from pathlib import Path
import subprocess
import tempfile


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--sqlfluff", default="sqlfluff")
    args = parser.parse_args()
    root = Path(tempfile.mkdtemp(prefix="reins-sqlfluff-"))
    template = Path(__file__).resolve().parents[2] / "reinsdev-plugin/skills/spec-driven-dev/templates/quality/sqlfluff.template"
    config = root / ".sqlfluff"
    config.write_text(template.read_text(encoding="utf-8").replace("<dialect>", "postgres"), encoding="utf-8")
    cases = [
        ("placeholder-and-implicit-alias", "SELECT p.id value FROM points p WHERE p.id = #{id,jdbcType=BIGINT} OR p.id = ?;", 0, set()),
        ("uppercase", "select id FROM points;", 1, {"CP01"}),
        ("select-star", "SELECT * FROM points;", 1, {"AM04"}),
        ("qualified-join", "SELECT id FROM points p JOIN users u ON p.id = u.id;", 1, {"RF02"}),
        ("long-line-warning", "SELECT '" + "x" * 125 + "' value;", 0, {"LT05"}),
    ]
    records = []
    for name, sql, expected, required in cases:
        command = [args.sqlfluff, "lint", "--format", "json", "--config", str(config), "-"]
        run = subprocess.run(command, cwd=str(root), input=sql, capture_output=True, encoding="utf-8", timeout=60)
        try:
            violations = [v for f in json.loads(run.stdout) for v in f["violations"]]
            codes = {v["code"] for v in violations}
            parsed = True
        except (ValueError, KeyError, TypeError):
            violations, codes = [], set()
            parsed = False
        matches = parsed and run.returncode == expected and required.issubset(codes)
        if name == "long-line-warning":
            matches = matches and all(v.get("warning") for v in violations if v["code"] == "LT05")
        records.append(dict(name=name, command=command, stdin=sql, exit_code=run.returncode,
                            expected=expected, stdout=run.stdout, stderr=run.stderr, matches=matches))
        print("%s：%s，退出码 %s" % (name, "符合" if matches else "不符合", run.returncode))
    (root / "steps.json").write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")
    print("证据：%s" % root)
    return 0 if all(r["matches"] for r in records) else 1


if __name__ == "__main__":
    raise SystemExit(main())
