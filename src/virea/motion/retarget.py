from __future__ import annotations

from typing import Any

import numpy as np

from virea.motion.canonical import CORE_BONES, CORE_INDEX, HAND_BONES, HAND_INDEX, identity_quats, pack_sequence
from virea.motion.rotation import (
    normalize_quat_xyzw,
    quat_apply_xyzw,
    quat_from_two_vectors_xyzw,
    quat_inverse_xyzw,
    quat_multiply_xyzw,
)
from virea.motion.skeleton import (
    BODY_BONES,
    BODY_INDEX,
    CANONICAL_PARENT,
    DEFAULT_REST_OFFSETS,
    FK_BONES,
    forward_kinematics,
    forward_kinematics_from_sequence,
    target_rest_offsets_map,
)


STABLE_SCALE_CHAINS = (
    ("spine", "chest", "upperChest", "neck", "head"),
    ("leftUpperLeg", "leftLowerLeg", "leftFoot"),
    ("rightUpperLeg", "rightLowerLeg", "rightFoot"),
    ("leftUpperArm", "leftLowerArm", "leftHand"),
    ("rightUpperArm", "rightLowerArm", "rightHand"),
)

PRIMARY_CHILD = {
    "hips": "spine",
    "spine": "chest",
    "chest": "upperChest",
    "upperChest": "neck",
    "neck": "head",
    "leftShoulder": "leftUpperArm",
    "leftUpperArm": "leftLowerArm",
    "leftLowerArm": "leftHand",
    "rightShoulder": "rightUpperArm",
    "rightUpperArm": "rightLowerArm",
    "rightLowerArm": "rightHand",
    "leftUpperLeg": "leftLowerLeg",
    "leftLowerLeg": "leftFoot",
    "leftFoot": "leftToes",
    "rightUpperLeg": "rightLowerLeg",
    "rightLowerLeg": "rightFoot",
    "rightFoot": "rightToes",
    "leftThumbProximal": "leftThumbIntermediate",
    "leftThumbIntermediate": "leftThumbDistal",
    "leftIndexProximal": "leftIndexIntermediate",
    "leftIndexIntermediate": "leftIndexDistal",
    "leftMiddleProximal": "leftMiddleIntermediate",
    "leftMiddleIntermediate": "leftMiddleDistal",
    "leftRingProximal": "leftRingIntermediate",
    "leftRingIntermediate": "leftRingDistal",
    "leftLittleProximal": "leftLittleIntermediate",
    "leftLittleIntermediate": "leftLittleDistal",
    "rightThumbProximal": "rightThumbIntermediate",
    "rightThumbIntermediate": "rightThumbDistal",
    "rightIndexProximal": "rightIndexIntermediate",
    "rightIndexIntermediate": "rightIndexDistal",
    "rightMiddleProximal": "rightMiddleIntermediate",
    "rightMiddleIntermediate": "rightMiddleDistal",
    "rightRingProximal": "rightRingIntermediate",
    "rightRingIntermediate": "rightRingDistal",
    "rightLittleProximal": "rightLittleIntermediate",
    "rightLittleIntermediate": "rightLittleDistal",
}

WORLD_UPPER_BONES = ("head", "neck", "upperChest", "chest")
WORLD_LOWER_BONES = ("leftFoot", "rightFoot", "leftToes", "rightToes")
WORLD_LEFT_RIGHT_PAIRS = (
    ("leftUpperLeg", "rightUpperLeg"),
    ("leftShoulder", "rightShoulder"),
    ("leftHand", "rightHand"),
    ("leftFoot", "rightFoot"),
)


def _rest_offset(bone_name: str, offsets: dict[str, list[float] | np.ndarray] | None = None) -> np.ndarray:
    target_offsets = target_rest_offsets_map()
    source = offsets if offsets is not None else target_offsets
    return np.asarray(source.get(bone_name, target_offsets.get(bone_name, DEFAULT_REST_OFFSETS.get(bone_name, [0.0, 0.0, 0.0]))), dtype=np.float32)


