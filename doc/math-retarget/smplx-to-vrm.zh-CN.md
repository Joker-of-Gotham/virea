# SMPL-X 到 VRM 的 retarget 数学

覆盖数据集：GRAB、Motion-X。对应代码：`GRABAdapter`、`MotionXAdapter`、`SMPLXFullposeCodec`、`retarget_named_quats_to_vrm()`。

SMPL-X 路径和 SMPL-H 路径共享 direct local quaternion retarget，但输入是 $55$ joint fullpose，并额外映射 hands。数学主线是：

$$
\mathrm{SMPL{-}X\ fullpose}\in\mathbb{R}^{T\times165}
\rightarrow
Q^{55}\in\mathbb{R}^{T\times55\times4}
\rightarrow
\mathrm{body+hand\ VRM\ local\ quaternions}
$$

## 1. GRAB adapter 读取

GRAB `.npz` 中：

$$
\mathrm{fullpose}=\mathrm{payload}[\mathrm{body}].\mathrm{item}()[\mathrm{params}][\mathrm{fullpose}]
\in\mathbb{R}^{T\times D}
$$

$$
\mathrm{translation}=
\mathrm{payload}[\mathrm{body}].\mathrm{item}()[\mathrm{params}][\mathrm{transl}]
\in\mathbb{R}^{T\times3}
$$

若 `transl` 缺失：

$$
\mathrm{translation}_t=[0,0,0]
$$

fps：

$$
f=
\begin{cases}
\mathrm{payload}[\mathrm{framerate}],&\mathrm{if\ present}\\
120,&\mathrm{otherwise}
\end{cases}
$$

metadata 显式写入：

$$
\mathrm{DeclaredWorldBasis}=\mathrm{ZUpToYUp}
$$

## 2. Motion-X adapter 读取

Motion-X `.npy` 要求：

$$
A\in\mathbb{R}^{T\times322}
$$

若 $A$ 不是二维或第二维小于 $322$，代码报错。切片为：

$$
\mathrm{fullpose}=A_{[:,0:165]}
$$

$$
\mathrm{FaceExpr}=A_{[:,159:209]}
$$

$$
\mathrm{translation}^{\mathrm{raw}}=A_{[:,309:312]}
$$

translation 单位保护逻辑为：

$$
\Delta=ptp(\mathrm{translation}^{\mathrm{raw}},\mathrm{axis}=0)
$$

$$
\eta=
\begin{cases}
0.01,&\max|\Delta|>20\ \mathrm{or}\ percentile_{95}(|\mathrm{translation}^{\mathrm{raw}}|)>20\\
1.0,&\mathrm{otherwise}
\end{cases}
$$

$$
\mathrm{translation}=\eta\,\mathrm{translation}^{\mathrm{raw}}
$$

fps 固定为：

$$
f=30
$$

metadata 显式写入：

$$
\mathrm{DeclaredWorldBasis}=\mathrm{IdentityYUp}
$$

## 3. fullpose 到 55 个四元数

`SMPLXFullposeCodec.to_canonical()` 要求：

$$
D\ge165
$$

取前 $165$ 维：

$$
A=reshape\left(\mathrm{fullpose}_{[:,0:165]},T,55,3\right)
$$

axis-angle 到 quaternion：

$$
Q^{55}_{t,i}=q(A_{t,i})
$$

其中 $q(\cdot)$ 是：

$$
q(a)=
\left[
\frac{a_x}{\|a\|}\sin\frac{\|a\|}{2},\
\frac{a_y}{\|a\|}\sin\frac{\|a\|}{2},\
\frac{a_z}{\|a\|}\sin\frac{\|a\|}{2},\
\cos\frac{\|a\|}{2}
\right]
$$

并带有 $\|a\|<10^{-8}$ 的单位四元数分支。

## 4. body 映射

前 $22$ 个 SMPL-X body joints 按 `CANONICAL_BODY_WITH_ROOT` 解释：

$$
q_t^{\mathrm{root,src}}=Q^{55}(t,I_B(\mathrm{hips}))
$$

$$
q_t^{j,\mathrm{body,src}}=Q^{55}(t,I_B(j)),\qquad j\in B\setminus\{\mathrm{hips}\}
$$

代码还先创建了 `core`：

$$
Q^{C}_{\mathrm{raw}}(t,I_C(j))=Q^{55}(t,I_B(j))
$$

但真正传给 `retarget_named_quats_to_vrm()` 的 body 输入是：

$$
\mathrm{LocalQuatsByName}=\{j\mapsto Q^{55}(:,I_B(j))\mid j\in B,j\neq\mathrm{hips}\}
$$

其中 $I_B$ 表示代码中的 `BODY_INDEX`，$I_C$ 表示代码中的 `CORE_INDEX`。

## 5. hand 映射

`SMPLX_HAND_INDEX` 定义从 SMPL-X fullpose index 到 canonical hand bone 的映射。记该映射为：

$$
\psi:H_{\mathrm{mapped}}\rightarrow\{25,\ldots,54\}
$$

例如：

$$
\psi(\mathrm{leftIndexProximal})=25,\quad
\psi(\mathrm{leftIndexIntermediate})=26,\quad
\psi(\mathrm{leftIndexDistal})=27
$$

$$
\psi(\mathrm{rightThumbProximal})=52,\quad
\psi(\mathrm{rightThumbIntermediate})=53,\quad
\psi(\mathrm{rightThumbDistal})=54
$$

代码先初始化：

$$
Q_t^{k,\mathrm{hand,raw}}=[0,0,0,1],\qquad k\in H
$$

若 $\psi(k)<55$ 且 $k\in H$：

