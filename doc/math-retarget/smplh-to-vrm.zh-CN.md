# SMPL-H / SMPL body 到 VRM 的 retarget 数学

覆盖数据集：AMASS、BABEL。对应代码：`AMASSAdapter`、`BABELAdapter`、`AxisAngleBody22Codec`、`retarget_named_quats_to_vrm()`。

AMASS 和 BABEL 在 VIREA 中共享同一个数学主路径。BABEL 的 annotation 只改变 text/metadata，不改变 pose tensor 的解释。主路径是：

$$
\mathrm{SMPL/SMPL\text{-}H\ axis\text{-}angle}\rightarrow
\mathrm{22\ body\ local\ quaternions}\rightarrow
\mathrm{rest\ corrected\ VRM\ local\ quaternions}
$$

## 1. adapter 读取与输入张量

AMASS `.npz` 读取：

$$
\mathrm{poses}\in\mathbb{R}^{T\times D},\qquad
\mathrm{trans}\in\mathbb{R}^{T\times3}
$$

若 `trans` 缺失，代码置零：

$$
\mathrm{trans}_t=[0,0,0]
$$

fps 读取为：

$$
f=
\begin{cases}
\mathrm{mocap\_framerate},&\mathrm{if\ present}\\
\mathrm{mocap\_frame\_rate},&\mathrm{if\ present}\\
60,&\mathrm{otherwise}
\end{cases}
$$

BABEL 如果 sample id 来自 `babel-teach/{split}/{key}`，先通过 `feat_p` 定位 carrier motion：

$$
\mathrm{path}=
\begin{cases}
\mathrm{raw\_root}/\mathrm{feat\_p},&\mathrm{exists}\\
\mathrm{raw\_root.parent}/\mathrm{amass}/\mathrm{feat\_p},&\mathrm{fallback}
\end{cases}
$$

然后读取同样的 $\mathrm{poses}$、$\mathrm{trans}$、$f$。annotation record $\mathcal{A}$ 只进入：

$$
\mathrm{annotations},\quad \mathrm{text},\quad \mathrm{metadata}
$$

不参与下面任何旋转或 FK 计算。

## 2. body pose 切片

`AxisAngleBody22Codec._body_quats()` 要求：

$$
D\ge 22\cdot3=66
$$

代码只取前 $66$ 维：

$$
A=\operatorname{reshape}\left(\mathrm{poses}_{[:,0:66]},T,22,3\right)
$$

其中 $A_{t,i}\in\mathbb{R}^3$ 是第 $t$ 帧第 $i$ 个 body joint 的 axis-angle。

若 $\mathrm{poses}$ 不是二维或 $D<66$，代码抛出错误：

$$
\mathrm{ValueError}(\mathrm{expected\ body\ axis\text{-}angle\ block})
$$

## 3. axis-angle 转 body quaternions

对每个 $A_{t,i}$：

$$
\theta_{t,i}=\|A_{t,i}\|_2
$$

$$
u_{t,i}=\frac{A_{t,i}}{\max(\theta_{t,i},10^{-8})}
$$

$$
q_{t,i}=
\left[
u_x\sin\frac{\theta_{t,i}}{2},\
u_y\sin\frac{\theta_{t,i}}{2},\
u_z\sin\frac{\theta_{t,i}}{2},\
\cos\frac{\theta_{t,i}}{2}
\right]
$$

若 $\theta_{t,i}<10^{-8}$：

$$
q_{t,i}=[0,0,0,1]
$$

最终得到：

$$
Q^{\mathrm{body}}\in\mathbb{R}^{T\times22\times4}
$$

## 4. 22 joint 顺序到 VIREA body bones

`BODY_BONES` 与 `CANONICAL_BODY_WITH_ROOT` 的顺序为：

$$
\mathcal{B}=[
\mathrm{hips},\mathrm{leftUpperLeg},\mathrm{rightUpperLeg},\mathrm{spine},
\ldots,\mathrm{leftHand},\mathrm{rightHand}
]
$$

因此索引映射是直接按位置：

$$
\phi(i)=\mathcal{B}_i,\qquad i=0,\ldots,21
$$

root rotation：

$$
q_t^{\mathrm{root,src}}=Q^{\mathrm{body}}_{t,\mathrm{BODY\_INDEX}(\mathrm{hips})}
$$

非 root 局部旋转：

$$
q_t^{j,\mathrm{src}}=
Q^{\mathrm{body}}_{t,\mathrm{BODY\_INDEX}(j)},\qquad j\in\mathcal{B}\setminus\{\mathrm{hips}\}
$$

这些值被传入 `local_quats_by_name`。

## 5. source profile 与 basis

AMASS/BABEL 进入默认 `AxisAngleBody22Codec()`：

$$
\mathrm{source\_profile}=\texttt{smplh\_body22}
$$

$$
\mathrm{world\_basis}=\texttt{z\_up\_to\_y\_up}
$$

source rest offsets 在当前构造中是 `DEFAULT_REST_OFFSETS`，记作 $o_j^{\mathrm{src}}$。target rest offsets 为 $\bar{o}_j$，可能来自 VRM rest inspection，也可能是默认模板。

basis 矩阵：

$$
B=
\begin{bmatrix}
1&0&0\\
0&0&1\\
0&-1&0
\end{bmatrix}
$$

## 6. root translation 的尺度和归零

`retarget_named_quats_to_vrm()` 先计算 rest scale：

$$
\lambda=
\frac{\sum_{C\in\mathcal{K}}\sum_{j\in C}\|\bar{o}_j\|_2}
{\sum_{C\in\mathcal{K}}\sum_{j\in C}\|o_j^{\mathrm{src}}\|_2}
$$

然后：

$$
r_t^0=\lambda\,\mathrm{trans}_t
$$

