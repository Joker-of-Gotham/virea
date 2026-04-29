from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml

DATA_SOURCE_FULL = "full"
DATA_SOURCE_DEMO = "demo"
AVAILABLE_DATA_SOURCES = (DATA_SOURCE_FULL, DATA_SOURCE_DEMO)


def repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def load_project_config(config_path: str | Path | None = None) -> dict[str, Any]:
    path = Path(config_path) if config_path else repo_root() / "configs" / "project.yaml"
    with path.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {}


def _resolve_repo_relative(root: Path, value: str | Path) -> Path:
    path = Path(str(value)).expanduser()
    if not path.is_absolute():
        path = root / path
    return path


class ProjectPaths:
    def __init__(self, config: dict[str, Any] | None = None, data_source: str | None = None) -> None:
        self.config = config or load_project_config()
        path_cfg = self.config.get("paths", {})
        self.root = repo_root()
        data_source_env = str(path_cfg.get("data_source_env", "VIREA_DATA_SOURCE"))
        selected_source = str(data_source or os.getenv(data_source_env, DATA_SOURCE_FULL)).strip().lower()
        if selected_source not in AVAILABLE_DATA_SOURCES:
            raise ValueError(f"unsupported VIREA data source: {selected_source}")
        self.data_source = selected_source

        data_root_env = str(path_cfg.get("data_root_env", "VIREA_DATA_ROOT"))
        raw_root_env = str(path_cfg.get("raw_root_env", "VIREA_RAW_ROOT"))
        processed_root_env = str(path_cfg.get("processed_root_env", "VIREA_PROCESSED_ROOT"))

        fallback_data_root = Path(str(path_cfg.get("default_workspace_data_root", ""))).expanduser()
        if not fallback_data_root.exists():
            sibling = self.root.parent / "LLM-driven-VRM" / "vrm_motion" / "runtime" / "datasets"
            fallback_data_root = sibling if sibling.exists() else self.root / "data"

        self.data_root = Path(os.getenv(data_root_env, str(fallback_data_root))).expanduser()
        source_cfg = dict(self.config.get("data_sources", {}).get(selected_source, {}))
        configured_raw_root = source_cfg.get("raw_root")
        if configured_raw_root:
            default_raw_root = _resolve_repo_relative(self.root, configured_raw_root)
        else:
            default_raw_root = self.data_root / "raw"
        self.raw_root = Path(os.getenv(raw_root_env, str(default_raw_root))).expanduser()

        processed_default = Path(str(path_cfg.get("default_processed_root", ""))).expanduser()
        if not processed_default.is_absolute():
            processed_default = self.root / processed_default
        processed_subdir = str(path_cfg.get("processed_subdir", "virea_processed"))
        if not str(path_cfg.get("default_processed_root", "")).strip():
            processed_default = self.data_root / processed_subdir
        configured_processed_root = source_cfg.get("processed_root")
        if configured_processed_root:
            processed_default = _resolve_repo_relative(self.root, configured_processed_root)
        self.processed_root = Path(
            os.getenv(processed_root_env, str(processed_default))
        ).expanduser()

    @classmethod
    def available_sources(cls, config: dict[str, Any] | None = None) -> dict[str, dict[str, Any]]:
        cfg = config or load_project_config()
        root = repo_root()
        result: dict[str, dict[str, Any]] = {}
        for key in AVAILABLE_DATA_SOURCES:
            item = dict(cfg.get("data_sources", {}).get(key, {}))
            raw = item.get("raw_root", "")
            processed = item.get("processed_root", "")
            item["raw_root"] = str(_resolve_repo_relative(root, raw)) if raw else ""
            item["processed_root"] = str(_resolve_repo_relative(root, processed)) if processed else ""
            item["exists"] = bool(item.get("raw_root") and Path(str(item["raw_root"])).exists())
            result[key] = item
        return result

    @property
    def processing_version(self) -> str:
        return str(self.config.get("runtime", {}).get("processing_version", "v0.1.0"))

    @property
    def target_fps(self) -> float:
        return float(self.config.get("runtime", {}).get("target_fps", 30.0))

    @property
    def preview_max_frames(self) -> int:
        return int(self.config.get("runtime", {}).get("preview_max_frames", 180))
