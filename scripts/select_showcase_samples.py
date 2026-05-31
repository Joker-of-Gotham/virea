from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def _score_quality(meta: dict[str, Any]) -> float:
    quality = meta.get("quality") or {}
    direction = quality.get("retarget_direction_error") or {}
    velocity = quality.get("velocity") or {}
    ground = quality.get("ground_contact") or {}
    symmetry = quality.get("symmetry") or {}
    frames = int(quality.get("frame_count") or meta.get("time", {}).get("num_frames") or 0)

    score = 0.0
    score += float(direction.get("overall_max_rad") or 0.0) * 1000.0
    score += float(direction.get("overall_mean_rad") or 0.0) * 400.0
    score += float(ground.get("penetrating_ratio") or 0.0) * 10.0
    score += max(0.0, float(ground.get("floating_ratio") or 0.0) - 0.75) * 2.0
    score += int(velocity.get("jittery_joints") or 0) * 2.0
    score += float(symmetry.get("max_asymmetry") or 0.0) * 0.15
    if frames < 48:
        score += 100.0
    return score


def select_samples(metadata_root: Path, per_dataset: int) -> dict[str, list[dict[str, Any]]]:
    output: dict[str, list[dict[str, Any]]] = {}
    for dataset_dir in sorted(metadata_root.iterdir()):
        if not dataset_dir.is_dir():
            continue
        rows: list[dict[str, Any]] = []
        for path in dataset_dir.glob("*.json"):
            meta = json.loads(path.read_text(encoding="utf-8"))
            quality = meta.get("quality") or {}
            if quality.get("status") != "passed" or not quality.get("finite", False):
                continue
            source = meta.get("source") or {}
            time = meta.get("time") or {}
            direction = quality.get("retarget_direction_error") or {}
            velocity = quality.get("velocity") or {}
            ground = quality.get("ground_contact") or {}
            symmetry = quality.get("symmetry") or {}
            rows.append(
                {
                    "dataset": dataset_dir.name,
                    "sample_id": source.get("source_id", ""),
                    "motion_uid": meta.get("motion_uid", ""),
                    "fps": time.get("fps"),
                    "frames": int(quality.get("frame_count") or time.get("num_frames") or 0),
                    "duration_sec": time.get("duration_sec"),
                    "score": round(_score_quality(meta), 6),
                    "quality": {
                        "retarget_max_deg": direction.get("overall_max_deg"),
                        "retarget_mean_deg": direction.get("overall_mean_deg"),
                        "jittery_joints": velocity.get("jittery_joints"),
                        "floating_ratio": ground.get("floating_ratio"),
                        "penetrating_ratio": ground.get("penetrating_ratio"),
                        "max_asymmetry": symmetry.get("max_asymmetry"),
                    },
                }
            )
        rows.sort(key=lambda row: (row["score"], -row["frames"], row["sample_id"]))
        output[dataset_dir.name] = rows[:per_dataset]
    return output


def main() -> None:
    parser = argparse.ArgumentParser(description="Select high-quality VIREA showcase clips.")
    parser.add_argument(
        "--metadata-root",
        type=Path,
        default=Path("demo/processed/canonical/v0.1.0/metadata"),
    )
    parser.add_argument("--per-dataset", type=int, default=7)
    parser.add_argument("--out", type=Path, default=Path("doc/showcase/showcase-samples.json"))
    args = parser.parse_args()

    selected = select_samples(args.metadata_root, args.per_dataset)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(selected, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    total = sum(len(items) for items in selected.values())
    print(f"selected {total} clips across {len(selected)} datasets -> {args.out}")


if __name__ == "__main__":
    main()
