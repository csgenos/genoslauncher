from __future__ import annotations
import shutil
import tempfile
import uuid
import zipfile
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

from .config import config
from .instances import list_instances
from .validators import safe_path_segment

_SENSITIVE_SYNC_NAMES = {
    "launcher_accounts.json",
    "launcher_profiles.json",
    "servers.dat",
    "usercache.json",
    "usernamecache.json",
}
_SENSITIVE_SYNC_PARTS = {
    "logs",
    "crash-reports",
    "backups",
    ".fabric",
}
_SENSITIVE_SYNC_FRAGMENTS = (
    "access_token",
    "account",
    "credential",
    "oauth",
    "refresh_token",
    "session",
    "token",
)


def _safe_instance_id(instance_id: str) -> str:
    raw = str(instance_id or "").strip()
    clean = safe_path_segment(raw, "instance", 96)
    if clean != raw:
        raise ValueError(f"Unsafe instance id: {instance_id!r}")
    return clean


def _safe_instance_dest(instances_dir: str, instance_id: str) -> Path:
    base = Path(instances_dir).resolve()
    dest = (base / _safe_instance_id(instance_id)).resolve()
    try:
        dest.relative_to(base)
    except ValueError as exc:
        raise ValueError(f"Unsafe instance destination: {dest}") from exc
    return dest


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


def _should_sync_file(path: Path, instance_root: Path) -> bool:
    try:
        rel = path.relative_to(instance_root)
    except ValueError:
        return False
    if path.is_symlink():
        return False
    name = path.name.lower()
    if name in _SENSITIVE_SYNC_NAMES or name.endswith(".log"):
        return False
    rel_parts = {part.lower() for part in rel.parts}
    if rel_parts & _SENSITIVE_SYNC_PARTS:
        return False
    return not any(fragment in name for fragment in _SENSITIVE_SYNC_FRAGMENTS)


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
    safe_id = _safe_instance_id(str(instance.get("id", "")))
    out_dir = Path(sync_dir) / "instances" / safe_id
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    zip_path = out_dir / f"{ts}.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED, allowZip64=True) as zf:
        for f in inst_dir.rglob("*"):
            if f.is_file() and _should_sync_file(f, inst_dir):
                zf.write(f, f.relative_to(inst_dir))
    zips = sorted(out_dir.glob("*.zip"))
    for old in zips[:-5]:
        old.unlink(missing_ok=True)
    return str(zip_path)


def pull_instance(instance_id: str, zip_path: str, instances_dir: str) -> str:
    base_dir = Path(instances_dir).resolve()
    dest = _safe_instance_dest(instances_dir, instance_id)
    with tempfile.TemporaryDirectory() as tmp:
        extracted_root = Path(tmp) / "extracted"
        extracted_root.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(zip_path) as zf:
            for info in zf.infolist():
                if info.is_dir():
                    continue
                if _zip_member_is_symlink(info):
                    raise ValueError(f"Archive contains unsupported symlink: {info.filename}")
                target = _safe_extract_member(extracted_root, info.filename)
                if target is None:
                    raise ValueError(f"Unsafe path in archive: {info.filename}")
                target.parent.mkdir(parents=True, exist_ok=True)
                with zf.open(info, "r") as src, open(target, "wb") as dst:
                    shutil.copyfileobj(src, dst)
        staged_dest = base_dir / f".{dest.name}.sync-{uuid.uuid4().hex[:8]}"
        if staged_dest.exists():
            shutil.rmtree(staged_dest, ignore_errors=True)
        shutil.copytree(extracted_root, staged_dest)
        if dest.exists():
            shutil.rmtree(dest)
        staged_dest.replace(dest)
    return str(dest)


def list_remote_backups(instance_id: str, sync_dir: str) -> list[dict]:
    out_dir = Path(sync_dir) / "instances" / _safe_instance_id(instance_id)
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
