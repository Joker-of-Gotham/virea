# BVH / BEAT 到 VRM 的 retarget 数学

覆盖数据集：BEAT。对应代码：`BEATAdapter`、`AxisAngleBody22Codec(source_profile="beat_bvh_body22", world_basis="identity_y_up")`。

BEAT 在 VIREA 中并不直接解析 `.bvh` 文本。当前读取的是上游整理后的 BVH-derived `.npz`，其中 body pose 已经表示为 $22$ joint axis-angle。因此数学上它复用 `AxisAngleBody22Codec`，但不能复用 AMASS/BABEL 的 basis。

## 1. BVH 一般数学背景

标准 BVH 给出一棵层级树。对 root：

$$
\mathrm{channels}_{\mathrm{root}}=
[p_x,p_y,p_z,\alpha_1,\alpha_2,\alpha_3]
$$

对普通 joint：

$$
\mathrm{channels}_{j}=[\alpha_1,\alpha_2,\alpha_3]
$$

如果 rotation order 是 $(a,b,c)$，对应局部旋转矩阵通常是：

$$
R_j=R_a(\alpha_a)R_b(\alpha_b)R_c(\alpha_c)
$$

不同 BVH 文件的 rotation order 会改变 $R_j$。但 BEAT adapter 当前读取的不是原始 channels，而是：

$$
\mathrm{poses}\in\mathbb{R}^{T\times D},\qquad D\ge66
$$

也就是说，BVH Euler/channel 到 axis-angle 的步骤已经在上游完成。VIREA 从这里开始：

$$
\mathrm{BVH\ channels}\rightarrow_{\mathrm{upstream}}\mathrm{axis{-}angle\ body22}
\rightarrow_{\mathrm{VIREA}}\mathrm{VRM}
$$

## 2. BEAT adapter 读取

读取路径：

$$
\mathrm{PosePath}=\mathrm{RawRoot}/\mathrm{pose}/\mathrm{speaker}/\mathrm{sample}.npz
$$

文本路径：

$$
\mathrm{TextPath}=\mathrm{RawRoot}/\mathrm{hf}/\mathrm{speaker}/\mathrm{sample}.txt
$$

动作张量：

$$
\mathrm{poses}\in\mathbb{R}^{T\times D},\qquad
\mathrm{trans}\in\mathbb{R}^{T\times3}
$$

若 `trans` 缺失：

$$
\mathrm{trans}_t=[0,0,0]
$$

fps：

$$
f=
\begin{cases}
\mathrm{payload}[\mathrm{fps}],&\mathrm{if\ present}\\
30,&\mathrm{otherwise}
\end{cases}
$$

adapter 输出：

$$
\mathrm{SourceFormat}=\mathrm{BeatBvhAxisAngleNpz}
$$

$$
\mathrm{CodecKey}=\mathrm{BeatAxisAngleBody22}
$$

文本 annotations 只进入：

$$
\mathrm{annotations},\quad \mathrm{text},\quad \mathrm{metadata}
$$

不参与 body FK。

## 3. codec 配置

`default_codecs()` 注册：

$$
\mathrm{BeatAxisAngleBody22}
=
AxisAngleBody22Codec
\left(
o^{\mathrm{src}}=\mathrm{DefaultRestOffsets},
\mathrm{SourceProfile}=\mathrm{BeatBvhBody22},
\mathrm{WorldBasis}=\mathrm{IdentityYUp}
\right)
$$

与 AMASS/BABEL 的差异是：

$$
\mathrm{BEAT}:\ B=I
$$

$$
\mathrm{AMASS/BABEL}:\ B=
\begin{bmatrix}
1&0&0\\
0&0&1\\
0&-1&0
\end{bmatrix}
$$

如果误把 BEAT 套用 AMASS/BABEL 的 $B$，数学上会变成：

$$
P_t'(j)=B_{\mathrm{ZUpToYUp}}P_t(j)
$$

这会把已经 Y-up 的对话手势整体旋转到错误平面。

## 4. axis-angle 切片与四元数

和 `AxisAngleBody22Codec._body_quats()` 一致：

$$
A=reshape\left(\mathrm{poses}_{[:,0:66]},T,22,3\right)
$$

对每个 $A_{t,i}$：

