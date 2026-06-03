# SMPL-X 到 VRM 的 retarget 原理

覆盖数据集：GRAB、Motion-X。

SMPL-X 是包含 body、hands、jaw、eyes 和 face expression 的统一人体模型。VIREA 当前从 SMPL-X fullpose 中映射 body 与 hands 到 VRM humanoid；jaw、eyes、face expression 会进入 metadata 或保留字段，但不在当前 canonical body/hand FK 中驱动 VRM 表情。

## 1. 原始读取

### GRAB

GRAB `.npz` 的主体结构：

```text
payload["body"].item()["params"]["fullpose"] -> (T, >=165)
payload["body"].item()["params"]["transl"]   -> (T, 3)
payload["framerate"]                         -> fps，常见 120
payload["obj_name"] / contact / gender       -> metadata
```

adapter 声明：

```text
source_format = smplx_fullpose_npz
codec_key = smplx_fullpose
declared_world_basis = z_up_to_y_up
```

### Motion-X

Motion-X motion array 是：

```text
arr: (T, 322)
fullpose = arr[:, :165]
face_expr = arr[:, 159:209]
translation = arr[:, 309:312]
fps = 30
```

adapter 声明：

```text
source_format = smplx_322_npy
codec_key = smplx_fullpose
declared_world_basis = identity_y_up
```

Motion-X translation 会做单位保护：如果位移 span 或绝对值明显大于米制运动范围，则使用 `0.01` scale 视为厘米级输入。

## 2. fullpose 布局

SMPL-X fullpose 前 165 维解释为：

```text
55 joints * 3 axis-angle
```

先转成：

```text
axis_angle: (T, 55, 3)
quats:      (T, 55, 4)
```

转换公式同 SMPL-H：

```text
theta = ||a||
q = [a/theta * sin(theta/2), cos(theta/2)]
```

## 3. body 映射

SMPL-X body 前 22 个关节按 canonical body 顺序解释。`hips` 是 root rotation，其余 body joints 进入 `core_quats`。

```text
root_rotation = quats[:, hips]
core[name] = quats[:, source_index(name)]
```

这部分与 SMPL-H 路径相同，差异在于 SMPL-X 可以继续提供手部。

## 4. hand 映射

SMPL-X hand index 到 VRM hand bone 的映射在代码中显式定义。例如：

```text
leftIndexProximal      <- 25
leftIndexIntermediate  <- 26
leftIndexDistal        <- 27
...
rightThumbProximal     <- 52
rightThumbIntermediate <- 53
rightThumbDistal       <- 54
```

映射后的 hand quaternions 进入 canonical `HAND_BONES`。由于 VRM 1.0 的 thumb 命名和 VIREA canonical 命名略有差异，最终 viewer 会通过 `CANONICAL_TO_VRM_BONE_NAME` 做名称修正，例如：

```text
leftThumbProximal     -> leftThumbMetacarpal
leftThumbIntermediate -> leftThumbProximal
```

## 5. 坐标 basis

GRAB 与 Motion-X 同为 SMPL-X，但 basis 不同：

```text
GRAB:     z_up_to_y_up
Motion-X: identity_y_up
```

因此不能只因为它们都是 SMPL-X 就共享所有 metadata。统一公式仍是：

```text
p_vrm = B (scale * p_source - scale * p_0)
q_root_vrm = q(B) q_root_source
```

其中 `B` 由 adapter 声明。

## 6. rest correction

body 与 hand 都使用同一 correction 逻辑：

```text
c_j = rotation_between(target_primary_child_offset, source_primary_child_offset)
q'_j = inverse(c_parent(j)) q_j c_j
```

body 使用 canonical/VRM body rest offsets；hand 使用 hand rest offsets。对手指尤其重要，因为源模型和 VRM avatar 的拇指、掌骨方向经常不同。缺少 correction 时，常见现象是手指弯曲轴错、掌心翻转或拇指横向漂移。

## 7. 输出 sequence

SMPL-X 路径输出：

```text
root_translation_vrm
root_rotation_vrm
core_quats_vrm      # body
hand_quats_vrm      # fingers
```

它是当前 VIREA 中最完整的参数化人体 retarget 路径：既保留 body motion，也保留手部姿态。

## 8. face 与 object 的边界

GRAB 的 object/contact 和 Motion-X 的 face/text 不直接进入 canonical skeleton：

- object/contact 是 quality 与语义上下文，用于理解动作是否合理；
- face expression 需要 VRM expression/blendshape 通道，不能混进 humanoid bone rotation；
- jaw/eyes 可在未来扩展为 VRM eye/lookAt/expression，但当前 body retarget 不负责。

这种边界避免把“身体骨骼 retarget”写成一个含混的全模态转换器。

## 9. 数据集差异清单

GRAB：

- `.npz` nested body params。
- `transl` 通常可按米制处理。
- `framerate` 常高，播放必须使用 clip fps。
- 声明 `z_up_to_y_up`。
- 有物体名与接触信息。

Motion-X：

- `.npy` shape `(T, 322)`。
- `fullpose`、`face_expr`、`translation` 在固定切片中。
- fps 当前按 30。
- 声明 `identity_y_up`。
- translation 有厘米/米自动保护。
- 有 sequence/frame text metadata。

## 10. 验证重点

SMPL-X retarget 的核心风险：

- basis 错会让地面动作跑到墙上；
- translation 单位错会导致 avatar 飞走或步幅极大；
- hand index 错会导致手指错位；
- root rotation 错会让动作整体面向错误；
- face/object 信息不能误当 skeleton 参与 FK。

因此质量报告应同时看 root span、head-above-hips、left-right symmetry、ground contact、hand finite 和 direction error。

