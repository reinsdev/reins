"""Java build and report adapters shared by the implementation gates."""
import hashlib
import json
import os
import re
import shlex
import subprocess
import time
import xml.etree.ElementTree as ET
from xml.parsers import expat
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

from . import gitutil


CHECKS = ("archunit", "checkstyle", "spotbugs", "pmd", "sqlfluff")
TEST_PATHS = ("**/target/surefire-reports/TEST-*.xml", "**/build/test-results/**/TEST-*.xml")
COVERAGE_PATHS = ("**/target/site/jacoco*/jacoco.xml", "**/build/reports/jacoco/**/*.xml")
FREEZE_KEYS = ("archunit_freeze.store.default.allowStoreCreation", "archunit_freeze.store.default.allowStoreUpdate", "archunit_freeze.refreeze")


class JavaError(ValueError):
    """A build or report cannot provide trustworthy gate evidence."""


def detect_build(root: Path) -> str:
    """Detect the root build, refusing missing or ambiguous descriptors."""
    maven = (root / "pom.xml").is_file()
    gradle = any((root / name).is_file() for name in ("build.gradle", "build.gradle.kts", "settings.gradle", "settings.gradle.kts"))
    if maven == gradle:
        raise JavaError("无法唯一识别 Java 构建：需要 Maven 或 Gradle 配置")
    return "maven" if maven else "gradle"


def _tag(element):
    return element.tag.rsplit("}", 1)[-1]


def _xml(path):
    try:
        return ET.fromstring(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ET.ParseError) as exc:
        raise JavaError("XML 报告无法读取或已损坏：%s（%s）" % (path.name, exc))


def _number(value, label):
    if isinstance(value, bool) or not isinstance(value, (int, str)) or not re.fullmatch(r"\d+", str(value)):
        raise JavaError("%s 必须是非负整数" % label)
    return int(value)


def _paths(root, report_path, defaults=(), required=True, suffix=".xml"):
    patterns = defaults if report_path is None else report_path
    if isinstance(patterns, (str, Path)):
        patterns = [patterns]
    if not isinstance(patterns, (list, tuple)) or not patterns:
        raise JavaError("缺少报告路径配置")
    result = set()
    for pattern in patterns:
        if not isinstance(pattern, (str, Path)) or not str(pattern).strip():
            raise JavaError("报告路径无效")
        path = Path(pattern)
        if path.is_absolute():
            try:
                pattern = path.relative_to(root.resolve()).as_posix()
            except ValueError:
                raise JavaError("报告路径必须位于项目内")
        else:
            pattern = path.as_posix()
        if ".." in Path(pattern).parts:
            raise JavaError("报告路径不能越过项目目录")
        try:
            candidates = root.glob(pattern)
            for candidate in candidates:
                if candidate.is_file():
                    result.add(candidate)
                elif candidate.is_dir():
                    result.update(p for p in candidate.rglob("*" + suffix) if p.is_file())
        except (ValueError, OSError) as exc:
            raise JavaError("报告路径无法读取：%s" % exc)
    if required and not result:
        raise JavaError("未找到检查报告")
    return sorted(result)


def _suite_counts(document):
    if _tag(document) not in ("testsuite", "testsuites"):
        raise JavaError("不是 JUnit 测试报告")
    suites = [node for node in document.iter() if _tag(node) == "testsuite" and not any(_tag(child) == "testsuite" for child in node.iter() if child is not node)]
    if not suites:
        raise JavaError("测试报告缺少 testsuite")
    result = dict(tests=0, failures=0, errors=0, skipped=0)
    for suite in suites:
        counts = {key: _number(suite.get(key, "0") if key == "skipped" else suite.get(key), key) for key in result}
        if counts["failures"] + counts["errors"] + counts["skipped"] > counts["tests"]:
            raise JavaError("测试报告的计数不一致")
        cases = [node for node in suite if _tag(node) == "testcase"]
        actual = {"tests": len(cases), "failures": 0, "errors": 0, "skipped": 0}
        for case in cases:
            for singular, plural in (("failure", "failures"), ("error", "errors"), ("skipped", "skipped")):
                actual[plural] += int(any(_tag(child) == singular for child in case))
        if actual != counts:
            raise JavaError("测试报告的 testcase 与汇总计数不一致")
        for key in result:
            result[key] += counts[key]
    return result


