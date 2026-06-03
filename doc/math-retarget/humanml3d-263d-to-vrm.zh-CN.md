# HumanML3D 263D 到 VRM 的 retarget 原理

覆盖数据集：HumanML3D。

HumanML3D 在 VIREA 中不是 SMPL 参数路径，而是 text-to-motion 生态常用的 263D motion feature。它包含 root motion、局部关节位置、速度、6D rotation、foot contact 等特征。当前实现优先通过 `VIREA_TMR_SRC` 中的 `guofeats_to_joints` 解码成 22 关节位置；如果外部解码器不可用，则使用 fallback rest-pose preview，确保 pipeline 可运行但会在 metadata 中记录 decoder error。

## 1. 原始读取

adapter 读取 parquet：

```text
raw_root/data/*.parquet
row["motion"]    -> (T, 263)
row["caption"]   -> text annotations
row["meta_data"] -> name, num_frames, duration
fps = 20
```

sample id 形如：

```text
split/shard/row_index
```

HumanML3D 官方数据通常是从 AMASS/HumanAct12 处理而来，并下采样到 20 fps；但进入 VIREA 时它已经不是原始 SMPL-H pose，而是 feature vector。

## 2. 为什么不能按 SMPL-H 处理

263D 不是：

```text
22 joints * axis-angle
```

也不是：

```text
SMPL-H poses + trans
```

它是 motion generation 友好的特征表达。一个常见 22-joint 263D 分解为：

```text
root angular velocity
root linear velocity
root height
local joint positions
local joint velocities
continuous 6D joint rotations
foot contacts
```

因此 VIREA 的第一步不是 axis-angle -> quaternion，而是 feature -> joint positions。

## 3. feature 解码为 positions

优先路径：

```text
motion: (T, 263)
positions, joint_names = guofeats_to_joints(motion)
```

如果 `VIREA_TMR_SRC` 配置了 TMR/HumanML3D 解码代码，codec 会导入：

```text
from guofeats.motion_representation import guofeats_to_joints
from joints import JOINT_NAMES
```

输出通常是 Guo/HumanML3D 22-joint skeleton positions。

fallback 路径：

```text
root[:, [x,z]] = cumsum(motion[:, 0:2]) * 0.03
sequence = pack_sequence(root_translation=root)
positions = FK(rest pose sequence)[:, :22]
```

fallback 只用于 pipeline 可视化和 smoke test，不代表真实动作解码质量。

## 4. joint name 映射

HumanML3D/Guo joints 映射到 VIREA body bones：

```text
pelvis      -> hips
left_hip    -> leftUpperLeg
right_hip   -> rightUpperLeg
spine1      -> spine
left_knee   -> leftLowerLeg
right_knee  -> rightLowerLeg
spine2      -> chest
left_ankle  -> leftFoot
right_ankle -> rightFoot
spine3      -> upperChest
left_foot   -> leftToes
right_foot  -> rightToes
neck        -> neck
head        -> head
left_shoulder/right_shoulder -> upper arms chain
```

映射后得到：

```text
body_positions: (T, len(BODY_BONES), 3)
```

## 5. positions 到 VRM rotations

位置路径不能直接得到唯一局部旋转，因为围绕骨骼自身方向的 twist 在单个 child position 中不可观测。VIREA 使用确定性主 child 拟合：

1. 先按声明或推断的 world basis 转到 VRM basis。
2. 用稳定骨链估计 scale。
3. root translation 取 `hips` 位置并减第一帧。
4. root rotation 用 `hips -> spine` 方向拟合。
5. 每个骨骼用 primary child 方向拟合局部旋转。

数学形式：

```text
working = B positions
working = scale * working
root_translation_t = working_t[hips] - working_0[hips]

for each bone j:
  k = primary_child(j)
  d_world = working_t[k] - working_t[j]
  d_local = inverse(Q_parent_t) d_world
  q_j = rotation_between(target_offset_k, d_local)
  Q_j = Q_parent_t q_j
```

最终通过 target VRM rest offsets 做 FK，生成 after positions。

## 6. world basis

当前 `HumanML3D263Codec` 继承 `PositionSequenceCodec`，默认：

```text
world_basis = z_up_to_y_up
```

这反映当前项目对 HumanML3D decoded joints 的源坐标假设。若后续接入的 parquet 已经是 Y-up，需要显式新增 source_format/profile，而不是静默改默认值。

## 7. 输出

HumanML3D 输出：

```text
root_translation_vrm
root_rotation_vrm
core_quats_vrm
hand_quats_identity
```

它是 body-only，因为 HumanML3D 263D 不包含可直接驱动 VRM 手指和表情的完整信息。

## 8. 质量边界

HumanML3D 的 after preview 质量高度依赖解码器：

- 有 `guofeats_to_joints`：可以显示真实 22-joint motion；
- 无解码器：fallback 只能证明 pipeline 没坏，不能证明动作效果好。

文档、metadata、quality report 都必须保留 `humanml_decoder` 字段，避免把 fallback 当成真实 retarget 效果。

