from __future__ import annotations

from collections import Counter
from pathlib import Path

from virea.data.registry import DatasetRegistry


class CatalogPipeline:
    def __init__(self, registry: DatasetRegistry) -> None:
        self.registry = registry

    def summary(self) -> dict:
        datasets = []
        for record in self.registry.iter_records():
            root = self.registry.paths.raw_root / record.raw_dir
            extensions: Counter[str] = Counter()
            top_dirs: Counter[str] = Counter()
            file_count = 0
            if root.exists():
                for path in root.rglob("*"):
                    if not path.is_file():
                        continue
                    file_count += 1
                    extensions[path.suffix.lower() or "<none>"] += 1
                    try:
                        top_dirs[path.relative_to(root).parts[0]] += 1
                    except Exception:
                        top_dirs["."] += 1
            datasets.append(
                {
                    **record.to_dict(),
                    "raw_root": root.as_posix(),
                    "exists": root.exists(),
                    "file_count": file_count,
                    "extensions": dict(extensions.most_common(16)),
                    "top_dirs": dict(top_dirs.most_common(16)),
                }
            )
        return {
            "raw_root": self.registry.paths.raw_root.as_posix(),
            "processed_root": self.registry.paths.processed_root.as_posix(),
            "datasets": datasets,
        }
