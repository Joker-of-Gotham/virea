from __future__ import annotations

import pytest

from virea.data.registry import DatasetRegistry
from virea.pipelines.processed_preview import ProcessedPreviewPipeline
from virea.pipelines.raw_preview import RawPreviewPipeline


@pytest.mark.parametrize("dataset", ["amass", "babel", "beat", "grab", "humanml3d", "motionx", "susuinteracts"])
def test_first_sample_has_raw_and_processed_preview(dataset: str) -> None:
    registry = DatasetRegistry.default()
    adapter = registry.adapter(dataset)
    if not adapter.exists():
        pytest.skip(f"raw root not available for {dataset}")
    samples = adapter.discover(limit=1)
    if not samples:
        pytest.skip(f"no samples found for {dataset}")

    raw = RawPreviewPipeline(registry).preview(dataset, samples[0].sample_id, max_frames=8)
    processed = ProcessedPreviewPipeline(registry).preview(dataset, samples[0].sample_id, max_frames=8)

    assert raw.positions.ndim == 3
    assert processed.positions.ndim == 3
    assert raw.positions.shape[0] <= 8
    assert processed.positions.shape[0] <= 8
    assert raw.quality["status"] == "passed"
    assert processed.quality["status"] == "passed"
