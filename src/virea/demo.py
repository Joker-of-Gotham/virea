from __future__ import annotations

import json
import shutil
from pathlib import Path

import pandas as pd

from virea.data.registry import DatasetRegistry
from virea.paths import ProjectPaths, repo_root


def _copy_file(src: Path, dst: Path, copied: list[dict]) -> None:
    if not src.exists() or not src.is_file():
        return
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)
    copied.append({"source": str(src), "target": str(dst), "bytes": dst.stat().st_size})


def _copy_related_sample(sample, full_raw_root: Path, demo_raw_root: Path, copied: list[dict]) -> None:
    _copy_file(sample.source_path, demo_raw_root / sample.source_path.relative_to(full_raw_root), copied)
    for related in sample.related_paths.values():
        if related.exists() and related.is_file():
            _copy_file(related, demo_raw_root / related.relative_to(full_raw_root), copied)
    sidecar_json = sample.source_path.with_suffix(".json")
    if sidecar_json.exists():
        _copy_file(sidecar_json, demo_raw_root / sidecar_json.relative_to(full_raw_root), copied)
    sidecar_txt = sample.source_path.with_suffix(".txt")
    if sidecar_txt.exists():
        _copy_file(sidecar_txt, demo_raw_root / sidecar_txt.relative_to(full_raw_root), copied)


def _build_humanml3d_demo(full_raw_root: Path, demo_raw_root: Path, max_rows: int, copied: list[dict]) -> None:
    src = full_raw_root / "humanml3d" / "data" / "test-00000-of-00002.parquet"
    if not src.exists():
        return
    dst = demo_raw_root / "humanml3d" / "data" / src.name
    dst.parent.mkdir(parents=True, exist_ok=True)
    df = pd.read_parquet(src).head(max(1, max_rows))
    df.to_parquet(dst, index=False)
    copied.append({"source": str(src), "target": str(dst), "rows": len(df), "bytes": dst.stat().st_size})
    readme = full_raw_root / "humanml3d" / "README.md"
    _copy_file(readme, demo_raw_root / "humanml3d" / "README.md", copied)


def _build_susu_split_files(demo_raw_root: Path, sample_id: str, copied: list[dict]) -> None:
    split_root = demo_raw_root / "SuSuInterActs" / "split"
    split_root.mkdir(parents=True, exist_ok=True)
    for name in ("all", "train", "val", "test"):
        path = split_root / f"{name}_file_list.txt"
        path.write_text(sample_id + "\n", encoding="utf-8")
        copied.append({"source": "generated", "target": str(path), "bytes": path.stat().st_size})


def _build_susu_split_files_multi(demo_raw_root: Path, sample_ids: list[str], copied: list[dict]) -> None:
    split_root = demo_raw_root / "SuSuInterActs" / "split"
    split_root.mkdir(parents=True, exist_ok=True)
    content = "\n".join(sample_ids) + "\n"
    for name in ("all", "train", "val", "test"):
        path = split_root / f"{name}_file_list.txt"
        path.write_text(content, encoding="utf-8")
        copied.append({"source": "generated", "target": str(path), "bytes": path.stat().st_size})


def _build_susu_text_files(full_raw_root: Path, demo_raw_root: Path, sample_id: str, copied: list[dict]) -> None:
    src = full_raw_root / "SuSuInterActs" / "text_data" / "motion2text.json"
    if not src.exists():
        return
    payload = json.loads(src.read_text(encoding="utf-8"))
    text = payload.get(sample_id, "")
    dst_root = demo_raw_root / "SuSuInterActs" / "text_data"
    dst_root.mkdir(parents=True, exist_ok=True)
    for name in ("motion2text", "train", "val", "test"):
        dst = dst_root / f"{name}.json"
        dst.write_text(json.dumps({sample_id: text}, ensure_ascii=False, indent=2), encoding="utf-8")
        copied.append({"source": str(src), "target": str(dst), "bytes": dst.stat().st_size})


def build_demo_dataset(max_rows: int = 100, overwrite: bool = False, samples_per_dataset: int = 100) -> dict:
    full_registry = DatasetRegistry.default(data_source="full")
    full_raw_root = full_registry.paths.raw_root
    demo_paths = ProjectPaths(data_source="demo")
    demo_raw_root = demo_paths.raw_root

    if overwrite and demo_raw_root.exists():
        shutil.rmtree(demo_raw_root)
    demo_raw_root.mkdir(parents=True, exist_ok=True)

    copied: list[dict] = []
    selected: dict[str, list[str]] = {}
    for record in full_registry.iter_records():
        if record.key == "humanml3d":
            _build_humanml3d_demo(full_raw_root, demo_raw_root, max_rows, copied)
            selected[record.key] = [f"test/test-00000-of-00002/{i}" for i in range(min(max_rows, 100))]
            continue

        adapter = full_registry.adapter(record.key)
        discover_limit = max(samples_per_dataset * 2, 500)
        samples = adapter.discover(limit=discover_limit)
        if not samples:
            selected[record.key] = []
            continue

        chosen = samples[:samples_per_dataset]
        selected[record.key] = [s.sample_id for s in chosen]
        susu_split_ids: list[str] = []
        for sample in chosen:
            _copy_related_sample(sample, full_raw_root, demo_raw_root, copied)
            if record.key == "susuinteracts":
                susu_split_ids.append(sample.sample_id)
                _build_susu_text_files(full_raw_root, demo_raw_root, sample.sample_id, copied)
        if record.key == "susuinteracts" and susu_split_ids:
            _build_susu_split_files_multi(demo_raw_root, susu_split_ids, copied)
        print(f"  [{record.key}] copied {len(chosen)} samples", flush=True)

    manifest = {
        "schema_version": "virea.demo_manifest.v0.1.0",
        "description": "Local same-layout demo fixture copied from the configured full raw data source.",
        "full_raw_root": str(full_raw_root),
        "demo_raw_root": str(demo_raw_root),
        "selected_samples": selected,
        "copied_files": copied,
    }
    manifest_path = repo_root() / "demo" / "manifest.json"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return manifest
