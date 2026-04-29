from __future__ import annotations

import numpy as np


def preview_quality(positions: np.ndarray, source_positions: np.ndarray | None = None) -> dict:
    pos = np.asarray(positions, dtype=np.float32)
    finite = bool(np.isfinite(pos).all())
    frame_count = int(pos.shape[0]) if pos.ndim == 3 else 0
    joint_count = int(pos.shape[1]) if pos.ndim == 3 else 0
    bbox_min = pos.reshape(-1, 3).min(axis=0).tolist() if pos.size else [0.0, 0.0, 0.0]
    bbox_max = pos.reshape(-1, 3).max(axis=0).tolist() if pos.size else [0.0, 0.0, 0.0]
    velocity = np.diff(pos, axis=0, prepend=pos[:1]) if frame_count else np.zeros_like(pos)
    velocity_norm = np.linalg.norm(velocity, axis=-1) if velocity.size else np.zeros((0,))
    ground_penetration_ratio = float((pos[..., 1] < -0.03).mean()) if pos.size else 0.0
    report = {
        "schema_valid": finite and frame_count > 0 and joint_count > 0,
        "finite": finite,
        "frame_count": frame_count,
        "joint_count": joint_count,
        "bbox_min": [round(float(v), 5) for v in bbox_min],
        "bbox_max": [round(float(v), 5) for v in bbox_max],
        "root_velocity_mean": round(float(velocity_norm.mean()), 6) if velocity_norm.size else 0.0,
        "root_velocity_max": round(float(velocity_norm.max()), 6) if velocity_norm.size else 0.0,
        "ground_penetration_ratio": round(ground_penetration_ratio, 6),
        "status": "passed" if finite and frame_count > 0 else "failed",
    }
    if source_positions is not None:
        src = np.asarray(source_positions, dtype=np.float32)
        if src.shape == pos.shape:
            delta = np.linalg.norm(src - pos, axis=-1)
            report["source_target_position_error_mean"] = round(float(delta.mean()), 6)
            report["source_target_position_error_max"] = round(float(delta.max()), 6)
    return report
