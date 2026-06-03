# BVH / BEAT 到 VRM 的 retarget 原理

覆盖数据集：BEAT。

BEAT 是对话手势多模态数据集，包含 audio、text、emotion、face 等信息。当前 VIREA 对 BEAT 的动作侧读取 `pose/*.npz`，它是 BVH 派生的 22 关节 body axis-angle pack，因此数学上接近 SMPL-H 的 axis-angle body retarget，但 source profile、rest offsets 和 world basis 不同，必须单独记录。

## 1. BVH 的一般结构

BVH 文件通常由两部分组成：

```text
HIERARCHY
  ROOT / JOINT / OFFSET / CHANNELS / End Site

MOTION
  Frames: N
  Frame Time: dt
  frame channel values...
```

root 往往有 6 个通道：3 个 position + 3 个 rotation。普通 joint 通常只有 rotation channels。rotation order 由 `CHANNELS` 中的顺序决定，例如 `Zrotation Xrotation Yrotation` 与 `Xrotation Yrotation Zrotation` 不是同一个数学对象。

BEAT adapter 当前不直接解析 `.bvh` 文本，而是读取已经整理成 `.npz` 的 BVH-derived axis-angle：

```text
poses: (T, D)
trans: (T, 3)
fps: payload["fps"] 或默认 30
```

因此在 VIREA 中，BVH 的 Euler/channel 阶段已经发生在上游，当前需要保证的是：把这个 BVH-derived 22-joint body pose 按正确 rest/basis 解释。

## 2. BEAT adapter 读取

读取路径：

```text
raw_root/pose/<speaker>/<sample>.npz
raw_root/hf/<speaker>/<sample>.txt
```

输出：

```text
source_format = beat_bvh_axis_angle_npz
codec_key = beat_axis_angle_body22
text/annotations = hf text file
```

`hf` 文本用于 gesture/semantic annotations，不参与姿态数学。

## 3. axis-angle 数学

与 SMPL-H 相同：

```text
body_axis_angle = poses[:, :22*3].reshape(T, 22, 3)
q_j = axis_angle_to_quat_xyzw(body_axis_angle_j)
```

每帧 body pose 分成：

```text
root_rotation = q_hips
local_quats_by_name[j] = q_j, j != hips
root_translation = trans
```

## 4. BEAT 与 AMASS 的关键差异

虽然二者进入同一个 `AxisAngleBody22Codec` 类，但 BEAT 注册为：

```text
source_profile = beat_bvh_body22
world_basis = identity_y_up
```

而 AMASS/BABEL 是：

```text
source_profile = smplh_body22
world_basis = z_up_to_y_up
```

这说明 BEAT 的姿态 pack 已经处在目标兼容的 Y-up basis 中，不能再套 AMASS 的 Z-up 转换。否则典型错误是整个人绕 X 轴旋转，地面动作变成墙面动作。

## 5. rest profile

BVH skeleton 的 rest pose 由 `OFFSET` 层级定义，和 SMPL/VRM 都不同。当前 VIREA 使用 `beat_bvh_body22` profile，并用默认/目标 rest offsets 做 correction。

核心公式仍是：

```text
c_j = rotation_between(target_primary_child_offset, source_primary_child_offset)
q'_j = inverse(c_parent(j)) q_j c_j
```

对 BVH 派生数据要特别注意：

- BVH rotation channel 可能来自不同 Euler order；
- 上游转换成 axis-angle 后已经丢失 channel order 显式信息；
- 因此 adapter 必须把这个 `.npz` 当作一个明确 source_format，而不能假设所有 BVH 都可复用。

## 6. root 与 fps

BEAT 的 fps 来自 `.npz` 中的 `fps` 字段，缺失时默认 30。播放时必须使用每个 clip 的 fps：

```text
time_sec = frame_index / fps
```

如果固定用 viewer 刷新率或固定 30fps，会造成口型/语音/手势节奏错位。BEAT 是语音手势数据，这一点比纯动作数据更敏感。

## 7. 输出

BEAT 当前输出 body-only VRM motion：

```text
root_translation_vrm
root_rotation_vrm
core_quats_vrm
hand_quats_identity
```

虽然 BEAT 数据集有 face/audio/emotion，但当前骨骼 retarget 不驱动 VRM expression。后续扩展应把 face/audio pipeline 与 humanoid skeleton pipeline 分开。

## 8. 验证重点

BEAT retarget 的评审重点：

- fps 与语音/文本 annotation 时间是否一致；
- `identity_y_up` 是否被保留，没有误套 Z-up 变换；
- root translation 是否中心化；
- 手臂手势是否仍围绕躯干自然运动；
- body-only 输出不会伪造不存在的手指 motion。

