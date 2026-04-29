from __future__ import annotations

import numpy as np
import pytest

from virea.data.registry import DatasetRegistry
from virea.motion.canonical import pack_sequence
from virea.motion.codecs import SUSU_BODY_NAMES
from virea.motion.skeleton import (
    DEFAULT_REST_OFFSETS,
    FK_BONES,
    FK_INDEX,
    control_rest_alignment_audit,
    forward_kinematics_from_sequence,
    target_rest_offsets_map,
)
from virea.pipelines.processed_preview import ProcessedPreviewPipeline
from virea.pipelines.raw_preview import RawPreviewPipeline


def _long_edges(payload) -> list[tuple[int, int, float]]:
    long = []
    for a, b in payload.edges:
        distance = np.linalg.norm(payload.positions[:, a] - payload.positions[:, b], axis=1)
        median = float(np.median(distance))
        if median > 0.95:
            long.append((a, b, median))
    return long


def _assert_finite_payload(payload) -> None:
    assert payload.positions.ndim == 3
    assert payload.positions.shape[0] > 0
    assert payload.positions.shape[2] == 3
    assert np.isfinite(payload.positions).all()
    if "hips" in payload.joint_names:
        hips0 = payload.positions[0, payload.joint_names.index("hips")]
        assert float(np.linalg.norm(hips0)) <= 1e-4
    assert _long_edges(payload) == []


def _assert_processed_is_true_vrm_fk(payload) -> None:
    assert payload.joint_names == FK_BONES
    assert payload.motion is not None
    motion = payload.motion
    sequence = pack_sequence(
        root_translation=np.asarray(motion["root_translation"], dtype=np.float32),
        root_rotation_xyzw=np.asarray(motion["root_rotation"], dtype=np.float32),
        core_quats_xyzw=np.asarray(motion["core_quaternions"], dtype=np.float32),
        hand_quats_xyzw=np.asarray(motion["hand_quaternions"], dtype=np.float32),
    )
    fk_positions = forward_kinematics_from_sequence(sequence)
    error_mm = float(np.max(np.linalg.norm(fk_positions - payload.positions, axis=2)) * 1000.0)
    assert error_mm <= 0.02
    edge_std_mm = [
        float(np.std(np.linalg.norm(payload.positions[:, a] - payload.positions[:, b], axis=1)) * 1000.0)
        for a, b in payload.edges
    ]
    assert max(edge_std_mm, default=0.0) <= 0.02


def _max_foot_above_head(payload) -> float:
    head = payload.positions[:, FK_INDEX["head"], 1]
    feet = np.maximum(payload.positions[:, FK_INDEX["leftFoot"], 1], payload.positions[:, FK_INDEX["rightFoot"], 1])
    return float(np.max(feet - head))


def _mean_delta(payload, parent: str, child: str) -> np.ndarray:
    names = payload.joint_names
    return np.mean(
        payload.positions[:, names.index(child)] - payload.positions[:, names.index(parent)],
        axis=0,
    )


@pytest.mark.parametrize("dataset", ["amass", "babel", "beat", "grab", "humanml3d", "motionx", "susuinteracts"])
def test_processed_preview_is_vrm_fk_not_a_raw_copy(dataset: str) -> None:
    registry = DatasetRegistry.default(data_source="full")
    adapter = registry.adapter(dataset)
    if not adapter.exists():
        pytest.skip(f"raw root not available for {dataset}")
    samples = adapter.discover(limit=500)
    if not samples:
        pytest.skip(f"no samples found for {dataset}")

    selected = samples[0].sample_id
    if dataset == "susuinteracts":
        selected = next((sample.sample_id for sample in samples if "chonglu" in sample.sample_id), selected)

    raw = RawPreviewPipeline(registry).preview(dataset, selected, max_frames=32)
    processed = ProcessedPreviewPipeline(registry).preview(dataset, selected, max_frames=32)

    _assert_finite_payload(raw)
    _assert_finite_payload(processed)
    _assert_processed_is_true_vrm_fk(processed)
    assert processed.joint_names != raw.joint_names or processed.positions.shape != raw.positions.shape
    head_delta = _mean_delta(processed, "hips", "head")
    assert head_delta[1] > abs(head_delta[0])
    assert head_delta[1] > abs(head_delta[2])


def test_susu_retarget_maya_uses_safe_body_order_and_no_foot_flip() -> None:
    registry = DatasetRegistry.default(data_source="full")
    adapter = registry.adapter("susuinteracts")
    assert adapter._profile_for("fbx_to_json_data_susu_retarget_maya/example", has_positions=True)[1] == "susu_retarget_maya_6d_body_hands"
    assert adapter._profile_for("fbx_to_json_data_susu_chonglu/example", has_positions=False)[1] == "susu_chonglu_6d_body_hands_cm"
    samples = adapter.discover(limit=500)
    selected = next(sample.sample_id for sample in samples if "retarget_maya" in sample.sample_id)

    raw = RawPreviewPipeline(registry).preview("susuinteracts", selected, max_frames=32)
    processed = ProcessedPreviewPipeline(registry).preview("susuinteracts", selected, max_frames=32)

    assert SUSU_BODY_NAMES[20:25] == ["clavicle_r", "upperarm_r", "lowerarm_r", "hand_l", "hand_r"]
    _assert_finite_payload(raw)
    _assert_finite_payload(processed)
    _assert_processed_is_true_vrm_fk(processed)
    assert _max_foot_above_head(processed) < 0.05
    assert processed.metadata["root_translation"] == "absolute_xzy_zeroed_auto_units"
    assert processed.metadata["rotation_space"] == "global_6d_converted_to_parent_local_quaternions"
    hips = raw.positions[:, raw.joint_names.index("hips")]
    root_steps = np.linalg.norm(np.diff(hips, axis=0), axis=1)
    assert float(np.max(root_steps)) < 0.05
    names = raw.joint_names
    hips = raw.positions[:, names.index("hips")]
    left_hand = raw.positions[:, names.index("leftHand")] - hips
    right_hand = raw.positions[:, names.index("rightHand")] - hips
    left_upper_arm = raw.positions[:, names.index("leftUpperArm")] - hips
    right_upper_arm = raw.positions[:, names.index("rightUpperArm")] - hips
    assert float(np.median(left_hand[:, 0] - right_hand[:, 0])) > 0.25
    assert float(np.median(left_upper_arm[:, 0] - right_upper_arm[:, 0])) > 0.05


def test_processed_target_rest_comes_from_real_vrm_control_template() -> None:
    audit = control_rest_alignment_audit()
    assert audit["passed"]
    assert audit["source"]["mode"] == "vrm_control_rest_template"
    assert audit["source"]["inspected_vrm_count"] >= 1
    assert audit["left_right_axis_passed"]
    assert audit["head_above_hips_passed"]

    target_offsets = target_rest_offsets_map()
    assert target_offsets["leftUpperArm"] != DEFAULT_REST_OFFSETS["leftUpperArm"]

    registry = DatasetRegistry.default(data_source="demo")
    adapter = registry.adapter("amass")
    samples = adapter.discover(limit=1)
    assert samples
    processed = ProcessedPreviewPipeline(registry).preview("amass", samples[0].sample_id, max_frames=4)
    assert processed.motion["rest_source"]["mode"] == "vrm_control_rest_template"
    assert processed.motion["rest_offsets"]["leftUpperArm"] == target_offsets["leftUpperArm"]
