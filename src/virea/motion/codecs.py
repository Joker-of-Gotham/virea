from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from virea.data.types import RawClip
from virea.motion.canonical import CORE_INDEX, HAND_INDEX, identity_quats, pack_sequence
from virea.motion.retarget import body_positions_from_fk_positions, fit_positions_to_vrm, retarget_named_quats_to_vrm
from virea.motion.snapshot import SourceSnapshot
from virea.motion.source_fk import SUSU_MAYA_AIM_AXES, center_positions_at_root, positions_from_global_rotations, source_fk_from_body_quats, source_offsets_from_globals, source_positions_normalized
from virea.motion.rotation import axis_angle_to_quat_xyzw, quat_inverse_xyzw, quat_multiply_xyzw, sixd_rows_to_quat_xyzw
from virea.motion.skeleton import (
    BODY_BONES,
    BODY_EDGES,
    BODY_INDEX,
    CANONICAL_PARENT,
    CANONICAL_BODY_WITH_ROOT,
    DEFAULT_REST_OFFSETS,
    FK_BONES,
    FK_EDGES,
    forward_kinematics_from_sequence,
)


@dataclass
class CanonicalResult:
    sequence: np.ndarray
    positions: np.ndarray
    joint_names: list[str]
    edges: list[tuple[int, int]]
    metadata: dict[str, Any]
    retarget_source_positions: np.ndarray | None = None


class MotionCodec:
    key = "base"

    def extract_source(self, clip: RawClip) -> SourceSnapshot:
        raise NotImplementedError

    def to_canonical(self, clip: RawClip) -> CanonicalResult:
        raise NotImplementedError


class AxisAngleBody22Codec(MotionCodec):
    key = "axis_angle_body22"

    def __init__(
        self,
        source_rest_offsets: dict[str, list[float]] | None = None,
        source_profile: str = "smplh_body22",
        world_basis: str = "z_up_to_y_up",
    ) -> None:
        self.source_rest_offsets = source_rest_offsets or DEFAULT_REST_OFFSETS
        self.source_profile = source_profile
        self.world_basis = world_basis

    def _body_quats(self, poses: np.ndarray) -> np.ndarray:
        arr = np.asarray(poses, dtype=np.float32)
        if arr.ndim != 2 or arr.shape[1] < 22 * 3:
            raise ValueError(f"expected body axis-angle block with at least 66 dims, got {arr.shape}")
        return axis_angle_to_quat_xyzw(arr[:, : 22 * 3].reshape(arr.shape[0], 22, 3))

    def _pack(self, body_quats: np.ndarray, translation: np.ndarray) -> np.ndarray:
        frame_count = body_quats.shape[0]
        core = identity_quats(frame_count, len(CORE_INDEX))
        for body_index, bone_name in enumerate(CANONICAL_BODY_WITH_ROOT):
            if bone_name == "hips" or bone_name not in CORE_INDEX:
                continue
            core[:, CORE_INDEX[bone_name]] = body_quats[:, body_index]
        return pack_sequence(
            root_translation=translation,
            root_rotation_xyzw=body_quats[:, BODY_INDEX["hips"]],
            core_quats_xyzw=core,
        )

    def to_canonical(self, clip: RawClip) -> CanonicalResult:
        poses = np.asarray(clip.motion["poses"], dtype=np.float32)
        translation = np.asarray(clip.motion.get("translation"), dtype=np.float32)
        if translation.ndim != 2 or translation.shape[0] != poses.shape[0]:
            translation = np.zeros((poses.shape[0], 3), dtype=np.float32)
        body_quats = self._body_quats(poses)
        retarget = retarget_named_quats_to_vrm(
            root_translation=translation,
            root_rotation_xyzw=body_quats[:, BODY_INDEX["hips"]],
            local_quats_by_name={name: body_quats[:, idx] for idx, name in enumerate(BODY_BONES) if name != "hips"},
            source_body_rest_offsets=self.source_rest_offsets,
            world_basis=self.world_basis,
        )
        return CanonicalResult(
            sequence=retarget["sequence"],
            positions=retarget["positions"],
            joint_names=FK_BONES,
            edges=FK_EDGES,
            metadata={
                "codec": self.key,
                "source_profile": self.source_profile,
                "canonical_skeleton": "virea_canonical_v0.1",
                "target_skeleton": "vrm1_humanoid",
                "retarget_mode": retarget["mode"],
                "retarget_scale": retarget["scale"],
                "declared_world_basis": self.world_basis,
                "world_basis": retarget.get("world_basis", {}),
            },
            retarget_source_positions=retarget.get("source_positions"),
        )

    def extract_source(self, clip: RawClip) -> SourceSnapshot:
        poses = np.asarray(clip.motion["poses"], dtype=np.float32)
        translation = np.asarray(clip.motion.get("translation"), dtype=np.float32)
        if translation.ndim != 2 or translation.shape[0] != poses.shape[0]:
            translation = np.zeros((poses.shape[0], 3), dtype=np.float32)
        body_quats = self._body_quats(poses)
        positions, names, edges = source_fk_from_body_quats(
            translation,
            body_quats[:, BODY_INDEX["hips"]],
            {name: body_quats[:, idx] for idx, name in enumerate(BODY_BONES) if name != "hips"},
            self.source_rest_offsets,
            normalize_world=True,
            world_basis=self.world_basis,
        )
        return SourceSnapshot(
            positions=positions,
            joint_names=names,
            edges=edges,
            fps=float(clip.motion.get("fps", clip.sample.fps or 30.0)),
            coordinate_system="world_normalized",
            metadata={"codec": self.key, "source_profile": self.source_profile, "declared_world_basis": self.world_basis},
        )


