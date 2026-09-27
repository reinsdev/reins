"""Project and artifact layout (design doc §3.1). The only place that knows
where things live under `.openspec/`; every other module asks here."""

from pathlib import Path
from typing import List, Optional

OPENSPEC = ".openspec"

# Artifact file names inside a change directory.
META = ".meta.json"
INVARIANTS = "invariants.json"
PROPOSAL = "proposal.md"
BUGFIX_ANALYSIS = "bugfix-analysis.md"
DESIGN = "design.md"
SPEC = "spec.md"
TASKS = "tasks.md"
SPEC_REVIEW = "spec-review.md"
IMPLEMENTATION_LOG = "implementation-log.md"
STATIC_ANALYSIS = "static-analysis-report.md"
QA_REPORT = "qa-report.md"
CODE_REVIEW = "code-review.md"
DEPLOY_REPORT = "deploy-report.md"
RETROSPECTIVE = "retrospective.md"


def find_root(start: Optional[Path] = None) -> Path:
    """Nearest directory upward holding `.openspec/`, else the git root, else `start`."""
    start = (start or Path.cwd()).resolve()
    for d in [start] + list(start.parents):
        if (d / OPENSPEC).is_dir():
            return d
    for d in [start] + list(start.parents):
        if (d / ".git").exists():
            return d
    return start


class Project:
    def __init__(self, root: Path):
        self.root = Path(root)

    @classmethod
    def here(cls, start: Optional[Path] = None) -> "Project":
        return cls(find_root(start))

    @property
    def openspec(self) -> Path:
        return self.root / OPENSPEC

    @property
    def enabled(self) -> bool:
        return self.openspec.is_dir()

    @property
    def config_path(self) -> Path:
        return self.openspec / ".config.json"

    @property
    def changes_dir(self) -> Path:
        return self.openspec / "changes"

    @property
    def archive_dir(self) -> Path:
        return self.changes_dir / "archive"

    @property
    def specs_dir(self) -> Path:
        return self.openspec / "specs"

    @property
    def decisions_dir(self) -> Path:
        return self.openspec / "decisions"

    @property
    def architecture(self) -> Path:
        return self.openspec / "architecture.md"

    @property
    def quality_baseline(self) -> Path:
        return self.openspec / "quality-baseline.json"

    def change_dir(self, change: str) -> Path:
        return self.changes_dir / change

    def active_changes(self) -> List[str]:
        """Names of changes with a `.meta.json`, excluding the archive."""
        if not self.changes_dir.is_dir():
            return []
        return sorted(p.parent.name for p in self.changes_dir.glob("*/" + META)
                      if p.parent.name != "archive")

    def is_java(self) -> bool:
        """Maven or Gradle build file at the root (gate-0)."""
        return any((self.root / f).is_file() for f in ("pom.xml", "build.gradle", "build.gradle.kts"))