def _fresh_report(root, report):
    module = _module(root, report)
    stamp = report.stat().st_mtime_ns
    for source in module.rglob("*.java"):
        relative = source.relative_to(module).as_posix()
        if "/src/main/java/" not in "/" + relative and "/src/test/java/" not in "/" + relative:
            continue
        if source.stat().st_mtime_ns > stamp:
            raise JavaError("报告早于 Java 源码，请重新运行测试：%s" % report.relative_to(root).as_posix())


def test_reports(root: Path, report_path=None) -> Dict[str, int]:
    """Sum leaf JUnit suites, preserving the total including skipped tests."""
    result = dict(tests=0, failures=0, errors=0, skipped=0)
    for path in _paths(root, report_path, TEST_PATHS):
        _fresh_report(root, path)
        for key, value in _suite_counts(_xml(path)).items():
            result[key] += value
    return result


def _argv(command):
    if isinstance(command, str):
        try:
            command = shlex.split(command)
        except ValueError as exc:
            raise JavaError("命令格式无效：%s" % exc)
    if not isinstance(command, (list, tuple)) or not command or not all(isinstance(part, str) and part for part in command):
        raise JavaError("检查命令必须是非空字符串或参数列表")
    return list(command)


def _resolve_property(value, properties):
    for unused in range(20):
        if "${" not in value:
            return value.strip().lower()
        resolved = re.sub(r"\$\{([^}]+)\}", lambda match: properties.get(match.group(1), match.group(0)), value)
        if resolved == value:
            break
        value = resolved
    return "unresolved"


def skip_reasons(root: Path, commands: List) -> List[str]:
    """Find test suppression, treating unresolved Maven skip values as unsafe."""
    reasons = []
    command_properties = {}
    for command in commands:
        args = _argv(command)
        for index, arg in enumerate(args):
            if arg.startswith("-D"):
                key, separator, value = arg[2:].partition("=")
                command_properties[key] = value if separator else "true"
                if key in ("skipTests", "maven.test.skip") and value.lower() != "false":
                    reasons.append("命令跳过测试：%s" % arg)
            task = None
            if arg in ("-x", "--exclude-task"):
                if index + 1 >= len(args):
                    reasons.append("Gradle 排除任务参数缺少任务名")
                else:
                    task = args[index + 1]
            elif arg.startswith("--exclude-task="):
                task = arg.split("=", 1)[1]
            elif arg.startswith("-x") and len(arg) > 2:
                task = arg[2:]
            if task is not None and task.rsplit(":", 1)[-1] == "test":
                reasons.append("Gradle 排除测试任务：%s" % task)
    poms = {}
    for path in sorted(root.rglob("pom.xml")):
        relative = path.relative_to(root)
        if any(part in (".git", "target", "build") for part in relative.parts):
            continue
        poms[path.parent] = _xml(path)
    for directory, document in poms.items():
        properties = {}
        ancestors = [directory] + list(directory.parents)
        for ancestor in reversed(ancestors):
            if ancestor not in poms:
                continue
            for node in poms[ancestor].iter():
                if _tag(node) == "properties":
                    properties.update({_tag(child): child.text or "" for child in node})
        properties.update(command_properties)
        values = [(key, properties[key]) for key in ("skipTests", "maven.test.skip") if key in properties]
        for plugin in document.iter():
            if _tag(plugin) != "plugin" or not any(_tag(child) == "artifactId" and (child.text or "").strip() == "maven-surefire-plugin" for child in plugin):
                continue
            values.extend((_tag(node), node.text or "") for node in plugin.iter() if _tag(node) in ("skip", "skipTests"))
        for key, value in values:
            resolved = _resolve_property(value, properties)
            if resolved != "false":
                reasons.append("%s 的 %s 跳过测试或值无法确认：%s" % ((directory / "pom.xml").relative_to(root).as_posix(), key, value))
    return sorted(set(reasons))


