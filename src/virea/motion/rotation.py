from __future__ import annotations

import numpy as np

EPS = 1e-8


def normalize_quat_xyzw(quat: np.ndarray) -> np.ndarray:
    arr = np.asarray(quat, dtype=np.float32)
    norm = np.linalg.norm(arr, axis=-1, keepdims=True)
    return arr / np.clip(norm, EPS, None)


def axis_angle_to_quat_xyzw(axis_angle: np.ndarray) -> np.ndarray:
    aa = np.asarray(axis_angle, dtype=np.float32)
    angle = np.linalg.norm(aa, axis=-1, keepdims=True)
    half = 0.5 * angle
    axis = aa / np.clip(angle, EPS, None)
    xyz = axis * np.sin(half)
    w = np.cos(half)
    quat = np.concatenate([xyz, w], axis=-1)
    small = angle[..., 0] < 1e-8
    if np.any(small):
        quat[small] = np.array([0.0, 0.0, 0.0, 1.0], dtype=np.float32)
    return normalize_quat_xyzw(quat)


def quat_multiply_xyzw(q1: np.ndarray, q2: np.ndarray) -> np.ndarray:
    q1 = normalize_quat_xyzw(q1)
    q2 = normalize_quat_xyzw(q2)
    x1, y1, z1, w1 = np.moveaxis(q1, -1, 0)
    x2, y2, z2, w2 = np.moveaxis(q2, -1, 0)
    out = np.stack(
        [
            w1 * x2 + x1 * w2 + y1 * z2 - z1 * y2,
            w1 * y2 - x1 * z2 + y1 * w2 + z1 * x2,
            w1 * z2 + x1 * y2 - y1 * x2 + z1 * w2,
            w1 * w2 - x1 * x2 - y1 * y2 - z1 * z2,
        ],
        axis=-1,
    )
    return normalize_quat_xyzw(out)


def quat_inverse_xyzw(quat: np.ndarray) -> np.ndarray:
    q = normalize_quat_xyzw(quat)
    out = q.copy()
    out[..., :3] *= -1.0
    return out


def quat_from_two_vectors_xyzw(source: np.ndarray, target: np.ndarray) -> np.ndarray:
    src = np.asarray(source, dtype=np.float32)
    dst = np.asarray(target, dtype=np.float32)
    src = src / np.clip(np.linalg.norm(src, axis=-1, keepdims=True), EPS, None)
    dst = dst / np.clip(np.linalg.norm(dst, axis=-1, keepdims=True), EPS, None)
    dot = np.sum(src * dst, axis=-1, keepdims=True)
    cross = np.cross(src, dst, axis=-1)
    quat = np.concatenate([cross, 1.0 + dot], axis=-1)

    opposite = dot[..., 0] < -0.999999
    if np.any(opposite):
        fallback = np.zeros_like(src)
        fallback[..., 0] = 1.0
        nearly_parallel = np.abs(src[..., 0]) > 0.9
        fallback[nearly_parallel] = np.array([0.0, 1.0, 0.0], dtype=np.float32)
        axis = np.cross(src, fallback, axis=-1)
        axis = axis / np.clip(np.linalg.norm(axis, axis=-1, keepdims=True), EPS, None)
        opposite_quat = np.concatenate([axis, np.zeros((*axis.shape[:-1], 1), dtype=np.float32)], axis=-1)
        quat[opposite] = opposite_quat[opposite]
    return normalize_quat_xyzw(quat)


def quat_to_matrix_xyzw(quat: np.ndarray) -> np.ndarray:
    q = normalize_quat_xyzw(quat)
    x, y, z, w = np.moveaxis(q, -1, 0)
    xx = x * x
    yy = y * y
    zz = z * z
    xy = x * y
    xz = x * z
    yz = y * z
    xw = x * w
    yw = y * w
    zw = z * w
    return np.stack(
        [
            1.0 - 2.0 * (yy + zz),
            2.0 * (xy - zw),
            2.0 * (xz + yw),
            2.0 * (xy + zw),
            1.0 - 2.0 * (xx + zz),
            2.0 * (yz - xw),
            2.0 * (xz - yw),
            2.0 * (yz + xw),
            1.0 - 2.0 * (xx + yy),
        ],
        axis=-1,
    ).reshape(*q.shape[:-1], 3, 3)


def quat_apply_xyzw(quat: np.ndarray, vector: np.ndarray) -> np.ndarray:
    matrix = quat_to_matrix_xyzw(quat)
    vec = np.asarray(vector, dtype=np.float32)
    return np.matmul(matrix, np.expand_dims(vec, axis=-1)).squeeze(-1)


