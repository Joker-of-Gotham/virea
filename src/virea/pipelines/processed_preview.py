from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np

from virea.data.registry import DatasetRegistry
from virea.data.types import PreviewPayload, RawClip
from virea.motion.canonical import CANONICAL_TO_VRM_BONE_NAME, CORE_BONES, HAND_BONES, unpack_sequence
from virea.motion.codecs import CanonicalResult, MotionCodec, default_codecs
from virea.motion.skeleton import FK_BONES, target_rest_offsets_map, vrm_control_rest_source
from virea.motion.quality import preview_quality


def motion_uid(dataset: str, sample_id: str, frame_count: int) -> str:
    safe = "".join(ch if ch.isalnum() else "_" for ch in sample_id).strip("_")
    digest = hashlib.sha1(f"{dataset}:{sample_id}:{frame_count}".encode("utf-8")).hexdigest()[:8]
    return f"virea:{dataset}:{safe}:000000:{frame_count:06d}:{digest}"


class ProcessedPreviewPipeline:
    def __init__(self, registry: DatasetRegistry, codecs: dict[str, MotionCodec] | None = None) -> None:
        self.registry = registry
        self.codecs = codecs or default_codecs()

    def _motion_dict(self, result: CanonicalResult) -> dict[str, Any]:
        unpacked = unpack_sequence(result.sequence)
        frame_count = int(result.sequence.shape[0])
        return {
            "schema_version": "virea.vrm_motion_payload.v0.1.0",
            "frame_count": frame_count,
            "coordinate_system": "gltf_y_up_z_forward",
            "unit": "meter",
            "root_translation": np.round(unpacked["root_translation"].astype(float), 6).tolist(),
            "root_rotation": np.round(unpacked["root_rotation_xyzw"].astype(float), 6).tolist(),
            "core_bones": list(CORE_BONES),
            "core_quaternions": np.round(unpacked["core_quats_xyzw"].astype(float), 6).tolist(),
            "hand_bones": list(HAND_BONES),
            "hand_quaternions": np.round(unpacked["hand_quats_xyzw"].astype(float), 6).tolist(),
            "canonical_to_vrm": dict(CANONICAL_TO_VRM_BONE_NAME),
            "rest_bones": list(FK_BONES),
            "rest_offsets": {key: [float(v) for v in value] for key, value in target_rest_offsets_map().items()},
            "rest_source": vrm_control_rest_source(),
        }

    def _payload_from_result(self, clip: RawClip, result: CanonicalResult, files: dict[str, Any] | None = None) -> PreviewPayload:
        return PreviewPayload(
            stage="processed",
            sample=clip.sample,
            fps=float(clip.motion.get("fps", clip.sample.fps or self.registry.paths.target_fps)),
            positions=result.positions,
            joint_names=result.joint_names,
            edges=result.edges,
            annotations=clip.annotations,
            metadata=result.metadata,
            quality=preview_quality(result.positions, result.source_positions if result.source_positions.shape == result.positions.shape else None),
            files=files or {},
            motion=self._motion_dict(result),
        )

    def preview(self, dataset: str, sample_id: str, max_frames: int | None = None, persist: bool = False) -> PreviewPayload:
        adapter = self.registry.adapter(dataset)
        clip = adapter.load(sample_id, max_frames=max_frames)
        codec = self.codecs[clip.sample.codec_key]
        result = codec.to_canonical(clip)
        files = self.persist(clip, result) if persist else {}
        return self._payload_from_result(clip, result, files=files)

    def persist(self, clip: RawClip, result: CanonicalResult) -> dict[str, str]:
        version = self.registry.paths.processing_version
        root = self.registry.paths.processed_root
        uid = motion_uid(clip.sample.dataset, clip.sample.sample_id, int(result.positions.shape[0]))
        file_stem = "".join(ch if ch.isalnum() or ch in "._-" else "_" for ch in uid)
        dataset = clip.sample.dataset

        canonical_path = root / "canonical" / version / "motion" / dataset / f"{file_stem}.npz"
        vrm_motion_path = root / "vrm" / version / "motion" / dataset / f"{file_stem}.npz"
        quality_path = root / "vrm" / version / "quality" / dataset / f"{file_stem}.json"
        metadata_path = root / "canonical" / version / "metadata" / dataset / f"{file_stem}.json"

        for path in (canonical_path, vrm_motion_path, quality_path, metadata_path):
            path.parent.mkdir(parents=True, exist_ok=True)

        np.savez_compressed(
            canonical_path,
            sequence=result.sequence.astype(np.float32),
            positions=result.positions.astype(np.float32),
            joint_names=np.asarray(result.joint_names, dtype=object),
            edges=np.asarray(result.edges, dtype=np.int32),
        )
        np.savez_compressed(
            vrm_motion_path,
            positions=result.positions.astype(np.float32),
            joint_names=np.asarray(result.joint_names, dtype=object),
            edges=np.asarray(result.edges, dtype=np.int32),
            coordinate_system=np.asarray(["gltf_y_up_z_forward"], dtype=object),
        )
        quality = preview_quality(result.positions, result.source_positions if result.source_positions.shape == result.positions.shape else None)
        quality_path.write_text(json.dumps(quality, ensure_ascii=False, indent=2), encoding="utf-8")

        sample_record = {
            "schema_version": "virea.motion_sample.v0.1.0",
            "motion_uid": uid,
            "source": {
                "dataset": clip.sample.dataset,
                "source_id": clip.sample.sample_id,
                "source_path": str(clip.sample.source_path),
                "source_format": clip.sample.source_format,
                "license_family": clip.sample.metadata.get("license_family"),
                "citation_keys": clip.sample.metadata.get("citation_keys", []),
            },
            "time": {
                "fps": clip.sample.fps,
                "num_frames": int(result.positions.shape[0]),
                "duration_sec": float(result.positions.shape[0] / (clip.sample.fps or 30.0)),
                "start_frame": 0,
                "end_frame": int(result.positions.shape[0]),
            },
            "skeleton": {
                "source_skeleton": result.metadata.get("source_profile"),
                "canonical_skeleton": "virea_canonical_v0.1",
                "target_skeleton": "vrm1_humanoid",
                "coordinate_system": "gltf_y_up_z_forward",
                "rotation_format": "quat_xyzw",
                "unit": "meter",
            },
            "annotations": clip.annotations,
            "files": {
                "canonical_motion": str(canonical_path.relative_to(root)),
                "vrm_motion": str(vrm_motion_path.relative_to(root)),
                "quality_report": str(quality_path.relative_to(root)),
                "metadata": str(metadata_path.relative_to(root)),
            },
            "quality": quality,
            "processing": {
                "version": version,
                "codec": result.metadata.get("codec"),
            },
        }
        metadata_path.write_text(json.dumps(sample_record, ensure_ascii=False, indent=2), encoding="utf-8")
        return {
            "motion_uid": uid,
            "processed_root": str(root),
            "canonical_motion": str(canonical_path),
            "vrm_motion": str(vrm_motion_path),
            "quality_report": str(quality_path),
            "metadata": str(metadata_path),
        }
