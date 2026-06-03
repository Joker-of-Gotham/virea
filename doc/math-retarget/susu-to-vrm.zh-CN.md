# SuSuInterActs 到 VRM 的 retarget 原理

覆盖数据集：SuSuInterActs。

SuSuInterActs 是当前项目中最需要单独审计的路径。它不是 SMPL-H/SMPL-X，也不是标准 BVH。动作文件是 `.npy` dict，包含自定义 25 body joints、左右手、可选 positions、ARKit face、wav audio 和中文 dialogue text。body/hand rotation 使用 6D 表达，并且不同子目录有不同单位和坐标 profile。

## 1. 原始读取

adapter 读取：

```text
motion_data/<sample>.npy -> dict
  body:      (T, 153) 或兼容形状
  left:      (T, 20*6)
  right:     (T, 20*6)
  positions: (T, J, 3), 可选

arkit_data/<sample>.npy -> face, 可选
wav_data/<sample>.wav   -> audio, 可选
text_data/motion2text.json -> dialogue text
```

当前 profile 分流：

```text
fbx_to_json_data_susu_retarget_maya/*
  -> susu_retarget_maya_6d_body_hands

fbx_to_json_data_susu_chonglu/* 或包含 positions
  -> susu_chonglu_6d_body_hands_cm

其他
  -> susu_6d_body_hands
```

## 2. SuSu body skeleton

body 25 joints：

```text
pelvis,
thigh_r, calf_r, foot_r, ball_r,
thigh_l, calf_l, foot_l, ball_l,
spine_01, spine_02, spine_03, spine_04, spine_05,
neck_01, neck_02, head,
clavicle_l, upperarm_l, lowerarm_l,
clavicle_r, upperarm_r, lowerarm_r,
hand_l, hand_r
```

映射到 canonical：

```text
pelvis    -> hips
thigh_l   -> leftUpperLeg
calf_l    -> leftLowerLeg
foot_l    -> leftFoot
ball_l    -> leftToes
thigh_r   -> rightUpperLeg
...
spine_01  -> spine
spine_03  -> chest
spine_05  -> upperChest
neck_01   -> neck
head      -> head
upperarm_l/lowerarm_l/hand_l -> left arm chain
upperarm_r/lowerarm_r/hand_r -> right arm chain
```

注意 SuSu 源顺序是右腿在前、左腿在后，canonical 按 VRM 左右语义重新排列。

## 3. 6D rotation 到矩阵/四元数

SuSu 使用 6D rotation。VIREA 对 SuSu 使用 row-major first-two-rows 的解释：

```text
a1 = sixd[0:3]
a2 = sixd[3:6]
b1 = normalize(a1)
b2 = normalize(a2 - dot(b1, a2) b1)
b3 = cross(b1, b2)
R = stack rows/axes according to sixd_rows_to_matrix
q = matrix_to_quat_xyzw(R)
```

这来自 6D rotation representation 的连续表示思想：网络或数据可以存储旋转矩阵的前两列/行，再用 Gram-Schmidt 重建 SO(3)。

## 4. root translation

SuSu 的 `body` 前 3 维不是统一语义，必须按 profile 处理：

```text
root_raw = body[:, root_axes]
root = root_raw * root_translation_scale
root = root - root[0]
```

当前 profile：

```text
retarget_maya:
  root_axes = (0, 2, 1)
  root_translation_mode = absolute_xzy_zeroed_auto_units
  如果 median height > 5 或 max_abs > 20，则按厘米 *0.01；否则按米
  position_world_basis = neg_z_up_to_y_up

chonglu:
  root_axes = (0, 2, 1)
  root_translation_scale = 0.01
  root_translation_mode = absolute_xzy_cm_zeroed
  position_world_basis = identity_y_up
```

这一步是防止畸形和“动作飞走”的关键。

## 5. 全局旋转转局部旋转

SuSu body rotation 当前按全局方向解释。VRM 需要父节点局部旋转，所以必须做：

```text
q_local(j) = inverse(q_global(parent(j))) q_global(j)
```

root：

```text
root_rotation = q_global(hips)
```

hand 也类似，但 hand 的 parent 可能在手内，也可能是 body 的 `leftHand/rightHand`：

```text
if parent is finger parent:
  parent_global = q_global(finger_parent)
else:
  parent_global = body_global(leftHand/rightHand)

q_local(finger) = inverse(parent_global) q_global(finger)
```

如果把全局旋转直接当局部旋转写入 VRM，父子旋转会被重复叠加，表现为手臂/手掌翻转、肢体畸形。

## 6. positions 优先路径

如果 motion dict 中有 `positions`，VIREA 优先相信 positions：

```text
positions_m = positions * profile.position_scale
native_positions, native_names = map_susu_positions_to_canonical()
body_positions = body_positions_from_fk_positions(native_positions, native_names)
retarget = fit_positions_to_vrm(body_positions, world_basis=profile.position_world_basis)
```

这样可以绕开部分 6D/global rotation 的不确定性。positions 路径仍然需要 basis 和 scale，因为 SuSu 的 positions 可能是厘米或 Maya/FBX basis。

## 7. 无 positions 时的 rotation 路径

如果没有 positions，则：

1. 从 root translation 和 global body quats 估计 source body positions。
2. 用 anatomical aim axis 决定每个 parent 轴向。
3. 调用 `fit_positions_to_vrm()` 生成 VRM sequence。

数学上：

```text
direction_j = normalize(R(q_global(parent(j))) aim_axis_j)
P(j) = P(parent(j)) + length(target_offset_j) direction_j
```

这里不是直接把 6D local quats 写入 VRM，而是先构造一个可解释的 source position skeleton，再走 position fitting。原因是 SuSu 的 global 6D 与 Maya aim axis/骨骼方向存在 profile 差异，直接 quaternion retarget 容易放大畸形。

## 8. face/audio/text 边界

SuSu 包含：

- ARKit face `.npy`
- wav audio
- 中文 dialogue text
- behavior/action text

这些都进入 metadata 或 annotations。当前 humanoid retarget 只输出 skeleton motion；face expression 需要未来单独的 VRM expression/blendshape pipeline，audio 需要时间同步播放或训练 pipeline，不能混入 body FK。

## 9. 质量审计重点

SuSu 最容易出现三类问题：

1. **初始姿态畸形**：说明原始 6D/positions 或 profile 解释已经错，不是 VRM retarget 后才错。
2. **单位错**：root 或 positions 厘米/米误判，导致身体巨大、飞走或脚步漂移。
3. **global/local 错**：把全局旋转当局部旋转，导致父子叠加。

因此 SuSu 的 quality/audit 必须检查：

```text
finite values
static/frozen samples
head above hips
feet below head
left/right upper arm order
root span
position_scale
root_translation_effective_scale
declared_world_basis
source_positions_available
```

## 10. profile 扩展规则

后续如果出现新的 SuSu 子目录，不应直接复用旧 profile。必须先确认：

- `body[:, :3]` 是速度还是绝对 root；
- root axis order 是 `XYZ`、`XZY` 还是其他；
- rotation 6D 是 rows 还是 columns；
- rotation 是 local 还是 global；
- positions 是否存在，单位是米还是厘米；
- source up axis 是 `+Y`、`+Z` 还是 `-Z`。

确认后新增明确的 `SuSuProfile`，并在 metadata 里写入 profile 名称，保证每个样本都可追溯。

