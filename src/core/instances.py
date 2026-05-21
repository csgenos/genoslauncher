"""Persistent Minecraft instance helpers."""

from __future__ import annotations

import re
import uuid
from pathlib import Path

from .config import INSTANCES_DIR, config


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
