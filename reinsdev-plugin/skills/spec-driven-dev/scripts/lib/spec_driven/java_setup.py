"""Maven quality onboarding. Owner: T16; no changes to gate execution."""

import copy
import difflib
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
from typing import Dict, List
import xml.etree.ElementTree as ET
from xml.parsers import expat

from . import java


ARCHUNIT = "1.3.0"
PLUGINS = {
    "checkstyle": "org.apache.maven.plugins:maven-checkstyle-plugin:3.6.0:checkstyle",
    "pmd": "org.apache.maven.plugins:maven-pmd-plugin:3.26.0:pmd",
    "spotbugs": "com.github.spotbugs:spotbugs-maven-plugin:4.9.3.0:spotbugs",
}
LAYERS = ("foundation", "domain", "application", "adapter")
TEMPLATES = Path(__file__).resolve().parents[3] / "templates/quality"


def read_text(path):
    """Keep original newline bytes when inserting into a POM."""
    return path.read_bytes().decode("utf-8")


def write_text(path, text):
    with path.open("w", encoding="utf-8", newline="") as stream:
        stream.write(text)


def load_config(root):
    path = root / ".openspec/.config.json"
    try:
        result = json.loads(read_text(path)) if path.exists() else {}
    except (ValueError, OSError) as exc:
        raise ValueError("团队配置无法读取：%s" % exc)
    if not isinstance(result, dict) or not isinstance(result.get("quality", {}), dict):
        raise ValueError("团队配置与 quality 必须是 JSON 对象")
    return result


def pom_tree(path):
    text = read_text(path)
    if "<!DOCTYPE" in text or "<!ENTITY" in text:
        raise ValueError("pom 含 DTD/实体，无法安全做最小插入：%s" % path)
    node = ET.fromstring(text)
    if node.tag.split("}")[-1] != "project":
        raise ValueError("pom 根节点必须是 project：%s" % path)
    return node


def modules(root):
    """Discover the static reactor, refusing uncertain profile modules."""
    found = []
    seen = set()

    def visit(directory):
        directory = directory.resolve()
        try:
            directory.relative_to(root)
        except ValueError:
            raise ValueError("模块超出项目目录：%s" % directory)
        if directory in seen:
            raise ValueError("模块重复或形成循环：%s" % directory)
        seen.add(directory)
        tree = pom_tree(directory / "pom.xml")
        if tree.findall("{*}profiles/{*}profile/{*}modules/{*}module"):
            raise ValueError("存在 profile 条件模块，无法确定激活范围；请在确认的模块内执行")
        found.append((directory, tree))
        for node in tree.findall("{*}modules/{*}module"):
            name = (node.text or "").strip()
            if not name or "${" in name:
                raise ValueError("模块路径未确定：%s" % name)
            visit(directory / name)

    visit(root)
    return found


def inherited_dependencies(directory, root, seen=None):
    seen = set() if seen is None else seen
    if directory in seen:
        raise ValueError("pom parent 形成循环")
    seen.add(directory)
    tree = pom_tree(directory / "pom.xml")
    result = tree.findall("{*}dependencies/{*}dependency")
    parent = tree.find("{*}parent")
    if parent is not None:
        rel = parent.find("{*}relativePath")
        name = "../pom.xml" if rel is None else (rel.text or "").strip()
        if name:
            path = (directory / name).resolve()
            if path.is_dir():
                path = path / "pom.xml"
            if path.is_file() and (path.parent == root or root in path.parents):
                result += inherited_dependencies(path.parent, root, seen)
    return result


def detect_junit(directory, root, confirmed=None):
    versions = set()
    for dep in inherited_dependencies(directory, root):
        group = dep.findtext("{*}groupId", "")
        artifact = dep.findtext("{*}artifactId", "")
        if group == "junit" and artifact == "junit":
            versions.add("4")
        if group == "org.junit.jupiter" and artifact.startswith("junit-jupiter"):
            versions.add("5")
    for path in (directory / "src/test/java").rglob("*.java"):
        text = read_text(path)
        if re.search(r"import\s+org\.junit\.jupiter\.", text):
            versions.add("5")
        if re.search(r"import\s+org\.junit\.(?:Test|Before|After|runner)\b", text):
            versions.add("4")
    if confirmed:
        return confirmed
    if len(versions) != 1:
        raise ValueError("%s 的 JUnit 无法唯一确定（候选：%s）；请确认后用 --junit 4 或 --junit 5 重试" %
                         (directory.relative_to(root).as_posix(), ", ".join(sorted(versions)) or "无"))
    return next(iter(versions))