SMPLX_HAND_INDEX = {
    "leftIndexProximal": 25,
    "leftIndexIntermediate": 26,
    "leftIndexDistal": 27,
    "leftMiddleProximal": 28,
    "leftMiddleIntermediate": 29,
    "leftMiddleDistal": 30,
    "leftLittleProximal": 31,
    "leftLittleIntermediate": 32,
    "leftLittleDistal": 33,
    "leftRingProximal": 34,
    "leftRingIntermediate": 35,
    "leftRingDistal": 36,
    "leftThumbProximal": 37,
    "leftThumbIntermediate": 38,
    "leftThumbDistal": 39,
    "rightIndexProximal": 40,
    "rightIndexIntermediate": 41,
    "rightIndexDistal": 42,
    "rightMiddleProximal": 43,
    "rightMiddleIntermediate": 44,
    "rightMiddleDistal": 45,
    "rightLittleProximal": 46,
    "rightLittleIntermediate": 47,
    "rightLittleDistal": 48,
    "rightRingProximal": 49,
    "rightRingIntermediate": 50,
    "rightRingDistal": 51,
    "rightThumbProximal": 52,
    "rightThumbIntermediate": 53,
    "rightThumbDistal": 54,
}


class SMPLXFullposeCodec(MotionCodec):
    key = "smplx_fullpose"

    def _world_basis_for_clip(self, clip: RawClip) -> str:
        metadata = dict(clip.motion.get("source_metadata", {}))
        if metadata.get("declared_world_basis"):
            return str(metadata["declared_world_basis"])
        if metadata.get("world_basis") and isinstance(metadata["world_basis"], str):
            return str(metadata["world_basis"])
        if clip.sample.dataset == "grab":
            return "z_up_to_y_up"
        return "identity_y_up"

    def to_canonical(self, clip: RawClip) -> CanonicalResult:
        fullpose = np.asarray(clip.motion["fullpose"], dtype=np.float32)
        if fullpose.ndim != 2 or fullpose.shape[1] < 165:
            raise ValueError(f"expected SMPL-X fullpose block with at least 165 dims, got {fullpose.shape}")
        translation = np.asarray(clip.motion.get("translation"), dtype=np.float32)
        if translation.ndim != 2 or translation.shape[0] != fullpose.shape[0]:
            translation = np.zeros((fullpose.shape[0], 3), dtype=np.float32)
        world_basis = self._world_basis_for_clip(clip)
        quats = axis_angle_to_quat_xyzw(fullpose[:, :165].reshape(fullpose.shape[0], 55, 3))
        frame_count = quats.shape[0]
        core = identity_quats(frame_count, len(CORE_INDEX))
        hands = identity_quats(frame_count, len(HAND_INDEX))
        for body_index, bone_name in enumerate(CANONICAL_BODY_WITH_ROOT):
            if bone_name == "hips" or bone_name not in CORE_INDEX:
                continue
            core[:, CORE_INDEX[bone_name]] = quats[:, body_index]
        for bone_name, source_index in SMPLX_HAND_INDEX.items():
            if source_index < quats.shape[1] and bone_name in HAND_INDEX:
                hands[:, HAND_INDEX[bone_name]] = quats[:, source_index]
        retarget = retarget_named_quats_to_vrm(
            root_translation=translation,
            root_rotation_xyzw=quats[:, BODY_INDEX["hips"]],
            local_quats_by_name={name: quats[:, idx] for idx, name in enumerate(BODY_BONES) if name != "hips"},
            source_body_rest_offsets=DEFAULT_REST_OFFSETS,
            hand_quats_by_name={name: hands[:, idx] for idx, name in enumerate(HAND_INDEX)},
            source_hand_rest_offsets=DEFAULT_REST_OFFSETS,
            world_basis=world_basis,
        )
        return CanonicalResult(
            sequence=retarget["sequence"],
            positions=retarget["positions"],
            joint_names=FK_BONES,
            edges=FK_EDGES,
            metadata={
                "codec": self.key,
                "source_profile": "smplx_fullpose55",
                "canonical_skeleton": "virea_canonical_v0.1",
                "target_skeleton": "vrm1_humanoid",
                "retarget_mode": retarget["mode"],
                "retarget_scale": retarget["scale"],
                **dict(clip.motion.get("source_metadata", {})),
                "declared_world_basis": world_basis,
                "world_basis": retarget.get("world_basis", {}),
            },
            retarget_source_positions=retarget.get("source_positions"),
        )

    def extract_source(self, clip: RawClip) -> SourceSnapshot:
        fullpose = np.asarray(clip.motion["fullpose"], dtype=np.float32)
        translation = np.asarray(clip.motion.get("translation"), dtype=np.float32)
        if translation.ndim != 2 or translation.shape[0] != fullpose.shape[0]:
            translation = np.zeros((fullpose.shape[0], 3), dtype=np.float32)
        world_basis = self._world_basis_for_clip(clip)
        quats = axis_angle_to_quat_xyzw(fullpose[:, :165].reshape(fullpose.shape[0], 55, 3))
        positions, names, edges = source_fk_from_body_quats(
            translation,
            quats[:, BODY_INDEX["hips"]],
            {name: quats[:, idx] for idx, name in enumerate(BODY_BONES) if name != "hips"},
            DEFAULT_REST_OFFSETS,
            normalize_world=True,
            world_basis=world_basis,
        )
        return SourceSnapshot(
            positions=positions,
            joint_names=names,
            edges=edges,
            fps=float(clip.motion.get("fps", clip.sample.fps or 30.0)),
            coordinate_system="world_normalized",
            metadata={
                "codec": self.key,
                "source_profile": "smplx_fullpose55",
                "declared_world_basis": world_basis,
                **dict(clip.motion.get("source_metadata", {})),
            },
        )