def changed_lines(root: Path, base: str) -> Dict[str, Set[int]]:
    """Return added post-image Java source lines from committed base..HEAD only."""
    if not isinstance(base, str) or not base or base.startswith("-"):
        raise JavaError("缺少有效的覆盖率基线提交")
    try:
        diff = gitutil.git(["-c", "core.quotepath=false", "diff", "--no-ext-diff", "--no-renames", "--unified=0", base + "..HEAD", "--"], root)
    except (SystemExit, OSError, ValueError) as exc:
        raise JavaError("无法读取 Java 变更：%s" % exc)
    result = {}
    current = None
    for line in diff.splitlines():
        if line.startswith("diff --git "):
            current = None
        elif line.startswith("+++ "):
            name = line[4:]
            if name.startswith('"'):
                try:
                    name = json.loads(name)
                except ValueError:
                    raise JavaError("无法解析 Java 变更路径")
            if name.startswith("b/"):
                name = name[2:]
                if ("/src/main/java/" in "/" + name) and name.endswith(".java"):
                    current = name
        elif current is not None and line.startswith("@@ "):
            match = re.match(r"@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@", line)
            if not match:
                raise JavaError("无法解析 Java 变更行")
            start, count = int(match.group(1)), int(match.group(2) or "1")
            if count:
                result.setdefault(current, set()).update(range(start, start + count))
    return result


def _module(root, report):
    parts = report.relative_to(root).parts
    for index, part in enumerate(parts):
        if part in ("target", "build"):
            return root.joinpath(*parts[:index])
    return root


def _coverage_packages(root, node, module):
    for child in node:
        if _tag(child) == "package":
            yield child, module
        elif _tag(child) == "group":
            name = child.get("name", "")
            if not name or Path(name).is_absolute() or ".." in Path(name).parts:
                raise JavaError("JaCoCo 聚合分组缺少合法模块名")
            candidates = {path for path in (module / name, root / name) if path.is_dir()}
            if not candidates:
                for pom in root.rglob("pom.xml"):
                    if any(part in ("target", "build", ".git") for part in pom.relative_to(root).parts):
                        continue
                    document = _xml(pom)
                    if any(_tag(item) in ("artifactId", "name") and (item.text or "").strip() == name for item in document):
                        candidates.add(pom.parent)
            if len(candidates) != 1:
                raise JavaError("JaCoCo 聚合分组无法唯一定位模块：%s" % name)
            yield from _coverage_packages(root, child, candidates.pop())


def diff_coverage(root: Path, lines: Dict[str, Set[int]], report_path=None) -> Dict:
    """Join changed executable lines to module-local JaCoCo source records."""
    result = {"covered": 0, "total": 0, "percent": 100.0, "uncovered": []}
    if not any(lines.values()):
        return result
    sources = {}
    for report in _paths(root, report_path, COVERAGE_PATHS):
        _fresh_report(root, report)
        document = _xml(report)
        if _tag(document) != "report":
            raise JavaError("不是 JaCoCo XML 报告")
        module = _module(root, report)
        for package, module in _coverage_packages(root, document, module):
            package_name = package.get("name")
            if package_name is None:
                raise JavaError("JaCoCo 缺少包名")
            for source in package:
                if _tag(source) != "sourcefile":
                    continue
                name = source.get("name")
                if not name or "/" in name or "\\" in name:
                    raise JavaError("JaCoCo 源文件名无效")
                path = (module / "src/main/java" / package_name / name).relative_to(root).as_posix()
                records = sources.setdefault(path, {})
                for item in source:
                    if _tag(item) != "line":
                        continue
                    number = _number(item.get("nr"), "JaCoCo 行号")
                    missed = _number(item.get("mi"), "JaCoCo 未覆盖指令")
                    covered = _number(item.get("ci"), "JaCoCo 已覆盖指令")
                    if number == 0:
                        raise JavaError("JaCoCo 行号必须大于零")
                    if missed + covered:
                        records[number] = records.get(number, False) or covered > 0
    for path, changed in sorted(lines.items()):
        if not changed:
            continue
        if path not in sources:
            raise JavaError("JaCoCo 缺少改动源文件：%s" % path)
        for number in sorted(changed):
            if number not in sources[path]:
                continue
            result["total"] += 1
            if sources[path][number]:
                result["covered"] += 1
            else:
                result["uncovered"].append("%s:%s" % (path, number))
    if result["total"]:
        result["percent"] = 100.0 * result["covered"] / result["total"]
    result["uncovered"].sort()
    return result


