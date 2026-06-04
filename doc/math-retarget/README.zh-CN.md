# Retarget 数学原理索引

本目录把 VIREA 当前代码中的 retarget pipeline 转写为数学公式。它不是重新设计，也不是理想化动画系统说明；所有推导都以本仓库实现为边界，尤其对应这些文件：

- `rotation.py`: 四元数、axis-angle、6D rotation、matrix-to-quat。
- `canonical.py`: canonical sequence 的打包和解包。
- `skeleton.py`: canonical parent map、rest offsets、forward kinematics。
- `retarget.py`: world basis、scale、rest correction、direct quaternion retarget、position fitting。
- `codecs.py`: 各源骨骼系统到两条 retarget 路径的接线逻辑。

## 统一符号

帧数记为 $T$，帧索引记为 $t$，其中 $0\le t<T$。VIREA 的目标骨骼不是 SMPL 参数体，而是面向 VRM/glTF humanoid 的 canonical skeleton。完整骨骼集合写作：

$$
F=\{\mathrm{hips}\}\cup C\cup H
$$

这里 $F$ 是 forward kinematics 会输出的位置集合，$\mathrm{hips}$ 是根节点，$C$ 是 body/core bones，$H$ 是 hand bones。数量为：

$$
N_{C}=21,\qquad N_{H}=30,\qquad N_{F}=1+N_{C}+N_{H}=52
$$

常用索引和结构记号如下。

| 符号 | 含义 |
|---|---|
| $j$ | 任意 body/core bone 名，通常满足 $j\in C$。 |
| $k$ | 任意 hand bone 名，通常满足 $k\in H$。 |
| $\pi(j)$ | bone $j$ 的父节点，对应代码里的 parent map。 |
| $\chi(j)$ | bone $j$ 的 primary child，用来估计该骨骼的主要朝向。 |
| $o_{j}^{T}$ | target/VRM rest offset，即目标骨架中 bone $j$ 相对父节点的静态偏移。 |
| $o_{j}^{\mathrm{src}}$ | source rest offset，即源骨架中 bone $j$ 相对父节点的静态偏移。 |
| $B$ | source world basis 到 VRM/glTF world basis 的旋转矩阵。 |
| $\lambda$ | 源骨架尺度到目标 VRM 尺度的比例。 |
| $R(q)$ | 四元数 $q$ 对应的 $3\times3$ 旋转矩阵。 |
| $Rot(a\to b)$ | 把方向 $a$ 旋到方向 $b$ 的单位四元数，对应 `quat_from_two_vectors_xyzw()`。 |
| $\widehat{q}$ | 四元数归一化结果，对应 `normalize_quat_xyzw()`。 |

每一帧 canonical motion 都被打包成一个 $211$ 维向量：

$$
s_{t}=
\left[
r_{t},\ q_{t}^{\mathrm{root}},\ \{q_{t}^{j}\}_{j\in C},\ \{q_{t}^{k}\}_{k\in H}
\right]\in\mathbb{R}^{211}
$$

这个公式的含义是：

- $r_{t}\in\mathbb{R}^{3}$ 是第 $t$ 帧 root translation，也就是 $\mathrm{hips}$ 的位置。
- $q_{t}^{\mathrm{root}}\in\mathbb{R}^{4}$ 是 root rotation。
- $q_{t}^{j}$ 是 body/core bone $j$ 的父节点局部旋转。
- $q_{t}^{k}$ 是 hand bone $k$ 的父节点局部旋转。
- 维度来源是 $3+4+4N_{C}+4N_{H}=3+4+84+120=211$。

所有四元数都使用 glTF/three.js/VIREA 一致的 `xyzw` 顺序：

$$
q=[x,y,z,w]
$$

## 前向运动学

给定一帧 $s_{t}$ 和一套 rest offsets，forward kinematics 输出每个骨骼的 world position $P_{t}(j)$ 和 world rotation $Q_{t}(j)$。根节点先定义为：

$$
P_{t}(\mathrm{hips})=r_{t}
$$

$$
Q_{t}(\mathrm{hips})=q_{t}^{\mathrm{root}}
$$

其中 $P_{t}(\mathrm{hips})$ 是 root 的世界位置，$Q_{t}(\mathrm{hips})$ 是 root 的世界旋转。对任意非 root 骨骼 $j$，代码按父节点递推：

$$
P_{t}(j)=P_{t}(\pi(j))+R(Q_{t}(\pi(j)))o_{j}
$$

$$
Q_{t}(j)=Q_{t}(\pi(j))q_{t}^{j}
$$

这里 $o_{j}$ 是当前 FK 使用的 rest offset。如果在 VRM target 上做 FK，则 $o_{j}=o_{j}^{T}$；如果在 source preview 上做 FK，则 $o_{j}=o_{j}^{\mathrm{src}}$。第一条公式表示“父节点位置加上被父节点世界旋转带动后的骨骼静态偏移”；第二条公式表示“子节点世界旋转等于父节点世界旋转乘以子节点局部旋转”。