def sixd_to_matrix(sixd: np.ndarray) -> np.ndarray:
    arr = np.asarray(sixd, dtype=np.float32)
    a1 = arr[..., 0:3]
    a2 = arr[..., 3:6]
    b1 = a1 / np.clip(np.linalg.norm(a1, axis=-1, keepdims=True), EPS, None)
    dot = np.sum(b1 * a2, axis=-1, keepdims=True)
    b2 = a2 - dot * b1
    b2 = b2 / np.clip(np.linalg.norm(b2, axis=-1, keepdims=True), EPS, None)
    b3 = np.cross(b1, b2)
    return np.stack([b1, b2, b3], axis=-1)


def sixd_rows_to_matrix(sixd: np.ndarray) -> np.ndarray:
    arr = np.asarray(sixd, dtype=np.float32)
    a1 = arr[..., 0:3]
    a2 = arr[..., 3:6]
    b1 = a1 / np.clip(np.linalg.norm(a1, axis=-1, keepdims=True), EPS, None)
    dot = np.sum(b1 * a2, axis=-1, keepdims=True)
    b2 = a2 - dot * b1
    b2 = b2 / np.clip(np.linalg.norm(b2, axis=-1, keepdims=True), EPS, None)
    b3 = np.cross(b1, b2)
    return np.stack([b1, b2, b3], axis=-2)


def matrix_to_quat_xyzw(matrix: np.ndarray) -> np.ndarray:
    m = np.asarray(matrix, dtype=np.float32)
    q = np.zeros((*m.shape[:-2], 4), dtype=np.float32)
    trace = m[..., 0, 0] + m[..., 1, 1] + m[..., 2, 2]

    positive = trace > 0.0
    if np.any(positive):
        s = np.sqrt(np.clip(trace[positive] + 1.0, EPS, None)) * 2.0
        q[positive, 3] = 0.25 * s
        q[positive, 0] = (m[positive, 2, 1] - m[positive, 1, 2]) / s
        q[positive, 1] = (m[positive, 0, 2] - m[positive, 2, 0]) / s
        q[positive, 2] = (m[positive, 1, 0] - m[positive, 0, 1]) / s

    not_positive = ~positive
    cond_x = not_positive & (m[..., 0, 0] > m[..., 1, 1]) & (m[..., 0, 0] > m[..., 2, 2])
    if np.any(cond_x):
        s = np.sqrt(np.clip(1.0 + m[cond_x, 0, 0] - m[cond_x, 1, 1] - m[cond_x, 2, 2], EPS, None)) * 2.0
        q[cond_x, 3] = (m[cond_x, 2, 1] - m[cond_x, 1, 2]) / s
        q[cond_x, 0] = 0.25 * s
        q[cond_x, 1] = (m[cond_x, 0, 1] + m[cond_x, 1, 0]) / s
        q[cond_x, 2] = (m[cond_x, 0, 2] + m[cond_x, 2, 0]) / s

    cond_y = not_positive & ~cond_x & (m[..., 1, 1] > m[..., 2, 2])
    if np.any(cond_y):
        s = np.sqrt(np.clip(1.0 + m[cond_y, 1, 1] - m[cond_y, 0, 0] - m[cond_y, 2, 2], EPS, None)) * 2.0
        q[cond_y, 3] = (m[cond_y, 0, 2] - m[cond_y, 2, 0]) / s
        q[cond_y, 0] = (m[cond_y, 0, 1] + m[cond_y, 1, 0]) / s
        q[cond_y, 1] = 0.25 * s
        q[cond_y, 2] = (m[cond_y, 1, 2] + m[cond_y, 2, 1]) / s

    cond_z = not_positive & ~cond_x & ~cond_y
    if np.any(cond_z):
        s = np.sqrt(np.clip(1.0 + m[cond_z, 2, 2] - m[cond_z, 0, 0] - m[cond_z, 1, 1], EPS, None)) * 2.0
        q[cond_z, 3] = (m[cond_z, 1, 0] - m[cond_z, 0, 1]) / s
        q[cond_z, 0] = (m[cond_z, 0, 2] + m[cond_z, 2, 0]) / s
        q[cond_z, 1] = (m[cond_z, 1, 2] + m[cond_z, 2, 1]) / s
        q[cond_z, 2] = 0.25 * s

    return normalize_quat_xyzw(q)


def sixd_to_quat_xyzw(sixd: np.ndarray) -> np.ndarray:
    return matrix_to_quat_xyzw(sixd_to_matrix(sixd))


def sixd_rows_to_quat_xyzw(sixd: np.ndarray) -> np.ndarray:
    return matrix_to_quat_xyzw(sixd_rows_to_matrix(sixd))
