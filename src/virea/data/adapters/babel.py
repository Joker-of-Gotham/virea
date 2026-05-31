from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

import numpy as np

from virea.data.adapters.base import BaseDatasetAdapter
from virea.data.types import RawClip, SampleRef


class BABELAdapter(BaseDatasetAdapter):
    @lru_cache(maxsize=2)
    def _annotations(self, split: str) -> dict[str, Any]:
        path = self.raw_root / "babel-teach" / f"{split}.json"
        if not path.exists():
            return {}
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)

    def _annotation_motion_path(self, record: dict[str, Any]) -> Path:
        feat = str(record.get("feat_p", "")).strip()
        candidates = [self.raw_root / feat, self.raw_root.parent / "amass" / feat]
        for candidate in candidates:
            if candidate.exists():
                return candidate
        return candidates[-1]

    def _annotation_text(self, record: dict[str, Any]) -> str:
        labels: list[str] = []
        for block in ("seq_ann", "frame_ann"):
            ann = record.get(block, {})
            for item in ann.get("labels", []) if isinstance(ann, dict) else []:
                value = item.get("proc_label") or item.get("raw_label")
                if value:
                    labels.append(str(value))
        return ", ".join(dict.fromkeys(labels))

    def discover(self, limit: int = 50, query: str = "") -> list[SampleRef]:
        if not self.raw_root.exists():
            return []
        samples: list[SampleRef] = []
        for split in ("train", "val"):
            for key, record in self._annotations(split).items():
                sample_id = f"babel-teach/{split}/{key}"
                text = self._annotation_text(record)
                if not (self._matches(sample_id, query) or self._matches(text, query)):
                    continue
                motion_path = self._annotation_motion_path(record)
                if not motion_path.exists():
                    continue
                samples.append(
                    self._sample(
                        sample_id,
                        motion_path,
                        "babel_annotation_json",
                        "axis_angle_body22",
                        duration_sec=float(record.get("dur", 0.0) or 0.0),
                        text=text,
                        split=split,
                        related_paths={"annotation": self.raw_root / "babel-teach" / f"{split}.json"},
                        metadata={"babel_sid": record.get("babel_sid"), "feat_p": record.get("feat_p")},
                    )
                )
                if len(samples) >= limit:
                    return samples
        _skip_stems = {"female_stagei", "male_stagei", "shape", "marker"}
        for path in sorted(self.raw_root.rglob("*.npz")):
            if path.stem.lower() in _skip_stems:
                continue
            sample_id = self._rel_id(path)
            if not self._matches(sample_id, query):
                continue
            samples.append(self._sample(sample_id, path, "smplh_axis_angle_npz", "axis_angle_body22"))
            if len(samples) >= limit:
                break
        return samples

    def _record_for_sample(self, sample_id: str) -> tuple[str | None, dict[str, Any] | None]:
        parts = sample_id.split("/")
        if len(parts) == 3 and parts[0] == "babel-teach":
            split, key = parts[1], parts[2]
            return split, self._annotations(split).get(key)
        return None, None

    def load(self, sample_id: str, max_frames: int | None = None) -> RawClip:
        split, record = self._record_for_sample(sample_id)
        annotations: list[dict[str, Any]] = []
        text = ""
        if record is not None:
            path = self._annotation_motion_path(record)
            text = self._annotation_text(record)
            for item in record.get("seq_ann", {}).get("labels", []):
                annotations.append({"type": "action", "text": item.get("proc_label") or item.get("raw_label"), "scope": "sequence"})
            for item in record.get("frame_ann", {}).get("labels", []):
                annotations.append({
                    "type": "action",
                    "text": item.get("proc_label") or item.get("raw_label"),
                    "scope": "frame",
                    "start_sec": item.get("start_t"),
                    "end_sec": item.get("end_t"),
                })
        else:
            path = self._path_from_id(sample_id, ".npz")
        if not path.exists():
            raise FileNotFoundError(f"BABEL carrier motion not found for {sample_id}: {path}")
        payload = np.load(path, allow_pickle=True)
        poses = np.asarray(payload["poses"], dtype=np.float32)
        trans = np.asarray(payload.get("trans", np.zeros((poses.shape[0], 3))), dtype=np.float32)
        fps = float(np.asarray(payload.get("mocap_framerate", payload.get("mocap_frame_rate", payload.get("mocap_frame_rate", 60.0)))).reshape(-1)[0])
        sample = self._sample(
            sample_id,
            path,
            "babel_annotation_json" if record is not None else "smplh_axis_angle_npz",
            "axis_angle_body22",
            fps=fps,
            frame_count=poses.shape[0],
            text=text,
            split=split,
            metadata={"annotation_record": record} if record is not None else None,
        )
        clip = RawClip(sample=sample, motion={"poses": poses, "translation": trans, "fps": fps}, annotations=annotations)
        return clip.limited(max_frames)