## 两条核心 retarget 路径

VIREA 当前代码最终只走两类输出路径：一种是直接把源局部四元数修正到 VRM 局部四元数，另一种是先有 body positions，再从 positions 拟合出 VRM 局部四元数。

### 1. Direct Local Quaternion Retarget

这条路径用于 SMPL-H/AMASS/BABEL、BVH-derived BEAT、SMPL-X/GRAB/Motion-X。输入已经是 parent-local pose，或被当前代码当作 parent-local pose：

$$
\left(r_{t}^{\mathrm{src}},q_{t}^{\mathrm{root,src}},\{q_{t}^{j,\mathrm{src}}\}_{j\in C}\right)
$$

其中 $r_{t}^{\mathrm{src}}$ 是源 root translation，$q_{t}^{\mathrm{root,src}}$ 是源 root rotation，$q_{t}^{j,\mathrm{src}}$ 是源骨骼 $j$ 的父节点局部旋转。SMPL-X 还会额外传入 hand quaternions；SMPL-H、BABEL、BEAT 当前主路径没有 hand 输入，hand 输出会保持单位四元数。

核心函数是：

$$
retargetNamedQuatsToVrm
$$

第一步是 root translation 的尺度变换、首帧归零和 world basis 变换：

$$
r_{t}^{\mathrm{vrm}}=B\left(\lambda r_{t}^{\mathrm{src}}-\lambda r_{0}^{\mathrm{src}}\right)
$$

这里 $\lambda$ 把 source skeleton 的长度尺度对齐到 target VRM skeleton，$r_{0}^{\mathrm{src}}$ 是第 $0$ 帧 root translation。减去首帧后，输出动作从原点附近开始；左乘 $B$ 则把 source world coordinate 转成 VRM/glTF coordinate。

第二步是 root rotation 的 basis 变换：

$$
q_{t}^{\mathrm{root,basis}}=q(B)q_{t}^{\mathrm{root,src}}
$$

这里 $q(B)$ 是矩阵 $B$ 对应的四元数。只有 root world rotation 需要被 world basis 直接左乘；body 局部四元数仍留在 parent-local 空间中，后面通过 rest correction 修正。

第三步是 target/source rest pose 的方向修正。对有 primary child 的骨骼 $j$，定义：

$$
c_{j}=Rot(o_{\chi(j)}^{T}\to o_{\chi(j)}^{\mathrm{src}})
$$

其中 $o_{\chi(j)}^{T}$ 是 target 骨架中 child $\chi(j)$ 的 rest offset，$o_{\chi(j)}^{\mathrm{src}}$ 是 source 骨架中同名 child 的 rest offset。$c_{j}$ 的意义是：把 target rest pose 中骨骼 $j$ 指向 child 的方向，旋到 source rest pose 的对应方向。这样同一个局部 pose 可以从 source rest frame 转写到 target rest frame。

第四步把每个 source local quaternion 写成 target local quaternion：

$$
q_{t}^{j,\mathrm{target}}=
\widehat{c_{\pi(j)}^{-1}q_{t}^{j,\mathrm{src}}c_{j}}
$$

这个公式中，$c_{\pi(j)}^{-1}$ 抵消父节点 rest frame 差异，$c_{j}$ 注入当前骨骼 rest frame 差异，$\widehat{\cdot}$ 表示最后归一化。若某个 correction 在代码中不存在，就省略对应因子。root rotation 若存在 $c_{\mathrm{hips}}$，也会在 basis 变换后右乘该 correction。

最后打包：

$$
s_{t}^{\mathrm{out}}=
\left[
r_{t}^{\mathrm{vrm}},
q_{t}^{\mathrm{root,target}},
\{q_{t}^{j,\mathrm{target}}\}_{j\in C},
\{q_{t}^{k,\mathrm{target}}\}_{k\in H}
\right]
$$

这里 $s_{t}^{\mathrm{out}}$ 就是最终写入 canonical sequence 的第 $t$ 帧。若 hand 输入缺失，则 $q_{t}^{k,\mathrm{target}}=[0,0,0,1]$。

### 2. Position Fitting Retarget

这条路径用于 HumanML3D 263D 解码结果、AMASS HumanAct12 positions、SuSu positions，以及 SuSu global rotations 先构造出的 positions。输入不是局部 pose，而是按 body bones 对齐后的关节位置：

$$
X\in\mathbb{R}^{T\times22\times3}
$$

其中 $X_{t}(j)$ 表示第 $t$ 帧 body bone $j$ 的 source position。这里的 $22$ 对应 `BODY_BONES`，不包含 VRM hand bones。

核心函数是：

$$
fitPositionsToVrm
$$

第一步把 source positions 转到 VRM/glTF world basis：

$$
X'_{t}(j)=BX_{t}(j)
$$

这里 $B$ 的含义和 direct path 相同。第二步做尺度对齐：

$$
X''_{t}(j)=\lambda X'_{t}(j)
$$

这里 $\lambda$ 是从 target rest lengths 和 source 第 $0$ 帧 positions 的骨骼长度估计出来的比例。