def base_package(directory, confirmed=None):
    packages = set()
    for path in (directory / "src/main/java").rglob("*.java"):
        matches = re.findall(r"(?m)^\s*package\s+([A-Za-z_][\w]*(?:\.[A-Za-z_][\w]*)*)\s*;", read_text(path))
        if len(matches) != 1:
            raise ValueError("无法识别 package 声明：%s；请确认目录和包名" % path)
        expected = path.parent.relative_to(directory / "src/main/java").as_posix().replace("/", ".")
        if matches[0] != expected:
            raise ValueError("package 与源码目录不一致：%s" % path)
        packages.add(matches[0])
    if confirmed:
        if not re.fullmatch(r"[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*", confirmed) or not packages or not all(
                p == confirmed or p.startswith(confirmed + ".") for p in packages):
            raise ValueError("确认的基础包必须覆盖该模块的实际 package，候选：%s" % ", ".join(sorted(packages)))
        return confirmed
    candidates = set()
    for package in packages:
        parts = package.split(".")
        for index, part in enumerate(parts):
            if part in LAYERS and index:
                candidates.add(".".join(parts[:index]))
                break
    if len(candidates) == 1:
        candidate = next(iter(candidates))
        if all(p == candidate or p.startswith(candidate + ".") for p in packages):
            return candidate
    raise ValueError("无法确定分层基础包，候选：%s；请确认后用 --base-package <包名> 重试" %
                     ", ".join(sorted(packages)))


def insert_dependency(text, artifact):
    """Use XML byte offsets, not serialization, to preserve existing text."""
    data = text.encode("utf-8")
    parser = expat.ParserCreate()
    stack = []
    spans = []

    def start(name, attrs):
        stack.append((name, parser.CurrentByteIndex))

    def end(name):
        tag, offset = stack.pop()
        path = tuple(n.split(":")[-1] for n, unused in stack) + (name.split(":")[-1],)
        spans.append((path, tag, offset, parser.CurrentByteIndex))

    parser.StartElementHandler = start
    parser.EndElementHandler = end
    parser.Parse(data, True)
    root = next(s for s in spans if s[0] == ("project",))
    prefix = root[1].split(":")[0] + ":" if ":" in root[1] else ""
    nl = "\r\n" if "\r\n" in text else "\n"
    dependency = ("    <%(p)sdependency>\n"
                  "      <%(p)sgroupId>com.tngtech.archunit</%(p)sgroupId>\n"
                  "      <%(p)sartifactId>%(a)s</%(p)sartifactId>\n"
                  "      <%(p)sversion>%(v)s</%(p)sversion>\n"
                  "      <%(p)sscope>test</%(p)sscope>\n"
                  "    </%(p)sdependency>") % {"p": prefix, "a": artifact, "v": ARCHUNIT}
    dependency = dependency.replace("\n", nl)
    container = next((s for s in spans if s[0] == ("project", "dependencies")), None)
    if container:
        opening_end = data.index(b">", container[2]) + 1
        if data[container[2]:opening_end].rstrip().endswith(b"/>"):
            opening = data[container[2]:opening_end].decode("utf-8")
            replacement = opening[:-2] + ">" + nl + dependency + nl + "  </%sdependencies>" % prefix
            return (data[:container[2]] + replacement.encode("utf-8") + data[opening_end:]).decode("utf-8")
        point = container[3]
        insertion = nl + dependency + nl + "  "
    else:
        point = root[3]
        insertion = nl + "  <%sdependencies>" % prefix + nl + dependency + nl + "  </%sdependencies>" % prefix + nl
    return (data[:point] + insertion.encode("utf-8") + data[point:]).decode("utf-8")


