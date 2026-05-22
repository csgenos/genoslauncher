"""Persistent Minecraft instance helpers."""

from __future__ import annotations

import logging
import re
import shutil
import uuid
from pathlib import Path

from .config import INSTANCES_DIR, config

log = logging.getLogger(__name__)


_SAFE_NAME_RE = re.compile(r"[^A-Za-z0-9._ -]+")


def safe_instance_name(name: str) -> str:
    clean = _SAFE_NAME_RE.sub("_", name).strip(" .")
    clean = " ".join(clean.split())
    return clean[:64] or "Instance"


def list_instances() -> list[dict]:
    items = config.get("instances", [])
    return [i for i in items if isinstance(i, dict) and i.get("id") and i.get("directory")]


def save_instances(instances: list[dict]) -> None:
    config.set("instances", instances[:200])


def upsert_instance(instance: dict) -> dict:
    instances = [i for i in list_instances() if i.get("id") != instance.get("id")]
    instances.append(instance)
    save_instances(instances)
    return instance


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
    display_name = safe_instance_name(name or f"Minecraft {version_id}")
    instance_id = f"vanilla-{version_id.replace('.', '_')}"
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
        "jvm_args": "",
    })


def create_custom_instance(
    name: str,
    version_id: str,
    directory: Path | None = None,
    jvm_args: str = "",
) -> dict:
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
            updated = instance
            break
    if updated is not None:
        save_instances(instances)
    return updated


def clone_instance(instance_id: str) -> dict | None:
    source = find_instance(instance_id)
    if not source:
        return None
    clone_id = f"clone-{uuid.uuid4().hex[:12]}"
    clone_dir = INSTANCES_DIR / clone_id
    src_dir = Path(source["directory"])
    if src_dir.exists():
        ignore = shutil.ignore_patterns("logs", "crash-reports", "*.log")
        shutil.copytree(src_dir, clone_dir, ignore=ignore)
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


def create_modpack_instance(project: dict, mc_version: str, directory: Path) -> dict:
    project_id = project.get("id", str(uuid.uuid4()))
    display = safe_instance_name(project.get("title", "Modpack"))
    instance_id = f"modpack-{project_id[:12]}"
    return upsert_instance({
        "id": instance_id,
        "name": f"{display} ({mc_version})",
        "title": project.get("title", display),
        "mc_version": mc_version,
        "directory": str(directory),
        "type": "modpack",
        "source": project_id,
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


def remove_instance(instance_id: str) -> None:
    save_instances([i for i in list_instances() if i.get("id") != instance_id])


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
                "jvm_args":  cfg.get("JvmArgs", ""),
            })
            imported.append(instance)
        except Exception as exc:
            log.warning("Failed to import instance from %s: %s", child, exc)

    return imported