$$
\theta_{t,i}=\|A_{t,i}\|_2
$$

$$
q_{t,i}=
\left[
\frac{A_{t,i,x}}{\max(\theta_{t,i},10^{-8})}\sin\frac{\theta_{t,i}}{2},\
\frac{A_{t,i,y}}{\max(\theta_{t,i},10^{-8})}\sin\frac{\theta_{t,i}}{2},\
\frac{A_{t,i,z}}{\max(\theta_{t,i},10^{-8})}\sin\frac{\theta_{t,i}}{2},\
\cos\frac{\theta_{t,i}}{2}
\right]
$$

若 $\theta_{t,i}<10^{-8}$：

$$
q_{t,i}=[0,0,0,1]
$$

## 5. body 映射

BEAT 的 `.npz` 已被当前项目按 $22$ body order 解释：

$$
q_t^{\mathrm{root,src}}=q(t,I_B(\mathrm{hips}))
$$

$$
q_t^{j,\mathrm{src}}=q(t,I_B(j)),\qquad j\in B\setminus\{\mathrm{hips}\}
$$

其中 $B=B_{\mathrm{body}}$，$I_B$ 表示代码中的 `BODY_INDEX`。

## 6. direct quaternion retarget

BEAT 调用和 SMPL-H 同一个函数：

$$
retargetNamedQuatsToVrm
\left(
\mathrm{trans},
q^{\mathrm{root,src}},
\{q^{j,\mathrm{src}}\},
o^{\mathrm{src}},
\mathrm{WorldBasis}=\mathrm{IdentityYUp}
\right)
$$

scale：

$$
\lambda=
\frac{\sum_{C\in K}\sum_{j\in C}\|o_j^{T}\|}
{\sum_{C\in K}\sum_{j\in C}\|o_j^{\mathrm{src}}\|}
$$

root：

$$
r_t^{\mathrm{vrm}}=I(\lambda\mathrm{trans}_t-\lambda\mathrm{trans}_0)
=\lambda(\mathrm{trans}_t-\mathrm{trans}_0)
$$

root rotation basis：

$$
q_t^{\mathrm{root,basis}}=q(I)q_t^{\mathrm{root,src}}=q_t^{\mathrm{root,src}}
$$

rest correction：

$$
c_j=Rot(o_{\chi(j)}^{T}\to o_{\chi(j)}^{\mathrm{src}})
$$

$$
q_t^{j,\mathrm{target}}=
\widehat{
c_{\pi(j)}^{-1}q_t^{j,\mathrm{src}}c_j
}
$$

缺失 correction 时省略对应因子。hand 未传入，所以：

$$
q_t^{k,\mathrm{hand}}=[0,0,0,1],\qquad k\in H
$$

## 7. 输出和 fps 语义

输出 sequence：

$$
S=pack
\left(
r^{\mathrm{vrm}},
q^{\mathrm{root,target}},
Q^{C,\mathrm{target}},
I^{H}
\right)
$$

processed positions：

$$
P^{\mathrm{target}}=FK(S,o^{T})
$$

fps 保存在 `RawClip.motion["fps"]` 和 `SampleRef.fps` 中。播放时间应满足：

$$
t_{\mathrm{sec}}(n)=\frac{n}{f}
$$

而不能固定为：

$$
t_{\mathrm{sec}}(n)=\frac{n}{30}
$$

除非 $f=30$。BEAT 是语音手势数据，错误 fps 会破坏 gesture 和 text/audio annotation 的时间关系。

## 8. source preview

`extract_source()` 同样执行 source FK：

$$
\hat{P}^{\mathrm{src}}=
FK
\left(
\lambda\mathrm{trans}-\lambda\mathrm{trans}_0,
q^{\mathrm{root,src}},
\{q^{j,\mathrm{src}}\},
o^{\mathrm{src}}
\right)
$$

因为 $B=I$：

$$
\hat{P}^{\mathrm{src,basis}}=\hat{P}^{\mathrm{src}}
$$

最后以第一帧 hips 居中：

$$
\hat{P}_t(j)\leftarrow \hat{P}_t(j)-\hat{P}_0(\mathrm{hips})
$$

这说明 BEAT before preview 是 BVH-derived body skeleton 的解释结果；after preview 是 VRM target skeleton 的执行结果。