SMPL24_NAMES = [
    "pelvis",
    "left_hip",
    "right_hip",
    "spine1",
    "left_knee",
    "right_knee",
    "spine2",
    "left_ankle",
    "right_ankle",
    "spine3",
    "left_foot",
    "right_foot",
    "neck",
    "left_collar",
    "right_collar",
    "head",
    "left_shoulder",
    "right_shoulder",
    "left_elbow",
    "right_elbow",
    "left_wrist",
    "right_wrist",
    "left_hand",
    "right_hand",
]

GUOH3D_TO_CANONICAL = {
    "pelvis": "hips",
    "left_hip": "leftUpperLeg",
    "right_hip": "rightUpperLeg",
    "spine1": "spine",
    "left_knee": "leftLowerLeg",
    "right_knee": "rightLowerLeg",
    "spine2": "chest",
    "left_ankle": "leftFoot",
    "right_ankle": "rightFoot",
    "spine3": "upperChest",
    "left_foot": "leftToes",
    "right_foot": "rightToes",
    "neck": "neck",
    "left_collar": "leftShoulder",
    "right_collar": "rightShoulder",
    "head": "head",
    "left_shoulder": "leftUpperArm",
    "right_shoulder": "rightUpperArm",
    "left_elbow": "leftLowerArm",
    "right_elbow": "rightLowerArm",
    "left_wrist": "leftHand",
    "right_wrist": "rightHand",
}


def _canonical_edges_for_names(joint_names: list[str]) -> list[tuple[int, int]]:
    joint_index = {name: index for index, name in enumerate(joint_names)}
    return [
        (joint_index[parent], joint_index[child])
        for child in joint_names
        if child != "hips"
        for parent in [CANONICAL_PARENT.get(child)]
        if parent in joint_index
    ]


