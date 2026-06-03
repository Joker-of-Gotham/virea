# SMPL-X 到 VRM 的 retarget 数学

覆盖数据集：GRAB、Motion-X。对应代码：`GRABAdapter`、`MotionXAdapter`、`SMPLXFullposeCodec`、`retarget_named_quats_to_vrm()`。

SMPL-X 路径和 SMPL-H 路径共享 direct local quaternion retarget，但输入是 $55$ joint fullpose，并额外映射 hands。数学主线是：

$$
\mathrm{SMPL\text{-}X\ fullpose}\in\mathbb{R}^{T\times165}
\rightarrow
Q^{55}\in\mathbb{R}^{T\times55\times4}
\rightarrow
\mathrm{body+hand\ VRM\ local\ quaternions}
$$

## 1. GRAB adapter 读取

GRAB `.npz` 中：

$$
\mathrm{fullpose}=\mathrm{payload}[\texttt{body}].\mathrm{item}()[\texttt{params}][\texttt{fullpose}]
\in\mathbb{R}^{T\times D}
$$

$$
\mathrm{translation}=
\mathrm{payload}[\texttt{body}].\mathrm{item}()[\texttt{params}][\texttt{transl}]
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
\mathrm{payload}[\texttt{framerate}],&\mathrm{if\ present}\\
120,&\mathrm{otherwise}
\end{cases}
$$

metadata 显式写入：

$$
\mathrm{declared\_world\_basis}=\texttt{z\_up\_to\_y\_up}
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
\mathrm{face\_expr}=A_{[:,159:209]}
$$

$$
\mathrm{translation}^{\mathrm{raw}}=A_{[:,309:312]}
$$

translation 单位保护逻辑为：

$$
\Delta=\operatorname{ptp}(\mathrm{translation}^{\mathrm{raw}},\mathrm{axis}=0)
$$

$$
\eta=
\begin{cases}
0.01,&\max|\Delta|>20\ \mathrm{or}\ \operatorname{percentile}_{95}(|\mathrm{translation}^{\mathrm{raw}}|)>20\\
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
\mathrm{declared\_world\_basis}=\texttt{identity\_y\_up}
$$

## 3. fullpose 到 55 个四元数

`SMPLXFullposeCodec.to_canonical()` 要求：

$$
D\ge165
$$

取前 $165$ 维：

$$
A=\operatorname{reshape}\left(\mathrm{fullpose}_{[:,0:165]},T,55,3\right)
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
q_t^{\mathrm{root,src}}=Q^{55}_{t,\mathrm{BODY\_INDEX}(\mathrm{hips})}
$$

$$
q_t^{j,\mathrm{body,src}}=Q^{55}_{t,\mathrm{BODY\_INDEX}(j)},\qquad j\in\mathcal{B}\setminus\{\mathrm{hips}\}
$$

代码还先创建了 `core`：

$$
Q^{\mathcal{C}}_{\mathrm{raw}}[t,\mathrm{CORE\_INDEX}(j)]=Q^{55}_{t,\mathrm{BODY\_INDEX}(j)}
$$

但真正传给 `retarget_named_quats_to_vrm()` 的 body 输入是：

$$
\mathrm{local\_quats\_by\_name}=\{j\mapsto Q^{55}_{:, \mathrm{BODY\_INDEX}(j)}\mid j\in\mathcal{B},j\neq\mathrm{hips}\}
$$

## 5. hand 映射

`SMPLX_HAND_INDEX` 定义从 SMPL-X fullpose index 到 canonical hand bone 的映射。记该映射为：

$$
\psi:\mathcal{H}_{\mathrm{mapped}}\rightarrow\{25,\ldots,54\}
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
Q_t^{k,\mathrm{hand,raw}}=[0,0,0,1],\qquad k\in\mathcal{H}
$$

若 $\psi(k)<55$ 且 $k\in\mathcal{H}$：

$$
Q_t^{k,\mathrm{hand,raw}}=Q^{55}_{t,\psi(k)}
$$

然后传入：

$$
\mathrm{hand\_quats\_by\_name}=\{k\mapsto Q^{k,\mathrm{hand,raw}}\mid k\in\mathcal{H}\}
$$

## 6. basis 选择函数

`_world_basis_for_clip()` 的逻辑可写为：

$$
b=
\begin{cases}
\mathrm{metadata}[\texttt{declared\_world\_basis}],&\mathrm{if\ present}\\
\mathrm{metadata}[\texttt{world\_basis}],&\mathrm{if\ present\ and\ string}\\
\texttt{z\_up\_to\_y\_up},&\mathrm{dataset}=\texttt{grab}\\
\texttt{identity\_y\_up},&\mathrm{otherwise}
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
\operatorname{retarget\_named\_quats\_to\_vrm}
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
o^{\mathrm{body,src}}=\texttt{DEFAULT\_REST\_OFFSETS}
$$

$$
o^{\mathrm{hand,src}}=\texttt{DEFAULT\_REST\_OFFSETS}
$$

scale：

$$
\lambda=
\frac{\sum_{C\in\mathcal{K}}\sum_{j\in C}\|\bar{o}_j\|}
{\sum_{C\in\mathcal{K}}\sum_{j\in C}\|o_j^{\mathrm{src}}\|}
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
c_j^{\mathrm{body}}=\operatorname{Rot}(\bar{o}_{\chi(j)}\to o_{\chi(j)}^{\mathrm{body,src}})
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
c_k^{\mathrm{hand}}=\operatorname{Rot}(\bar{o}_{\chi(k)}\to o_{\chi(k)}^{\mathrm{hand,src}})
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
S=\operatorname{pack}
\left(
r^{\mathrm{vrm}},
q^{\mathrm{root,target}},
Q^{\mathcal{C},\mathrm{target}},
Q^{\mathcal{H},\mathrm{target}}
\right)
$$

target positions：

$$
P^{\mathrm{target}}=\operatorname{FK}(S,\bar{o})
$$

metadata：

$$
\mathrm{codec}=\texttt{smplx\_fullpose}
$$

$$
\mathrm{source\_profile}=\texttt{smplx\_fullpose55}
$$

$$
\mathrm{retarget\_mode}=\texttt{direct\_local\_quaternion\_retarget}
$$

## 9. face、jaw、eyes、object 的边界

Motion-X 中：

$$
\mathrm{face\_expr}=A_{[:,159:209]}
$$

GRAB 中：

$$
\mathrm{object\_name},\quad \mathrm{contact},\quad \mathrm{gender}
$$

这些进入 `motion` 或 metadata/annotations，但不进入：

$$
S=[r,q^{\mathrm{root}},Q^{\mathcal{C}},Q^{\mathcal{H}}]
$$

即当前 VRM humanoid retarget 只覆盖 body + hands，不驱动 VRM expression、lookAt、jaw 或 object channel。

## 10. source preview

`extract_source()` 对 fullpose 执行同样的 $55$ joint axis-angle 解码，但只把 body 局部旋转传给 `source_fk_from_body_quats()`：

$$
\hat{P}^{\mathrm{src}}=
\operatorname{FK}
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

