from __future__ import annotations

import numpy as np

from virea.data.adapters.base import BaseDatasetAdapter
from virea.data.types import RawClip, SampleRef


class GRABAdapter(BaseDatasetAdapter):
    def discover(self, limit: int = 50, query: str = "") -> list[SampleRef]:
        if not self.raw_root.exists():
            return []
        samples: list[SampleRef] = []
        for path in sorted(self.raw_root.glob("s*/*.npz")):
            sample_id = self._rel_id(path)
            if not self._matches(sample_id, query):
                continue
            samples.append(self._sample(sample_id, path, "smplx_fullpose_npz", "smplx_fullpose"))
            if len(samples) >= limit:
                break
        return samples

    def load(self, sample_id: str, max_frames: int | None = None) -> RawClip:
        path = self._path_from_id(sample_id, ".npz")
        if not path.exists():
            raise FileNotFoundError(f"GRAB sample not found: {sample_id}")
        payload = np.load(path, allow_pickle=True)
        body = payload["body"].item()
        params = body["params"]
        fullpose = np.asarray(params["fullpose"], dtype=np.float32)
        translation = np.asarray(params.get("transl", np.zeros((fullpose.shape[0], 3))), dtype=np.float32)
        fps = float(np.asarray(payload.get("framerate", 120.0)).reshape(-1)[0])
        metadata = {
            "subject_id": str(np.asarray(payload.get("sbj_id", path.parent.name)).reshape(-1)[0]),
            "gender": str(np.asarray(payload.get("gender", "")).reshape(-1)[0]),
            "object_name": str(np.asarray(payload.get("obj_name", "")).reshape(-1)[0]),
            "has_contact": "contact" in payload.files,
            "declared_world_basis": "z_up_to_y_up",
        }
        sample = self._sample(sample_id, path, "smplx_fullpose_npz", "smplx_fullpose", fps=fps, frame_count=fullpose.shape[0], metadata=metadata)
        motion = {"fullpose": fullpose, "translation": translation, "fps": fps, "source_metadata": metadata}
        annotations = [{"type": "object", "text": metadata["object_name"]}] if metadata.get("object_name") else []
        return RawClip(sample=sample, motion=motion, annotations=annotations).limited(max_frames)
