from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np


JsonDict = dict[str, Any]


@dataclass(frozen=True)
class DatasetRecord:
    key: str
    name: str
    full_name: str
    type: str
    raw_dir: str
    adapter: str
    license_family: str
    citation_keys: tuple[str, ...]
    modalities: JsonDict
    native_representations: tuple[str, ...] = ()

    @classmethod
    def from_yaml(cls, key: str, payload: JsonDict) -> "DatasetRecord":
        return cls(
            key=key,
            name=str(payload.get("name", key)),
            full_name=str(payload.get("full_name", payload.get("name", key))),
            type=str(payload.get("type", "unknown")),
            raw_dir=str(payload.get("raw_dir", key)),
            adapter=str(payload["adapter"]),
            license_family=str(payload.get("license_family", "unknown")),
            citation_keys=tuple(str(item) for item in payload.get("citation_keys", [])),
            modalities=dict(payload.get("modalities", {})),
            native_representations=tuple(str(item) for item in payload.get("native_representations", [])),
        )

    def to_dict(self) -> JsonDict:
        return {
            "key": self.key,
            "name": self.name,
            "full_name": self.full_name,
            "type": self.type,
            "raw_dir": self.raw_dir,
            "adapter": self.adapter,
            "license_family": self.license_family,
            "citation_keys": list(self.citation_keys),
            "modalities": self.modalities,
            "native_representations": list(self.native_representations),
        }


@dataclass
class SampleRef:
    dataset: str
    sample_id: str
    source_path: Path
    source_format: str
    codec_key: str
    fps: float | None = None
    frame_count: int | None = None
    duration_sec: float | None = None
    text: str = ""
    split: str | None = None
    related_paths: dict[str, Path] = field(default_factory=dict)
    metadata: JsonDict = field(default_factory=dict)

    def to_dict(self) -> JsonDict:
        return {
            "dataset": self.dataset,
            "sample_id": self.sample_id,
            "source_path": str(self.source_path),
            "source_format": self.source_format,
            "codec_key": self.codec_key,
            "fps": self.fps,
            "frame_count": self.frame_count,
            "duration_sec": self.duration_sec,
            "text": self.text,
            "split": self.split,
            "related_paths": {key: str(value) for key, value in self.related_paths.items()},
            "metadata": self.metadata,
        }


@dataclass
class RawClip:
    sample: SampleRef
    motion: dict[str, Any]
    annotations: list[JsonDict] = field(default_factory=list)
    source_joint_names: list[str] = field(default_factory=list)
    source_edges: list[tuple[int, int]] = field(default_factory=list)

    def limited(self, max_frames: int | None) -> "RawClip":
        if not max_frames:
            return self
        motion: dict[str, Any] = {}
        for key, value in self.motion.items():
            if isinstance(value, np.ndarray) and value.ndim >= 1:
                motion[key] = value[:max_frames]
            else:
                motion[key] = value
        sample = SampleRef(
            dataset=self.sample.dataset,
            sample_id=self.sample.sample_id,
            source_path=self.sample.source_path,
            source_format=self.sample.source_format,
            codec_key=self.sample.codec_key,
            fps=self.sample.fps,
            frame_count=min(self.sample.frame_count or max_frames, max_frames),
            duration_sec=self.sample.duration_sec,
            text=self.sample.text,
            split=self.sample.split,
            related_paths=self.sample.related_paths,
            metadata=self.sample.metadata,
        )
        return RawClip(sample=sample, motion=motion, annotations=self.annotations, source_joint_names=self.source_joint_names, source_edges=self.source_edges)


@dataclass
class PreviewPayload:
    stage: str
    sample: SampleRef
    fps: float
    positions: np.ndarray
    joint_names: list[str]
    edges: list[tuple[int, int]]
    annotations: list[JsonDict] = field(default_factory=list)
    metadata: JsonDict = field(default_factory=dict)
    quality: JsonDict = field(default_factory=dict)
    files: JsonDict = field(default_factory=dict)
    motion: JsonDict | None = None

    def to_dict(self) -> JsonDict:
        payload = {
            "stage": self.stage,
            "dataset": self.sample.dataset,
            "sample_id": self.sample.sample_id,
            "fps": self.fps,
            "frame_count": int(self.positions.shape[0]),
            "duration_sec": float(self.positions.shape[0] / self.fps) if self.fps else None,
            "skeleton": {
                "joint_names": self.joint_names,
                "edges": [[int(a), int(b)] for a, b in self.edges],
                "coordinate_system": "gltf_y_up_z_forward",
                "unit": "meter",
            },
            "frames": {
                "positions": np.round(self.positions.astype(float), 5).tolist(),
            },
            "annotations": self.annotations,
            "metadata": self.metadata,
            "quality": self.quality,
            "files": self.files,
            "sample": self.sample.to_dict(),
        }
        if self.motion is not None:
            payload["motion"] = self.motion
        return payload
