from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np

from virea.data.registry import DatasetRegistry
from virea.data.types import PreviewPayload, SampleRef
from virea.motion.quality import preview_quality
from virea.pipelines.artifacts import ArtifactPaths, artifact_paths, legacy_vrm_motion_path, motion_uid
from virea.pipelines.preview_builder import PreviewBuilder


class PreviewReader:
    """Read-only access to persisted pipeline artifacts. No conversion or retargeting."""

    def __init__(self, registry: DatasetRegistry) -> None:
        self.registry = registry
        self._builder = PreviewBuilder()

    def _resolve_paths(self, dataset: str, sample_id: str, frame_count: int) -> tuple[ArtifactPaths, Path]:
        root = self.registry.paths.processed_root
        version = self.registry.paths.processing_version
        uid = motion_uid(dataset, sample_id, frame_count)
        paths = artifact_paths(root, version, dataset, uid)
        return paths, root

    def _load_npz_positions(self, path: Path, max_frames: int | None) -> dict[str, Any]:
        if not path.exists():
            raise FileNotFoundError(path)
        data = np.load(path, allow_pickle=True)
        positions = np.asarray(data["positions"], dtype=np.float32)
        if max_frames:
            positions = positions[:max_frames]
        joint_names = [str(name) for name in np.asarray(data["joint_names"]).tolist()]
        edges = [tuple(int(v) for v in row) for row in np.asarray(data["edges"], dtype=np.int32).tolist()]
        fps = float(np.asarray(data.get("fps", 30.0)).reshape(-1)[0]) if "fps" in data.files else 30.0
        coordinate_system = "gltf_y_up_z_forward"
        if "coordinate_system" in data.files:
            coordinate_system = str(np.asarray(data["coordinate_system"]).reshape(-1)[0])
        return {
            "positions": positions,
            "joint_names": joint_names,
            "edges": edges,
            "fps": fps,
            "coordinate_system": coordinate_system,
        }

    def _vrm_positions_path(self, paths) -> Path:
        if paths.vrm_positions.exists():
            return paths.vrm_positions
        legacy = legacy_vrm_motion_path(paths)
        if legacy.exists():
            return legacy
        raise FileNotFoundError(paths.vrm_positions)

    def _guess_frame_count(self, dataset: str, sample_id: str) -> int:
        metadata_glob = list(
            (self.registry.paths.processed_root / "canonical" / self.registry.paths.processing_version / "metadata" / dataset).glob("*.json")
        )
        for meta_path in metadata_glob:
            record = json.loads(meta_path.read_text(encoding="utf-8"))
            if record.get("source", {}).get("source_id") == sample_id:
                return int(record.get("time", {}).get("num_frames", 0)) or 120
        adapter = self.registry.adapter(dataset)
        samples = adapter.discover(limit=500, query=sample_id)
        for sample in samples:
            if sample.sample_id == sample_id and sample.frame_count:
                return int(sample.frame_count)
        return 120

    def read_source_preview(
        self,
        dataset: str,
        sample_id: str,
        max_frames: int | None = None,
    ) -> PreviewPayload:
        frame_count = self._guess_frame_count(dataset, sample_id)
        if max_frames:
            frame_count = min(frame_count, max_frames)
        paths, _root = self._resolve_paths(dataset, sample_id, frame_count)
        loaded = self._load_npz_positions(paths.source_snapshot, max_frames)
        sample = SampleRef(
            dataset=dataset,
            sample_id=sample_id,
            source_path=Path(""),
            source_format="persisted",
            codec_key="",
            fps=loaded["fps"],
            frame_count=int(loaded["positions"].shape[0]),
        )
        return PreviewPayload(
            stage="raw",
            sample=sample,
            fps=loaded["fps"],
            positions=loaded["positions"],
            joint_names=loaded["joint_names"],
            edges=loaded["edges"],
            metadata={"coordinate_system": loaded["coordinate_system"], "from_artifact": True},
            quality=preview_quality(loaded["positions"]),
            files={"source_snapshot": str(paths.source_snapshot)},
        )

    def read_processed_preview(
        self,
        dataset: str,
        sample_id: str,
        max_frames: int | None = None,
    ) -> PreviewPayload:
        frame_count = self._guess_frame_count(dataset, sample_id)
        if max_frames:
            frame_count = min(frame_count, max_frames)
        paths, root = self._resolve_paths(dataset, sample_id, frame_count)
        vrm_path = self._vrm_positions_path(paths)
        loaded = self._load_npz_positions(vrm_path, max_frames)
        motion = None
        if paths.canonical_motion.exists():
            canonical = np.load(paths.canonical_motion, allow_pickle=True)
            sequence = np.asarray(canonical["sequence"], dtype=np.float32)
            if max_frames:
                sequence = sequence[:max_frames]
            motion = self._builder.motion_dict_from_sequence(sequence)
        quality: dict[str, Any] = {}
        if paths.quality_report.exists():
            quality = json.loads(paths.quality_report.read_text(encoding="utf-8"))
        else:
            quality = preview_quality(loaded["positions"])
        sample = SampleRef(
            dataset=dataset,
            sample_id=sample_id,
            source_path=Path(""),
            source_format="persisted",
            codec_key="",
            fps=loaded["fps"],
            frame_count=int(loaded["positions"].shape[0]),
        )
        try:
            vrm_rel = str(vrm_path.relative_to(root))
        except ValueError:
            vrm_rel = str(vrm_path)
        files = {
            "vrm_positions": vrm_rel,
            "canonical_motion": str(paths.canonical_motion),
            "quality_report": str(paths.quality_report),
            "metadata": str(paths.metadata),
        }
        return PreviewPayload(
            stage="processed",
            sample=sample,
            fps=loaded["fps"],
            positions=loaded["positions"],
            joint_names=loaded["joint_names"],
            edges=loaded["edges"],
            metadata={"coordinate_system": loaded["coordinate_system"], "from_artifact": True},
            quality=quality,
            files=files,
            motion=motion,
        )

    def read_motion_payload(self, dataset: str, sample_id: str, max_frames: int | None = None) -> dict[str, Any]:
        preview = self.read_processed_preview(dataset, sample_id, max_frames=max_frames)
        if preview.motion is None:
            raise FileNotFoundError(f"no motion payload for {dataset}/{sample_id}")
        return preview.motion

    def read_quality_report(self, dataset: str, sample_id: str) -> dict[str, Any]:
        frame_count = self._guess_frame_count(dataset, sample_id)
        paths, _ = self._resolve_paths(dataset, sample_id, frame_count)
        if not paths.quality_report.exists():
            raise FileNotFoundError(paths.quality_report)
        return json.loads(paths.quality_report.read_text(encoding="utf-8"))
