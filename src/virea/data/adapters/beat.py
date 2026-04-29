from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from virea.data.adapters.base import BaseDatasetAdapter
from virea.data.types import RawClip, SampleRef


class BEATAdapter(BaseDatasetAdapter):
    def _related_text_path(self, pose_path: Path) -> Path:
        speaker = pose_path.parent.name
        return self.raw_root / "hf" / speaker / f"{pose_path.stem}.txt"

    def _read_text(self, path: Path) -> tuple[str, list[dict]]:
        if not path.exists():
            return "", []
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        annotations = []
        heads = []
        for line in lines[:64]:
            parts = line.split("\t")
            if len(parts) >= 5:
                text = parts[5] if len(parts) > 5 else parts[0]
                heads.append(text)
                annotations.append({
                    "type": "gesture_or_semantic",
                    "label": parts[0],
                    "start_sec": float(parts[1]) if parts[1].replace(".", "", 1).isdigit() else None,
                    "end_sec": float(parts[2]) if parts[2].replace(".", "", 1).isdigit() else None,
                    "text": text,
                })
        return " ".join(head for head in heads if head).strip(), annotations

    def discover(self, limit: int = 50, query: str = "") -> list[SampleRef]:
        if not self.raw_root.exists():
            return []
        samples: list[SampleRef] = []
        for path in sorted((self.raw_root / "pose").rglob("*.npz")):
            sample_id = self._rel_id(path)
            text_path = self._related_text_path(path)
            text = text_path.read_text(encoding="utf-8", errors="replace")[:200] if text_path.exists() else ""
            if not (self._matches(sample_id, query) or self._matches(text, query)):
                continue
            samples.append(self._sample(sample_id, path, "beat_bvh_axis_angle_npz", "beat_axis_angle_body22", text=text, related_paths={"text": text_path}))
            if len(samples) >= limit:
                break
        return samples

    def load(self, sample_id: str, max_frames: int | None = None) -> RawClip:
        path = self._path_from_id(sample_id, ".npz")
        if not path.exists():
            raise FileNotFoundError(f"BEAT sample not found: {sample_id}")
        payload = np.load(path, allow_pickle=True)
        poses = np.asarray(payload["poses"], dtype=np.float32)
        trans = np.asarray(payload.get("trans", np.zeros((poses.shape[0], 3))), dtype=np.float32)
        fps = float(np.asarray(payload.get("fps", 30.0)).reshape(-1)[0])
        text_path = self._related_text_path(path)
        text, annotations = self._read_text(text_path)
        meta_path = path.with_suffix(".json")
        metadata = {}
        if meta_path.exists():
            metadata = json.loads(meta_path.read_text(encoding="utf-8", errors="replace"))
        sample = self._sample(
            sample_id,
            path,
            "beat_bvh_axis_angle_npz",
            "beat_axis_angle_body22",
            fps=fps,
            frame_count=poses.shape[0],
            text=text,
            related_paths={"text": text_path, "metadata": meta_path},
            metadata=metadata,
        )
        return RawClip(sample=sample, motion={"poses": poses, "translation": trans, "fps": fps}, annotations=annotations).limited(max_frames)