@dataclass(frozen=True)
class Violation:
    check: str
    rule: str
    file: str
    line: int
    message: str

    @property
    def fingerprint(self) -> str:
        """Keep source movement out of baseline identity."""
        message = re.sub(r"(\.java):\d+(?::\d+)?", r"\1:<line>", self.message)
        message = " ".join(message.split())
        value = json.dumps([self.check, self.file.replace("\\", "/"), self.rule, message], ensure_ascii=False, separators=(",", ":"))
        return hashlib.sha256(value.encode("utf-8")).hexdigest()

    def to_dict(self) -> Dict:
        return {"check": self.check, "rule": self.rule, "file": self.file, "line": self.line, "message": self.message, "fingerprint": self.fingerprint}


def quality_defaults(root: Path, initialize: bool = False) -> Dict:
    """Provide editable commands; initialization alone may create freeze stores."""
    build = detect_build(root)
    value = "true" if initialize else "false"
    freeze = ["-D%s=%s" % (key, "false" if key.endswith("refreeze") else value) for key in FREEZE_KEYS]
    if build == "maven":
        executable = ("./mvnw.cmd" if os.name == "nt" else "./mvnw") if (root / ("mvnw.cmd" if os.name == "nt" else "mvnw")).is_file() else "mvn"
        commands = {
            "archunit": [executable, "-o", "-q", "test", "-Dtest=*Arch*", "-Dmaven.test.failure.ignore=true", "-DskipTests=false", "-Dmaven.test.skip=false"] + freeze,
            "checkstyle": [executable, "-o", "-q", "checkstyle:checkstyle"],
            "spotbugs": [executable, "-o", "-q", "test-compile", "spotbugs:spotbugs", "-Dspotbugs.xmlOutput=true"],
            "pmd": [executable, "-o", "-q", "pmd:pmd"],
        }
        reports = {"archunit": "**/target/surefire-reports/TEST-*Arch*.xml", "checkstyle": "**/target/checkstyle-result.xml", "spotbugs": "**/target/spotbugsXml.xml", "pmd": "**/target/pmd.xml"}
    else:
        executable = ("./gradlew.bat" if os.name == "nt" else "./gradlew") if (root / ("gradlew.bat" if os.name == "nt" else "gradlew")).is_file() else "gradle"
        commands = {
            "archunit": [executable, "--offline", "test", "--tests", "*Arch*", "--rerun-tasks"] + freeze,
            "checkstyle": [executable, "--offline", "checkstyleMain", "--rerun-tasks"],
            "spotbugs": [executable, "--offline", "spotbugsMain", "--rerun-tasks"],
            "pmd": [executable, "--offline", "pmdMain", "--rerun-tasks"],
        }
        reports = {"archunit": "**/build/test-results/test/TEST-*Arch*.xml", "checkstyle": "**/build/reports/checkstyle/main.xml", "spotbugs": "**/build/reports/spotbugs/main.xml", "pmd": "**/build/reports/pmd/main.xml"}
    result = {check: {"command": commands[check], "report_path": reports[check]} for check in commands}
    result["sqlfluff"] = {"command": ["sqlfluff", "lint", "--format", "json", "-"], "report_path": "-", "source": "java-resources"}
    return result


