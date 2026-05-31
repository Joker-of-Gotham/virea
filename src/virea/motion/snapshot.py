from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np


@dataclass
class SourceSnapshot:
    """Lightweight source-space skeleton snapshot (no VRM retarget)."""

    positions: np.ndarray
    joint_names: list[str]
    edges: list[tuple[int, int]]
    fps: float
    coordinate_system: str = "source_native"
    metadata: dict[str, Any] | None = None

    def __post_init__(self) -> None:
        self.positions = np.asarray(self.positions, dtype=np.float32)
        if self.metadata is None:
            self.metadata = {}
