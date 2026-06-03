# Retarget 文档评审清单

本文用于检查 `doc/math-retarget/` 下每条数学路径是否讲清楚、可追溯、可实现。

## 覆盖矩阵

| 骨骼系统 | 数据集 | 文档 | 是否拆分差异 |
|---|---|---|---|
| VRM/glTF target | 全部 | `vrm-gltf-target.zh-CN.md` | 统一目标层 |
| SMPL-H / SMPL body | AMASS、BABEL | `smplh-to-vrm.zh-CN.md` | BABEL annotation 单独说明 |
| SMPL-X | GRAB、Motion-X | `smplx-to-vrm.zh-CN.md` | GRAB/Motion-X basis、fps、translation 单位分开说明 |
| BVH-derived body | BEAT | `bvh-to-vrm.zh-CN.md` | 与 AMASS 同型但 profile/basis 单独说明 |
| 263D feature | HumanML3D | `humanml3d-263d-to-vrm.zh-CN.md` | 解码器/fallback 分开说明 |
| 自定义 6D body-hands | SuSuInterActs | `susu-to-vrm.zh-CN.md` | retarget-maya/chonglu profile 分开说明 |

## 必须出现的内容

每篇 source 文档应回答：

- 原始文件或 tensor 从哪里读。
- adapter 输出的 `source_format` 与 `codec_key` 是什么。
- source fps 如何确定。
- source skeleton 的关节数量和顺序如何解释。
- rotation 表达如何转换到 quaternion `xyzw`，或 positions 如何拟合到 rotations。
- world basis 是显式声明还是推断。
- 单位和 scale 如何处理。
- root translation 为什么要减第一帧。
- source preview 与 processed/VRM preview 的区别。
- 哪些 dataset 差异会影响 retarget 数学。
- 当前没有覆盖的通道是什么，例如 face、object、audio、expression。

## 公式一致性

统一采用：

```text
P(j) = P(parent(j)) + R(Q(parent(j))) o_j
Q(j) = Q(parent(j)) q_j
q_local(j) = inverse(q_global(parent(j))) q_global(j)
```

axis-angle 到 quaternion：

```text
theta = ||a||
q = [a/theta * sin(theta/2), cos(theta/2)]
```

position fitting：

```text
d_local = inverse(Q_parent) (P(child) - P(j))
q_j = rotation_between(target_offset_child, d_local)
```

rest correction：

```text
c_j = rotation_between(target_primary_child_offset, source_primary_child_offset)
q'_j = inverse(c_parent(j)) q_j c_j
```

## 已确认边界

- 文档没有把 VRM 描述成 SMPL-H/SMPL-X 一类参数化人体模型，而是描述成 glTF avatar + humanoid bone mapping。
- 文档没有把 face/audio/object 混入 humanoid bone retarget。
- 文档明确 HumanML3D fallback 不是高质量真实解码。
- 文档明确 SuSu 的 profile 是数据解释的一部分，不是后处理美化。
- 文档明确同骨骼系统可以共享数学路径，但 dataset profile 不能混用。

