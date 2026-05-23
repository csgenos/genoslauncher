from __future__ import annotations
import shutil
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from .config import config, APP_DIR
from .instances import list_instances


def get_sync_config() -> dict:
    return {
        "enabled": config.get("cloud_sync_enabled", False),
        "sync_dir": config.get("cloud_sync_dir", ""),
        "auto_sync_on_launch": config.get("cloud_sync_auto", False),
        "last_sync": config.get("cloud_sync_last", None),
    }


def save_sync_config(cfg: dict) -> None:
    config.set("cloud_sync_enabled", cfg.get("enabled", False))
    config.set("cloud_sync_dir", cfg.get("sync_dir", ""))
    config.set("cloud_sync_auto", cfg.get("auto_sync_on_launch", False))
    if "last_sync" in cfg:
        config.set("cloud_sync_last", cfg["last_sync"])


def push_instance(instance: dict, sync_dir: str) -> str:
    inst_dir = Path(instance["directory"])
    out_dir = Path(sync_dir) / "instances" / instance["id"]
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    zip_path = out_dir / f"{ts}.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED, allowZip64=True) as zf:
        for f in inst_dir.rglob("*"):
            if f.is_file():
                zf.write(f, f.relative_to(inst_dir))
    zips = sorted(out_dir.glob("*.zip"))
    for old in zips[:-5]:
        old.unlink(missing_ok=True)
    return str(zip_path)


def pull_instance(instance_id: str, zip_path: str, instances_dir: str) -> str:
    dest = Path(instances_dir) / instance_id
    with tempfile.TemporaryDirectory() as tmp:
        with zipfile.ZipFile(zip_path) as zf:
            for member in zf.namelist():
                if ".." in member or member.startswith("/"):
                    raise ValueError(f"Unsafe path in archive: {member}")
            zf.extractall(tmp)
        if dest.exists():
            shutil.rmtree(dest)
        shutil.copytree(tmp, dest)
    return str(dest)


def list_remote_backups(instance_id: str, sync_dir: str) -> list[dict]:
    out_dir = Path(sync_dir) / "instances" / instance_id
    if not out_dir.is_dir():
        return []
    results = []
    for z in sorted(out_dir.glob("*.zip"), reverse=True):
        results.append({"path": str(z), "timestamp": z.stem, "size_bytes": z.stat().st_size})
    return results


def sync_all(sync_dir: str, progress_cb=None) -> int:
    cfg = get_sync_config()
    last_sync_str = cfg.get("last_sync")
    last_sync_ts = None
    if last_sync_str:
        try:
            last_sync_ts = datetime.fromisoformat(last_sync_str).timestamp()
        except ValueError:
            pass
    instances = list_instances()
    pushed = 0
    for i, inst in enumerate(instances):
        if progress_cb:
            progress_cb(i, len(instances), inst.get("name", inst["id"]))
        d = Path(inst.get("directory", ""))
        if not d.is_dir():
            continue
        if last_sync_ts is None or d.stat().st_mtime > last_sync_ts:
            push_instance(inst, sync_dir)
            pushed += 1
    now = datetime.now(timezone.utc).isoformat()
    save_sync_config({**cfg, "last_sync": now})
    return pushed
