# HumanML3D 263D 到 VRM 的 retarget 数学

覆盖数据集：HumanML3D，以及 AMASS HumanAct12 `.npy` 这类 position sequence 旁路。对应代码：`HumanML3DAdapter`、`HumanML3D263Codec`、`PositionSequenceCodec`、`fit_positions_to_vrm()`。

HumanML3D 在 VIREA 中不是 SMPL-H axis-angle，也不是 SMPL-X fullpose。它首先被解释为 motion feature：

$$
M\in\mathbb{R}^{T\times263}
$$

然后解码为 positions，再通过 position fitting 生成 VRM 局部四元数：

$$
\mathrm{263D\ feature}\rightarrow
\mathrm{22\ joint\ positions}\rightarrow
\mathrm{BodyBones\ positions}\rightarrow
\mathrm{VRM\ local\ quaternions}
$$

## 1. parquet 读取

`HumanML3DAdapter.load()` 要求 sample id 为：

$$
\mathrm{SampleId}=\mathrm{split}/\mathrm{shard}/\mathrm{row}
$$

读取：

$$
\mathrm{path}=\mathrm{RawRoot}/\mathrm{data}/(\mathrm{shard}+\mathrm{.parquet})
$$

row 中：

$$
M=\mathrm{row}[\mathrm{motion}]\in\mathbb{R}^{T\times263}
$$

文本：

$$
c=\mathrm{row}[\mathrm{caption}]
$$

metadata：

$$
\mathrm{NumFrames}=
\begin{cases}
\mathrm{MetaData}[\mathrm{NumFrames}],&\mathrm{if\ present}\\
T,&\mathrm{otherwise}
\end{cases}
$$

fps 固定为：

$$
f=20
$$

annotations 来自 caption 行。代码取第一个井号分隔符之前的文本；令 $h$ 表示这个截断函数：

$$
a_i=\mathrm{strip}(h(c_i))
$$

这些 annotations 不参与姿态数学。

## 2. 263D 不是 pose 参数

代码没有把 $M$ 切成 axis-angle，也没有将其解释为 SMPL pose。当前 `HumanML3D263Codec._decode_positions()` 的输入输出是：

$$
decode:\mathbb{R}^{T\times263}\rightarrow
\left(X\in\mathbb{R}^{T\times J\times3},\ N,\ \mathrm{meta}\right)
$$

其中 $X$ 是关节位置，$N$ 是 joint names。

## 3. 优先解码路径

若 `VIREA_TMR_SRC` 存在并可导入：

$$
X=guofeatsToJoints(M)
$$

代码实际调用：

$$
X=
cpu\left(
detach\left(
guofeatsToJoints(torch.tensor(M,\mathrm{float32}))
\right)
\right)
$$

并转为：

$$
X\in\mathbb{R}^{T\times J\times3},\qquad X.\mathrm{dtype}=\mathrm{float32}
$$

joint names：

$$
N=\mathrm{JointNames}[\mathrm{guoh3djoints}]
$$

metadata：

$$
\mathrm{HumanmlDecoder}=\mathrm{GuofeatsToJoints}
$$

## 4. fallback 解码路径

如果导入或解码失败，代码不报错，而是生成 fallback rest-pose preview。设：

$$
T=M.\mathrm{shape}[0]
$$

先置：

$$
r_t=[0,0,0]
$$

如果 feature 维度至少为 $3$：

$$
r_{t,xz}=\left(\sum_{\tau=0}^{t}M_{\tau,0:2}\right)\cdot0.03
$$

具体代码只写入 $x$ 和 $z$：

$$
r_t[0]=0.03\sum_{\tau=0}^{t}M_{\tau,0},\qquad
r_t[2]=0.03\sum_{\tau=0}^{t}M_{\tau,1}
$$

然后：

$$
S_{\mathrm{fallback}}=pack(r)
$$

其中 root rotation、core、hand 都是单位四元数。fallback positions：

$$
X_{\mathrm{fallback}}=
FK(S_{\mathrm{fallback}},\bar{o})_{[:,0:22]}
$$