def _file(root, value, report=None, java_source=False):
    if not isinstance(value, str) or not value.strip():
        raise JavaError("违规报告缺少文件路径")
    value = value.replace("\\", "/")
    path = Path(value)
    if path.is_absolute():
        try:
            return path.relative_to(root.resolve()).as_posix()
        except ValueError:
            raise JavaError("违规文件不在项目目录内")
    if ".." in path.parts:
        raise JavaError("违规文件路径越过项目目录")
    if java_source:
        module = _module(root, report) if report is not None else root
        direct = module / "src/main/java" / path
        if direct.is_file():
            return direct.relative_to(root).as_posix()
        matches = list(module.glob("**/src/main/java/" + path.as_posix()))
        if len(matches) == 1:
            return matches[0].relative_to(root).as_posix()
        if len(matches) > 1:
            raise JavaError("违规文件在多个 Java 模块中无法唯一定位：%s" % value)
        return direct.relative_to(root).as_posix()
    if report is None:
        return path.as_posix()
    module = _module(root, report)
    module_parts = module.relative_to(root).parts
    if module_parts and path.parts[:len(module_parts)] == module_parts:
        return path.as_posix()
    return (module / path).relative_to(root).as_posix()


def _text(element):
    return " ".join("".join(element.itertext()).split())


def _parse_quality(root, check, path=None, stdout=None):
    result = []
    if check == "sqlfluff":
        try:
            data = json.loads(stdout if stdout is not None else path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, ValueError) as exc:
            raise JavaError("SQLFluff JSON 报告损坏：%s" % exc)
        if not isinstance(data, list):
            raise JavaError("SQLFluff 报告必须是数组")
        for entry in data:
            if not isinstance(entry, dict) or not isinstance(entry.get("violations"), list):
                raise JavaError("SQLFluff 文件记录无效")
            filename = _file(root, entry.get("filepath"), path)
            for item in entry["violations"]:
                if not isinstance(item, dict) or not isinstance(item.get("code"), str) or not isinstance(item.get("description"), str):
                    raise JavaError("SQLFluff 违规记录无效")
                if item["code"] in ("PRS", "LXR", "TMP"):
                    raise JavaError("SQLFluff 无法解析或展开 SQL：%s" % item["description"])
                number = _number(item.get("start_line_no", item.get("line_no")), "SQLFluff 行号")
                result.append(Violation(check, item["code"], filename, number, item["description"]))
        return result
    document = _xml(path)
    expected = {"checkstyle": "checkstyle", "spotbugs": "BugCollection", "pmd": "pmd"}
    if check in expected and _tag(document) != expected[check]:
        raise JavaError("%s 报告格式错误" % check)
    if check == "checkstyle":
        for source in document:
            if _tag(source) != "file":
                raise JavaError("Checkstyle 报告包含工具错误")
            filename = _file(root, source.get("name"), path)
            for item in source:
                if _tag(item) != "error" or not item.get("source") or not item.get("message"):
                    raise JavaError("Checkstyle 违规记录无效")
                result.append(Violation(check, item.get("source"), filename, _number(item.get("line"), "Checkstyle 行号"), item.get("message")))
    elif check == "pmd":
        for source in document:
            if _tag(source) in ("error", "processingerror", "configerror"):
                raise JavaError("PMD 报告包含工具错误")
            if _tag(source) != "file":
                continue
            filename = _file(root, source.get("name"), path)
            for item in source:
                if _tag(item) != "violation" or not item.get("rule") or not _text(item):
                    raise JavaError("PMD 违规记录无效")
                result.append(Violation(check, item.get("rule"), filename, _number(item.get("beginline"), "PMD 行号"), _text(item)))
    elif check == "spotbugs":
        for item in document.iter():
            if _tag(item) == "Errors" and (_number(item.get("errors", "0"), "SpotBugs 错误数") or list(item)):
                raise JavaError("SpotBugs 报告包含分析错误")
            if _tag(item) != "BugInstance":
                continue
            sources = [node for node in item.iter() if _tag(node) == "SourceLine" and (node.get("sourcepath") or node.get("sourcefile"))]
            messages = [node for node in item if _tag(node) in ("LongMessage", "ShortMessage")]
            if not sources or not messages or not item.get("type"):
                raise JavaError("SpotBugs 违规记录不完整")
            source = next((node for node in sources if node.get("primary") == "true"), sources[0])
            filename = _file(root, source.get("sourcepath") or source.get("sourcefile"), path, True)
            result.append(Violation(check, item.get("type"), filename, _number(source.get("start", "0"), "SpotBugs 行号"), _text(messages[0])))
    elif check == "archunit":
        counts = _suite_counts(document)
        if counts["errors"] or counts["tests"] <= counts["skipped"]:
            raise JavaError("ArchUnit 测试未运行或发生执行错误")
        for case in document.iter():
            if _tag(case) != "testcase":
                continue
            for failure in case:
                if _tag(failure) != "failure":
                    continue
                if failure.get("type") and "Assertion" not in failure.get("type"):
                    raise JavaError("ArchUnit 测试发生工具异常")
                message = failure.get("message") or _text(failure)
                rule = case.get("name")
                if not message or not rule:
                    raise JavaError("ArchUnit 违规记录不完整")
                match = re.search(r"([\w/.$-]+\.java):(\d+)", message)
                filename, number = "-", 0
                if match:
                    source_name, number = match.group(1), int(match.group(2))
                    module = _module(root, path)
                    candidates = list(module.glob("**/src/main/java/**/" + Path(source_name).name))
                    qualified = []
                    for source in candidates:
                        relative = source.relative_to(root).as_posix()
                        class_name = relative.split("src/main/java/", 1)[1][:-5].replace("/", ".")
                        if class_name in message:
                            qualified.append(source)
                    candidates = qualified or candidates
                    if len(candidates) != 1:
                        raise JavaError("ArchUnit 违规源码无法唯一定位：%s" % source_name)
                    filename = candidates[0].relative_to(root).as_posix()
                result.append(Violation(check, rule, filename, number, message))
        if counts["failures"] != len(result):
            raise JavaError("ArchUnit 失败计数与报告不一致")
    return result


