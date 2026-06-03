# Retarget 文档公式级评审清单

本文用于审查 `doc/math-retarget/` 是否真的把代码逻辑转写为数学逻辑，而不是停留在概念介绍。

## 覆盖矩阵

| 骨骼系统 | 数据集 | 文档 | 必须覆盖 |
|---|---|---|---|
| VRM/glTF target | 全部 | `vrm-gltf-target.zh-CN.md` | quaternion、FK、basis、scale、correction、direct retarget、position fitting |
| SMPL-H / SMPL body | AMASS、BABEL | `smplh-to-vrm.zh-CN.md` | `.npz` 读取、66 维切片、axis-angle、body22、basis、correction |
| SMPL-X | GRAB、Motion-X | `smplx-to-vrm.zh-CN.md` | 165 维 fullpose、55 joints、hand index、GRAB/Motion-X profile |
| BVH-derived body | BEAT | `bvh-to-vrm.zh-CN.md` | BVH 上游边界、BEAT `.npz`、identity basis、fps |
| 263D/positions | HumanML3D | `humanml3d-263d-to-vrm.zh-CN.md` | parquet、decode/fallback、joint mapping、position fitting |
| 自定义 6D | SuSuInterActs | `susu-to-vrm.zh-CN.md` | profile、root axes、unit auto rule、6D rows、global-to-local、positions output |

## 公式格式要求

段内符号必须使用 `$...$`，例如 $T$、$q=[x,y,z,w]$、$B$。

段间公式必须使用：

$$
P_t(j)=P_t(\pi(j))+R(Q_t(\pi(j)))o_j
$$

不能用伪公式替代核心推导，例如只写“做 FK”“做归一化”是不够的。

## 每篇 source 文档必须回答

- 原始文件或 tensor 从哪里读，shape 是什么。
- adapter 输出的 `source_format` 与 `codec_key` 是什么。
- fps 如何确定。
- source skeleton 的关节数量和顺序如何映射。
- rotation 表达如何转成 quaternion，或 positions 如何转成 rotations。
- world basis 是什么，矩阵 $B$ 是什么。
- scale $\lambda$ 如何计算。
- root translation 为什么是 $r_t-r_0$。
- source preview 和 processed preview 分别对应哪个公式。
- metadata 中的 `retarget_mode` 和 `declared_world_basis` 与公式如何对应。
- 哪些通道没有进入当前 VRM humanoid sequence。

## 必须和代码一致的关键点

四元数顺序：

$$
q=[x,y,z,w]
$$

axis-angle：

$$
q(a)=
\left[
\frac{a}{\|a\|}\sin\frac{\|a\|}{2},
\cos\frac{\|a\|}{2}
\right]
$$

6D rows：

$$
R(d)=
\begin{bmatrix}
b_1^\top\\
b_2^\top\\
(b_1\times b_2)^\top
\end{bmatrix}
$$

global-to-local：

$$
q_t^{j,\mathrm{local}}=
\left(q_t^{\pi(j),\mathrm{global}}\right)^{-1}
q_t^{j,\mathrm{global}}
$$

rest correction：

$$
c_j=Rot(o_{\chi(j)}^{T}\to o_{\chi(j)}^{\mathrm{src}})
$$

$$
q_t^{j,\mathrm{target}}=
\widehat{c_{\pi(j)}^{-1}q_t^{j,\mathrm{src}}c_j}
$$

position fitting：

$$
q_t^j=
Rot
\left(
o_{\chi(j)}^{T}
\to
R(Q_t(\pi(j))^{-1})(X_t(\chi(j))-X_t(j))
\right)
$$

SuSu 当前输出边界：

$$
S_{\mathrm{SuSu}}=fitPositionsToVrm(\cdot)
$$

$$
Q^{H,\mathrm{output}}=I^{H}
$$

## 禁止出现的错误

- 把 VRM 说成 SMPL-H/SMPL-X 一类参数化人体模型。
- 把 HumanML3D 263D 当成 SMPL pose。
- 把 BEAT 套用 AMASS 的 `z_up_to_y_up` basis。
- 把 Motion-X 的 translation 单位保护省略。
- 把 SuSu 6D 写成旧的列主序两列重建逻辑。
- 声称 SuSu 当前最终 output 已经使用 hand local quats。
- 把 face/audio/object/expression 混入 humanoid bone FK。
