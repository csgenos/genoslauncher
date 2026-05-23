"""Persistent Minecraft instance helpers."""

from __future__ import annotations

import logging
import re
import shutil
import uuid
from pathlib import Path

from .config import INSTANCES_DIR, config
from .validators import safe_path_segment, validate_version_id

log = logging.getLogger(__name__)


_SAFE_NAME_RE = re.compile(r"[^A-Za-z0-9._ -]+")
_SAFE_GROUP_RE = re.compile(r"[^A-Za-z0-9._ -]+")
_MAX_INSTANCES = 2000


def safe_instance_name(name: str) -> str:
    clean = _SAFE_NAME_RE.sub("_", name).strip(" .")
    clean = " ".join(clean.split())
    return clean[:64] or "Instance"


def _default_group_for_type(instance_type: str) -> str:
    mapping = {
        "vanilla": "Vanilla",
        "modpack": "Modpacks",
        "imported": "Imported",
        "custom": "Custom",
    }
    return mapping.get(instance_type, "Other")


def normalize_instance_group(group_name: str | None, instance_type: str = "") -> str:
    raw = (group_name or "").strip()
    if not raw:
        return _default_group_for_type(instance_type)
    clean = _SAFE_GROUP_RE.sub("_", raw).strip(" .")
    clean = " ".join(clean.split())
    return clean[:32] or _default_group_for_type(instance_type)


def _normalize_instance(instance: dict) -> dict:
    cleaned = dict(instance)
    cleaned["group"] = normalize_instance_group(
        cleaned.get("group"),
        str(cleaned.get("type", "")).strip().lower(),
    )
    return cleaned


def list_instances() -> list[dict]:
    items = config.get("instances", [])
    instances = [i for i in items if isinstance(i, dict) and i.get("id") and i.get("directory")]
    return [_normalize_instance(i) for i in instances]


def save_instances(instances: list[dict]) -> None:
    config.set("instances", [_normalize_instance(i) for i in instances[:_MAX_INSTANCES] if isinstance(i, dict)])


def upsert_instance(instance: dict) -> dict:
    instances = [i for i in list_instances() if i.get("id") != instance.get("id")]
    instances.append(_normalize_instance(instance))
    save_instances(instances)
    return _normalize_instance(instance)


def list_instance_groups() -> list[str]:
    groups = {normalize_instance_group(i.get("group"), i.get("type", "")) for i in list_instances()}
    return sorted(groups)


def selected_instance() -> dict | None:
    instance_id = config.get("selected_instance_id", "")
    if instance_id:
        found = find_instance(instance_id)
        if found:
            return found
    items = list_instances()
    return items[0] if items else None


def selected_instance_dir() -> Path:
    instance = selected_instance()
    if instance:
        return Path(instance["directory"])
    return Path(config.get("minecraft_dir"))


def set_selected_instance(instance_id: str) -> None:
    config.set("selected_instance_id", instance_id)


def create_vanilla_instance(version_id: str, name: str | None = None) -> dict:
    version_id = validate_version_id(version_id)
    display_name = safe_instance_name(name or f"Minecraft {version_id}")
    instance_id = f"vanilla-{safe_path_segment(version_id, 'version').replace('.', '_')}"
    directory = INSTANCES_DIR / instance_id
    directory.mkdir(parents=True, exist_ok=True)
    return upsert_instance({
        "id": instance_id,
        "name": display_name,
        "title": display_name,
        "mc_version": version_id,
        "directory": str(directory),
        "type": "vanilla",
        "source": "vanilla",
        "group": "Vanilla",
        "jvm_args": "",
    })


def create_custom_instance(
    name: str,
    version_id: str,
    directory: Path | None = None,
    jvm_args: str = "",
) -> dict:
    version_id = validate_version_id(version_id)
    display_name = safe_instance_name(name)
    instance_id = f"custom-{uuid.uuid4().hex[:12]}"
    instance_dir = directory or (INSTANCES_DIR / instance_id)
    instance_dir.mkdir(parents=True, exist_ok=True)
    return upsert_instance({
        "id": instance_id,
        "name": display_name,
        "title": display_name,
        "mc_version": version_id,
        "directory": str(instance_dir),
        "type": "custom",
        "source": "custom",
        "group": "Custom",
        "jvm_args": jvm_args,
    })


