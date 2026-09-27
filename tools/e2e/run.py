#!/usr/bin/env python3
"""Exercise real CLI transitions in disposable Java repositories."""

import argparse
import contextlib
import io
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
import xml.etree.ElementTree as ET


REPO = Path(__file__).resolve().parents[2]
SKILL = REPO / "reinsdev-plugin/skills/spec-driven-dev"
CLI = SKILL / "scripts/spec-driven"
FIXTURES = Path(__file__).resolve().parent / "fixtures"
sys.path.insert(0, str(SKILL / "scripts/lib"))
from spec_driven import gitutil  # noqa: E402


class FlowError(Exception):
    """A recorded step did not meet its expectation."""


class Runner:
    def __init__(self, output, offline=True, maven_repo=None, diagnose=False):
        self.output = output
        self.offline = offline
        self.maven_repo = maven_repo
        self.diagnose = diagnose
        self.deviations = []
        self.rows = []
        self.flow = "环境"
        self.root = output
        self.change = ""
        self.env = dict(os.environ, REINS_HOME=str(output / "reins-home"),
                        GIT_TERMINAL_PROMPT="0")
        self.env.pop("GIT_DIR", None)
        self.env.pop("GIT_WORK_TREE", None)

    def record(self, command, code, stdout, stderr, expected, stdin=None):
        ok = code in expected
        row = {"flow": self.flow, "cwd": str(self.root), "command": command,
               "exit_code": code, "expected": list(expected), "matches": ok,
               "stdout": stdout, "stderr": stderr, "stdin": stdin}
        self.rows.append(row)
        self.save()
        print("[%s] %s rc=%s %s" % (self.flow, "符合" if ok else "不符合", code,
                                    " ".join(shlex.quote(s) for s in command)), flush=True)
        if not ok:
            print((stdout + stderr)[-6000:], flush=True)
            raise FlowError("命令结果与预期不符")
        return stdout

    def run(self, args, expected=(0,), stdin=None):
        try:
            result = subprocess.run([str(s) for s in args], cwd=str(self.root),
                                    env=self.env, input=stdin, capture_output=True,
                                    encoding="utf-8", errors="replace", timeout=300)
            code, out, err = result.returncode, result.stdout, result.stderr
        except (OSError, subprocess.TimeoutExpired) as exc:
            code, out, err = 124, "", str(exc)
        return self.record([str(s) for s in args], code, out, err, expected, stdin)

    def git(self, *args, **kwargs):
        # gitutil normalizes git failures to exit code 1; retain its diagnostic.
        stdout, stderr = io.StringIO(), io.StringIO()
        old_env = dict(os.environ)
        os.environ.update(self.env)
        code = 0
        try:
            with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                try:
                    value = gitutil.git(list(args), self.root)
                    stdout.write(value)
                except SystemExit as exc:
                    code = exc.code if isinstance(exc.code, int) else 1
                    if not isinstance(exc.code, int):
                        stderr.write(str(exc.code))
        finally:
            os.environ.clear()
            os.environ.update(old_env)
        return self.record(["gitutil.git"] + list(args), code, stdout.getvalue(),
                           stderr.getvalue(), kwargs.get("expected", (0,)))

    def cli(self, *args, **kwargs):
        return self.run([CLI] + list(args), **kwargs)

    def check(self, label, condition, evidence):
        return self.record(["核对", label], 0 if condition else 1,
                           str(evidence), "", (0,))

    def write(self, path, content):
        target = self.root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        self.record(["填写", path], 0, content, "", (0,))

    def artifact(self, name, **replacements):
        content = (FIXTURES / name).read_text(encoding="utf-8")
        content = content.replace("<change-name>", self.change)
        for key, value in replacements.items():
            content = content.replace("<%s>" % key, value)
        self.write(".openspec/changes/%s/%s" % (self.change, name), content)

    def report(self, name, block=False):
        template = (SKILL / "templates/reports" / name).read_text(encoding="utf-8")
        lines = [line for line in template.splitlines()
                 if not line.startswith("填写说明") and not line.startswith("<格式契约")]
        content = "\n".join(lines).split("## bugfix 升级判定")[0]
        content = content.replace("<change-name>", self.change)
        content = content.replace("<BLOCK 数>", "1" if block else "0")
        content = content.replace("<WARN 数>", "0").replace("<INFO 数>", "0")
        example = "| <BLOCK、WARN 或 INFO> | <文件:行，或 -> | <问题，一句话> | <修复建议> |"
        finding = "| BLOCK | - | 联调预设风险 | 仅在临时项目演练用户确认放行 |" if block else ""
        content = content.replace(example, finding)
        content += "\n## 联调说明\n\n这是离线 CLI 协议测试输入，不是独立 agent 实际评审结果。\n"
        self.write(".openspec/changes/%s/%s" % (self.change, name), content)

    def meta(self):
        return json.loads((self.root / ".openspec/changes" / self.change / ".meta.json").read_text(encoding="utf-8"))

    def phase(self, phase):
        value = self.meta()["phase"]
        self.check("当前 Phase = %s" % phase, str(value) == phase, value)

    def prompt(self, phrase):
        return self.cli("hook", "prompt-submit", "--runtime", "claude",
                        stdin=json.dumps({"hook_event_name": "UserPromptSubmit",
                                          "cwd": str(self.root), "prompt": phrase}, ensure_ascii=False))

    def setup(self, flow):
        self.flow = flow
        self.root = self.output / ("flow-" + flow.lower())
        self.root.mkdir()
        self.change = "points-" + flow.lower()
        self.write("pom.xml", (FIXTURES / "pom.xml").read_text(encoding="utf-8"))
        options = ["-o"] if self.offline else []
        if self.maven_repo:
            options.append("-Dmaven.repo.local=%s" % self.maven_repo)
        self.write(".mvn/maven.config", "\n".join(options) + "\n")
        self.write(".gitignore", "target/\n")
        self.source(False)
        self.test(False)
        self.git("init", "-q")
        self.git("config", "user.name", "Json E2E")
        self.git("config", "user.email", "json-e2e@example.invalid")
        self.git("config", "commit.gpgsign", "false")
        self.git("add", ".")
        self.git("commit", "-qm", "Json: T13: 初始化临时 Maven 项目")

    def source(self, green):
        self.write("src/main/java/demo/Points.java", """package demo;

public class Points {
    public int total(int amount) {
        return %s;
    }
}
""" % ("amount + 1" if green else "amount"))

    def test(self, changed):
        self.write("src/test/java/demo/PointsTest.java", """package demo;

import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.assertEquals;

class PointsTest {
    @Test
    void addsPoint() {
        assertEquals(%s, new Points().total(1));
    }
}
""" % ("2" if changed else "1"))

    def begin(self, tier=None, bugfix=False):
        self.cli("new", self.change, *( ["--mode", "bugfix"] if bugfix else []))
        self.phase("0")
        self.cli("advance")
        self.phase("1")
        self.artifact("proposal.md")
        if tier:
            self.cli("complexity", "set", tier)

    def advance(self, phase):
        try:
            self.cli("advance")
        except FlowError:
            if not self.diagnose or self.flow != "A":
                raise
            self.deviations.append(dict(self.rows[-1]))
            current = str(self.meta()["phase"])
            for gate in (["6", "6.5", "6.7"] if current == "6" else [current]):
                self.diagnostic_waive(gate)
            self.cli("advance", "--ack-warn")
        self.phase(phase)

    def diagnostic_waive(self, gate):
        raw = self.cli("gate", gate, "--json", expected=(0, 2, 3))
        data = json.loads(raw)
        findings = data if isinstance(data, list) else data["findings"]
        checks = sorted(set(f["check"] for f in findings if f["level"] == "BLOCK" and not f.get("waived")))
        for check in checks:
            self.prompt("确认放行 %s %s %s" % (self.change, gate, check))
            self.cli("waive", gate, check, "--reason", "T13 临时项目诊断放行，仅用于探查后续步骤；不代表验证通过")

    def flow_b(self):
        self.setup("B")
        self.begin("M")
        self.advance("2")
        self.artifact("design.md")
        self.cli("design", "set", "直接计算")
        self.advance("3")
        self.artifact("spec.md")
        self.advance("4")
        self.artifact("tasks.md", reference="SC-points-001")
        self.advance("5")
        self.report("spec-review.md", block=True)
        raw = self.cli("gate", "5", "--json", expected=(3,))
        self.cli("advance", expected=(3,))
        self.phase("5")
        data = json.loads(raw)
        findings = data if isinstance(data, list) else data["findings"]
        checks = sorted(set(f["check"] for f in findings if f["level"] == "BLOCK"))
        self.check("评审风险产生一个检查项", len(checks) == 1, checks)
        check = checks[0]
        self.cli("waive", "5", check, "--reason", "联调演练接受预设风险", expected=(1,))
        self.prompt("确认放行 %s 5 %s" % (self.change, check))
        self.cli("waive", "5", check, "--reason", "联调演练接受预设风险")
        output = self.cli("gate", "5")
        self.check("放行按指纹生效", "WAIVED" in output, output)
        self.advance("6")

    def flow_c(self):
        self.setup("C")
        self.begin(bugfix=True)
        self.artifact("bugfix-analysis.md")
        path = self.root / ".openspec/changes" / self.change / "proposal.md"
        proposal = path.read_text(encoding="utf-8").replace(
            "| AC-1 |", "| AC-regression | US-1 | 回归测试覆盖增加一分 | 运行 PointsTest 验证原缺陷 |\n| AC-1 |")
        self.write(path.relative_to(self.root).as_posix(), proposal)
        self.cli("scope", "show")
        self.cli("scope", "set", "--files", "3", "--public-api")
        self.check("扩大范围时 2/3 必走", not any(self.meta()["skipped"].get(p) for p in ("2", "3")), self.meta()["skipped"])
        self.cli("scope", "set", "--files", "2")
        self.cli("scope", "show")
        self.advance("4")
        self.check("小范围 bugfix 跳过 2/3", all(self.meta()["skipped"].get(p) for p in ("2", "3")), self.meta()["skipped"])
        self.cli("scope", "set", "--files", "2", expected=(1,))

    def flow_a(self):
        self.setup("A")
        self.run(["mvn", "-B", "test"])
        self.begin("S")
        self.advance("4")
        self.check("S 已跳过 2/3", all(self.meta()["skipped"].get(p) for p in ("2", "3")), self.meta()["skipped"])
        self.artifact("tasks.md", reference="AC-1")
        self.advance("6")
        self.test(True)
        self.run(["mvn", "-B", "test"], expected=(1,))
        reports = list((self.root / "target/surefire-reports").glob("TEST-*.xml"))
        failures = sum(int(ET.parse(p).getroot().get("failures", 0)) for p in reports)
        self.check("RED 是真实断言失败", failures == 1, failures)
        for report in reports:
            shutil.copyfile(str(report), str(self.output / ("red-" + report.name)))
        self.git("add", ".")
        self.git("commit", "-qm", "Json: T13: RED 缺少任务标识", expected=(1,))
        self.git("commit", "-qm", "Json: T13: RED 增加积分测试\n\nTask-Id: T1\nTDD-Phase: RED")
        red = self.git("rev-parse", "HEAD")
        self.cli("tasks-sync", "--apply")
        tasks = self.root / ".openspec/changes" / self.change / "tasks.md"
        self.check("RED 不算完成", "- [ ] T1" in tasks.read_text(encoding="utf-8"), tasks.read_text(encoding="utf-8"))
        self.source(True)
        self.run(["mvn", "-B", "verify"])
        for report in (self.root / "target/surefire-reports").glob("TEST-*.xml"):
            suite = ET.parse(report).getroot()
            self.check("GREEN 真实运行且无失败", int(suite.get("tests", 0)) == 1 and
                       all(int(suite.get(k, 0)) == 0 for k in ("failures", "errors", "skipped")), suite.attrib)
            shutil.copyfile(str(report), str(self.output / ("green-" + report.name)))
        shutil.copyfile(str(self.root / "target/site/jacoco/jacoco.xml"), str(self.output / "jacoco.xml"))
        self.git("add", ".")
        self.git("commit", "-qm", "Json: T13: GREEN 实现增加积分\n\nTask-Id: T1\nTDD-Phase: GREEN")
        green = self.git("rev-parse", "HEAD")
        self.cli("tasks-sync", "--apply")
        self.check("GREEN 算完成", "- [x] T1" in tasks.read_text(encoding="utf-8"), tasks.read_text(encoding="utf-8"))
        self.git("add", ".openspec")
        try:
            self.git("commit", "-qm", "Json: T13: 保存 tasks-sync 结果")
        except FlowError:
            if not self.diagnose:
                raise
            self.deviations.append(dict(self.rows[-1]))
        coverage = ET.parse(self.root / "target/site/jacoco/jacoco.xml").getroot()
        changed_line = coverage.find(".//sourcefile[@name='Points.java']/line[@nr='5']")
        self.check("改动行有真实 JaCoCo 执行证据", changed_line is not None and int(changed_line.get("ci", 0)) > 0,
                   ET.tostring(changed_line, encoding="unicode") if changed_line is not None else "缺失")
        self.artifact("implementation-log.md", red=red, green=green, base=self.meta()["baseCommit"])
        preview = self.cli("init-config", "--java", "--dry-run")
        self.check("初始化预览不写配置", not (self.root / ".openspec/.config.json").exists(), ".config.json 不存在")
        try:
            self.cli("init-config", "--java")
        except FlowError:
            if not self.diagnose:
                raise
            self.deviations.append(dict(self.rows[-1]))
            self.check("初始化失败不写基线", not (self.root / ".openspec/quality-baseline.json").exists(), "quality-baseline.json 不存在")
            defaults = json.loads(preview[preview.index("{"):])["quality"]
            for name in ("archunit", "checkstyle", "pmd", "spotbugs"):
                self.run(defaults[name]["command"], expected=(0, 1))
        self.advance("8")
        self.check("S 已跳过 2/3/5/7", all(self.meta()["skipped"].get(p) for p in ("2", "3", "5", "7")), self.meta()["skipped"])
        self.check("静态分析报告已生成", (self.root / ".openspec/changes" / self.change / "static-analysis-report.md").exists(), "static-analysis-report.md")
        self.report("code-review.md")
        self.advance("8.5")
        self.cli("deploy", "skip", "--reason", "联调示例是 Java 类库，无应用需要部署")
        self.phase("8.9")
        self.cli("uat", "accept", expected=(1,))
        self.prompt("确认验收 " + self.change)
        self.cli("uat", "accept")
        self.cli("uat", "reject", "--phase", "8", "--reason", "联调演练：重新核对评审摘要")
        self.phase("8")
        self.check("拒绝后撤销验收", not self.meta().get("uatAccepted"), self.meta().get("uatAccepted"))
        self.report("code-review.md")
        self.advance("8.9")
        self.check("回退后保留部署跳过决定", bool(self.meta()["skipped"].get("8.5")), self.meta()["skipped"])
        self.prompt("确认验收 " + self.change)
        self.cli("uat", "accept")
        self.advance("9")
        self.git("add", ".openspec")
        self.cli("archive", "--dry-run")
        self.cli("archive")
        archived = list((self.root / ".openspec/changes/archive").glob("*" + self.change))
        self.check("归档迁移完成", len(archived) == 1 and not (self.root / ".openspec/changes" / self.change).exists(), archived)
        self.git("add", ".openspec")
        self.git("commit", "-qm", "Json: T13: 保存临时项目归档")
        self.cli("status")

    def save(self):
        (self.output / "steps.json").write_text(json.dumps(self.rows, ensure_ascii=False, indent=2), encoding="utf-8")
        lines = ["# CLI 联调执行记录", "", "git 步骤经 gitutil.git；失败退出码为包装器返回的 1。", ""]
        for index, row in enumerate(self.rows, 1):
            lines.extend(["## %s. %s · %s" % (index, row["flow"], "符合预期" if row["matches"] else "不符合预期"),
                          "", "目录：`%s`" % row["cwd"], "", "```text",
                          " ".join(shlex.quote(s) for s in row["command"]),
                          "退出码：%s；预期：%s" % (row["exit_code"], row["expected"]), "```", ""])
            if row["stdin"]:
                lines.extend(["stdin：", "```json", row["stdin"], "```", ""])
            lines.extend(["```text", (row["stdout"] + row["stderr"])[-6000:], "```", ""])
        (self.output / "steps.md").write_text("\n".join(lines), encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description="在临时目录运行真实 Java/CLI 联调，保留全部证据")
    parser.add_argument("--flows", nargs="+", choices=["A", "B", "C"], default=["A", "B", "C"])
    parser.add_argument("--online", action="store_true", help="显式允许 Maven 下载依赖；默认离线")
    parser.add_argument("--maven-repo", type=Path, help="已有的 Maven 本地仓库")
    parser.add_argument("--diagnose", action="store_true", help="仅临时流程 A：记录阻塞后模拟口令放行以探查后续；最终仍返回失败")
    args = parser.parse_args()
    output = Path(tempfile.mkdtemp(prefix="reins-e2e-"))
    runner = Runner(output, offline=not args.online,
                    maven_repo=args.maven_repo.resolve() if args.maven_repo else None,
                    diagnose=args.diagnose)
    print("证据目录：%s" % output, flush=True)
    if not all(shutil.which(name) for name in ("java", "javac", "mvn")):
        print("缺少 JDK 或 Maven，停止；请告知协调者。", file=sys.stderr)
        return 1
    runner.run(["java", "-version"])
    runner.run(["mvn", "-version"])
    runner.git("--version")
    failed = []
    for flow in args.flows:
        try:
            getattr(runner, "flow_" + flow.lower())()
        except (FlowError, KeyError, ValueError) as exc:
            failed.append(flow)
            print("流程 %s 停在失败点：%s；继续独立流程。" % (flow, exc), flush=True)
    summary = {"failed_flows": failed, "diagnostic_deviations": runner.deviations,
               "evidence": str(output), "finished_at": time.strftime("%Y-%m-%dT%H:%M:%S%z")}
    (output / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print("完成；中断流程：%s；诊断偏差：%s；证据：%s" % (failed, len(runner.deviations), output), flush=True)
    return 1 if failed or runner.deviations else 0


if __name__ == "__main__":
    sys.exit(main())