class PositionSequenceCodec(MotionCodec):
    key = "position_sequence"

    def __init__(
        self,
        default_joint_names: list[str] | None = None,
        source_profile: str = "position_sequence",
        world_basis: str = "z_up_to_y_up",
    ) -> None:
        self.default_joint_names = default_joint_names or SMPL24_NAMES
        self.source_profile = source_profile
        self.world_basis = world_basis

    def to_canonical(self, clip: RawClip) -> CanonicalResult:
        source_positions = np.asarray(clip.motion["positions"], dtype=np.float32)
        source_names = clip.source_joint_names or self.default_joint_names[: source_positions.shape[1]]
        mapped_names: list[str] = []
        mapped_positions: list[np.ndarray] = []
        seen: set[str] = set()
        for source_index, source_name in enumerate(source_names):
            canonical = GUOH3D_TO_CANONICAL.get(source_name, source_name)
            if canonical in FK_BONES and canonical not in seen:
                mapped_names.append(canonical)
                mapped_positions.append(source_positions[:, source_index])
                seen.add(canonical)
        if mapped_positions:
            target = np.stack(mapped_positions, axis=1).astype(np.float32)
        else:
            mapped_names = ["hips"]
            target = np.zeros((source_positions.shape[0], 1, 3), dtype=np.float32)
        target = target.copy()
        source_edges = _canonical_edges_for_names(mapped_names)
        body_positions = body_positions_from_fk_positions(target, mapped_names)
        retarget = fit_positions_to_vrm(body_positions, world_basis=self.world_basis)
        return CanonicalResult(
            sequence=retarget["sequence"],
            positions=retarget["positions"],
            joint_names=FK_BONES,
            edges=FK_EDGES,
            metadata={
                "codec": self.key,
                "source_profile": self.source_profile,
                "canonical_skeleton": "virea_canonical_v0.1",
                "position_to_rotation": retarget["mode"],
                "position_only_preview": False,
                "source_coordinates_preserved": False,
                "mapped_joint_count": len(mapped_names),
                "unmapped_canonical_joint_count": len(FK_BONES) - len(mapped_names),
                "original_source_joint_count": int(source_positions.shape[1]),
                "source_joint_names": BODY_BONES,
                "source_edges": BODY_EDGES,
                "native_mapped_joint_names": mapped_names,
                "native_mapped_edges": source_edges,
                "retarget_scale": retarget["scale"],
                "declared_world_basis": self.world_basis,
                "world_basis": retarget.get("world_basis", {}),
            },
            retarget_source_positions=retarget.get("source_positions"),
        )

    def extract_source(self, clip: RawClip) -> SourceSnapshot:
        source_positions = np.asarray(clip.motion["positions"], dtype=np.float32)
        source_names = clip.source_joint_names or self.default_joint_names[: source_positions.shape[1]]
        mapped_names: list[str] = []
        mapped_positions: list[np.ndarray] = []
        seen: set[str] = set()
        for source_index, source_name in enumerate(source_names):
            canonical = GUOH3D_TO_CANONICAL.get(source_name, source_name)
            if canonical in BODY_BONES and canonical not in seen:
                mapped_names.append(canonical)
                mapped_positions.append(source_positions[:, source_index])
                seen.add(canonical)
        if mapped_positions:
            body_pos = body_positions_from_fk_positions(
                np.stack(mapped_positions, axis=1).astype(np.float32), mapped_names
            )
            positions = source_positions_normalized(body_pos, BODY_BONES, world_basis=self.world_basis)
        else:
            positions = center_positions_at_root(source_positions.copy())
        return SourceSnapshot(
            positions=positions,
            joint_names=list(BODY_BONES),
            edges=list(BODY_EDGES),
            fps=float(clip.motion.get("fps", clip.sample.fps or 20.0)),
            coordinate_system="world_normalized",
            metadata={"codec": self.key, "source_profile": self.source_profile, "declared_world_basis": self.world_basis},
        )