class Plan:
    def __init__(self, root):
        self.root = root
        self.changes = {}  # type: Dict[Path, str]
        self.originals = {}  # type: Dict[Path, bytes]
        self.poms = []  # type: List[Path]
        self.notes = []  # type: List[str]
        self.quality = {}

    def add(self, path, text):
        if self.root not in path.resolve().parents:
            raise ValueError("计划写入路径超出项目目录：%s" % path)
        original = path.read_bytes() if path.exists() else None
        if original == text.encode("utf-8"):
            return
        self.changes[path] = text
        self.originals[path] = original

    def render(self):
        parts = list(self.notes)
        for path, text in self.changes.items():
            name = path.relative_to(self.root).as_posix()
            old = (self.originals[path] or b"").decode("utf-8")
            parts.append("修改 %s\n%s" % (name, "".join(difflib.unified_diff(
                old.splitlines(True), text.splitlines(True), fromfile=name, tofile=name))))
        return "\n".join(parts) if parts else "接入文件已存在，无需修改。"


def plan(root, confirmed_package=None, confirmed_junit=None):
    root = root.resolve()
    if java.detect_build(root) != "maven":
        raise ValueError("Gradle 自动接入暂不支持。请手工配置 checkstyle、pmd、com.github.spotbugs 插件，添加 ArchUnit 测试及冻结规则，配置 quality 的命令和报告路径后再执行 init-config --java。")
    result = Plan(root)
    config = load_config(root)
    reactor = modules(root)
    selected = []
    for directory, tree in reactor:
        name = directory.relative_to(root).as_posix()
        sources = list((directory / "src/main/java").rglob("*.java"))
        if not sources:
            result.notes.append("模块 %s：无 Java 业务源码，不修改。" % name)
            continue
        selected.append(name)
        package = base_package(directory, confirmed_package)
        junit = detect_junit(directory, root, confirmed_junit)
        result.notes.append("模块 %s：基础包 %s，JUnit %s；生成 Foundation → Domain → Application → Adapter 依赖约束，缺少的层为可选。" % (name, package, junit))
        artifact = "archunit-junit%s" % junit
        deps = inherited_dependencies(directory, root)
        if not any(d.findtext("{*}groupId") == "com.tngtech.archunit" and d.findtext("{*}artifactId") == artifact for d in deps):
            path = directory / "pom.xml"
            updated = insert_dependency(read_text(path), artifact)
            ET.fromstring(updated)
            result.add(path, updated)
            result.poms.append(path)
            result.notes.append("修改前备份：%s.reins-bak" % path.relative_to(root).as_posix())
        else:
            result.notes.append("ArchUnit 依赖已存在，不重复添加。")
        test = directory / "src/test/java" / package.replace(".", "/") / "architecture/ReinsArchTest.java"
        if test.exists():
            result.notes.append("%s 已存在，不覆盖；请核对冻结参数和分层规则。" % test.relative_to(root).as_posix())
        else:
            text = read_text(TEMPLATES / "ReinsArchTest.java.template")
            store = Path(os.path.relpath(root / ".openspec/archunit-store" / (name if name != "." else "root"), directory)).as_posix()
            text = text.replace("<base-package>", package).replace("<junit-import>", "org.junit.jupiter.api.Test" if junit == "5" else "org.junit.Test")
            result.add(test, text.replace("<freeze-store>", store))
    if not selected:
        raise ValueError("没有含 src/main/java 业务源码的 Maven 模块，无法接入")
    quality = copy.deepcopy(java.quality_defaults(root))
    prefix = quality["archunit"]["command"][:]
    prefix = prefix[:prefix.index("test")]
    if len(reactor) > 1:
        prefix += ["-pl", ",".join(selected)]
        arch = quality["archunit"]["command"]
        quality["archunit"]["command"] = prefix + arch[arch.index("test"):]
    quality["checkstyle"]["command"] = prefix + [PLUGINS["checkstyle"], "-Dcheckstyle.config.location=google_checks.xml"]
    quality["pmd"]["command"] = prefix + [PLUGINS["pmd"]]
    quality["spotbugs"]["command"] = prefix + ["test-compile", PLUGINS["spotbugs"], "-Dspotbugs.xmlOutput=true"]
    for name, value in config.get("quality", {}).items():
        if not isinstance(value, dict):
            raise ValueError("quality.%s 必须是对象" % name)
        quality.setdefault(name, {}).update(value)
        result.notes.append("保留已有 quality.%s 配置。" % name)
    config["quality"] = quality
    result.quality = quality
    result.add(root / ".openspec/.config.json", json.dumps(config, ensure_ascii=False, indent=2) + "\n")
    sql = list(root.glob("**/src/main/resources/**/*.sql")) + list(root.glob("**/src/main/resources/**/*Mapper.xml"))
    if not sql:
        result.notes.append("未发现 SQL 文件；无 SQL/MyBatis 资源时可以不装 SQLFluff。")
    elif not shutil.which("sqlfluff"):
        result.notes.append("SQLFluff 未安装：由用户运行 pip install sqlfluff，并在 .sqlfluff 配置 [sqlfluff] / dialect = <实际数据库方言，如 postgres/mysql>；数据库无法自动确认，不写猜测的方言。")
    else:
        result.notes.append("SQLFluff 已可用；请确认 .sqlfluff 的 dialect 与项目数据库一致。")
    return result


