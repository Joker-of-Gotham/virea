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
\mathrm{BODY\_BONES\ positions}\rightarrow
\mathrm{VRM\ local\ quaternions}
$$

## 1. parquet 读取

`HumanML3DAdapter.load()` 要求 sample id 为：

$$
\mathrm{sample\_id}=\mathrm{split}/\mathrm{shard}/\mathrm{row}
$$

读取：

$$
\mathrm{path}=\mathrm{raw\_root}/\texttt{data}/(\mathrm{shard}+\texttt{.parquet})
$$

row 中：

$$
M=\mathrm{row}[\texttt{motion}]\in\mathbb{R}^{T\times263}
$$

文本：

$$
c=\mathrm{row}[\texttt{caption}]
$$

metadata：

$$
\mathrm{num\_frames}=
\begin{cases}
\mathrm{meta\_data}[\texttt{num\_frames}],&\mathrm{if\ present}\\
T,&\mathrm{otherwise}
\end{cases}
$$

fps 固定为：

$$
f=20
$$

annotations 来自 caption 行：

$$
\mathrm{annotation}_i=\mathrm{strip}\left(\mathrm{split}(c_i,\#)[0]\right)
$$

这些 annotations 不参与姿态数学。

## 2. 263D 不是 pose 参数

代码没有把 $M$ 切成 axis-angle，也没有将其解释为 SMPL pose。当前 `HumanML3D263Codec._decode_positions()` 的输入输出是：

$$
\operatorname{decode}:\mathbb{R}^{T\times263}\rightarrow
\left(X\in\mathbb{R}^{T\times J\times3},\ \mathcal{N},\ \mathrm{meta}\right)
$$

其中 $X$ 是关节位置，$\mathcal{N}$ 是 joint names。

## 3. 优先解码路径

若 `VIREA_TMR_SRC` 存在并可导入：

$$
X=\operatorname{guofeats\_to\_joints}(M)
$$

代码实际调用：

$$
X=
\operatorname{cpu}\left(
\operatorname{detach}\left(
\operatorname{guofeats\_to\_joints}(\operatorname{torch.tensor}(M,\mathrm{float32}))
\right)
\right)
$$

并转为：

$$
X\in\mathbb{R}^{T\times J\times3},\qquad X.\mathrm{dtype}=\mathrm{float32}
$$

joint names：

$$
\mathcal{N}=\mathrm{JOINT\_NAMES}[\texttt{guoh3djoints}]
$$

metadata：

$$
\mathrm{humanml\_decoder}=\texttt{guofeats\_to\_joints}
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
S_{\mathrm{fallback}}=\operatorname{pack}(r)
$$

其中 root rotation、core、hand 都是单位四元数。fallback positions：

$$
X_{\mathrm{fallback}}=
\operatorname{FK}(S_{\mathrm{fallback}},\bar{o})_{[:,0:22]}
$$

names：

$$
\mathcal{N}=\mathrm{FK\_BONES}_{0:22}
$$

metadata：

$$
\mathrm{humanml\_decoder}=\texttt{fallback\_rest\_pose}
$$

$$
\mathrm{decoder\_error}=\mathrm{str}(\mathrm{exception})
$$

因此 fallback 是 pipeline 保底，不是高质量 HumanML3D 真实解码。

## 5. joint name 映射

`PositionSequenceCodec` 先把 source joint names 映射到 canonical。映射表 `GUOH3D_TO_CANONICAL` 定义：

$$
g(\mathrm{pelvis})=\mathrm{hips}
$$

$$
g(\mathrm{left\_hip})=\mathrm{leftUpperLeg},\qquad
g(\mathrm{right\_hip})=\mathrm{rightUpperLeg}
$$

$$
g(\mathrm{spine1})=\mathrm{spine},\quad
g(\mathrm{spine2})=\mathrm{chest},\quad
g(\mathrm{spine3})=\mathrm{upperChest}
$$

$$
g(\mathrm{left\_wrist})=\mathrm{leftHand},\qquad
g(\mathrm{right\_wrist})=\mathrm{rightHand}
$$

完整映射见代码中的 `GUOH3D_TO_CANONICAL`。

对 source positions $X\in\mathbb{R}^{T\times J\times3}$，代码遍历 source index $i$：

$$
n_i=
\begin{cases}
\mathrm{clip.source\_joint\_names}_i,&\mathrm{if\ provided}\\
\mathrm{default\_joint\_names}_i,&\mathrm{otherwise}
\end{cases}
$$

$$
m_i=
\begin{cases}
g(n_i),&n_i\in\operatorname{dom}(g)\\
n_i,&\mathrm{otherwise}
\end{cases}
$$

若 $m_i\in\mathrm{FK\_BONES}$ 且之前未出现，则加入 mapped set：

$$
\mathcal{M}=\{m_i\}
$$

positions 收集为：

$$
Y_{:,k,:}=X_{:,i_k,:},\qquad m_{i_k}\in\mathcal{M}
$$

若没有任何 mapped positions：

$$
\mathcal{M}=[\mathrm{hips}],\qquad Y\in\mathbb{R}^{T\times1\times3},\quad Y_{t,0}=[0,0,0]
$$

## 6. BODY_BONES 对齐

`body_positions_from_fk_positions(Y, mapped_names)` 生成：

$$
B_{\mathrm{pos}}\in\mathbb{R}^{T\times22\times3}
$$

初始化为零：

$$
B_{\mathrm{pos},t,j}=[0,0,0]
$$

对每个 body bone $b\in\mathrm{BODY\_BONES}$，若 $b\in\mathcal{M}$：

$$
B_{\mathrm{pos},t,\mathrm{BODY\_INDEX}(b)}
=
Y_{t,\mathrm{index}_{\mathcal{M}}(b)}
$$

未映射骨骼保持零。这一点很重要：position fitting 会尝试拟合存在的 primary child，缺失骨骼会退化为单位旋转或父旋转继承。

## 7. world basis

`HumanML3D263Codec` 继承 `PositionSequenceCodec`，默认：

$$
\mathrm{world\_basis}=\texttt{z\_up\_to\_y\_up}
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
\frac{\sum_{C\in\mathcal{K}}\sum_{j\in C}\|\bar{o}_j\|}
{\sum_{C\in\mathcal{K}}\sum_{j\in C}\|X'_0(j)-X'_0(\pi_C(j))\|}
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
q_t^{\mathrm{root}}=\operatorname{Rot}(\bar{o}_{\mathrm{spine}}\to d_t^{\mathrm{spine}})
$$

否则：

$$
q_t^{\mathrm{root}}=[0,0,0,1]
$$

## 10. core bones 的 direction fitting

对每个 $j\in\mathcal{C}$，取 primary child：

$$
\chi(j)=\mathrm{PRIMARY\_CHILD}[j]
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
q_t^j=\operatorname{Rot}(\bar{o}_{\chi(j)}\to d_t^{\mathrm{local}})
$$

world rotation 递推：

$$
Q_t(j)=Q_t(\pi(j))q_t^j
$$

## 11. canonical 输出

HumanML3D/position sequence 当前没有 hand rotations：

$$
q_t^{k,\mathrm{hand}}=[0,0,0,1],\qquad k\in\mathcal{H}
$$

打包：

$$
S=\operatorname{pack}(r,q^{\mathrm{root}},\{q^j\}_{j\in\mathcal{C}},I^{\mathcal{H}})
$$

target positions：

$$
P^{\mathrm{target}}=\operatorname{FK}(S,\bar{o})
$$

metadata：

$$
\mathrm{position\_to\_rotation}=\texttt{position\_fit\_to\_vrm}
$$

$$
\mathrm{retarget\_scale}=\lambda
$$

$$
\mathrm{native\_joint\_names}=\mathcal{N}
$$

## 12. source preview

`HumanML3D263Codec.extract_source()` 同样先 decode：

$$
X,\mathcal{N},\mathrm{meta}=\operatorname{decode}(M)
$$

然后将 names 映射到 canonical names：

$$
\tilde{n}_i=g(n_i)\ \mathrm{if\ exists,\ else}\ n_i
$$

生成 body positions：

$$
B_{\mathrm{pos}}=\operatorname{body\_positions\_from\_fk\_positions}(X,\tilde{\mathcal{N}})
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
\mathrm{codec\_key}=\texttt{position\_sequence},\qquad f=20
$$

其数学路径从本文第 $5$ 节开始，不经过 HumanML3D 263D decode：

$$
\mathrm{positions}\rightarrow
\mathrm{joint\ name\ mapping}\rightarrow
\mathrm{body\ positions}\rightarrow
\operatorname{fit\_positions\_to\_vrm}
$$