第三步从位置中取 root translation：

$$
r_{t}=X''_{t}(\mathrm{hips})-X''_{0}(\mathrm{hips})
$$

这个公式表示：把第 $0$ 帧 hips 当作起点，后续 root translation 只保留相对位移。

第四步拟合 root rotation。先用 spine 相对 hips 的方向作为 root 主方向：

$$
d_{t}^{\mathrm{spine}}=X''_{t}(\mathrm{spine})-X''_{t}(\mathrm{hips})
$$

然后令 target rest spine offset 旋到观测 spine 方向：

$$
q_{t}^{\mathrm{root}}=Rot(o_{\mathrm{spine}}^{T}\to d_{t}^{\mathrm{spine}})
$$

这里 $o_{\mathrm{spine}}^{T}$ 是 VRM target rest pose 中 spine 相对 hips 的 offset。若 $d_{t}^{\mathrm{spine}}$ 太短，代码保持单位 root rotation。

第五步对每个 body/core bone $j$ 做方向拟合。先取 child 的世界方向：

$$
d_{t}^{\mathrm{world}}(j)=X''_{t}(\chi(j))-X''_{t}(j)
$$

再用父节点世界旋转的逆把它转回父节点局部空间：

$$
d_{t}^{\mathrm{local}}(j)=R(Q_{t}(\pi(j))^{-1})d_{t}^{\mathrm{world}}(j)
$$

这里 $Q_{t}(\pi(j))$ 是已经递推出的父节点 world rotation。最后令 target rest child offset 旋到这个局部观测方向：

$$
q_{t}^{j}=Rot(o_{\chi(j)}^{T}\to d_{t}^{\mathrm{local}}(j))
$$

得到 $q_{t}^{j}$ 后，代码继续用 $Q_{t}(j)=Q_{t}(\pi(j))q_{t}^{j}$ 递推子节点 world rotation。位置路径当前只拟合 swing direction，不单独求解 twist。

位置路径不输出手指运动：

$$
q_{t}^{k,\mathrm{target}}=[0,0,0,1],\qquad k\in H
$$

因此 HumanML3D、position sequence 和 SuSu 当前最终 sequence 的 hand quaternions 都是单位四元数。

## 文档分组

| 文档 | 覆盖数据集 | 代码入口 | 最终 retarget |
|---|---|---|---|
| [VRM/glTF 目标层](vrm-gltf-target.zh-CN.md) | 全部 | `rotation.py`, `canonical.py`, `skeleton.py`, `retarget.py` | 共同数学层 |
| [SMPL-H 到 VRM](smplh-to-vrm.zh-CN.md) | AMASS、BABEL | `AxisAngleBody22Codec` | direct local quaternion |
| [SMPL-X 到 VRM](smplx-to-vrm.zh-CN.md) | GRAB、Motion-X | `SMPLXFullposeCodec` | direct local quaternion + hands |
| [BVH/BEAT 到 VRM](bvh-to-vrm.zh-CN.md) | BEAT | `beat_axis_angle_body22` | direct local quaternion |
| [HumanML3D 263D 到 VRM](humanml3d-263d-to-vrm.zh-CN.md) | HumanML3D、position sequence | `HumanML3D263Codec`, `PositionSequenceCodec` | position fitting |
| [SuSu 到 VRM](susu-to-vrm.zh-CN.md) | SuSuInterActs | `SuSu6DCodec` | position fitting |

## 合并和拆分原则

AMASS 与 BABEL 合并，是因为 BABEL 的 motion carrier 仍是 AMASS/SMPL-H poses；BABEL annotation 只进入 text/metadata，不改变 pose tensor 的数学解释。

GRAB 与 Motion-X 放在同一篇 SMPL-X 文档，但 profile 分开，因为 GRAB 使用 $B_{\mathrm{GRAB}}=\mathrm{ZUpToYUp}$，Motion-X 使用 $B_{\mathrm{MotionX}}=\mathrm{IdentityYUp}$。

BEAT 单独写，是因为虽然它进入同一个 `AxisAngleBody22Codec` 类，但配置是 $B_{\mathrm{BEAT}}=\mathrm{IdentityYUp}$，不能套用 AMASS/BABEL 的 Z-up 到 Y-up 变换。

SuSu 单独写，是因为当前代码存在 profile、root axes、单位自动判定、6D rows 重建、global-to-local 中间计算和 position fitting 最终输出的多层逻辑。

## 当前实现边界

文档必须忠实保留这些边界：

- VRM 是 glTF humanoid target，不是 SMPL-H/SMPL-X 参数化人体模型。
- direct quaternion 路径会输出 body quats；SMPL-X 路径还输出 hand quats。
- position fitting 路径只从 positions 拟合 body/core quats，hand quats 保持单位。
- SuSu 当前虽然计算 hand local quats，但最终 sequence 来自 position fitting，因此 hand quats 没有进入 output。
- HumanML3D fallback 只是 rest-pose 可运行保底，不代表真实动作解码。
