"""
Mod dependency resolution and conflict detection for Modrinth mods.

resolve_dependencies() recursively fetches the dependency graph for a mod
version and returns a flat list of DepNode objects.  detect_conflicts()
scans that list for incompatible or duplicate-version entries.

All network calls are synchronous; callers should use a worker thread.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Optional

from . import modrinth as mr

log = logging.getLogger(__name__)

_MAX_DEPTH = 5


@dataclass
class DepNode:
    project_id: str
    title: str
    version_id: str
    version_number: str
    dependency_type: str          # "required" | "optional" | "incompatible" | "embedded"
    project: dict = field(default_factory=dict, repr=False)
    version: dict = field(default_factory=dict, repr=False)
    already_installed: bool = False
    children: list["DepNode"] = field(default_factory=list)


def resolve_dependencies(
    version_id: str,
    loader: str = "",
    mc_version: str = "",
    installed_ids: Optional[set[str]] = None,
    _visited: Optional[set[str]] = None,
    _depth: int = 0,
) -> list[DepNode]:
    """
    Return the dependency graph for a given Modrinth version ID.

    Each DepNode contains the dependency type, resolved project/version info,
    whether the dep is already installed, and its own transitive children.

    installed_ids: set of project_ids already present in the instance (marks
    already_installed = True so the UI can skip them).
    """
    if _depth > _MAX_DEPTH:
        return []
    if installed_ids is None:
        installed_ids = set()
    if _visited is None:
        _visited = set()

    try:
        version = mr.get_version(version_id)
    except mr.ModrinthError as exc:
        log.warning("Could not fetch version %s: %s", version_id, exc)
        return []

    nodes: list[DepNode] = []
    for dep in version.get("dependencies", []):
        dep_project_id = dep.get("project_id") or ""
        dep_version_id = dep.get("version_id") or ""
        dep_type = dep.get("dependency_type", "required")

        if not dep_project_id:
            continue
        if dep_project_id in _visited:
            continue
        _visited.add(dep_project_id)

        try:
            dep_project = mr.get_project(dep_project_id)
        except mr.ModrinthError as exc:
            log.warning("Could not fetch dep project %s: %s", dep_project_id, exc)
            continue

        dep_title = dep_project.get("title", dep_project_id)

        dep_version: dict = {}
        if dep_version_id:
            try:
                dep_version = mr.get_version(dep_version_id)
            except mr.ModrinthError:
                pass

        if not dep_version:
            try:
                vers = mr.get_project_versions(
                    dep_project_id,
                    game_versions=[mc_version] if mc_version else None,
                    loaders=[loader] if loader else None,
                )
                dep_version = vers[0] if vers else {}
            except mr.ModrinthError:
                pass

        node = DepNode(
            project_id=dep_project_id,
            title=dep_title,
            version_id=dep_version.get("id", ""),
            version_number=dep_version.get("version_number", "unknown"),
            dependency_type=dep_type,
            project=dep_project,
            version=dep_version,
            already_installed=dep_project_id in installed_ids,
        )

        if node.version_id and dep_type not in ("incompatible",):
            node.children = resolve_dependencies(
                node.version_id,
                loader=loader,
                mc_version=mc_version,
                installed_ids=installed_ids,
                _visited=_visited,
                _depth=_depth + 1,
            )

        nodes.append(node)

    return nodes


def flatten_required(nodes: list[DepNode]) -> list[DepNode]:
    """Return all required, not-yet-installed deps from the tree, flattened."""
    result: list[DepNode] = []

    def _walk(n: DepNode) -> None:
        if n.dependency_type == "required" and not n.already_installed:
            result.append(n)
        for child in n.children:
            _walk(child)

    for node in nodes:
        _walk(node)
    return result


def detect_conflicts(nodes: list[DepNode]) -> list[dict]:
    """
    Return a list of conflict dicts found in the dependency tree.

    Detects:
    - incompatible deps (dependency_type == "incompatible")
    - same project required with two different version IDs
    """
    conflicts: list[dict] = []
    seen: dict[str, str] = {}

    def _walk(n: DepNode) -> None:
        if n.dependency_type == "incompatible":
            conflicts.append({
                "type": "incompatible",
                "project_id": n.project_id,
                "title": n.title,
                "message": f"{n.title} is incompatible with this mod.",
            })
            return
        vid = n.version_id or "?"
        if n.project_id in seen and seen[n.project_id] != vid:
            conflicts.append({
                "type": "version_conflict",
                "project_id": n.project_id,
                "title": n.title,
                "message": f"{n.title} is required by multiple mods in different versions.",
            })
        else:
            seen[n.project_id] = vid
        for child in n.children:
            _walk(child)

    for node in nodes:
        _walk(node)
    return conflicts
