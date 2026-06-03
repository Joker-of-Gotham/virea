# SMPL-H / SMPL body 到 VRM 的 retarget 原理

覆盖数据集：AMASS、BABEL。

AMASS 把多来源 mocap 统一到 SMPL/SMPL-H 参数空间；BABEL 在 AMASS 动作上增加 sequence-level 和 frame-level 的语言动作标签。对 VIREA 来说，二者的动作 carrier 相同，都是 `poses + trans + mocap_framerate` 一类 SMPL/SMPL-H `.npz`。因此它们共享 `axis_angle_body22` 数学路径。

## 1. 原始读取

adapter 读取：

```text
poses: (T, D) float32
trans: (T, 3) float32, 缺失时置零
fps: mocap_framerate 或 mocap_frame_rate，缺失时默认 60
```

当前 codec 只取 body 前 22 个关节：

```text
body_axis_angle = poses[:, :22*3].reshape(T, 22, 3)
```

BABEL 如果通过 annotation record 发现样本，会额外读取文本标签和 frame annotation；这些 annotation 不参与骨骼数学，只进入 metadata/annotations。

## 2. axis-angle 到四元数

每个 axis-angle 向量 `a` 同时编码旋转轴和角度：

```text
theta = ||a||
u = a / max(theta, eps)
q = [u_x sin(theta/2), u_y sin(theta/2), u_z sin(theta/2), cos(theta/2)]
```

当 `theta` 接近 0 时，使用单位四元数：

```text
q_identity = [0, 0, 0, 1]
```

输出为 `xyzw` 顺序，和 glTF rotation 顺序一致。

## 3. SMPL body 关节到 canonical body

VIREA 采用 22 个 body bone 名称：

```text
hips,
leftUpperLeg, rightUpperLeg, spine,
leftLowerLeg, rightLowerLeg, chest,
leftFoot, rightFoot, upperChest,
leftToes, rightToes, neck,
leftShoulder, rightShoulder, head,
leftUpperArm, rightUpperArm,
leftLowerArm, rightLowerArm,
leftHand, rightHand
```

SMPL/SMPL-H 的前 22 个 body pose 在当前实现中按这个顺序解释。`hips` 的 rotation 作为 root rotation，其余骨骼进入 `local_quats_by_name`。

```text
root_rotation = q_body[hips]
local_quats[name] = q_body[index(name)] for name != hips
```

## 4. 世界 basis 与单位

AMASS/BABEL 在当前实现中声明：

```text
world_basis = z_up_to_y_up
unit = meter
```

其 basis 矩阵为：

```text
B = [[1, 0, 0],
     [0, 0, 1],
     [0,-1, 0]]
```

处理顺序：

```text
p_scaled = scale * trans
p_centered = p_scaled - p_scaled[0]
p_vrm = B p_centered
q_root_vrm = q(B) q_root_source
```

局部 body quaternions 不直接左乘 `q(B)`，因为它们已经是父节点局部旋转。只有 root/world orientation 需要 world basis 转换。

## 5. rest offset correction

SMPL/SMPL-H rest pose 与 VRM humanoid rest template 的骨骼方向不同。若直接把局部旋转写到 VRM，动作会产生系统性偏差。VIREA 先计算源 rest offset 到 target rest offset 的 correction。

对每个骨骼 `j`：

```text
c_j = rotation_between(target_primary_child_offset, source_primary_child_offset)
```

局部旋转修正为：

```text
q'_j = inverse(c_parent(j)) q_j c_j
```

root 则是：

```text
q'_root = q_root_vrm c_hips
```

这个公式来自坐标基变换：`c_parent` 把父局部坐标系对齐，`c_j` 把当前骨骼的 child aim axis 对齐。它保留源关节的相对旋转语义，同时让 target avatar 使用自己的 rest pose。

## 6. scale

源 translation 的米制尺度与 target avatar rest offset 不一定一致。VIREA 使用稳定骨链估计全局比例：

```text
scale =
  sum_j ||target_offset_j|| over stable chains
  /
  sum_j ||source_offset_j|| over stable chains
```

稳定链包括脊柱、双腿、双臂。这样不会因为某一根手指或脚趾的局部差异污染整体位移尺度。

## 7. 生成 canonical sequence

最终 packing：

```text
sequence[t] =
  root_translation_vrm[t]      # 3
  root_rotation_vrm[t]         # 4
  core_quats_vrm[t, 21, 4]
  hand_quats_identity[t, 30, 4]
```

AMASS/BABEL 当前只映射 body，hand 输出单位旋转。虽然 SMPL-H 本身可以有 hand pose，但当前 adapter/codec 主路径只取 22 body joints；后续若启用 SMPL-H hand block，需要补充手指索引表和 hand rest correction。

## 8. before/after 的语义

`extract_source()` 使用同一 axis-angle 解码和源 rest offset 做 source FK，再转到 VRM basis，仅用于 before preview。`to_canonical()` 生成 target VRM FK 结果，用于 after preview 和真实 VRM avatar。

二者不应逐点强制一致：

- before 显示“源 skeleton 被如何解释”；
- after 显示“目标 VRM skeleton 执行同一运动意图后的结果”。

质量检查应关注方向、root、接触、速度、左右关系和异常值，而不是要求不同骨长 skeleton 的所有 joint position 完全相等。

## 9. 数据集差异

AMASS：

- 直接扫描 `.npz`。
- 读取 `poses`、`trans`、`mocap_framerate`。
- 数学路径完全由 SMPL/SMPL-H body pose 决定。

BABEL：

- 优先读取 `babel-teach/{train,val}.json`。
- 根据 `feat_p` 定位 AMASS carrier motion。
- 文本标签只影响 annotation，不改变 retarget 数学。