def _target_scale_from_rest_offsets(source_rest_offsets: dict[str, list[float] | np.ndarray]) -> float:
    target_total = 0.0
    source_total = 0.0
    for chain in STABLE_SCALE_CHAINS:
        for bone_name in chain:
            target_total += float(np.linalg.norm(_rest_offset(bone_name)))
            source_total += float(np.linalg.norm(_rest_offset(bone_name, source_rest_offsets)))
    return 1.0 if source_total < 1e-6 else float(target_total / source_total)


def _target_scale_from_positions(body_positions: np.ndarray) -> float:
    positions = np.asarray(body_positions, dtype=np.float32)
    target_total = 0.0
    source_total = 0.0
    frame = positions[0]
    for chain in STABLE_SCALE_CHAINS:
        parent = "hips"
        for bone_name in chain:
            if bone_name not in BODY_INDEX or parent not in BODY_INDEX:
                parent = bone_name
                continue
            source_total += float(np.linalg.norm(frame[BODY_INDEX[bone_name]] - frame[BODY_INDEX[parent]]))
            target_total += float(np.linalg.norm(_rest_offset(bone_name)))
            parent = bone_name
    return 1.0 if source_total < 1e-6 else float(target_total / source_total)


def _corrections_from_rest_offsets(source_rest_offsets: dict[str, list[float] | np.ndarray], bones: list[str]) -> dict[str, np.ndarray]:
    corrections: dict[str, np.ndarray] = {}
    for bone_name in ["hips", *bones]:
        child_name = PRIMARY_CHILD.get(bone_name)
        if not child_name:
            continue
        source_vec = _rest_offset(child_name, source_rest_offsets)
        target_vec = _rest_offset(child_name)
        if np.linalg.norm(source_vec) < 1e-6 or np.linalg.norm(target_vec) < 1e-6:
            continue
        corrections[bone_name] = quat_from_two_vectors_xyzw(target_vec, source_vec)
    return corrections


def _broadcast_quat(quat: np.ndarray, frame_count: int) -> np.ndarray:
    return np.broadcast_to(np.asarray(quat, dtype=np.float32).reshape(1, 4), (frame_count, 4)).copy()