def _signature(path):
    stat = path.stat()
    return stat.st_mtime_ns, stat.st_ctime_ns, stat.st_size, hashlib.sha256(path.read_bytes()).hexdigest()


def _freeze_command(command, initialize):
    result = []
    for arg in command:
        key, separator, value = arg.partition("=")
        canonical = next((item for item in FREEZE_KEYS if key in
                          ("-D" + item, "-D" + item.replace(".", "_"),
                           "-D" + item.replace("_", "."))), None)
        if canonical:
            desired = "true" if initialize and not canonical.endswith("refreeze") else "false"
            if desired == "false" and (not separator or value != "false"):
                raise JavaError("ArchUnit gate 禁止创建或扩大冻结基线")
            arg = "-D%s=%s" % (canonical, desired)
        result.append(arg)
    return result


def _mapper_sql(root, path):
    """Expand static mapper statements in memory while keeping source line origins."""
    parser = expat.ParserCreate()
    stack = []
    roots = []

    def start(name, attributes):
        node = {"tag": name, "attrs": attributes, "parts": [], "line": parser.CurrentLineNumber}
        if stack:
            stack[-1]["parts"].append(node)
        else:
            roots.append(node)
        stack.append(node)

    def characters(value):
        if stack:
            stack[-1]["parts"].append((value, parser.CurrentLineNumber))

    def doctype(name, system_id, public_id, internal_subset):
        if internal_subset:
            raise JavaError("Mapper 不支持内部 DTD 实体")

    parser.StartElementHandler = start
    parser.EndElementHandler = lambda name: stack.pop()
    parser.CharacterDataHandler = characters
    parser.StartDoctypeDeclHandler = doctype
    parser.ExternalEntityRefHandler = lambda *args: 1
    try:
        parser.Parse(path.read_text(encoding="utf-8"), True)
    except (expat.ExpatError, OSError, UnicodeError) as exc:
        raise JavaError("Mapper XML 无法解析：%s（%s）" % (path.relative_to(root).as_posix(), exc))
    if not roots or roots[0]["tag"] != "mapper":
        return []
    mapper = roots[0]
    children = [part for part in mapper["parts"] if isinstance(part, dict)]
    fragments = {}
    for node in children:
        if node["tag"] == "sql":
            name = node["attrs"].get("id")
            if not name or name in fragments:
                raise JavaError("Mapper SQL 片段编号缺失或重复")
            fragments[name] = node
    namespace = mapper["attrs"].get("namespace", "")

    def expand(node, seen):
        result = []
        for part in node["parts"]:
            if isinstance(part, tuple):
                result.append(part)
            elif part["tag"] == "include":
                key = part["attrs"].get("refid", "")
                if namespace and key.startswith(namespace + "."):
                    key = key[len(namespace) + 1:]
                if key not in fragments or key in seen or part["parts"]:
                    raise JavaError("Mapper include 无法静态展开：%s" % key)
                result.extend(expand(fragments[key], seen | {key}))
            else:
                raise JavaError("Mapper 动态 SQL 需要配置专用提取命令：%s" % part["tag"])
        return result

    statements = []
    for node in children:
        if node["tag"] not in ("select", "insert", "update", "delete"):
            continue
        text = ""
        origins = []
        for value, number in expand(node, set()):
            text += value
            for char in value:
                origins.append(number)
                if char == "\n":
                    number += 1
        if "${" in text:
            raise JavaError("Mapper 含无法确定的动态 SQL 取值")
        # Bind values are literals; preserving whitespace keeps report locations useful.
        pieces = []
        mapped = []
        offset = 0
        for match in re.finditer(r"#\{[^{}]+\}", text):
            pieces.append(text[offset:match.start()])
            mapped.extend(origins[offset:match.start()])
            pieces.append("NULL")
            mapped.extend([origins[match.start()]] * 4)
            offset = match.end()
        pieces.append(text[offset:])
        mapped.extend(origins[offset:])
        sql = "".join(pieces)
        if "#{" in sql or not sql.strip():
            raise JavaError("Mapper SQL 内容为空或绑定参数无效")
        line_map = []
        index = 0
        for line in sql.splitlines(keepends=True):
            line_map.append(mapped[index])
            index += len(line)
        statements.append((path.relative_to(root).as_posix(), sql, line_map))
    return statements


