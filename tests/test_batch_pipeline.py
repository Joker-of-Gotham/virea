from __future__ import annotations

from pathlib import Path

import numpy as np

from virea.pipelines.artifacts import artifact_paths, motion_uid
from virea.pipelines.batch import BatchPipeline, ProcessingTask
from virea.server.binary_codec import pack_positions_binary, unpack_positions_binary


def test_binary_codec_roundtrip() -> None:
    positions = np.arange(24, dtype=np.float32).reshape(2, 4, 3)
    packed = pack_positions_binary(positions, 2, 4)
    decoded = unpack_positions_binary(packed)
    assert decoded["frame_count"] == 2
    assert decoded["joint_count"] == 4
    np.testing.assert_allclose(decoded["positions"], positions)


def test_artifact_paths_exists(tmp_path: Path) -> None:
    uid = motion_uid("beat", "sample", 10)
    paths = artifact_paths(tmp_path, "v0.1.0", "beat", uid)
    assert not paths.exists()
    for path in paths.all_outputs():
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.suffix == ".npz":
            np.savez_compressed(
                path,
                positions=np.zeros((10, 22, 3), dtype=np.float32),
                joint_names=np.asarray(["hips"], dtype=object),
                edges=np.zeros((0, 2), dtype=np.int32),
            )
        else:
            path.write_text("{}", encoding="utf-8")
    assert paths.exists()


def test_batch_collect_tasks_structure() -> None:
    pipeline = BatchPipeline.__new__(BatchPipeline)
    pipeline.registry = None  # type: ignore[assignment]
    task = ProcessingTask(dataset="amass", sample_id="x")
    assert task.dataset == "amass"