def retarget_named_quats_to_vrm(
    root_translation: np.ndarray,
    root_rotation_xyzw: np.ndarray,
    local_quats_by_name: dict[str, np.ndarray],
    source_body_rest_offsets: dict[str, list[float] | np.ndarray],
    hand_quats_by_name: dict[str, np.ndarray] | None = None,
    source_hand_rest_offsets: dict[str, list[float] | np.ndarray] | None = None,
    normalize_world: bool = True,
) -> dict[str, Any]:
    frame_count = int(np.asarray(root_translation).shape[0])
    scale = _target_scale_from_rest_offsets(source_body_rest_offsets)
    target_root_translation = np.asarray(root_translation, dtype=np.float32) * np.float32(scale)
    target_root_translation = target_root_translation - target_root_translation[:1]
    source_root_rotation = normalize_quat_xyzw(root_rotation_xyzw)

    source_positions = forward_kinematics(
        root_translation=target_root_translation,
        root_rotation_xyzw=source_root_rotation,
        local_quats=local_quats_by_name,
        rest_offsets=source_body_rest_offsets,
        joint_names=BODY_BONES,
    )
    basis: dict[str, Any] | None = None
    if normalize_world:
        basis = infer_clip_world_basis(source_positions)
        basis_matrix = basis["rotation_matrix"]
        basis_quat = basis["rotation_xyzw"]
        target_root_translation = rotate_positions_by_matrix(target_root_translation[:, None, :], basis_matrix)[:, 0]
        source_positions = rotate_positions_by_matrix(source_positions, basis_matrix)
        source_root_rotation = quat_multiply_xyzw(_broadcast_quat(basis_quat, frame_count), source_root_rotation)

    body_corrections = _corrections_from_rest_offsets(source_body_rest_offsets, CORE_BONES)
    root_rotation = source_root_rotation.copy()
    if "hips" in body_corrections:
        root_rotation = quat_multiply_xyzw(root_rotation, _broadcast_quat(body_corrections["hips"], frame_count))

    core = identity_quats(frame_count, len(CORE_BONES))
    for bone_name in CORE_BONES:
        source_quat = local_quats_by_name.get(bone_name)
        if source_quat is None:
            continue
        mapped = normalize_quat_xyzw(source_quat)
        parent_name = CANONICAL_PARENT.get(bone_name, "hips")
        parent_correction = body_corrections.get(parent_name)
        if parent_correction is not None:
            mapped = quat_multiply_xyzw(_broadcast_quat(quat_inverse_xyzw(parent_correction), frame_count), mapped)
        correction = body_corrections.get(bone_name)
        if correction is not None:
            mapped = quat_multiply_xyzw(mapped, _broadcast_quat(correction, frame_count))
        core[:, CORE_INDEX[bone_name]] = normalize_quat_xyzw(mapped)

    hand = identity_quats(frame_count, len(HAND_BONES))
    if hand_quats_by_name:
        hand_corrections = _corrections_from_rest_offsets(source_hand_rest_offsets or DEFAULT_REST_OFFSETS, HAND_BONES)
        all_corrections = {**body_corrections, **hand_corrections}
        for bone_name, source_quat in hand_quats_by_name.items():
            if bone_name not in HAND_INDEX:
                continue
            mapped = normalize_quat_xyzw(source_quat)
            parent_name = CANONICAL_PARENT.get(bone_name, "hips")
            parent_correction = all_corrections.get(parent_name)
            if parent_correction is not None:
                mapped = quat_multiply_xyzw(_broadcast_quat(quat_inverse_xyzw(parent_correction), frame_count), mapped)
            correction = hand_corrections.get(bone_name)
            if correction is not None:
                mapped = quat_multiply_xyzw(mapped, _broadcast_quat(correction, frame_count))
            hand[:, HAND_INDEX[bone_name]] = normalize_quat_xyzw(mapped)

    sequence = pack_sequence(
        root_translation=target_root_translation,
        root_rotation_xyzw=root_rotation,
        core_quats_xyzw=core,
        hand_quats_xyzw=hand,
    )
    return {
        "sequence": sequence,
        "positions": forward_kinematics_from_sequence(sequence),
        "source_positions": source_positions,
        "scale": float(scale),
        "mode": "direct_local_quaternion_retarget",
        "world_basis": {key: value for key, value in (basis or {}).items() if key not in {"rotation_matrix", "rotation_xyzw"}},
    }


def _normalize_vec3(value: np.ndarray | list[float] | tuple[float, ...] | None) -> np.ndarray | None:
    if value is None:
        return None
    vec = np.asarray(value, dtype=np.float64).reshape(-1)
    if vec.shape[0] < 3:
        return None
    norm = float(np.linalg.norm(vec[:3]))
    if not np.isfinite(norm) or norm < 1e-8:
        return None
    return (vec[:3] / norm).astype(np.float64)


def _project_away_axis(vector: np.ndarray, axis: np.ndarray) -> np.ndarray:
    axis_n = _normalize_vec3(axis)
    if axis_n is None:
        return vector.astype(np.float64)
    return vector - float(np.dot(vector, axis_n)) * axis_n


