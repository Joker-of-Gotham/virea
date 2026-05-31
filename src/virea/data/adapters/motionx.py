from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from virea.data.adapters.base import BaseDatasetAdapter
from virea.data.types import RawClip, SampleRef


class MotionXAdapter(BaseDatasetAdapter):
    def _seq_text_path(self, motion_path: Path) -> Path:
        rel = motion_path.relative_to(self.raw_root / "motion_data" / "smplx_322").with_suffix(".txt")
        return self.raw_root / "motionx_seq_text_v1.1" / rel

    def _frame_text_path(self, motion_path: Path, kind: str) -> Path:
        rel = motion_path.relative_to(self.raw_root / "motion_data" / "smplx_322").with_suffix(".json")
        return self.raw_root / "texts" / kind / rel

    def discover(self, limit: int = 50, query: str = "") -> list[SampleRef]:
        root = self.raw_root / "motion_data" / "smplx_322"
        if not root.exists():
            return []
        samples: list[SampleRef] = []
        for path in sorted(root.rglob("*.npy")):
            sample_id = path.relative_to(self.raw_root).with_suffix("").as_posix()
            text_path = self._seq_text_path(path)
            text = text_path.read_text(encoding="utf-8", errors="replace").splitlines()[0] if text_path.exists() else ""
            if not (self._matches(sample_id, query) or self._matches(text, query)):
                continue
            samples.append(self._sample(sample_id, path, "smplx_322_npy", "smplx_fullpose", text=text, related_paths={"sequence_text": text_path}))
            if len(samples) >= limit:
                break
        return samples

    def load(self, sample_id: str, max_frames: int | None = None) -> RawClip:
        path = self.raw_root / Path(sample_id + ".npy")
        if not path.exists():
            raise FileNotFoundError(f"Motion-X sample not found: {sample_id}")
        arr = np.asarray(np.load(path, allow_pickle=True), dtype=np.float32)
        if arr.ndim != 2 or arr.shape[1] < 322:
            raise ValueError(f"Motion-X expected shape (T, 322), got {arr.shape}")
        fullpose = arr[:, :165]
        translation = arr[:, 309:312]
        trans_span = np.ptp(translation, axis=0) if translation.size else np.zeros(3, dtype=np.float32)
        translation_scale = 0.01 if float(np.nanmax(np.abs(trans_span))) > 20.0 or float(np.nanpercentile(np.abs(translation), 95)) > 20.0 else 1.0
        translation = (translation * np.float32(translation_scale)).astype(np.float32)
        face_expr = arr[:, 159:209]
        text_path = self._seq_text_path(path)
        text = text_path.read_text(encoding="utf-8", errors="replace").strip() if text_path.exists() else ""
        annotations = [{"type": "text", "text": line.split("#", 1)[0].strip()} for line in text.splitlines() if line.strip()]
        related = {"sequence_text": text_path}
        metadata = {
            "sub_source": Path(sample_id).parts[2] if len(Path(sample_id).parts) > 2 else "",
            "translation_scale": translation_scale,
            "translation_scale_rule": "scale_0.01_when_translation_span_or_abs_position_exceeds_20",
            "declared_world_basis": "identity_y_up",
        }
        for kind in ("body_texts", "hand_texts"):
            frame_path = self._frame_text_path(path, kind)
            if frame_path.exists():
                related[kind] = frame_path
                try:
                    metadata[kind] = list(json.loads(frame_path.read_text(encoding="utf-8")).values())[:3]
                except Exception:
                    pass
        sample = self._sample(sample_id, path, "smplx_322_npy", "smplx_fullpose", fps=30.0, frame_count=arr.shape[0], text=text, related_paths=related, metadata=metadata)
        motion = {"fullpose": fullpose, "translation": translation, "fps": 30.0, "face_expr": face_expr, "source_metadata": metadata}
        return RawClip(sample=sample, motion=motion, annotations=annotations).limited(max_frames)