names：

$$
N=\mathrm{FkBones}_{0:22}
$$

metadata：

$$
\mathrm{HumanmlDecoder}=\mathrm{FallbackRestPose}
$$

$$
\mathrm{DecoderError}=\mathrm{str}(\mathrm{exception})
$$

因此 fallback 是 pipeline 保底，不是高质量 HumanML3D 真实解码。

## 5. joint name 映射

`PositionSequenceCodec` 先把 source joint names 映射到 canonical。映射表 `GUOH3D_TO_CANONICAL` 定义：

$$
g(\mathrm{pelvis})=\mathrm{hips}
$$

$$
g(\mathrm{LeftHip})=\mathrm{leftUpperLeg},\qquad
g(\mathrm{RightHip})=\mathrm{rightUpperLeg}
$$

$$
g(\mathrm{spine1})=\mathrm{spine},\quad
g(\mathrm{spine2})=\mathrm{chest},\quad
g(\mathrm{spine3})=\mathrm{upperChest}
$$

$$
g(\mathrm{LeftWrist})=\mathrm{leftHand},\qquad
g(\mathrm{RightWrist})=\mathrm{rightHand}
$$

完整映射见代码中的 `GUOH3D_TO_CANONICAL`。

对 source positions $X\in\mathbb{R}^{T\times J\times3}$，代码遍历 source index $i$：

$$
n_i=
\begin{cases}
\mathrm{clip.sourceJointNames}_i,&\mathrm{if\ provided}\\
\mathrm{DefaultJointNames}_i,&\mathrm{otherwise}
\end{cases}
$$

$$
m_i=
\begin{cases}
g(n_i),&n_i\in dom(g)\\
n_i,&\mathrm{otherwise}
\end{cases}
$$

若 $m_i\in\mathrm{FkBones}$ 且之前未出现，则加入 mapped set：

$$
M=\{m_i\}
$$

positions 收集为：

$$
Y_{:,k,:}=X_{:,i_k,:},\qquad m_{i_k}\in M
$$

若没有任何 mapped positions：

$$
M=[\mathrm{hips}],\qquad Y\in\mathbb{R}^{T\times1\times3},\quad Y_{t,0}=[0,0,0]
$$

## 6. BODY bones 对齐

`body_positions_from_fk_positions(Y, mapped_names)` 生成：

$$
B_{\mathrm{pos}}\in\mathbb{R}^{T\times22\times3}
$$

初始化为零：

$$
B_{\mathrm{pos},t,j}=[0,0,0]
$$

对每个 body bone $b\in B_{\mathrm{body}}$，若 $b\in M$。令 $I_B$ 表示代码中的 `BODY_INDEX`，令 $I_M$ 表示 mapped set 中的索引函数：

$$
B_{\mathrm{pos}}(t,I_B(b))=Y(t,I_M(b))
$$

未映射骨骼保持零。这一点很重要：position fitting 会尝试拟合存在的 primary child，缺失骨骼会退化为单位旋转或父旋转继承。

## 7. world basis

`HumanML3D263Codec` 继承 `PositionSequenceCodec`，默认：

$$
\mathrm{WorldBasis}=\mathrm{ZUpToYUp}
$$

因此：

$$
B=
\begin{bmatrix}
1&0&0\\
0&0&1\\
0&-1&0
\end{bmatrix}
$$

`fit_positions_to_vrm()` 首先做：

$$
X'_t(j)=B B_{\mathrm{pos},t}(j)
$$

## 8. position scale 与中心化

scale：

$$
\lambda=
\frac{\sum_{C\in K}\sum_{j\in C}\|\bar{o}_j\|}
{\sum_{C\in K}\sum_{j\in C}\|X'_0(j)-X'_0(\pi_C(j))\|}
$$

positions 缩放：

$$
X''_t(j)=\lambda X'_t(j)
$$

root translation：

$$
r_t=X''_t(\mathrm{hips})-X''_0(\mathrm{hips})
$$

centered positions：

