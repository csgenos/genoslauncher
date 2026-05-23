from __future__ import annotations
from collections import Counter


def recommend_modpacks(instances: list[dict]) -> list[tuple[str, str, str]]:
    version_counts: Counter = Counter()
    loader_counts: Counter = Counter()
    for inst in instances:
        ver = inst.get("mc_version", "")
        if ver:
            version_counts[ver] += 1
        loader = inst.get("type", "vanilla")
        if loader not in ("vanilla", "custom"):
            loader_counts[loader] += 1

    top_versions = [v for v, _ in version_counts.most_common(3)]
    top_loaders = [l for l, _ in loader_counts.most_common(2)]

    queries: list[tuple[str, str, str]] = []
    for ver in top_versions:
        loader = top_loaders[0] if top_loaders else ""
        queries.append(("popular", ver, loader))
        queries.append(("adventure", ver, loader))
        if len(queries) >= 8:
            break
    if not queries:
        queries = [("popular", "", ""), ("adventure", "", ""), ("technology", "", "")]
    return queries[:8]