def _quat_from_rotation_matrix(matrix: np.ndarray) -> np.ndarray:
    m = np.asarray(matrix, dtype=np.float32)
    q = np.zeros(4, dtype=np.float32)
    trace = float(m[0, 0] + m[1, 1] + m[2, 2])
    if trace > 0.0:
        scale = np.sqrt(trace + 1.0) * 2.0
        q[:] = [(m[2, 1] - m[1, 2]) / scale, (m[0, 2] - m[2, 0]) / scale, (m[1, 0] - m[0, 1]) / scale, 0.25 * scale]
    elif m[0, 0] > m[1, 1] and m[0, 0] > m[2, 2]:
        scale = np.sqrt(1.0 + m[0, 0] - m[1, 1] - m[2, 2]) * 2.0
        q[:] = [0.25 * scale, (m[0, 1] + m[1, 0]) / scale, (m[0, 2] + m[2, 0]) / scale, (m[2, 1] - m[1, 2]) / scale]
    elif m[1, 1] > m[2, 2]:
        scale = np.sqrt(1.0 + m[1, 1] - m[0, 0] - m[2, 2]) * 2.0
        q[:] = [(m[0, 1] + m[1, 0]) / scale, 0.25 * scale, (m[1, 2] + m[2, 1]) / scale, (m[0, 2] - m[2, 0]) / scale]
    else:
        scale = np.sqrt(1.0 + m[2, 2] - m[0, 0] - m[1, 1]) * 2.0
        q[:] = [(m[0, 2] + m[2, 0]) / scale, (m[1, 2] + m[2, 1]) / scale, 0.25 * scale, (m[1, 0] - m[0, 1]) / scale]
    return normalize_quat_xyzw(q)


def infer_clip_world_basis(source_positions: np.ndarray) -> dict[str, Any]:
    pos = np.asarray(source_positions, dtype=np.float64)
    upper = pos[:, [BODY_INDEX[name] for name in WORLD_UPPER_BONES]].mean(axis=1)
    lower = pos[:, [BODY_INDEX[name] for name in WORLD_LOWER_BONES]].mean(axis=1)
    upper_minus_lower = upper - lower
    anchor_frame = int(np.argmax(np.max(np.abs(upper_minus_lower), axis=1)))
    axis_idx = int(np.argmax(np.abs(upper_minus_lower[anchor_frame])))
    axis_sign = 1.0 if float(upper_minus_lower[anchor_frame, axis_idx]) >= 0.0 else -1.0

    up_axis = np.zeros(3, dtype=np.float64)
    up_axis[axis_idx] = axis_sign
    left_candidates = []
    for left_name, right_name in WORLD_LEFT_RIGHT_PAIRS:
        delta = pos[anchor_frame, BODY_INDEX[left_name]] - pos[anchor_frame, BODY_INDEX[right_name]]
        projected = _project_away_axis(delta, up_axis)
        normalized = _normalize_vec3(projected)
        if normalized is not None:
            left_candidates.append(normalized)
    left_reference = _normalize_vec3(np.sum(left_candidates, axis=0)) if left_candidates else None
    toe_forward = (
        (pos[anchor_frame, BODY_INDEX["leftToes"]] - pos[anchor_frame, BODY_INDEX["leftFoot"]])
        + (pos[anchor_frame, BODY_INDEX["rightToes"]] - pos[anchor_frame, BODY_INDEX["rightFoot"]])
    )
    toe_forward = _project_away_axis(toe_forward, up_axis)
    trajectory_forward = _project_away_axis(pos[-1, BODY_INDEX["hips"]] - pos[0, BODY_INDEX["hips"]], up_axis)
    torso_forward = _project_away_axis(upper[anchor_frame] - pos[anchor_frame, BODY_INDEX["hips"]], up_axis)
    forward_reference = _normalize_vec3(toe_forward)
    if forward_reference is None:
        forward_reference = _normalize_vec3(trajectory_forward)
    if forward_reference is None and left_reference is not None:
        forward_reference = _normalize_vec3(np.cross(left_reference, up_axis))
    if forward_reference is None:
        forward_reference = _normalize_vec3(torso_forward)
    if forward_reference is None:
        forward_reference = np.array([0.0, 0.0, 1.0], dtype=np.float64)
    left_axis = _normalize_vec3(np.cross(up_axis, forward_reference))
    if left_axis is None:
        left_axis = left_reference if left_reference is not None else np.array([1.0, 0.0, 0.0], dtype=np.float64)
    if left_reference is not None and float(np.dot(left_axis, left_reference)) < 0.0:
        left_axis = -left_axis
    forward_axis = _normalize_vec3(np.cross(left_axis, up_axis))
    if forward_axis is None:
        forward_axis = np.array([0.0, 0.0, 1.0], dtype=np.float64)
    matrix = np.column_stack([left_axis, up_axis, forward_axis]).T.astype(np.float32)
    return {
        "rotation_matrix": matrix,
        "rotation_xyzw": _quat_from_rotation_matrix(matrix),
        "anchor_frame": anchor_frame,
        "detected_up_source_axis": f"{'+' if axis_sign >= 0.0 else '-'}{'xyz'[axis_idx]}",
    }


