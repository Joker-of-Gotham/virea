from __future__ import annotations

from pathlib import Path

from virea.data.types import DatasetRecord, RawClip, SampleRef


class BaseDatasetAdapter:
    def __init__(self, record: DatasetRecord, raw_root: Path) -> None:
        self.record = record
        self.raw_root = Path(raw_root)

    def discover(self, limit: int = 50, query: str = "") -> list[SampleRef]:
        raise NotImplementedError

    def load(self, sample_id: str, max_frames: int | None = None) -> RawClip:
        raise NotImplementedError

    def exists(self) -> bool:
        return self.raw_root.exists()

    def _matches(self, sample_id: str, query: str) -> bool:
        q = str(query or "").strip().lower()
        return not q or q in sample_id.lower()

    def _rel_id(self, path: Path) -> str:
        return path.relative_to(self.raw_root).with_suffix("").as_posix()

    def _path_from_id(self, sample_id: str, suffix: str) -> Path:
        return self.raw_root / Path(sample_id + suffix)

    def _sample(
        self,
        sample_id: str,
        source_path: Path,
        source_format: str,
        codec_key: str,
        fps: float | None = None,
        frame_count: int | None = None,
        duration_sec: float | None = None,
        text: str = "",
        split: str | None = None,
        related_paths: dict[str, Path] | None = None,
        metadata: dict | None = None,
    ) -> SampleRef:
        meta = {
            "dataset_name": self.record.name,
            "license_family": self.record.license_family,
            "citation_keys": list(self.record.citation_keys),
        }
        if metadata:
            meta.update(metadata)
        return SampleRef(
            dataset=self.record.key,
            sample_id=sample_id,
            source_path=source_path,
            source_format=source_format,
            codec_key=codec_key,
            fps=fps,
            frame_count=frame_count,
            duration_sec=duration_sec,
            text=text,
            split=split,
            related_paths=related_paths or {},
            metadata=meta,
        )