$$
Y_t(j)=X''_t(j)-X''_0(\mathrm{hips})
$$

并强制：

$$
Y_t(\mathrm{hips})=r_t
$$

## 9. root rotation 拟合

target spine rest offset：

$$
\bar{o}_{\mathrm{spine}}
$$

若 $\|\bar{o}_{\mathrm{spine}}\|\ge10^{-6}$，每帧计算：

$$
d_t^{\mathrm{spine}}=Y_t(\mathrm{spine})-Y_t(\mathrm{hips})
$$

若 $\|d_t^{\mathrm{spine}}\|\ge10^{-6}$：

$$
q_t^{\mathrm{root}}=Rot(\bar{o}_{\mathrm{spine}}\to d_t^{\mathrm{spine}})
$$

否则：

$$
q_t^{\mathrm{root}}=[0,0,0,1]
$$

## 10. core bones 的 direction fitting

对每个 $j\in C$，取 primary child：

$$
\chi(j)=\mathrm{PrimaryChild}[j]
$$

若 $\chi(j)$ 或 $j$ 不在 `BODY_INDEX`，代码不拟合该骨骼，而是：

$$
Q_t(j)=Q_t(\pi(j))
$$

若 child 有效，取父 world rotation：

$$
Q_t(\pi(j))
$$

desired world direction：

$$
d_t^{\mathrm{world}}=Y_t(\chi(j))-Y_t(j)
$$

若 $\|d_t^{\mathrm{world}}\|<10^{-6}$，保持单位局部旋转：

$$
q_t^j=[0,0,0,1]
$$

否则转到父局部坐标：

$$
d_t^{\mathrm{local}}=
R(Q_t(\pi(j))^{-1})d_t^{\mathrm{world}}
$$

局部旋转：

$$
q_t^j=Rot(\bar{o}_{\chi(j)}\to d_t^{\mathrm{local}})
$$

world rotation 递推：

$$
Q_t(j)=Q_t(\pi(j))q_t^j
$$

## 11. canonical 输出

HumanML3D/position sequence 当前没有 hand rotations：

$$
q_t^{k,\mathrm{hand}}=[0,0,0,1],\qquad k\in H
$$

打包：

$$
S=pack(r,q^{\mathrm{root}},\{q^j\}_{j\in C},I^{H})
$$

target positions：

$$
P^{\mathrm{target}}=FK(S,\bar{o})
$$

metadata：

$$
\mathrm{PositionToRotation}=\mathrm{PositionFitToVrm}
$$

$$
\mathrm{RetargetScale}=\lambda
$$

$$
\mathrm{NativeJointNames}=N
$$

## 12. source preview

`HumanML3D263Codec.extract_source()` 同样先 decode：

$$
X,N,\mathrm{meta}=decode(M)
$$

然后将 names 映射到 canonical names：

$$
\tilde{n}_i=g(n_i)\ \mathrm{if\ exists,\ else}\ n_i
$$

生成 body positions：

$$
B_{\mathrm{pos}}=bodyPositionsFromFkPositions(X,\tilde{N})
$$

再调用 `source_positions_normalized()`：

$$
\hat{X}=B B_{\mathrm{pos}}
$$

$$
\hat{X}'=\lambda_{\mathrm{pos}}\hat{X}
$$

$$
\hat{X}'_t(j)\leftarrow
\hat{X}'_t(j)-\hat{X}'_0(\mathrm{hips})
$$

输出是 source/before preview，不是最终 VRM FK。

## 13. AMASS HumanAct12 position sequence 旁路

AMASS adapter 对 `humanact12/*.npy` 设置：

$$
\mathrm{positions}\in\mathbb{R}^{T\times J\times3},\qquad
\mathrm{CodecKey}=\mathrm{PositionSequence},\qquad f=20
$$

其数学路径从本文第 $5$ 节开始，不经过 HumanML3D 263D decode：

$$
\mathrm{positions}\rightarrow
\mathrm{joint\ name\ mapping}\rightarrow
\mathrm{body\ positions}\rightarrow
fitPositionsToVrm
$$