def rotate_positions_by_matrix(positions: np.ndarray, rotation_matrix: np.ndarray) -> np.ndarray:
    return np.einsum("ij,...j->...i", np.asarray(rotation_matrix, dtype=np.float32), np.asarray(positions, dtype=np.float32)).astype(np.float32)


def fit_positions_to_vrm(body_positions: np.ndarray, normalize_world: bool = True) -> dict[str, Any]:
    source_positions = np.asarray(body_positions, dtype=np.float32)
    basis: dict[str, Any] | None = None
    if normalize_world and source_positions.shape[1] >= len(BODY_BONES):
        basis = infer_clip_world_basis(source_positions)
        working = rotate_positions_by_matrix(source_positions, basis["rotation_matrix"])
    else:
        working = source_positions.copy()

    scale = _target_scale_from_positions(working)
    working = working * np.float32(scale)
    root_translation = working[:, BODY_INDEX["hips"]].copy()
    root_translation = root_translation - root_translation[:1]
    centered = working.copy()
    centered -= working[:1, BODY_INDEX["hips"]].reshape(1, 1, 3)
    centered[:, BODY_INDEX["hips"]] = root_translation

    frame_count = centered.shape[0]
    root_rotation = identity_quats(frame_count, 1)[:, 0]
    core = identity_quats(frame_count, len(CORE_BONES))
    world_rotations: dict[str, np.ndarray] = {"hips": root_rotation}
    for bone_name in CORE_BONES:
        child_name = PRIMARY_CHILD.get(bone_name)
        if child_name not in BODY_INDEX or bone_name not in BODY_INDEX:
            world_rotations[bone_name] = world_rotations.get(CANONICAL_PARENT.get(bone_name, "hips"), root_rotation)
            continue
        parent_name = CANONICAL_PARENT.get(bone_name, "hips")
        parent_world = world_rotations[parent_name]
        target_child_offset = _rest_offset(child_name)
        output = identity_quats(frame_count, 1)[:, 0]
        if np.linalg.norm(target_child_offset) >= 1e-6:
            for frame_idx in range(frame_count):
                desired_world = centered[frame_idx, BODY_INDEX[child_name]] - centered[frame_idx, BODY_INDEX[bone_name]]
                if np.linalg.norm(desired_world) < 1e-6:
                    continue
                desired_local = quat_apply_xyzw(quat_inverse_xyzw(parent_world[frame_idx]), desired_world)
                output[frame_idx] = quat_from_two_vectors_xyzw(target_child_offset, desired_local)
        core[:, CORE_INDEX[bone_name]] = normalize_quat_xyzw(output)
        world_rotations[bone_name] = quat_multiply_xyzw(parent_world, output)

    sequence = pack_sequence(root_translation=root_translation, root_rotation_xyzw=root_rotation, core_quats_xyzw=core)
    return {
        "sequence": sequence,
        "positions": forward_kinematics_from_sequence(sequence),
        "source_positions": centered.astype(np.float32),
        "scale": float(scale),
        "mode": "position_fit_to_vrm",
        "world_basis": {key: value for key, value in (basis or {}).items() if key not in {"rotation_matrix", "rotation_xyzw"}},
    }


def body_positions_from_fk_positions(positions: np.ndarray, joint_names: list[str]) -> np.ndarray:
    index = {name: idx for idx, name in enumerate(joint_names)}
    output = np.zeros((positions.shape[0], len(BODY_BONES), 3), dtype=np.float32)
    for name in BODY_BONES:
        if name in index:
            output[:, BODY_INDEX[name]] = positions[:, index[name]]
    return output