def update_instance(instance_id: str, **updates) -> dict | None:
    instances = list_instances()
    updated: dict | None = None
    for instance in instances:
        if instance.get("id") == instance_id:
            instance.update({k: v for k, v in updates.items() if v is not None})
            if "name" in updates:
                instance["name"] = safe_instance_name(str(updates["name"]))
                instance["title"] = instance["name"]
            if "group" in updates:
                instance["group"] = normalize_instance_group(
                    str(updates["group"]) if updates["group"] is not None else "",
                    str(instance.get("type", "")),
                )
            updated = instance
            break
    if updated is not None:
        save_instances(instances)
    return updated


def set_instance_group(instance_id: str, group_name: str) -> dict | None:
    return update_instance(instance_id, group=group_name)


def clone_instance(instance_id: str) -> dict | None:
    source = find_instance(instance_id)
    if not source:
        return None
    clone_id = f"clone-{uuid.uuid4().hex[:12]}"
    clone_dir = INSTANCES_DIR / clone_id
    src_dir = Path(source["directory"])
    if src_dir.exists():
        ignore = shutil.ignore_patterns("logs", "crash-reports", "*.log")
        # Copy real files into the clone so it stays independent of the source.
        shutil.copytree(src_dir, clone_dir, ignore=ignore, symlinks=False)
    else:
        clone_dir.mkdir(parents=True, exist_ok=True)
    name = safe_instance_name(f"{source.get('name', 'Instance')} Copy")
    cloned = dict(source)
    cloned.update({
        "id": clone_id,
        "name": name,
        "title": name,
        "directory": str(clone_dir),
        "source": source.get("source", "clone"),
    })
    return upsert_instance(cloned)


def create_modpack_instance(
    project: dict,
    mc_version: str,
    directory: Path,
    pack_version_id: str = "",
    launch_version_id: str | None = None,
) -> dict:
    raw_project_id = str(project.get("id", "")).strip() or str(uuid.uuid4())
    project_id = safe_path_segment(raw_project_id, "project", 48)
    pack_id = safe_path_segment(pack_version_id or "version", "version", 48)
    mc_segment = safe_path_segment(mc_version, "minecraft", 32)
    launch_id = validate_version_id(launch_version_id or mc_version)
    display = safe_instance_name(project.get("title", "Modpack"))
    instance_id = f"modpack-{project_id[:16]}-{pack_id[:16]}-{mc_segment}"
    source_name = safe_path_segment(str(project.get("source", "modrinth")).strip() or "modrinth", "source", 24)
    return upsert_instance({
        "id": instance_id,
        "name": f"{display} ({mc_version})",
        "title": project.get("title", display),
        "mc_version": launch_id,
        "base_mc_version": mc_version,
        "pack_version_id": pack_version_id,
        "directory": str(directory),
        "type": "modpack",
        "source": f"{source_name}:{raw_project_id}",
        "source_project_id": raw_project_id,
        "group": "Modpacks",
        "jvm_args": "",
    })


def find_instance(instance_id: str) -> dict | None:
    for instance in list_instances():
        if instance.get("id") == instance_id:
            return instance
    return None


def find_instance_for_version(version_id: str) -> dict | None:
    for instance in list_instances():
        if instance.get("mc_version") == version_id and instance.get("type") == "vanilla":
            return instance
    return None


def remove_instance(instance_id: str, delete_files: bool = False) -> None:
    removed = find_instance(instance_id)
    save_instances([i for i in list_instances() if i.get("id") != instance_id])
    if not delete_files or not removed:
        return
    directory = Path(str(removed.get("directory", "")).strip())
    if not directory:
        return
    try:
        resolved = directory.resolve()
        resolved.relative_to(INSTANCES_DIR.resolve())
    except (OSError, ValueError):
        log.warning("Refusing to delete non-managed instance directory: %s", directory)
        return
    if resolved.exists():
        shutil.rmtree(resolved, ignore_errors=True)


