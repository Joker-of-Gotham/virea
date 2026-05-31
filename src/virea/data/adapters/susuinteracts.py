from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

import numpy as np

from virea.data.adapters.base import BaseDatasetAdapter
from virea.data.types import RawClip, SampleRef


class SuSuInterActsAdapter(BaseDatasetAdapter):
    def _profile_for(self, sample_id: str, has_positions: bool = False) -> tuple[str, str]:
        if sample_id.startswith("fbx_to_json_data_susu_retarget_maya/"):
            return "susu_retarget_maya_6d_body_hands_m_npy", "susu_retarget_maya_6d_body_hands"
        if sample_id.startswith("fbx_to_json_data_susu_chonglu/") or has_positions:
            return "susu_chonglu_6d_body_hands_cm_positions_npy", "susu_chonglu_6d_body_hands_cm"
        return "susu_6d_body_hands_npy", "susu_6d_body_hands"

    @lru_cache(maxsize=1)
    def _text_map(self) -> dict[str, str]:
        path = self.raw_root / "text_data" / "motion2text.json"
        if not path.exists():
            return {}
        return json.loads(path.read_text(encoding="utf-8"))

    def _split_items(self, split: str) -> list[str]:
        path = self.raw_root / "split" / f"{split}_file_list.txt"
        if not path.exists():
            return []
        return [line.strip() for line in path.read_text(encoding="utf-8", errors="replace").splitlines() if line.strip()]

    def _motion_path(self, name: str) -> Path:
        return self.raw_root / "motion_data" / f"{name}.npy"

    def _face_path(self, name: str) -> Path:
        return self.raw_root / "arkit_data" / f"{name}.npy"

    def _audio_path(self, name: str) -> Path:
        return self.raw_root / "wav_data" / f"{name}.wav"

    def discover(self, limit: int = 50, query: str = "") -> list[SampleRef]:
        if not self.raw_root.exists():
            return []
        samples: list[SampleRef] = []
        seen: set[str] = set()
        text_map = self._text_map()
        for split in ("test", "val", "train", "all"):
            for name in self._split_items(split):
                if name in seen:
                    continue
                seen.add(name)
                path = self._motion_path(name)
                text = text_map.get(name, "")
                if not path.exists() or not (self._matches(name, query) or self._matches(text, query)):
                    continue
                source_format, codec_key = self._profile_for(name)
                samples.append(
                    self._sample(
                        name,
                        path,
                        source_format,
                        codec_key,
                        fps=20.0,
                        text=text,
                        split=None if split == "all" else split,
                        related_paths={"face": self._face_path(name), "audio": self._audio_path(name)},
                        metadata={"susu_profile": codec_key},
                    )
                )
                if len(samples) >= limit:
                    return samples
        for path in sorted((self.raw_root / "motion_data").rglob("*.npy")):
            name = path.relative_to(self.raw_root / "motion_data").with_suffix("").as_posix()
            if name in seen:
                continue
            text = text_map.get(name, "")
            if not (self._matches(name, query) or self._matches(text, query)):
                continue
            source_format, codec_key = self._profile_for(name)
            samples.append(
                self._sample(
                    name,
                    path,
                    source_format,
                    codec_key,
                    fps=20.0,
                    text=text,
                    related_paths={"face": self._face_path(name), "audio": self._audio_path(name)},
                    metadata={"susu_profile": codec_key},
                )
            )
            if len(samples) >= limit:
                break
        return samples

    def load(self, sample_id: str, max_frames: int | None = None) -> RawClip:
        path = self._motion_path(sample_id)
        if not path.exists():
            raise FileNotFoundError(f"SuSuInterActs sample not found: {sample_id}")
        data = np.load(path, allow_pickle=True).item()
        motion = {key: np.asarray(value, dtype=np.float32) for key, value in data.items() if key in {"body", "left", "right", "positions"}}
        frame_count = int(next(iter(motion.values())).shape[0]) if motion else 0
        if "body" in motion and frame_count > 1:
            body_arr = motion["body"]
            if body_arr.std(axis=0).max() < 1e-6:
                raise ValueError(f"SuSuInterActs sample is static/frozen (all frames identical): {sample_id}")
        motion["fps"] = 20.0
        source_format, codec_key = self._profile_for(sample_id, has_positions="positions" in motion)
        face_path = self._face_path(sample_id)
        if face_path.exists():
            motion["face"] = np.asarray(np.load(face_path, allow_pickle=True), dtype=np.float32)
        text = self._text_map().get(sample_id, "")
        sample = self._sample(
            sample_id,
            path,
            source_format,
            codec_key,
            fps=20.0,
            frame_count=frame_count,
            duration_sec=frame_count / 20.0 if frame_count else None,
            text=text,
            related_paths={"face": face_path, "audio": self._audio_path(sample_id)},
            metadata={"has_positions": "positions" in motion, "has_face": "face" in motion, "susu_profile": codec_key},
        )
        annotations = [{"type": "dialogue", "language": "zh", "text": text}] if text else []
        return RawClip(sample=sample, motion=motion, annotations=annotations).limited(max_frames)
