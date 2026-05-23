"""Safe in-place modpack instance updater with rollback support."""

from __future__ import annotations

import shutil
import uuid
from pathlib import Path
from typing import Callable

from . import modrinth as mr
from .config import APP_DIR
from .instances import update_instance
from .launcher import install_loader, install_minecraft_base


def update_modpack_instance(
    instance: dict,
    on_progress: Callable[[int, int, str], None] | None = None,
) -> tuple[bool, str]:
    if instance.get("type") != "modpack":
        return False, "Only modpack instances can be updated."
    project_id = str(instance.get("source_project_id", "")).strip()
    if not project_id:
        return False, "This modpack instance is missing source project metadata."

    current_pack_id = str(instance.get("pack_version_id", "")).strip()
    mc_family = str(instance.get("base_mc_version") or instance.get("mc_version") or "").strip()
    instance_dir = Path(str(instance.get("directory", "")).strip())
    if not instance_dir.exists():
        return False, "Instance directory does not exist."

    def _p(cur: int, tot: int, status: str) -> None:
        if on_progress:
            on_progress(cur, tot, status)

    versions = mr.get_project_versions(project_id, game_versions=[mc_family] if mc_family else None)
    if not versions:
        return False, "No modpack versions available for this instance."
    latest = versions[0]
    latest_pack_id = str(latest.get("id", "")).strip()
    if latest_pack_id and latest_pack_id == current_pack_id:
        return True, "Modpack is already up to date."

    files = latest.get("files", [])
    primary = next((f for f in files if f.get("primary")), files[0] if files else None)
    if not primary:
        return False, "Latest modpack version has no downloadable files."

    downloads_dir = APP_DIR / "downloads"
    filename = mr.safe_filename(primary.get("filename", "modpack.mrpack"))
    mrpack_path = mr.safe_download_path(downloads_dir, filename)
    hashes = primary.get("hashes", {})
    _p(0, 1, f"Downloading update {filename}...")
    mr.download_file(
        primary["url"],
        mrpack_path,
        expected_sha1=hashes.get("sha1", ""),
        expected_sha512=hashes.get("sha512", ""),
    )
    try:
        _p(0, 1, "Parsing update package...")
        index = mr.parse_mrpack(mrpack_path)
        mc_version = str(index.get("dependencies", {}).get("minecraft", "")).strip()
        if not mc_version:
            return False, "Update package is missing Minecraft dependency."

        staging_dir = instance_dir.with_name(f".{instance_dir.name}.update-{uuid.uuid4().hex[:8]}")
        backup_dir = instance_dir.with_name(f".{instance_dir.name}.backup-{uuid.uuid4().hex[:8]}")
        _p(0, 1, f"Installing Minecraft {mc_version}...")
        install_minecraft_base(mc_version, str(staging_dir), _p)
        _p(0, 1, "Installing mod loader...")
        loader_version_id = install_loader(index.get("dependencies", {}), str(staging_dir), _p)

        def _on_mod(cur: int, tot: int, fname: str) -> None:
            _p(cur, max(tot, 1), f"Downloading mod {cur}/{tot}: {fname}")

        failures = mr.install_mrpack_mods(index, staging_dir, on_progress=_on_mod)
        if failures:
            failed = ", ".join(failures[:3])
            if len(failures) > 3:
                failed += f" (+{len(failures) - 3} more)"
            shutil.rmtree(staging_dir, ignore_errors=True)
            return False, f"Update failed: {len(failures)} mod(s) failed to download: {failed}"
        _p(0, 1, "Extracting overrides...")
        mr.extract_mrpack_overrides(mrpack_path, staging_dir)

        _p(0, 1, "Applying update...")
        instance_dir.rename(backup_dir)
        try:
            shutil.move(str(staging_dir), str(instance_dir))
        except Exception:
            if backup_dir.exists() and not instance_dir.exists():
                shutil.move(str(backup_dir), str(instance_dir))
            raise

        shutil.rmtree(backup_dir, ignore_errors=True)
        update_instance(
            instance.get("id", ""),
            pack_version_id=latest_pack_id,
            base_mc_version=mc_version,
            mc_version=loader_version_id or mc_version,
        )
        return True, "Modpack updated successfully."
    finally:
        mrpack_path.unlink(missing_ok=True)

