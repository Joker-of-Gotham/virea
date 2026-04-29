from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd

from virea.data.adapters.base import BaseDatasetAdapter
from virea.data.types import RawClip, SampleRef


class HumanML3DAdapter(BaseDatasetAdapter):
    def _parquet_files(self) -> list[Path]:
        return sorted((self.raw_root / "data").glob("*.parquet"))

    @lru_cache(maxsize=16)
    def _metadata_table(self, path: str) -> pd.DataFrame:
        return pd.read_parquet(path, columns=["caption", "meta_data"])

    def discover(self, limit: int = 50, query: str = "") -> list[SampleRef]:
        if not self.raw_root.exists():
            return []
        samples: list[SampleRef] = []
        for path in self._parquet_files():
            split = path.name.split("-", 1)[0]
            table = self._metadata_table(str(path))
            for row_idx, row in table.iterrows():
                meta = row["meta_data"] or {}
                name = str(meta.get("name", row_idx)) if isinstance(meta, dict) else str(row_idx)
                sample_id = f"{split}/{path.stem}/{row_idx}"
                caption = str(row["caption"])
                if not (self._matches(sample_id, query) or self._matches(caption, query) or self._matches(name, query)):
                    continue
                frame_count = int(meta.get("num_frames", 0)) if isinstance(meta, dict) else None
                duration = float(meta.get("duration", 0.0)) if isinstance(meta, dict) else None
                samples.append(self._sample(sample_id, path, "humanml3d_263d_parquet", "humanml3d_263d", fps=20.0, frame_count=frame_count, duration_sec=duration, text=caption, split=split, metadata={"name": name, "row_index": int(row_idx)}))
                if len(samples) >= limit:
                    return samples
        return samples

    def load(self, sample_id: str, max_frames: int | None = None) -> RawClip:
        parts = sample_id.split("/")
        if len(parts) != 3:
            raise ValueError(f"HumanML3D sample_id must be split/shard/row, got {sample_id}")
        split, shard, row_str = parts
        path = self.raw_root / "data" / f"{shard}.parquet"
        if not path.exists():
            raise FileNotFoundError(f"HumanML3D shard not found: {path}")
        row_idx = int(row_str)
        df = pd.read_parquet(path)
        row = df.iloc[row_idx]
        motion = np.asarray(row["motion"].tolist() if hasattr(row["motion"], "tolist") else row["motion"], dtype=np.float32)
        meta = row["meta_data"] or {}
        caption = str(row["caption"])
        frame_count = int(meta.get("num_frames", motion.shape[0])) if isinstance(meta, dict) else motion.shape[0]
        duration = float(meta.get("duration", frame_count / 20.0)) if isinstance(meta, dict) else frame_count / 20.0
        sample = self._sample(sample_id, path, "humanml3d_263d_parquet", "humanml3d_263d", fps=20.0, frame_count=frame_count, duration_sec=duration, text=caption, split=split, metadata={"meta_data": meta, "row_index": row_idx})
        annotations = [{"type": "text", "language": "en", "text": line.split("#", 1)[0].strip()} for line in caption.splitlines() if line.strip()]
        return RawClip(sample=sample, motion={"motion": motion, "fps": 20.0}, annotations=annotations).limited(max_frames)