def validate_instance(instance: dict) -> tuple[bool, list[str]]:
    issues: list[str] = []
    instance_id = str(instance.get("id", "")).strip()
    if not instance_id:
        issues.append("Missing instance id.")
    directory_raw = str(instance.get("directory", "")).strip()
    if not directory_raw:
        issues.append("Missing instance directory.")
        return False, issues
    directory = Path(directory_raw)
    try:
        _ = directory.resolve()
    except OSError:
        issues.append("Instance directory path is not resolvable.")
    mc_version = str(instance.get("mc_version", "")).strip()
    if not mc_version:
        issues.append("Missing Minecraft version.")
    else:
        try:
            validate_version_id(mc_version)
        except ValueError:
            issues.append(f"Invalid Minecraft version id: {mc_version}")
    if not directory.exists():
        issues.append("Instance directory does not exist.")
    elif not directory.is_dir():
        issues.append("Instance directory is not a directory.")
    return len(issues) == 0, issues


def repair_instance_layout(instance: dict) -> list[str]:
    """
    Best-effort local repair for expected instance folder structure.
    Returns the list of created directories.
    """
    directory = Path(str(instance.get("directory", "")))
    directory.mkdir(parents=True, exist_ok=True)
    created: list[str] = []
    for rel in ("mods", "saves", "resourcepacks", "shaderpacks", "screenshots", "logs", "crash-reports"):
        target = directory / rel
        if not target.exists():
            target.mkdir(parents=True, exist_ok=True)
            created.append(rel)
    return created


# ---------------------------------------------------------------------------
# Import from MultiMC / Prism Launcher
# ---------------------------------------------------------------------------

def _parse_instance_cfg(path: Path) -> dict:
    """Parse a MultiMC/Prism instance.cfg INI-style file into a plain dict."""
    result: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if line.startswith("[") or not line or "=" not in line:
            continue
        key, _, value = line.partition("=")
        result[key.strip()] = value.strip()
    return result


def import_prism_instances(prism_dir: Path) -> list[dict]:
    """
    Scan a MultiMC/Prism Launcher instances directory for importable instances.

    Each subfolder containing an instance.cfg with an IntendedVersion is imported
    as a GenosLauncher instance pointing to the existing game files (no copy made).
    Returns the list of newly created instance dicts.
    """
    if not prism_dir.is_dir():
        return []

    imported: list[dict] = []
    for child in sorted(prism_dir.iterdir()):
        if not child.is_dir():
            continue
        cfg_path = child / "instance.cfg"
        if not cfg_path.exists():
            continue
        try:
            cfg = _parse_instance_cfg(cfg_path)
            version = cfg.get("IntendedVersion", "").strip()
            if not version:
                continue
            try:
                version = validate_version_id(version)
            except ValueError:
                log.warning("Skipping imported instance with unsafe version id: %s", version)
                continue

            name = cfg.get("name", child.name).strip() or child.name

            # Locate the actual game dir (.minecraft or minecraft subdir)
            for candidate in (".minecraft", "minecraft"):
                game_dir = child / candidate
                if game_dir.is_dir():
                    break
            else:
                game_dir = child

            instance_id = f"import-{uuid.uuid4().hex[:12]}"
            instance = upsert_instance({
                "id":        instance_id,
                "name":      safe_instance_name(f"{name} (imported)"),
                "title":     name,
                "mc_version": version,
                "directory": str(game_dir),
                "type":      "imported",
                "source":    "prism",
                "group":     "Imported",
                "jvm_args":  cfg.get("JvmArgs", ""),
            })
            imported.append(instance)
        except Exception as exc:
            log.warning("Failed to import instance from %s: %s", child, exc)

    return imported