class HumanML3D263Codec(PositionSequenceCodec):
    key = "humanml3d_263d"

    def __init__(self) -> None:
        super().__init__(default_joint_names=SMPL24_NAMES[:22], source_profile="humanml3d_263d")

    def _decode_positions(self, motion: np.ndarray) -> tuple[np.ndarray, list[str], dict[str, Any]]:
        try:
            tmr_src = os.getenv("VIREA_TMR_SRC")
            if not tmr_src:
                guess = Path(__file__).resolve().parents[4] / "LLM-driven-VRM" / "tmp_repos" / "TMR" / "src"
                tmr_src = str(guess)
            if tmr_src and tmr_src not in sys.path and Path(tmr_src).exists():
                sys.path.insert(0, tmr_src)
            import torch
            from guofeats.motion_representation import guofeats_to_joints
            from joints import JOINT_NAMES

            joints = guofeats_to_joints(torch.as_tensor(motion, dtype=torch.float32)).detach().cpu().numpy().astype(np.float32)
            names = list(JOINT_NAMES["guoh3djoints"])
            return joints, names, {"humanml_decoder": "guofeats_to_joints"}
        except Exception as exc:
            frame_count = motion.shape[0]
            root = np.zeros((frame_count, 3), dtype=np.float32)
            if motion.shape[1] >= 3:
                root[:, [0, 2]] = np.cumsum(motion[:, 0:2], axis=0) * 0.03
            sequence = pack_sequence(root_translation=root)
            fallback = forward_kinematics_from_sequence(sequence)[:, :22]
            return fallback, FK_BONES[:22], {"humanml_decoder": "fallback_rest_pose", "decoder_error": str(exc)}

    def to_canonical(self, clip: RawClip) -> CanonicalResult:
        motion = np.asarray(clip.motion["motion"], dtype=np.float32)
        positions, names, decoder_meta = self._decode_positions(motion)
        position_clip = RawClip(
            sample=clip.sample,
            motion={"positions": positions, "fps": clip.motion.get("fps", 20.0)},
            annotations=clip.annotations,
            source_joint_names=names,
            source_edges=BODY_EDGES,
        )
        result = super().to_canonical(position_clip)
        mapped_names = list(result.metadata.get("source_joint_names", []))
        mapped_edges = [tuple(edge) for edge in result.metadata.get("source_edges", [])]
        result.metadata.update(decoder_meta)
        result.metadata["codec"] = self.key
        result.metadata["native_joint_names"] = names
        result.metadata["source_joint_names"] = mapped_names
        result.metadata["source_edges"] = mapped_edges
        return result

    def extract_source(self, clip: RawClip) -> SourceSnapshot:
        motion = np.asarray(clip.motion["motion"], dtype=np.float32)
        positions, names, decoder_meta = self._decode_positions(motion)
        canonical_names = [GUOH3D_TO_CANONICAL.get(n, n) for n in names]
        body_pos = body_positions_from_fk_positions(
            np.asarray(positions, dtype=np.float32), canonical_names
        )
        normalized = source_positions_normalized(body_pos, BODY_BONES, world_basis=self.world_basis)
        return SourceSnapshot(
            positions=normalized,
            joint_names=list(BODY_BONES),
            edges=list(BODY_EDGES),
            fps=float(clip.motion.get("fps", clip.sample.fps or 20.0)),
            coordinate_system="world_normalized",
            metadata={"codec": self.key, "source_profile": "humanml3d_263d", "declared_world_basis": self.world_basis, **decoder_meta},
        )


SUSU_BODY_NAMES = [
    "pelvis",
    "thigh_r",
    "calf_r",
    "foot_r",
    "ball_r",
    "thigh_l",
    "calf_l",
    "foot_l",
    "ball_l",
    "spine_01",
    "spine_02",
    "spine_03",
    "spine_04",
    "spine_05",
    "neck_01",
    "neck_02",
    "head",
    "clavicle_l",
    "upperarm_l",
    "lowerarm_l",
    "clavicle_r",
    "upperarm_r",
    "lowerarm_r",
    "hand_l",
    "hand_r",
]
SUSU_BODY_TO_CANONICAL = {
    "pelvis": "hips",
    "thigh_l": "leftUpperLeg",
    "calf_l": "leftLowerLeg",
    "foot_l": "leftFoot",
    "ball_l": "leftToes",
    "thigh_r": "rightUpperLeg",
    "calf_r": "rightLowerLeg",
    "foot_r": "rightFoot",
    "ball_r": "rightToes",
    "spine_01": "spine",
    "spine_03": "chest",
    "spine_05": "upperChest",
    "neck_01": "neck",
    "head": "head",
    "clavicle_l": "leftShoulder",
    "upperarm_l": "leftUpperArm",
    "lowerarm_l": "leftLowerArm",
    "hand_l": "leftHand",
    "clavicle_r": "rightShoulder",
    "upperarm_r": "rightUpperArm",
    "lowerarm_r": "rightLowerArm",
    "hand_r": "rightHand",
}
SUSU_SOURCE_NAMES = [*SUSU_BODY_NAMES]
SUSU_SOURCE_EDGES = [
    (0, 1), (1, 2), (2, 3), (3, 4),
    (0, 5), (5, 6), (6, 7), (7, 8),
    (0, 9), (9, 10), (10, 11), (11, 12), (12, 13), (13, 14), (14, 15), (15, 16),
    (13, 17), (17, 18), (18, 19), (19, 23),
    (13, 20), (20, 21), (21, 22), (22, 24),
]


