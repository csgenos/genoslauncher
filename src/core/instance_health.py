"""Instance health check and safe optimizer actions."""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path

from .instances import repair_instance_layout, validate_instance


@dataclass(frozen=True)
class HealthIssue:
    code: str
    message: str
    severity: str  # high, medium, low


@dataclass(frozen=True)
class HealthReport:
    score: int
    issues: list[HealthIssue]
    reclaimable_bytes: int


def _dir_size(path: Path) -> int:
    total = 0
    if not path.exists():
        return 0
    for p in path.rglob("*"):
        if p.is_file():
            try:
                total += p.stat().st_size
            except OSError:
                pass
    return total


def analyze_instance_health(instance: dict) -> HealthReport:
    issues: list[HealthIssue] = []
    reclaimable = 0
    score = 100

    ok, validate_issues = validate_instance(instance)
    if not ok:
        issues.append(HealthIssue("layout.invalid", "; ".join(validate_issues[:2]), "high"))
        score -= 25

    root = Path(str(instance.get("directory", "")).strip())
    logs_dir = root / "logs"
    crash_dir = root / "crash-reports"
    mods_dir = root / "mods"

    logs_size = _dir_size(logs_dir)
    crashes_size = _dir_size(crash_dir)
    reclaimable += logs_size + crashes_size
    if logs_size > 100 * 1024 * 1024:
        issues.append(HealthIssue("logs.large", "Instance logs are large; cleanup recommended.", "low"))
        score -= 8
    if crashes_size > 50 * 1024 * 1024:
        issues.append(HealthIssue("crash.large", "Crash reports are accumulating significant size.", "low"))
        score -= 6

    if mods_dir.exists():
        mod_count = sum(1 for p in mods_dir.iterdir() if p.is_file() and p.suffix.lower() == ".jar")
        if mod_count > 250:
            issues.append(HealthIssue("mods.heavy", f"Very large mod set detected ({mod_count} mods).", "medium"))
            score -= 10

    for rel in ("mods", "saves", "resourcepacks", "shaderpacks", "screenshots"):
        if not (root / rel).exists():
            issues.append(HealthIssue("layout.missing", f"Missing expected folder: {rel}", "medium"))
            score -= 4

    score = max(0, min(score, 100))
    return HealthReport(score=score, issues=issues[:12], reclaimable_bytes=reclaimable)


def optimize_instance(instance: dict) -> tuple[int, list[str]]:
    """Run safe optimization tasks. Returns (bytes_reclaimed, actions)."""
    root = Path(str(instance.get("directory", "")).strip())
    reclaimed = 0
    actions: list[str] = []

    created = repair_instance_layout(instance)
    if created:
        actions.append(f"Created folders: {', '.join(created)}")

    for rel in ("logs", "crash-reports"):
        target = root / rel
        if not target.exists():
            continue
        size_before = _dir_size(target)
        if size_before <= 0:
            continue
        shutil.rmtree(target, ignore_errors=True)
        target.mkdir(parents=True, exist_ok=True)
        reclaimed += size_before
        actions.append(f"Cleared {rel} ({size_before // 1024} KB)")

    if not actions:
        actions.append("No optimization changes were necessary.")
    return reclaimed, actions

