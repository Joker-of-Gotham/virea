# VRM/glTF 目标层数学约定

本文说明 VIREA 的共同 retarget 终点：不是 SMPL mesh，也不是某个训练特征，而是可被 `.vrm` avatar 执行的 glTF/VRM humanoid motion。

## 1. VRM 与 glTF 的关系

VRM 是建立在 glTF 之上的 humanoid avatar 约定。glTF 提供场景图、node transform、mesh、skin、joint、inverse bind matrix 和动画通道；VRM 在此基础上声明哪些 glTF node 对应 `hips`、`spine`、`leftUpperArm` 等 humanoid bones。

glTF node 的局部 transform 可以用 TRS 表达：

```text
M_local = T(translation) R(rotation_xyzw) S(scale)
```

其中 rotation 是单位四元数，顺序是 `x, y, z, w`。VRM humanoid metadata 只做语义映射，例如：

```json
{
  "extensions": {
    "VRMC_vrm": {
      "humanoid": {
        "humanBones": {
          "hips": { "node": 1 },
          "spine": { "node": 2 }
        }
      }
    }
  }
}
```

所以 VIREA 的输出不是“生成一个新 VRM 文件”，而是生成一串 humanoid bone transforms，用 viewer 通过 `three-vrm` 写入真实 avatar。

## 2. 目标坐标系

VIREA 的 target basis 固定为：

```text
X: avatar 左右方向，+X 指向角色左侧
Y: up
Z: forward
unit: meter
rotation: quaternion xyzw
```

不同源数据可能是 `Z-up`、`Y-up`、`-Z-up` 或自定义 Maya/FBX 约定。统一变换写成：

```text
x_vrm = B x_source
R_vrm = B R_source
q_vrm = q(B) q_source
```

其中 `B` 是 `3 x 3` 正交旋转矩阵，`q(B)` 是它对应的四元数。当前实现中的显式 basis 包括：

```text
identity_y_up:
  B = I

z_up_to_y_up:
  B = [[1, 0, 0],
       [0, 0, 1],
       [0,-1, 0]]

neg_z_up_to_y_up:
  B = [[1, 0, 0],
       [0, 0,-1],
       [0, 1, 0]]
```

原则是：adapter/codec 能声明 basis 时优先相信声明；只有缺失声明时才使用姿态统计推断。

## 3. VIREA canonical sequence

VIREA 的 canonical motion 是一个帧序列：

```text
frame =
  root_translation[3]
  root_rotation_xyzw[4]
  core_bone_quats[21 x 4]
  hand_bone_quats[30 x 4]
```

核心 body bones：

```text
spine, chest, upperChest, neck, head,
leftShoulder, leftUpperArm, leftLowerArm, leftHand,
rightShoulder, rightUpperArm, rightLowerArm, rightHand,
leftUpperLeg, leftLowerLeg, leftFoot, leftToes,
rightUpperLeg, rightLowerLeg, rightFoot, rightToes
```

hand bones 是左右手五指各三节。canonical 的 `hips` 不在 `core_bone_quats` 中，因为它由 root translation 和 root rotation 单独表示。

## 4. 局部旋转与前向运动学

VRM/glTF humanoid 驱动需要局部旋转。设 `o_j` 是 target rest pose 中 parent 到 child 的 offset，`q_j` 是 child 对 parent 的局部旋转，则：

```text
P(root) = root_translation
Q(root) = root_rotation
P(j) = P(parent(j)) + R(Q(parent(j))) o_j
Q(j) = Q(parent(j)) q_j
```

注意：offset 使用的是 target avatar/rest template，而不是源 skeleton 的长度。这样做的原因是 VRM avatar 已有自己的 mesh、bone length 和 skinning，retarget 的目标是“让 avatar 以自己的身体比例执行同样的姿态意图”，不是把源 skeleton 的骨长硬塞进 avatar。

## 5. rest offset correction

源 skeleton 与 VRM target rest pose 不完全相同。即使两者骨骼名字一致，源 rest offset `s_j` 和 target rest offset `t_j` 的方向也可能不同。VIREA 用一组 correction quaternion 消除 rest pose 差异。

对每个有主 child 的骨骼：

```text
c_j = rotation_between(t_child, s_child)
```

局部旋转映射时使用：

```text
q'_j = inverse(c_parent(j)) q_j c_j
```

含义是：

- 先把父节点的 rest-space 差异抵消掉；
- 再应用源局部旋转；
- 最后把当前骨骼轴向转换到 target rest-space。

没有这一步时，最常见问题是手臂向下/向前偏、脚掌方向错、肩部扭转被误解。

## 6. scale 与 root translation

源数据的 root translation 与 target avatar 的骨长尺度不同。VIREA 用稳定骨链估计源到 target 的整体 scale：

```text
scale = sum(length(target stable chains)) / sum(length(source stable chains))
```

稳定链包括脊柱、双腿、双臂等主链。root translation 处理为：

```text
p'_t = scale * p_t
p''_t = p'_t - p'_0
```

减去第一帧 root 是为了让播放从 viewer 的局部原点开始，保留相对位移而避免把原始世界坐标带入 avatar 场景。

## 7. position fitting 路径

当源数据只给关节位置或需要优先相信位置时，旋转不是唯一可解。VIREA 使用可解释的逐骨骼方向拟合。

对每个骨骼 `j`，选一个 primary child `k`。目标是在父骨骼局部空间里，把 target rest offset 旋到观测到的 child 方向：

```text
d_world = P(k) - P(j)
d_local = R(Q(parent(j)))^{-1} d_world
q_j = rotation_between(o_k, d_local)
Q(j) = Q(parent(j)) q_j
```

这不是完整 IK，也不优化 twist，因此它适合稳定预览与 pipeline 对齐，不等价于最终高保真动画解算器。它的优点是确定、可审计、没有隐式训练依赖。

## 8. 最终写入 VRM

viewer 读取 canonical payload 后：

1. 解包 root、core、hand quaternions。
2. 将 canonical bone name 映射到 VRM humanoid bone name。
3. 构造 humanoid pose 字典。
4. 调用 `vrm.humanoid.setNormalizedPose()` 或兼容的 raw pose API。
5. 调用 `vrm.humanoid.update()`，由 three-vrm/glTF skinning 更新 mesh。

这条边界很重要：Python pipeline 负责数学转换和 artifacts，viewer 只负责把已完成的 motion payload 播放到 avatar 上。