def _susu_hand_map(side: str) -> dict[int, str]:
    prefix = "left" if side == "left" else "right"
    return {
        16: f"{prefix}ThumbProximal",
        17: f"{prefix}ThumbIntermediate",
        18: f"{prefix}ThumbDistal",
        0: f"{prefix}IndexProximal",
        1: f"{prefix}IndexIntermediate",
        2: f"{prefix}IndexDistal",
        4: f"{prefix}MiddleProximal",
        5: f"{prefix}MiddleIntermediate",
        6: f"{prefix}MiddleDistal",
        8: f"{prefix}RingProximal",
        9: f"{prefix}RingIntermediate",
        10: f"{prefix}RingDistal",
        12: f"{prefix}LittleProximal",
        13: f"{prefix}LittleIntermediate",
        14: f"{prefix}LittleDistal",
    }


def _susu_body_global_to_local(
    body_quats: np.ndarray,
) -> tuple[np.ndarray, dict[str, np.ndarray], dict[str, np.ndarray]]:
    frame_count = int(body_quats.shape[0])
    identity = identity_quats(frame_count, 1)[:, 0]
    global_by_name: dict[str, np.ndarray] = {}
    for source_idx, source_name in enumerate(SUSU_BODY_NAMES):
        canonical = SUSU_BODY_TO_CANONICAL.get(source_name)
        if canonical and canonical not in global_by_name and source_idx < body_quats.shape[1]:
            global_by_name[canonical] = body_quats[:, source_idx]

    root_rot = global_by_name.get("hips", identity)
    local_by_name: dict[str, np.ndarray] = {}
    for canonical, global_quat in global_by_name.items():
        if canonical == "hips":
            continue
        parent = CANONICAL_PARENT.get(canonical)
        parent_global = global_by_name.get(parent or "")
        if parent_global is None:
            local_by_name[canonical] = global_quat
        else:
            local_by_name[canonical] = quat_multiply_xyzw(quat_inverse_xyzw(parent_global), global_quat)
    return root_rot, local_by_name, global_by_name


def _susu_hand_global_to_local(
    hand_quats: np.ndarray,
    side: str,
    body_global_by_name: dict[str, np.ndarray],
) -> dict[str, np.ndarray]:
    global_by_name: dict[str, np.ndarray] = {}
    for source_idx, canonical in _susu_hand_map(side).items():
        if source_idx < hand_quats.shape[1] and canonical in HAND_INDEX:
            global_by_name[canonical] = hand_quats[:, source_idx]

    local_by_name: dict[str, np.ndarray] = {}
    for canonical, global_quat in global_by_name.items():
        parent = CANONICAL_PARENT.get(canonical)
        parent_global = global_by_name.get(parent or "")
        if parent_global is None:
            parent_global = body_global_by_name.get(parent or "")
        if parent_global is None:
            local_by_name[canonical] = global_quat
        else:
            local_by_name[canonical] = quat_multiply_xyzw(quat_inverse_xyzw(parent_global), global_quat)
    return local_by_name


@dataclass(frozen=True)
class SuSuProfile:
    name: str
    path_token: str
    position_scale: float
    root_translation_scale: float
    position_world_basis: str
    root_axes: tuple[int, int, int] = (0, 2, 1)
    root_translation_mode: str = "absolute_xzy_zeroed"


SUSU_RETARGET_MAYA_PROFILE = SuSuProfile(
    name="susu_retarget_maya_6d_body_hands",
    path_token="fbx_to_json_data_susu_retarget_maya/",
    position_scale=0.01,
    root_translation_scale=1.0,
    position_world_basis="neg_z_up_to_y_up",
    root_translation_mode="absolute_xzy_zeroed_auto_units",
)
SUSU_CHONGLU_PROFILE = SuSuProfile(
    name="susu_chonglu_6d_body_hands_cm",
    path_token="fbx_to_json_data_susu_chonglu/",
    position_scale=0.01,
    root_translation_scale=0.01,
    position_world_basis="identity_y_up",
    root_translation_mode="absolute_xzy_cm_zeroed",
)
SUSU_PROFILE_BY_CODEC = {
    SUSU_RETARGET_MAYA_PROFILE.name: SUSU_RETARGET_MAYA_PROFILE,
    SUSU_CHONGLU_PROFILE.name: SUSU_CHONGLU_PROFILE,
}
SUSU_CODEC_KEYS = frozenset({"susu_6d_body_hands", *SUSU_PROFILE_BY_CODEC})


