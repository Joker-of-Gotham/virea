from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

import numpy as np

from virea.data.registry import DatasetRegistry
from virea.data.types import RawClip
from virea.motion.codecs import CanonicalResult, MotionCodec, default_codecs
from virea.motion.quality import preview_quality
from virea.motion.skeleton import BODY_BONES
from virea.motion.snapshot import SourceSnapshot
from virea.pipelines.artifacts import artifact_paths, legacy_vrm_motion_path
from virea.pipelines.artifacts import motion_uid


@dataclass
class ProcessingOutput:
    clip: RawClip
    source: SourceSnapshot
    canonical: CanonicalResult
    quality: dict[str, Any]
    motion_uid: str
    paths: dict[str, str]


class ProcessingPipeline:
    """Pure data processing: load, extract source, convert, assess, persist. No preview payloads."""

    def __init__(self, registry: DatasetRegistry, codecs: dict[str, MotionCodec] | None = None) -> None:
        self.registry = registry
        self.codecs = codecs or default_codecs()

    def process_clip(self, clip: RawClip) -> tuple[SourceSnapshot, CanonicalResult]:
        codec = self.codecs[clip.sample.codec_key]
        source = codec.extract_source(clip)
        canonical = codec.to_canonical(clip)
        return source, canonical

    def process(self, dataset: str, sample_id: str, max_frames: int | None = None) -> ProcessingOutput:
        adapter = self.registry.adapter(dataset)
        clip = adapter.load(sample_id, max_frames=max_frames)
        source, canonical = self.process_clip(clip)
        uid = motion_uid(dataset, sample_id, int(canonical.positions.shape[0]))
        fps = float(clip.motion.get("fps", clip.sample.fps or 30.0))
        retarget_src = canonical.retarget_source_positions
        if retarget_src is not None and retarget_src.shape[0] == canonical.positions.shape[0]:
            src_pos = retarget_src
            src_names = list(BODY_BONES[:retarget_src.shape[1]])
        elif source.positions.shape[0] == canonical.positions.shape[0]:
            src_pos = source.positions
            src_names = source.joint_names
        else:
            src_pos = None
            src_names = None
        quality = preview_quality(
            canonical.positions,
            src_pos,
            joint_names=canonical.joint_names[:canonical.positions.shape[1]],
            source_joint_names=src_names,
            fps=fps,
        )
        return ProcessingOutput(
            clip=clip,
            source=source,
            canonical=canonical,
            quality=quality,
            motion_uid=uid,
            paths={},
        )

    def persist(self, output: ProcessingOutput) -> dict[str, str]:
        version = self.registry.paths.processing_version
        root = self.registry.paths.processed_root
        paths = artifact_paths(root, version, output.clip.sample.dataset, output.motion_uid)
        for path in paths.all_outputs():
            path.parent.mkdir(parents=True, exist_ok=True)

        source = output.source
        result = output.canonical
        clip = output.clip

        np.savez_compressed(
            paths.source_snapshot,
            positions=source.positions.astype(np.float32),
            joint_names=np.asarray(source.joint_names, dtype=object),
            edges=np.asarray(source.edges, dtype=np.int32),
            fps=np.float32(source.fps),
            coordinate_system=np.asarray([source.coordinate_system], dtype=object),
        )
        sample_fps = np.float32(clip.sample.fps or 30.0)
        np.savez_compressed(
            paths.canonical_motion,
            sequence=result.sequence.astype(np.float32),
            positions=result.positions.astype(np.float32),
            joint_names=np.asarray(result.joint_names, dtype=object),
            edges=np.asarray(result.edges, dtype=np.int32),
            fps=sample_fps,
        )
        np.savez_compressed(
            paths.vrm_positions,
            positions=result.positions.astype(np.float32),
            joint_names=np.asarray(result.joint_names, dtype=object),
            edges=np.asarray(result.edges, dtype=np.int32),
            fps=sample_fps,
            coordinate_system=np.asarray(["gltf_y_up_z_forward"], dtype=object),
        )
        legacy = legacy_vrm_motion_path(paths)
        legacy.parent.mkdir(parents=True, exist_ok=True)
        np.savez_compressed(
            legacy,
            positions=result.positions.astype(np.float32),
            joint_names=np.asarray(result.joint_names, dtype=object),
            edges=np.asarray(result.edges, dtype=np.int32),
            fps=sample_fps,
            coordinate_system=np.asarray(["gltf_y_up_z_forward"], dtype=object),
        )

        paths.quality_report.write_text(
            json.dumps(output.quality, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        sample_record = {
            "schema_version": "virea.motion_sample.v0.1.0",
            "motion_uid": output.motion_uid,
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
                "source_snapshot": str(paths.source_snapshot.relative_to(root)),
                "canonical_motion": str(paths.canonical_motion.relative_to(root)),
                "vrm_positions": str(paths.vrm_positions.relative_to(root)),
                "quality_report": str(paths.quality_report.relative_to(root)),
                "metadata": str(paths.metadata.relative_to(root)),
            },
            "quality": output.quality,
            "processing": {
                "version": version,
                "codec": result.metadata.get("codec"),
            },
        }
        paths.metadata.write_text(json.dumps(sample_record, ensure_ascii=False, indent=2), encoding="utf-8")

        file_map = {
            "motion_uid": output.motion_uid,
            "processed_root": str(root),
            "source_snapshot": str(paths.source_snapshot),
            "canonical_motion": str(paths.canonical_motion),
            "vrm_positions": str(paths.vrm_positions),
            "vrm_motion": str(legacy),
            "quality_report": str(paths.quality_report),
            "metadata": str(paths.metadata),
        }
        output.paths = file_map
        return file_map

    def run(
        self,
        dataset: str,
        sample_id: str,
        max_frames: int | None = None,
        persist: bool = True,
        skip_existing: bool = False,
    ) -> ProcessingOutput:
        output = self.process(dataset, sample_id, max_frames=max_frames)
        if persist:
            if skip_existing:
                paths = artifact_paths(
                    self.registry.paths.processed_root,
                    self.registry.paths.processing_version,
                    dataset,
                    output.motion_uid,
                )
                if paths.exists():
                    output.paths = {
                        "motion_uid": output.motion_uid,
                        "skipped": "true",
                        "source_snapshot": str(paths.source_snapshot),
                        "vrm_positions": str(paths.vrm_positions),
                    }
                    return output
            self.persist(output)
        return output
