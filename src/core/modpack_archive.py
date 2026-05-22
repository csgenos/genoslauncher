"""Basic instance import/export helpers for .zip and .mrpack round-trip."""

from __future__ import annotations

import json
import shutil
import uuid
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from .config import APP_DIR
from .instances import create_custom_instance, update_instance
from .modrinth import ModrinthError, _validate_zip_limits, extract_mrpack_overrides, parse_mrpack
from .validators import safe_path_segment

_META_NAME = ".genos_instance.json"


def _safe_extract_member(base_dir: Path, member_name: str) -> Path | None:
    rel = Path(member_name)
    if rel.is_absolute():
        return None
    parts = [p for p in rel.parts if p not in ("", ".", "..")]
    if not parts:
        return None
    target = (base_dir / Path(*parts)).resolve()
    try:
        target.relative_to(base_dir.resolve())
    except ValueError:
        return None
    return target


def export_instance_zip(instance: dict, output_zip: Path) -> Path:
    instance_dir = Path(instance.get("directory", ""))
    if not instance_dir.is_dir():
        raise RuntimeError(f"Instance directory does not exist: {instance_dir}")
    output_zip.parent.mkdir(parents=True, exist_ok=True)
    tmp_zip = output_zip.with_suffix(".tmp")

    meta = {
        "name": instance.get("name", "Instance"),
        "mc_version": instance.get("mc_version", ""),
        "type": instance.get("type", "custom"),
        "source": instance.get("source", "export"),
        "jvm_args": instance.get("jvm_args", ""),
        "exported_at": datetime.now(timezone.utc).isoformat(),
    }
    with zipfile.ZipFile(tmp_zip, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(_META_NAME, json.dumps(meta, ensure_ascii=False, indent=2))
        for path in instance_dir.rglob("*"):
            if not path.is_file():
                continue
            if path.name.endswith(".log"):
                continue
            arc = path.relative_to(instance_dir).as_posix()
            zf.write(path, arc)
    tmp_zip.replace(output_zip)
    return output_zip


def export_instance_mrpack(instance: dict, output_mrpack: Path) -> Path:
    """
    Export a basic .mrpack with local overrides only.
    This is sufficient for round-trip import but does not include remote mod URLs.
    """
    instance_dir = Path(instance.get("directory", ""))
    if not instance_dir.is_dir():
        raise RuntimeError(f"Instance directory does not exist: {instance_dir}")
    mc_version = str(instance.get("base_mc_version") or instance.get("mc_version") or "").strip()
    if not mc_version:
        raise RuntimeError("Instance is missing a Minecraft version.")
    output_mrpack.parent.mkdir(parents=True, exist_ok=True)
    tmp = output_mrpack.with_suffix(".tmp")

    manifest = {
        "formatVersion": 1,
        "game": "minecraft",
        "versionId": safe_path_segment(instance.get("id", uuid.uuid4().hex), "instance", 64),
        "name": instance.get("name", "Exported Instance"),
        "summary": "Exported from GenosLauncher",
        "files": [],
        "dependencies": {"minecraft": mc_version},
    }
    with zipfile.ZipFile(tmp, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("modrinth.index.json", json.dumps(manifest, ensure_ascii=False, indent=2))
        for path in instance_dir.rglob("*"):
            if not path.is_file():
                continue
            rel = path.relative_to(instance_dir).as_posix()
            if rel.startswith("logs/") or rel.endswith(".log"):
                continue
            zf.write(path, f"overrides/{rel}")
    tmp.replace(output_mrpack)
    return output_mrpack


def import_instance_archive(archive_path: Path, instance_name: str | None = None) -> dict:
    """
    Import a .zip or .mrpack into a new managed instance.
    Returns the created instance dict.
    """
    if not archive_path.is_file():
        raise RuntimeError(f"Archive does not exist: {archive_path}")
    suffix = archive_path.suffix.lower()
    if suffix not in {".zip", ".mrpack"}:
        raise RuntimeError("Only .zip and .mrpack archives are supported.")
    if not zipfile.is_zipfile(archive_path):
        raise RuntimeError("Selected file is not a valid ZIP archive.")

    if suffix == ".mrpack":
        try:
            index = parse_mrpack(archive_path)
        except ModrinthError as exc:
            raise RuntimeError(str(exc)) from exc
        mc_version = str(index.get("dependencies", {}).get("minecraft", "")).strip()
        if not mc_version:
            raise RuntimeError("The .mrpack is missing a Minecraft dependency.")
        name = instance_name or (index.get("name") or archive_path.stem)
        instance = create_custom_instance(name, mc_version)
        instance_dir = Path(instance["directory"])
        extract_mrpack_overrides(archive_path, instance_dir)
        update_instance(instance["id"], type="modpack", source="imported-mrpack")
        return instance

    # Generic zip import path
    with zipfile.ZipFile(archive_path, "r") as zf:
        _validate_zip_limits(zf)
        meta: dict = {}
        if _META_NAME in zf.namelist():
            try:
                meta = json.loads(zf.read(_META_NAME).decode("utf-8", errors="replace"))
            except (ValueError, OSError):
                meta = {}
        mc_version = str(meta.get("mc_version") or "1.21.4").strip()
        name = instance_name or str(meta.get("name") or archive_path.stem)
        instance = create_custom_instance(name, mc_version)
        instance_dir = Path(instance["directory"])
        for info in zf.infolist():
            if info.is_dir() or info.filename == _META_NAME:
                continue
            target = _safe_extract_member(instance_dir, info.filename)
            if target is None:
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(info, "r") as src, open(target, "wb") as dst:
                shutil.copyfileobj(src, dst)
        if meta.get("jvm_args"):
            update_instance(instance["id"], jvm_args=str(meta.get("jvm_args", "")))
        return instance
