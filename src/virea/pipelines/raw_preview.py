from __future__ import annotations

from virea.data.registry import DatasetRegistry
from virea.data.types import PreviewPayload
from virea.motion.codecs import MotionCodec, default_codecs


class RawPreviewPipeline:
    def __init__(self, registry: DatasetRegistry, codecs: dict[str, MotionCodec] | None = None) -> None:
        self.registry = registry
        self.codecs = codecs or default_codecs()

    def preview(self, dataset: str, sample_id: str, max_frames: int | None = None) -> PreviewPayload:
        adapter = self.registry.adapter(dataset)
        clip = adapter.load(sample_id, max_frames=max_frames)
        codec = self.codecs[clip.sample.codec_key]
        return codec.to_source_preview(clip)
