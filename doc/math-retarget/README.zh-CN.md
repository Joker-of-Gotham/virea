# Retarget 数学原理索引

本目录把 VIREA 当前代码中的 retarget pipeline 转写为数学公式。文档不是重新设计，也不是理想化动画系统说明；所有推导都以本仓库实现为边界，尤其是：

- `rotation.py`: 四元数、axis-angle、6D rotation、matrix-to-quat。
- `canonical.py`: canonical sequence 的打包和解包。
- `skeleton.py`: canonical parent map、rest offsets、forward kinematics。
- `retarget.py`: world basis、scale、rest correction、direct quaternion retarget、position fitting。
- `codecs.py`: 各源骨骼系统到上述两条 retarget 路径的接线逻辑。

## 统一符号

帧数记为 $T$，目标 VRM/canonical 骨骼集合记为：

$$
F=\{\mathrm{hips}\}\cup C\cup H
$$

其中 $N_C=21$，$N_H=30$。父节点映射为 $\pi(j)$，primary child 映射为 $\chi(j)$，target rest offset 为 $\bar{o}_j$，source rest offset 为 $o_j^{\mathrm{src}}$。

每一帧 canonical motion 为：

$$
s_t=\left[
r_t,\ q_t^{\mathrm{root}},\ \{q_t^j\}_{j\in C},\ \{q_t^k\}_{k\in H}
\right]\in\mathbb{R}^{211}
$$

其中 $r_t\in\mathbb{R}^3$，四元数全部为 `xyzw`：

$$
q=[x,y,z,w]
$$

前向运动学统一为：

$$
P_t(\mathrm{hips})=r_t,\qquad Q_t(\mathrm{hips})=q_t^{\mathrm{root}}
$$

$$
P_t(j)=P_t(\pi(j))+R(Q_t(\pi(j)))o_j
$$

$$
Q_t(j)=Q_t(\pi(j))q_t^j
$$

## 两条核心 retarget 路径

VIREA 当前代码实际只有两类最终输出路径。

### 1. direct local quaternion retarget

用于 SMPL-H/AMASS/BABEL、BVH-derived BEAT、SMPL-X/GRAB/Motion-X。输入已经是 parent-local pose，或被当作 parent-local pose：

$$
\left(r_t^{\mathrm{src}},q_t^{\mathrm{root,src}},\{q_t^{j,\mathrm{src}}\}\right)
$$

核心函数：

$$
retarget\_named\_quats\_to\_vrm
$$

数学步骤：

$$
r_t^{\mathrm{vrm}}=B\left(\lambda r_t^{\mathrm{src}}-\lambda r_0^{\mathrm{src}}\right)
$$

$$
q_t^{\mathrm{root,basis}}=q(B)q_t^{\mathrm{root,src}}
$$

$$
c_j=Rot(\bar{o}_{\chi(j)}\to o_{\chi(j)}^{\mathrm{src}})
$$

$$
q_t^{j,\mathrm{target}}=
\widehat{c_{\pi(j)}^{-1}q_t^{j,\mathrm{src}}c_j}
$$

缺失 correction 的因子按代码省略。

### 2. position fitting retarget

用于 HumanML3D 263D 解码结果、AMASS HumanAct12 positions、SuSu positions 和 SuSu global rotations 生成的 positions。输入是 body positions：

$$
X\in\mathbb{R}^{T\times22\times3}
$$

核心函数：

$$
fit\_positions\_to\_vrm
$$

数学步骤：

$$
X'_t(j)=BX_t(j)
$$

$$
X''_t(j)=\lambda X'_t(j)
$$

$$
r_t=X''_t(\mathrm{hips})-X''_0(\mathrm{hips})
$$

$$
q_t^{\mathrm{root}}=Rot(\bar{o}_{\mathrm{spine}}\to X''_t(\mathrm{spine})-X''_t(\mathrm{hips}))
$$

对每个 core bone $j$：

$$
q_t^j=
Rot
\left(
\bar{o}_{\chi(j)}
\to
R(Q_t(\pi(j))^{-1})(X''_t(\chi(j))-X''_t(j))
\right)
$$

位置路径当前不求解 twist，也不输出手指运动：

$$
Q^{H,\mathrm{output}}=I^{H}
$$

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

AMASS 与 BABEL 合并，是因为：

$$
\mathrm{BABEL\ motion\ carrier}=\mathrm{AMASS/SMPL{-}H\ poses}
$$

BABEL 只增加 annotation：

$$
A_{\mathrm{BABEL}}\to \mathrm{text/metadata},\qquad A_{\mathrm{BABEL}}\neq q_t^j
$$

GRAB 与 Motion-X 放在同一篇 SMPL-X 文档，但 profile 分开，因为：

$$
B_{\mathrm{GRAB}}=\mathrm{z\_up\_to\_y\_up},\qquad
B_{\mathrm{MotionX}}=\mathrm{identity\_y\_up}
$$

BEAT 单独写，是因为虽然它进入同一个 `AxisAngleBody22Codec` 类，但配置是：

$$
\mathrm{world\_basis}_{\mathrm{BEAT}}=\mathrm{identity\_y\_up}
$$

而不是 AMASS/BABEL 的：

$$
\mathrm{world\_basis}_{\mathrm{AMASS}}=\mathrm{z\_up\_to\_y\_up}
$$

SuSu 单独写，是因为当前代码存在 profile、root axes、单位自动判定、6D rows 重建、global-to-local 中间计算和 position fitting 最终输出的多层逻辑。

## 当前实现边界

文档必须忠实保留这些边界：

- VRM 是 glTF humanoid target，不是 SMPL-H/SMPL-X 参数化人体模型。
- direct quaternion 路径会输出 body quats；SMPL-X 路径还输出 hand quats。
- position fitting 路径只从 positions 拟合 body/core quats，hand quats 保持单位。
- SuSu 当前虽然计算 hand local quats，但最终 sequence 来自 position fitting，因此 hand quats 没有进入 output。
- HumanML3D fallback 只是 rest-pose 可运行保底，不代表真实动作解码。