class SuSu6DCodec(MotionCodec):
    key = "susu_6d_body_hands"

    def __init__(self, profile: SuSuProfile | None = None) -> None:
        self.profile = profile

    def _select_profile(self, clip: RawClip, has_positions: bool) -> SuSuProfile:
        if self.profile:
            return self.profile
        sample_id = clip.sample.sample_id
        for profile in SUSU_PROFILE_BY_CODEC.values():
            if sample_id.startswith(profile.path_token):
                return profile
        return SUSU_CHONGLU_PROFILE if has_positions else SUSU_RETARGET_MAYA_PROFILE

    def _positions_from_available_data(self, clip: RawClip, profile: SuSuProfile) -> np.ndarray | None:
        positions = clip.motion.get("positions")
        if isinstance(positions, np.ndarray) and positions.ndim == 3:
            return (positions.astype(np.float32) * np.float32(profile.position_scale)).astype(np.float32)
        return None

    def _source_body_positions(self, positions: np.ndarray) -> np.ndarray:
        return positions[:, : min(len(SUSU_SOURCE_NAMES), positions.shape[1])].astype(np.float32)

    def _canonical_body_from_source_positions(self, positions: np.ndarray) -> tuple[np.ndarray, list[str], list[tuple[int, int]]]:
        body_positions = self._source_body_positions(positions)
        mapped_names: list[str] = []
        mapped_positions: list[np.ndarray] = []
        seen: set[str] = set()
        for source_index, source_name in enumerate(SUSU_BODY_NAMES[: body_positions.shape[1]]):
            canonical = SUSU_BODY_TO_CANONICAL.get(source_name)
            if canonical and canonical in FK_BONES and canonical not in seen:
                mapped_names.append(canonical)
                mapped_positions.append(body_positions[:, source_index])
                seen.add(canonical)
        if mapped_positions:
            canonical_positions = np.stack(mapped_positions, axis=1).astype(np.float32)
        else:
            mapped_names = ["hips"]
            canonical_positions = np.zeros((positions.shape[0], 1, 3), dtype=np.float32)
        canonical_positions = canonical_positions.copy()
        return canonical_positions, mapped_names, _canonical_edges_for_names(mapped_names)

    def _root_translation(self, body: np.ndarray, profile: SuSuProfile) -> tuple[np.ndarray, float, str]:
        axes = list(profile.root_axes)
        root = body[:, axes].astype(np.float32)
        unit = "profile"
        scale = float(profile.root_translation_scale)
        if profile.name == SUSU_RETARGET_MAYA_PROFILE.name:
            # Retarget-maya files mix meter-like roots and centimeter FBX exports.
            # The values are absolute roots in the shipped data, not deltas.
            median_height = float(np.nanmedian(np.abs(root[:, 1]))) if root.size else 0.0
            max_abs = float(np.nanmax(np.abs(root))) if root.size else 0.0
            if median_height > 5.0 or max_abs > 20.0:
                scale = 0.01
                unit = "cm"
            else:
                scale = 1.0
                unit = "m"
        root = root * np.float32(scale)
        root = root - root[:1]
        return root.astype(np.float32), scale, unit

    def to_canonical(self, clip: RawClip) -> CanonicalResult:
        body = np.asarray(clip.motion["body"], dtype=np.float32)
        frame_count = body.shape[0]
        profile = self._select_profile(clip, has_positions="positions" in clip.motion)
        available_positions = self._positions_from_available_data(clip, profile)
        root_translation, root_translation_effective_scale, root_translation_unit = self._root_translation(body, profile)
        body_quats = sixd_rows_to_quat_xyzw(body[:, 3:].reshape(frame_count, 25, 6))
        root_rot, local_body_quats, global_body_quats = _susu_body_global_to_local(body_quats)
        core = identity_quats(frame_count, len(CORE_INDEX))
        hand = identity_quats(frame_count, len(HAND_INDEX))
        for canonical, local_quat in local_body_quats.items():
            if canonical in CORE_INDEX:
                core[:, CORE_INDEX[canonical]] = local_quat
        for side_key, map_side in [("left", "left"), ("right", "right")]:
            if side_key not in clip.motion:
                continue
            hand_quats = sixd_rows_to_quat_xyzw(np.asarray(clip.motion[side_key], dtype=np.float32).reshape(frame_count, 20, 6))
            for canonical, local_quat in _susu_hand_global_to_local(hand_quats, map_side, global_body_quats).items():
                hand[:, HAND_INDEX[canonical]] = local_quat
        use_fixed_axes = False
        if available_positions is not None:
            native_positions, native_names, native_edges = self._canonical_body_from_source_positions(available_positions)
            body_positions = body_positions_from_fk_positions(native_positions, native_names)
            retarget = fit_positions_to_vrm(body_positions, world_basis=profile.position_world_basis)
        else:
            fk_positions = positions_from_global_rotations(
                root_translation, global_body_quats,
                fixed_aim_axes=SUSU_MAYA_AIM_AXES if use_fixed_axes else None,
            )
            retarget = fit_positions_to_vrm(fk_positions, world_basis="identity_y_up")
            native_names = list(BODY_BONES)
            native_edges = list(BODY_EDGES)
        return CanonicalResult(
            sequence=retarget["sequence"],
            positions=retarget["positions"],
            joint_names=FK_BONES,
            edges=FK_EDGES,
            metadata={
                "codec": clip.sample.codec_key,
                "source_profile": profile.name,
                "root_translation": profile.root_translation_mode,
                "root_translation_scale": profile.root_translation_scale,
                "root_translation_effective_scale": root_translation_effective_scale,
                "root_translation_unit": root_translation_unit,
                "position_scale": profile.position_scale,
                "declared_world_basis": profile.position_world_basis if available_positions is not None else "identity_y_up",
                "source_positions_available": available_positions is not None,
                "native_mapped_joint_names": native_names,
                "native_mapped_edges": native_edges,
                "retarget_mode": retarget["mode"],
                "retarget_scale": retarget["scale"],
                "world_basis": retarget.get("world_basis", {}),
                "rotation_6d_layout": "row_major_first_two_rows",
                "rotation_space": "global_6d_converted_to_parent_local_quaternions",
            },
            retarget_source_positions=retarget.get("source_positions"),
        )

    def extract_source(self, clip: RawClip) -> SourceSnapshot:
        profile = self._select_profile(clip, has_positions="positions" in clip.motion)
        available_positions = self._positions_from_available_data(clip, profile)
        fps = float(clip.motion.get("fps", clip.sample.fps or 20.0))
        if available_positions is not None:
            native_positions, native_names, native_edges = self._canonical_body_from_source_positions(available_positions)
            body_pos = body_positions_from_fk_positions(native_positions, native_names)
            normalized = source_positions_normalized(body_pos, BODY_BONES, world_basis=profile.position_world_basis)
            return SourceSnapshot(
                positions=normalized,
                joint_names=list(BODY_BONES),
                edges=list(BODY_EDGES),
                fps=fps,
                coordinate_system="world_normalized",
                metadata={
                    "codec": clip.sample.codec_key,
                    "source_profile": profile.name,
                    "position_scale": profile.position_scale,
                    "declared_world_basis": profile.position_world_basis,
                },
            )
        body = np.asarray(clip.motion["body"], dtype=np.float32)
        frame_count = body.shape[0]
        root_translation, _, unit = self._root_translation(body, profile)
        body_quats = sixd_rows_to_quat_xyzw(body[:, 3:].reshape(frame_count, 25, 6))
        _, _, global_body_quats = _susu_body_global_to_local(body_quats)
        use_fixed_axes = False
        positions = positions_from_global_rotations(
            root_translation, global_body_quats,
            fixed_aim_axes=SUSU_MAYA_AIM_AXES if use_fixed_axes else None,
        )
        from virea.motion.retarget import _target_scale_from_positions
        scale = _target_scale_from_positions(positions)
        positions = positions * np.float32(scale)
        positions = positions - positions[:1, BODY_INDEX["hips"]].reshape(1, 1, 3)
        return SourceSnapshot(
            positions=positions,
            joint_names=list(BODY_BONES),
            edges=list(BODY_EDGES),
            fps=fps,
            coordinate_system="world_normalized",
            metadata={
                "codec": clip.sample.codec_key,
                "source_profile": profile.name,
                "root_translation_unit": unit,
                "declared_world_basis": "identity_y_up",
                "rotation_space": "global_6d_positions_from_aim_axes",
            },
        )


def default_codecs() -> dict[str, MotionCodec]:
    return {
        "axis_angle_body22": AxisAngleBody22Codec(),
        "beat_axis_angle_body22": AxisAngleBody22Codec(
            source_rest_offsets=DEFAULT_REST_OFFSETS,
            source_profile="beat_bvh_body22",
            world_basis="identity_y_up",
        ),
        "smplx_fullpose": SMPLXFullposeCodec(),
        "position_sequence": PositionSequenceCodec(),
        "humanml3d_263d": HumanML3D263Codec(),
        "susu_6d_body_hands": SuSu6DCodec(),
        "susu_retarget_maya_6d_body_hands": SuSu6DCodec(SUSU_RETARGET_MAYA_PROFILE),
        "susu_chonglu_6d_body_hands_cm": SuSu6DCodec(SUSU_CHONGLU_PROFILE),
    }