def warm(result):
    """Run report goals online without creating or changing a quality baseline."""
    logs = result.root / ".openspec/quality-setup-logs"
    logs.mkdir(parents=True, exist_ok=True)
    settings = result.root / ".mvn/maven.config"
    if settings.exists() and any(value in ("-o", "--offline") for value in shlex.split(read_text(settings))):
        raise ValueError(".mvn/maven.config 强制离线，请用户移除 -o/--offline 后再预热；不擅自修改 Maven 配置")
    for name in ("archunit", "checkstyle", "pmd", "spotbugs"):
        configured = result.quality[name].get("command")
        if not isinstance(configured, list) or not configured or Path(configured[0]).name not in ("mvn", "mvn.cmd", "mvnw", "mvnw.cmd"):
            raise ValueError("保留的 quality.%s 不是可识别的 Maven 参数列表，请手工预热；不会执行未知命令" % name)
        command = [str(value) for value in configured if value not in ("-o", "--offline")]
        command.insert(1, "-B")
        env = dict(os.environ)
        try:
            run = subprocess.run(command, cwd=str(result.root), env=env, capture_output=True,
                                 encoding="utf-8", errors="replace", timeout=600)
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise RuntimeError("%s 预热未完成：%s" % (name, exc))
        path = logs / (name + ".log")
        write_text(path, "命令：%s\n退出码：%s\n%s\n%s" % (json.dumps(command, ensure_ascii=False), run.returncode, run.stdout, run.stderr))
        if run.returncode:
            raise RuntimeError("%s 预热失败（退出 %s），见 %s" % (name, run.returncode, path.relative_to(result.root).as_posix()))


def apply(result, online=False):
    """Restore managed files on any failure; keep build logs for diagnosis."""
    root = result.root
    lock = root / ".openspec/.quality-setup.lock"
    lock.parent.mkdir(parents=True, exist_ok=True)
    try:
        fd = os.open(str(lock), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError:
        raise ValueError("quality setup 正在运行或留有锁，请确认原进程结束后清理 .openspec/.quality-setup.lock")
    os.close(fd)
    originals = dict(result.originals)
    written = []
    try:
        for path, original in result.originals.items():
            if (path.read_bytes() if path.exists() else None) != original:
                raise ValueError("文件在预览后发生变化，请重新执行：%s" % path)
        for pom in result.poms:
            backup = pom.with_name("pom.xml.reins-bak")
            old = backup.read_bytes() if backup.exists() else None
            if old is not None and old != result.originals[pom]:
                raise ValueError("已有不同的 pom.xml.reins-bak，请先人工保管；不覆盖旧备份")
            originals[backup] = old
            if old is None:
                written.append(backup)
                write_text(backup, result.originals[pom].decode("utf-8"))
        for path, text in result.changes.items():
            path.parent.mkdir(parents=True, exist_ok=True)
            written.append(path)
            write_text(path, text)
        if online:
            warm(result)
    except Exception:
        for path in reversed(written):
            old = originals[path]
            if old is None:
                if path.exists():
                    path.unlink()
            else:
                # Restoration must not depend on the failed writing helper.
                with path.open("wb") as stream:
                    stream.write(old)
        raise
    finally:
        lock.unlink()