def _sql_resources(root, command, environment, timeout):
    sources = []
    for directory in sorted(root.glob("**/src/main/resources")):
        if any(part in (".git", "target", "build") for part in directory.relative_to(root).parts):
            continue
        for path in sorted(directory.rglob("*")):
            if path.is_file() and path.suffix.lower() == ".sql":
                sql = path.read_text(encoding="utf-8")
                if sql.strip():
                    sources.append((path.relative_to(root).as_posix(), sql, list(range(1, len(sql.splitlines()) + 1))))
            elif path.is_file() and path.suffix.lower() == ".xml":
                sources.extend(_mapper_sql(root, path))
    result = []
    deadline = time.monotonic() + timeout
    for filename, sql, lines in sources:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise JavaError("SQL 检查超时")
        process = subprocess.run(command, input=sql, cwd=str(root), env=environment,
                                 stdout=subprocess.PIPE, stderr=subprocess.PIPE, encoding="utf-8",
                                 errors="replace", timeout=remaining, check=False, shell=False)
        if process.returncode not in (0, 1):
            raise JavaError("SQLFluff 命令异常退出：%s" % process.returncode)
        current = _parse_quality(root, "sqlfluff", stdout=process.stdout)
        if process.returncode == 1 and not current:
            raise JavaError("SQLFluff 命令失败且报告没有对应违规")
        for item in current:
            if item.line < 1 or item.line > len(lines):
                raise JavaError("SQLFluff 行号超出提取的 SQL")
            result.append(Violation(item.check, item.rule, filename, lines[item.line - 1], item.message))
    return result


