from __future__ import annotations

from pathlib import Path

import numpy as np

from virea.data.adapters.base import BaseDatasetAdapter
from virea.data.types import RawClip, SampleRef
from virea.motion.codecs import SMPL24_NAMES
from virea.motion.skeleton import BODY_EDGES


class AMASSAdapter(BaseDatasetAdapter):
    _SKIP_STEMS = {"female_stagei", "male_stagei", "shape", "marker"}

    def discover(self, limit: int = 50, query: str = "") -> list[SampleRef]:
        if not self.raw_root.exists():
            return []
        samples: list[SampleRef] = []
        for path in sorted(self.raw_root.rglob("*.npz")):
            if "LICENSE" in path.name.upper():
                continue
            if path.stem.lower() in self._SKIP_STEMS:
                continue
            sample_id = self._rel_id(path)
            if not self._matches(sample_id, query):
                continue
            samples.append(self._sample(sample_id, path, "smplh_axis_angle_npz", "axis_angle_body22"))
            if len(samples) >= limit:
                return samples
        for path in sorted((self.raw_root / "humanact12").rglob("*.npy")) if (self.raw_root / "humanact12").exists() else []:
            sample_id = self._rel_id(path)
            if not self._matches(sample_id, query):
                continue
            samples.append(self._sample(sample_id, path, "humanact12_positions_npy", "position_sequence", fps=20.0))
            if len(samples) >= limit:
                break
        return samples

    def load(self, sample_id: str, max_frames: int | None = None) -> RawClip:
        npz_path = self._path_from_id(sample_id, ".npz")
        npy_path = self._path_from_id(sample_id, ".npy")
        if npz_path.exists():
            payload = np.load(npz_path, allow_pickle=True)
            poses = np.asarray(payload["poses"], dtype=np.float32)
            trans = np.asarray(payload.get("trans", np.zeros((poses.shape[0], 3))), dtype=np.float32)
            fps = float(np.asarray(payload.get("mocap_framerate", payload.get("mocap_frame_rate", 60.0))).reshape(-1)[0])
            sample = self._sample(sample_id, npz_path, "smplh_axis_angle_npz", "axis_angle_body22", fps=fps, frame_count=poses.shape[0])
            clip = RawClip(sample=sample, motion={"poses": poses, "translation": trans, "fps": fps})
            return clip.limited(max_frames)
        if npy_path.exists():
            positions = np.asarray(np.load(npy_path, allow_pickle=True), dtype=np.float32)
            sample = self._sample(sample_id, npy_path, "humanact12_positions_npy", "position_sequence", fps=20.0, frame_count=positions.shape[0])
            edges = [edge for edge in BODY_EDGES if edge[0] < positions.shape[1] and edge[1] < positions.shape[1]]
            clip = RawClip(sample=sample, motion={"positions": positions, "fps": 20.0}, source_joint_names=SMPL24_NAMES[: positions.shape[1]], source_edges=edges)
            return clip.limited(max_frames)
        raise FileNotFoundError(f"AMASS sample not found: {sample_id}")