$$
r_t^1=r_t^0-r_0^0
$$

basis 后 root translation：

$$
r_t^{\mathrm{vrm}}=B r_t^1
$$

这对应代码：

$$
\texttt{target\_root\_translation = root\_translation * scale}
$$

$$
\texttt{target\_root\_translation -= target\_root\_translation[:1]}
$$

$$
\texttt{target\_root\_translation = rotate\_positions\_by\_matrix(..., B)}
$$

## 7. source FK 与 basis 后 source positions

代码先用 source rest offsets 做一次 FK，目的是生成 `source_positions` 供质量报告和 before/after 对齐分析：

$$
P_t^{\mathrm{src}}(\mathrm{hips})=r_t^1
$$

$$
Q_t^{\mathrm{src}}(\mathrm{hips})=q_t^{\mathrm{root,src}}
$$

$$
P_t^{\mathrm{src}}(j)=
P_t^{\mathrm{src}}(\pi(j))+
R(Q_t^{\mathrm{src}}(\pi(j)))\,o_j^{\mathrm{src}}
$$

$$
Q_t^{\mathrm{src}}(j)=
Q_t^{\mathrm{src}}(\pi(j))q_t^{j,\mathrm{src}}
$$

basis 后：

$$
P_t^{\mathrm{src,basis}}(j)=B P_t^{\mathrm{src}}(j)
$$

## 8. root rotation 的 basis 变换

根旋转从 source basis 转到 VRM basis：

$$
q_t^{\mathrm{root,basis}}=q(B)\,q_t^{\mathrm{root,src}}
$$

这里 $q(B)$ 由 `_quat_from_rotation_matrix(B)` 计算。局部 joint quaternions 不左乘 $q(B)$，因为它们不是世界旋转，而是 parent-local rotation。

## 9. rest correction 推导

对每个有 primary child 的骨骼 $j$，代码取 child $\chi(j)$。source child offset：

$$
u_j=o_{\chi(j)}^{\mathrm{src}}
$$

target child offset：

$$
v_j=\bar{o}_{\chi(j)}
$$

correction：

$$
c_j=\operatorname{Rot}(v_j\to u_j)
$$

root：

$$
q_t^{\mathrm{root,target}}=
\begin{cases}
q_t^{\mathrm{root,basis}}c_{\mathrm{hips}},&c_{\mathrm{hips}}\ \mathrm{exists}\\
q_t^{\mathrm{root,basis}},&\mathrm{otherwise}
\end{cases}
$$

每个 core bone $j\in\mathcal{C}$：

$$
\tilde{q}_t^j=\widehat{q_t^{j,\mathrm{src}}}
$$

若 $c_{\pi(j)}$ 存在：

$$
\tilde{q}_t^j\leftarrow c_{\pi(j)}^{-1}\tilde{q}_t^j
$$

若 $c_j$ 存在：

$$
\tilde{q}_t^j\leftarrow \tilde{q}_t^j c_j
$$

最终：

$$
q_t^{j,\mathrm{target}}=\widehat{\tilde{q}_t^j}
$$

这就是代码中：

$$
\texttt{mapped = inverse(parent\_correction) * mapped}
$$

和：

$$
\texttt{mapped = mapped * correction}
$$

的数学形式。

## 10. hand 输出

AMASS/BABEL 当前主路径没有传入 `hand_quats_by_name`，所以：

$$
q_t^{k,\mathrm{hand}}=[0,0,0,1],\qquad k\in\mathcal{H}
$$

也就是 `identity_quats(T, len(HAND_BONES))`。

## 11. canonical 输出

最终：

$$
S=\operatorname{pack}
\left(
r^{\mathrm{vrm}},
q^{\mathrm{root,target}},
\{q^{j,\mathrm{target}}\}_{j\in\mathcal{C}},
I^{\mathcal{H}}
\right)
$$

target positions：

$$
P^{\mathrm{target}}=\operatorname{FK}(S,\bar{o})
$$

`CanonicalResult` 中：

$$
\mathrm{retarget\_mode}=\texttt{direct\_local\_quaternion\_retarget}
$$

$$
\mathrm{retarget\_scale}=\lambda
$$

$$
\mathrm{declared\_world\_basis}=\texttt{z\_up\_to\_y\_up}
$$

## 12. source preview 的数学

`extract_source()` 调用 `source_fk_from_body_quats()`。它与上面共享 axis-angle 解码，但输出 source skeleton positions：

$$
\hat{r}_t=\lambda\mathrm{trans}_t-\lambda\mathrm{trans}_0
$$

$$
\hat{P}^{\mathrm{src}}=\operatorname{FK}(\hat{r},q^{\mathrm{root,src}},q^{j,\mathrm{src}},o^{\mathrm{src}})
$$

若启用 basis：

$$
\hat{P}^{\mathrm{src,basis}}=B\hat{P}^{\mathrm{src}}
$$

最后再以第一帧 hips 居中：

$$
\hat{P}_t(j)\leftarrow
\hat{P}_t(j)-\hat{P}_0(\mathrm{hips})
$$

这解释了 before preview 的语义：它是源骨架解释结果，不是 VRM target FK。

## 13. AMASS 的 HumanAct12 旁路

`AMASSAdapter` 还支持 `humanact12/*.npy`。这不是 SMPL-H direct quaternion path，而是：

$$
\mathrm{positions}\in\mathbb{R}^{T\times J\times3}
$$

并设置：

$$
\mathrm{codec\_key}=\texttt{position\_sequence},\qquad f=20
$$

它走 [HumanML3D/position fitting](humanml3d-263d-to-vrm.zh-CN.md) 中描述的 `PositionSequenceCodec` 逻辑，而不是本文的 axis-angle 逻辑。