def run_quality(root: Path, quality: Dict, initialize: bool = False) -> Tuple[List[Violation], Dict[str, str]]:
    """Execute all checks and accept only fresh reports from successful checks."""
    violations = []
    errors = {}
    for check in CHECKS:
        try:
            entry = quality.get(check) if isinstance(quality, dict) else None
            if not isinstance(entry, dict) or entry.get("enabled", True) is not True:
                raise JavaError("检查配置缺失或被禁用")
            command = _argv(entry.get("command"))
            if command[0].lower() in ("off", "false", "disabled"):
                raise JavaError("检查不能关闭")
            report_path = entry.get("report_path")
            if report_path is None or report_path == "-" and check != "sqlfluff":
                raise JavaError("检查缺少有效报告路径")
            timeout = entry.get("timeout", 120)
            if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or not 0 < timeout <= 600:
                raise JavaError("检查超时必须在 0 到 600 秒之间")
            environment = os.environ.copy()
            if check == "archunit":
                command = _freeze_command(command, initialize)
                value = "true" if initialize else "false"
                environment["JAVA_TOOL_OPTIONS"] = (environment.get("JAVA_TOOL_OPTIONS", "") + " " + " ".join("-D%s=%s" % (key, "false" if key.endswith("refreeze") else value) for key in FREEZE_KEYS)).strip()
            if check == "sqlfluff" and entry.get("source") is not None:
                if entry["source"] != "java-resources" or report_path != "-":
                    raise JavaError("SQL 输入模式无效，需要 java-resources 与标准输出报告")
                violations.extend(_sql_resources(root, command, environment, timeout))
                continue
            suffix = ".json" if check == "sqlfluff" else ".xml"
            before = {} if report_path == "-" else {path: _signature(path) for path in _paths(root, report_path, required=False, suffix=suffix)}
            started = time.time()
            process = subprocess.run(command, cwd=str(root), env=environment, stdout=subprocess.PIPE, stderr=subprocess.PIPE, encoding="utf-8", errors="replace", timeout=timeout, check=False, shell=False)
            if process.returncode != 0 and not (check == "sqlfluff" and process.returncode == 1):
                raise JavaError("检查命令未完成（退出 %s），XML 检查须配置为只生成报告且成功退出" % process.returncode)
            current = []
            if report_path == "-":
                current = _parse_quality(root, check, stdout=process.stdout)
            else:
                for path in _paths(root, report_path, suffix=suffix):
                    signature = _signature(path)
                    if signature == before.get(path) or path.stat().st_mtime < started - 2:
                        raise JavaError("检查未生成本次报告，检测到陈旧文件：%s" % path.relative_to(root).as_posix())
                    current.extend(_parse_quality(root, check, path))
            if process.returncode == 1 and not current:
                raise JavaError("检查命令失败且报告没有对应违规")
            violations.extend(current)
        except (JavaError, OSError, ValueError, subprocess.SubprocessError) as exc:
            errors[check] = "%s 检查失败：%s" % (check, exc)
    unique = {violation.fingerprint: violation for violation in violations}
    return sorted(unique.values(), key=lambda item: (item.check, item.file, item.rule, item.line)), errors


def load_baseline(path: Path) -> List[Violation]:
    """Validate the complete, versioned baseline rather than ignoring bad rows."""
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValueError) as exc:
        raise JavaError("质量基线无法读取或已损坏：%s" % exc)
    if not isinstance(value, dict) or set(value) != {"version", "violations"} or type(value["version"]) is not int or value["version"] != 1 or not isinstance(value["violations"], list):
        raise JavaError("质量基线格式或版本无效")
    result = []
    seen = set()
    for row in value["violations"]:
        if not isinstance(row, dict) or set(row) != {"check", "rule", "file", "line", "message", "fingerprint"}:
            raise JavaError("质量基线违规记录不完整")
        if row["check"] not in CHECKS or any(not isinstance(row[key], str) or not row[key].strip() for key in ("rule", "file", "message", "fingerprint")):
            raise JavaError("质量基线违规字段无效")
        if not isinstance(row["line"], int) or isinstance(row["line"], bool) or row["line"] < 0 or "\\" in row["file"] or Path(row["file"]).is_absolute() or ".." in Path(row["file"]).parts:
            raise JavaError("质量基线位置无效")
        violation = Violation(row["check"], row["rule"], row["file"], row["line"], row["message"])
        if row["fingerprint"] != violation.fingerprint or violation.fingerprint in seen:
            raise JavaError("质量基线指纹不一致或重复")
        seen.add(violation.fingerprint)
        result.append(violation)
    return result
