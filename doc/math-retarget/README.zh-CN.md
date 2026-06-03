# Retarget 数学原理索引

本目录记录 VIREA 从不同原始骨骼系统到 VRM/glTF humanoid 的数学转换逻辑。这里的重点不是数据集介绍，而是 retarget pipeline 的可验证推导：读入什么、坐标和单位如何归一、旋转如何转换、局部/全局关系如何处理、最后怎样写成可以驱动真实 VRM avatar 的 canonical motion。

## 统一目标

所有路径最后都落到同一个目标空间：

```text
source dataset
  -> DatasetAdapter.load()
  -> RawClip
  -> MotionCodec.extract_source()   # source/before preview
  -> MotionCodec.to_canonical()     # VRM-centered canonical sequence
  -> ProcessingPipeline artifacts
  -> viewer-web / three-vrm humanoid pose
```

目标约定见 [VRM/glTF 目标层](vrm-gltf-target.zh-CN.md)：

- 坐标：glTF/VRM `+Y` up、`+Z` forward、米制单位。
- 旋转：四元数 `xyzw`，局部旋转写入 humanoid bones。
- root：`hips` 拥有平移和根旋转，其他骨骼主要使用父节点局部旋转。
- 拓扑：VIREA canonical skeleton 对齐 VRM humanoid body + hands。

## 按骨骼系统分组

| 文档 | 覆盖数据集 | 原始骨骼/表达 | retarget 类型 |
|---|---|---|---|
| [SMPL-H 到 VRM](smplh-to-vrm.zh-CN.md) | AMASS、BABEL | SMPL/SMPL-H body pose，axis-angle | 直接局部四元数 retarget |
| [SMPL-X 到 VRM](smplx-to-vrm.zh-CN.md) | GRAB、Motion-X | SMPL-X fullpose 55 joints | body + hand 局部四元数 retarget |
| [BVH/BEAT 到 VRM](bvh-to-vrm.zh-CN.md) | BEAT | BVH 派生 22 关节 body pose | 与 SMPL-H 同型，但 basis/rest profile 不同 |
| [HumanML3D 263D 到 VRM](humanml3d-263d-to-vrm.zh-CN.md) | HumanML3D | 263D motion feature | feature decode -> position fitting |
| [SuSu 到 VRM](susu-to-vrm.zh-CN.md) | SuSuInterActs | 25 body + hands，6D/global rotations 或 positions | profile-specific 6D/global-to-local 或 position fitting |

## 什么时候合并，什么时候拆分

同一种数学路径会合并写：

- AMASS 和 BABEL 都是 SMPL/SMPL-H carrier motion；BABEL 的差异主要是文本/动作标签，不改变骨骼数学。
- GRAB 和 Motion-X 都使用 SMPL-X fullpose；但两者的文件布局、世界 basis、translation 单位和元数据不同，所以在同一篇 SMPL-X 文档中分小节说明。

数学路径不同则拆开写：

- BEAT 虽然也是 axis-angle body pose，但它来自 BVH 派生骨架，当前实现使用 `beat_axis_angle_body22` 和 `identity_y_up`，不能和 AMASS 的 `z_up_to_y_up` 混成同一配置。
- HumanML3D 不是直接的 SMPL pose，而是 263D feature，必须先解码或 fallback 成关节位置。
- SuSu 的 6D rotation、root layout、positions、单位和子目录 profile 都是自定义约定，必须单独审计。

## 共同数学对象

每一篇文档都会使用同一组符号：

- `T`：帧数。
- `J`：源骨骼关节数。
- `p_t`：第 `t` 帧 root translation。
- `q_t^j`：第 `t` 帧第 `j` 个骨骼的旋转四元数。
- `R(q)`：四元数对应的 `3 x 3` 旋转矩阵。
- `o_j`：rest pose 中从 parent 到 child 的 offset。
- `parent(j)`：骨骼父节点。
- `B`：source world basis 到 VRM/glTF basis 的旋转矩阵。

前向运动学统一写成：

```text
P_t(root) = p_t
Q_t(root) = q_t(root)
P_t(j) = P_t(parent(j)) + R(Q_t(parent(j))) o_j
Q_t(j) = Q_t(parent(j)) q_t(j)
```

其中 `q_t(j)` 是父节点局部旋转；如果源数据给的是全局旋转，则需要先做：

```text
q_local(j) = inverse(q_global(parent(j))) q_global(j)
```

如果源数据只给关节位置，则不能直接得到唯一旋转，VIREA 使用每根骨骼的主 child 方向做局部对齐：

```text
q_j = rotation_between(target_rest_child_offset, desired_child_vector_in_parent_space)
```

## 参考来源

- glTF 2.0 specification: https://registry.khronos.org/glTF/specs/2.0/glTF-2.0.html
- VRM 1.0 humanoid specification: https://github.com/vrm-c/vrm-specification/blob/master/specification/VRMC_vrm-1.0/humanoid.md
- AMASS: https://arxiv.org/abs/1904.03278
- SMPL-X: https://arxiv.org/abs/1904.05866
- SMPL+H / MANO: https://arxiv.org/abs/2201.02610
- 6D rotation representation: https://arxiv.org/abs/1812.07035

