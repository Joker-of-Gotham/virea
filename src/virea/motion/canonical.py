from __future__ import annotations

import numpy as np

ROOT_DIM = 7

CORE_BONES = [
    "spine",
    "chest",
    "upperChest",
    "neck",
    "head",
    "leftShoulder",
    "leftUpperArm",
    "leftLowerArm",
    "leftHand",
    "rightShoulder",
    "rightUpperArm",
    "rightLowerArm",
    "rightHand",
    "leftUpperLeg",
    "leftLowerLeg",
    "leftFoot",
    "leftToes",
    "rightUpperLeg",
    "rightLowerLeg",
    "rightFoot",
    "rightToes",
]

HAND_BONES = [
    "leftThumbProximal",
    "leftThumbIntermediate",
    "leftThumbDistal",
    "leftIndexProximal",
    "leftIndexIntermediate",
    "leftIndexDistal",
    "leftMiddleProximal",
    "leftMiddleIntermediate",
    "leftMiddleDistal",
    "leftRingProximal",
    "leftRingIntermediate",
    "leftRingDistal",
    "leftLittleProximal",
    "leftLittleIntermediate",
    "leftLittleDistal",
    "rightThumbProximal",
    "rightThumbIntermediate",
    "rightThumbDistal",
    "rightIndexProximal",
    "rightIndexIntermediate",
    "rightIndexDistal",
    "rightMiddleProximal",
    "rightMiddleIntermediate",
    "rightMiddleDistal",
    "rightRingProximal",
    "rightRingIntermediate",
    "rightRingDistal",
    "rightLittleProximal",
    "rightLittleIntermediate",
    "rightLittleDistal",
]

CORE_INDEX = {name: idx for idx, name in enumerate(CORE_BONES)}
HAND_INDEX = {name: idx for idx, name in enumerate(HAND_BONES)}
POSE_BONES = [*CORE_BONES, *HAND_BONES]
FRAME_DIM = ROOT_DIM + len(CORE_BONES) * 4 + len(HAND_BONES) * 4

CANONICAL_TO_VRM_BONE_NAME = {
    "leftThumbProximal": "leftThumbMetacarpal",
    "leftThumbIntermediate": "leftThumbProximal",
    "leftThumbDistal": "leftThumbDistal",
    "rightThumbProximal": "rightThumbMetacarpal",
    "rightThumbIntermediate": "rightThumbProximal",
    "rightThumbDistal": "rightThumbDistal",
}


def identity_quats(frame_count: int, joint_count: int) -> np.ndarray:
    quats = np.zeros((frame_count, joint_count, 4), dtype=np.float32)
    quats[..., 3] = 1.0
    return quats


def pack_sequence(
    root_translation: np.ndarray,
    root_rotation_xyzw: np.ndarray | None = None,
    core_quats_xyzw: np.ndarray | None = None,
    hand_quats_xyzw: np.ndarray | None = None,
) -> np.ndarray:
    root_translation = np.asarray(root_translation, dtype=np.float32)
    frame_count = root_translation.shape[0]
    if root_rotation_xyzw is None:
        root_rotation_xyzw = identity_quats(frame_count, 1)[:, 0]
    if core_quats_xyzw is None:
        core_quats_xyzw = identity_quats(frame_count, len(CORE_BONES))
    if hand_quats_xyzw is None:
        hand_quats_xyzw = identity_quats(frame_count, len(HAND_BONES))
    return np.concatenate(
        [
            root_translation,
            np.asarray(root_rotation_xyzw, dtype=np.float32),
            np.asarray(core_quats_xyzw, dtype=np.float32).reshape(frame_count, -1),
            np.asarray(hand_quats_xyzw, dtype=np.float32).reshape(frame_count, -1),
        ],
        axis=-1,
    ).astype(np.float32)


def unpack_sequence(sequence: np.ndarray) -> dict[str, np.ndarray]:
    seq = np.asarray(sequence, dtype=np.float32)
    if seq.ndim != 2 or seq.shape[1] != FRAME_DIM:
        raise ValueError(f"expected canonical sequence shape (T, {FRAME_DIM}), got {seq.shape}")
    core_start = ROOT_DIM
    core_stop = core_start + len(CORE_BONES) * 4
    return {
        "root_translation": seq[:, 0:3],
        "root_rotation_xyzw": seq[:, 3:7],
        "core_quats_xyzw": seq[:, core_start:core_stop].reshape(seq.shape[0], len(CORE_BONES), 4),
        "hand_quats_xyzw": seq[:, core_stop:].reshape(seq.shape[0], len(HAND_BONES), 4),
    }
