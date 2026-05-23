"""Basic instance import/export helpers for .zip and .mrpack round-trip."""

from __future__ import annotations

import json
import shutil
import uuid
import zipfile
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

from .config import APP_DIR
from .instances import create_custom_instance, remove_instance, update_instance
from .modrinth import ModrinthError, _validate_zip_limits, extract_mrpack_overrides, parse_mrpack
from .validators import safe_path_segment

_META_NAME = ".genos_instance.json"
_MAX_EXPORT_FILES = 20_000
_MAX_EXPORT_FILE_BYTES = 512 * 1024 * 1024
_MAX_EXPORT_TOTAL_BYTES = 4 * 1024 * 1024 * 1024
_SENSITIVE_EXPORT_NAMES = {
    "launcher_accounts.json",
    "launcher_profiles.json",
    "servers.dat",
    "usercache.json",
    "usernamecache.json",
}
_SENSITIVE_EXPORT_PARTS = {
    "logs",
    "crash-reports",
    "backups",
    ".fabric",
}
_SENSITIVE_NAME_FRAGMENTS = (
    "access_token",
    "account",
    "credential",
    "oauth",
    "refresh_token",
    "session",
    "token",
)


def _safe_extract_member(base_dir: Path, member_name: str) -> Path | None:
    rel = PurePosixPath(member_name.replace("\\", "/"))
    if rel.is_absolute() or any(part in ("", ".", "..") for part in rel.parts):
        return None
    target = (base_dir / Path(*rel.parts)).resolve()
    try:
        target.relative_to(base_dir.resolve())
    except ValueError:
        return None
    return target


def _zip_member_is_symlink(info: zipfile.ZipInfo) -> bool:
    return ((info.external_attr >> 16) & 0o170000) == 0o120000


def _should_export_file(path: Path, instance_dir: Path) -> bool:
    try:
        rel = path.relative_to(instance_dir)
    except ValueError:
        return False
    rel_parts = {p.lower() for p in rel.parts}
    name = path.name.lower()
    if path.is_symlink():
        return False
    if path.name == _META_NAME or name.endswith(".log"):
        return False
    if name in _SENSITIVE_EXPORT_NAMES:
        return False
    if rel_parts & _SENSITIVE_EXPORT_PARTS:
        return False
    return not any(fragment in name for fragment in _SENSITIVE_NAME_FRAGMENTS)


def _iter_export_files(instance_dir: Path):
    total = 0
    count = 0
    for path in instance_dir.rglob("*"):
        if not path.is_file() or not _should_export_file(path, instance_dir):
            continue
        size = path.stat().st_size
        if size > _MAX_EXPORT_FILE_BYTES:
            raise RuntimeError(f"Refusing to export oversized file: {path.name}")
        count += 1
        total += size
        if count > _MAX_EXPORT_FILES:
            raise RuntimeError("Refusing to export instance with too many files.")
        if total > _MAX_EXPORT_TOTAL_BYTES:
            raise RuntimeError("Refusing to export instance larger than the export limit.")
        yield path


def _promote_imported_instance(staging_dir: Path, name: str, mc_version: str, **updates) -> dict:
    instance = create_custom_instance(name, mc_version)
    instance_dir = Path(instance["directory"])
    try:
        if instance_dir.exists():
            shutil.rmtree(instance_dir)
        shutil.move(str(staging_dir), str(instance_dir))
        if updates:
            update_instance(instance["id"], **updates)
            instance.update({k: v for k, v in updates.items() if v is not None})
        return instance
    except Exception:
        remove_instance(instance["id"])
        try:
            if instance_dir.exists():
                shutil.rmtree(instance_dir)
        finally:
            if staging_dir.exists():
                shutil.rmtree(staging_dir, ignore_errors=True)
        raise


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
        "exported_at": datetime.now(timezone.utc).isoformat(),
    }
    with zipfile.ZipFile(tmp_zip, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(_META_NAME, json.dumps(meta, ensure_ascii=False, indent=2))
        for path in _iter_export_files(instance_dir):
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
        for path in _iter_export_files(instance_dir):
            rel = path.relative_to(instance_dir).as_posix()
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
        staging_dir = APP_DIR / "instances" / f".import-{uuid.uuid4().hex}"
        try:
            extract_mrpack_overrides(archive_path, staging_dir)
            return _promote_imported_instance(
                staging_dir,
                name,
                mc_version,
                type="modpack",
                source="imported-mrpack",
                group="Modpacks",
            )
        except Exception:
            shutil.rmtree(staging_dir, ignore_errors=True)
            raise

    # Generic zip import path
    with zipfile.ZipFile(archive_path, "r") as zf:
        _validate_zip_limits(zf)
        meta: dict = {}
        if _META_NAME in zf.namelist():
            try:
                meta = json.loads(zf.read(_META_NAME).decode("utf-8", errors="replace"))
            except (ValueError, OSError):
                meta = {}
        mc_version = str(meta.get("mc_version") or "").strip()
        if not mc_version:
            raise RuntimeError("Archive is missing GenosLauncher Minecraft version metadata.")
        name = instance_name or str(meta.get("name") or archive_path.stem)
        staging_dir = APP_DIR / "instances" / f".import-{uuid.uuid4().hex}"
        try:
            staging_dir.mkdir(parents=True, exist_ok=False)
            for info in zf.infolist():
                if info.is_dir() or info.filename == _META_NAME:
                    continue
                if _zip_member_is_symlink(info):
                    raise RuntimeError(f"Archive contains unsupported symlink: {info.filename}")
                target = _safe_extract_member(staging_dir, info.filename)
                if target is None:
                    raise RuntimeError(f"Archive contains unsafe path: {info.filename}")
                target.parent.mkdir(parents=True, exist_ok=True)
                with zf.open(info, "r") as src, open(target, "wb") as dst:
                    shutil.copyfileobj(src, dst)
            return _promote_imported_instance(staging_dir, name, mc_version)
        except Exception:
            shutil.rmtree(staging_dir, ignore_errors=True)
            raise