$$
Q_t^{k,\mathrm{hand,raw}}=Q^{55}_{t,\psi(k)}
$$

然后传入：

$$
\mathrm{HandQuatsByName}=\{k\mapsto Q^{k,\mathrm{hand,raw}}\mid k\in H\}
$$

## 6. basis 选择函数

`_world_basis_for_clip()` 的逻辑可写为：

$$
b=
\begin{cases}
\mathrm{metadata}[\mathrm{DeclaredWorldBasis}],&\mathrm{if\ present}\\
\mathrm{metadata}[\mathrm{WorldBasis}],&\mathrm{if\ present\ and\ string}\\
\mathrm{ZUpToYUp},&\mathrm{dataset}=\mathrm{grab}\\
\mathrm{IdentityYUp},&\mathrm{otherwise}
\end{cases}
$$

因此：

$$
B_{\mathrm{GRAB}}=
\begin{bmatrix}
1&0&0\\
0&0&1\\
0&-1&0
\end{bmatrix}
$$

$$
B_{\mathrm{MotionX}}=
\begin{bmatrix}
1&0&0\\
0&1&0\\
0&0&1
\end{bmatrix}
$$

这就是为什么同为 SMPL-X，GRAB 和 Motion-X 仍必须分开写 dataset profile。

## 7. direct retarget 的完整公式

SMPL-X 路径调用：

$$
retargetNamedQuatsToVrm
\left(
\mathrm{translation},
q^{\mathrm{root,src}},
\{q^{j,\mathrm{body,src}}\},
o^{\mathrm{body,src}},
\{q^{k,\mathrm{hand,raw}}\},
o^{\mathrm{hand,src}},
b
\right)
$$

当前代码中：

$$
o^{\mathrm{body,src}}=\mathrm{DefaultRestOffsets}
$$

$$
o^{\mathrm{hand,src}}=\mathrm{DefaultRestOffsets}
$$

scale：

$$
\lambda=
\frac{\sum_{C\in K}\sum_{j\in C}\|\bar{o}_j\|}
{\sum_{C\in K}\sum_{j\in C}\|o_j^{\mathrm{src}}\|}
$$

root：

$$
r_t^{\mathrm{vrm}}=B(\lambda\,\mathrm{translation}_t-\lambda\,\mathrm{translation}_0)
$$

root rotation：

$$
q_t^{\mathrm{root,basis}}=q(B)q_t^{\mathrm{root,src}}
$$

body correction：

$$
c_j^{\mathrm{body}}=Rot(\bar{o}_{\chi(j)}\to o_{\chi(j)}^{\mathrm{body,src}})
$$

body target local quaternion：

$$
q_t^{j,\mathrm{target}}=
\widehat{
\left(c_{\pi(j)}^{\mathrm{body}}\right)^{-1}
q_t^{j,\mathrm{body,src}}
c_j^{\mathrm{body}}
}
$$

缺失 correction 时相应因子省略。

hand correction：

$$
c_k^{\mathrm{hand}}=Rot(\bar{o}_{\chi(k)}\to o_{\chi(k)}^{\mathrm{hand,src}})
$$

hand target local quaternion 使用 body 与 hand correction 合并后的父 correction：

$$
q_t^{k,\mathrm{target}}=
\widehat{
\left(c_{\pi(k)}^{\mathrm{all}}\right)^{-1}
q_t^{k,\mathrm{hand,raw}}
c_k^{\mathrm{hand}}
}
$$

其中：

$$
c^{\mathrm{all}}=c^{\mathrm{body}}\cup c^{\mathrm{hand}}
$$

## 8. target FK 输出

打包：

$$
S=pack
\left(
r^{\mathrm{vrm}},
q^{\mathrm{root,target}},
Q^{C,\mathrm{target}},
Q^{H,\mathrm{target}}
\right)
$$

target positions：

$$
P^{\mathrm{target}}=FK(S,\bar{o})
$$

metadata：

$$
\mathrm{codec}=\mathrm{SmplxFullpose}
$$

$$
\mathrm{SourceProfile}=\mathrm{SmplxFullpose55}
$$

$$
\mathrm{RetargetMode}=\mathrm{DirectLocalQuaternionRetarget}
$$

## 9. face、jaw、eyes、object 的边界

Motion-X 中：

$$
\mathrm{FaceExpr}=A_{[:,159:209]}
$$

GRAB 中：

$$
\mathrm{ObjectName},\quad \mathrm{contact},\quad \mathrm{gender}
$$

这些进入 `motion` 或 metadata/annotations，但不进入：

$$
S=[r,q^{\mathrm{root}},Q^{C},Q^{H}]
$$

即当前 VRM humanoid retarget 只覆盖 body + hands，不驱动 VRM expression、lookAt、jaw 或 object channel。

## 10. source preview

`extract_source()` 对 fullpose 执行同样的 $55$ joint axis-angle 解码，但只把 body 局部旋转传给 `source_fk_from_body_quats()`：

$$
\hat{P}^{\mathrm{src}}=
FK
\left(
\lambda\mathrm{translation}-\lambda\mathrm{translation}_0,
q^{\mathrm{root,src}},
\{q^{j,\mathrm{body,src}}\},
o^{\mathrm{src}}
\right)
$$

再 basis：

$$
\hat{P}^{\mathrm{src,basis}}=B\hat{P}^{\mathrm{src}}
$$

并以第一帧 hips 居中：

$$
\hat{P}_t(j)\leftarrow \hat{P}_t(j)-\hat{P}_0(\mathrm{hips})
$$

因此 source preview 当前不显示 SMPL-X hand FK，只显示 body source skeleton。processed preview 和真实 VRM avatar 则包含 hand quats。
