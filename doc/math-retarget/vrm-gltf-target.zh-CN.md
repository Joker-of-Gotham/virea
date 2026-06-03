# VRM/glTF 目标层数学约定

本文把 VIREA 当前代码中的共同数学层完整写出。所有公式严格对应 `src/virea/motion/rotation.py`、`src/virea/motion/canonical.py`、`src/virea/motion/skeleton.py` 和 `src/virea/motion/retarget.py`。

## 1. 符号和张量形状

设帧数为 $T$。VIREA canonical skeleton 分成三组：

- root bone: $\mathrm{hips}$。
- body/core bones: $C$，数量 $N_C=21$，对应 `CORE_BONES`。
- hand bones: $H$，数量 $N_H=30$，对应 `HAND_BONES`。

完整 FK 输出骨骼集合为：

$$
F=\{\mathrm{hips}\}\cup C\cup H,\qquad N_F=52
$$

父节点映射由 `CANONICAL_PARENT` 给出，记作 $\pi(j)$。目标 rest offset 由 `target_rest_offsets_map()` 给出，记作 $\bar{o}_j\in\mathbb{R}^3$。如果没有外部 VRM rest template，$\bar{o}_j$ 退化为 `DEFAULT_REST_OFFSETS`。

每一帧 canonical sequence 的维度由 `FRAME_DIM` 定义：

$$
D_{\mathrm{frame}}=3+4+4N_C+4N_H=3+4+84+120=211
$$

第 $t$ 帧写作：

$$
s_t=\left[
r_t,\ q_t^{\mathrm{root}},\ \{q_t^j\}_{j\in C},\ \{q_t^k\}_{k\in H}
\right]\in\mathbb{R}^{211}
$$

其中 $r_t\in\mathbb{R}^3$ 是 root translation，所有四元数都按 glTF/three.js/VIREA 的 `xyzw` 顺序：

$$
q=[x,y,z,w]
$$

## 2. 四元数基础运算

代码中的归一化 `normalize_quat_xyzw()` 是：

$$
norm(q)=\sqrt{x^2+y^2+z^2+w^2}
$$

$$
\widehat{q}=\frac{q}{\max(norm(q),\epsilon)},\qquad \epsilon=10^{-8}
$$

四元数乘法 `quat_multiply_xyzw(q_1,q_2)` 先归一化两个输入。设 $q_1=[x_1,y_1,z_1,w_1]$，$q_2=[x_2,y_2,z_2,w_2]$，则：

$$
q_1q_2=
\begin{bmatrix}
w_1x_2+x_1w_2+y_1z_2-z_1y_2\\
w_1y_2-x_1z_2+y_1w_2+z_1x_2\\
w_1z_2+x_1y_2-y_1x_2+z_1w_2\\
w_1w_2-x_1x_2-y_1y_2-z_1z_2
\end{bmatrix}
$$

逆四元数 `quat_inverse_xyzw()` 在单位四元数假设下为共轭：

$$
q^{-1}=[-x,-y,-z,w]
$$

四元数转矩阵 `quat_to_matrix_xyzw()` 使用：

$$
R(q)=
\begin{bmatrix}
1-2(y^2+z^2)&2(xy-zw)&2(xz+yw)\\
2(xy+zw)&1-2(x^2+z^2)&2(yz-xw)\\
2(xz-yw)&2(yz+xw)&1-2(x^2+y^2)
\end{bmatrix}
$$

向量旋转 `quat_apply_xyzw(q,v)` 是：

$$
q\cdot v := R(q)v
$$

## 3. axis-angle 到四元数

`axis_angle_to_quat_xyzw()` 把源数据中的 axis-angle 向量 $a\in\mathbb{R}^3$ 转成四元数。代码逻辑是：

$$
\theta=\|a\|_2,\qquad u=\frac{a}{\max(\theta,\epsilon)}
$$

$$
q(a)=
\left[
u_x\sin\frac{\theta}{2},\
u_y\sin\frac{\theta}{2},\
u_z\sin\frac{\theta}{2},\
\cos\frac{\theta}{2}
\right]
$$

当 $\theta<10^{-8}$ 时，代码直接置为单位四元数：

$$
q(a)=[0,0,0,1]
$$

最后再次执行 $\widehat{q(a)}$。

## 4. 6D rotation 到四元数

SuSu 路径使用 `sixd_rows_to_quat_xyzw()`，它调用 `sixd_rows_to_matrix()`。给定 6D 向量 $d=[d_0,\ldots,d_5]$：

$$
a_1=[d_0,d_1,d_2],\qquad a_2=[d_3,d_4,d_5]
$$

Gram-Schmidt 步骤为：

$$
b_1=\frac{a_1}{\max(\|a_1\|,\epsilon)}
$$

$$
b_2' = a_2-(b_1^\top a_2)b_1,\qquad
b_2=\frac{b_2'}{\max(\|b_2'\|,\epsilon)}
$$

$$
b_3=b_1\times b_2
$$

`sixd_rows_to_matrix()` 与普通 `sixd_to_matrix()` 的区别在最后的 stack 轴。SuSu 当前采用 row-major first-two-rows：

$$
R_{\mathrm{rows}}(d)=
\begin{bmatrix}
b_1^\top\\
b_2^\top\\
b_3^\top
\end{bmatrix}
$$

然后 `matrix_to_quat_xyzw()` 将 $R_{\mathrm{rows}}$ 转为 $q=[x,y,z,w]$。该函数按矩阵 trace 分支实现稳定转换；若 $tr(R)>0$：

$$
\alpha=2\sqrt{tr(R)+1}
$$

$$
q=
\left[
\frac{R_{32}-R_{23}}{\alpha},\
\frac{R_{13}-R_{31}}{\alpha},\
\frac{R_{21}-R_{12}}{\alpha},\
\frac{\alpha}{4}
\right]
$$

其他分支按 $R_{11}$、$R_{22}$、$R_{33}$ 最大项分别计算，最后统一归一化。

## 5. 从两个方向构造旋转

`quat_from_two_vectors_xyzw(source,target)` 用在 rest correction 和 position fitting。设：

$$
u=\frac{\mathrm{source}}{\max(\|\mathrm{source}\|,\epsilon)},\qquad
v=\frac{\mathrm{target}}{\max(\|\mathrm{target}\|,\epsilon)}
$$

一般情况下构造：

$$
q_{u\to v}=\left[u\times v,\ 1+u^\top v\right]
$$

并归一化：

$$
\widehat{q}_{u\to v}=\frac{q_{u\to v}}{\max(\|q_{u\to v}\|,\epsilon)}
$$

当 $u^\top v<-0.999999$ 时，两个方向近似相反，代码选择一个 fallback axis。若 $|u_x|>0.9$，fallback 改用 $[0,1,0]$，否则用 $[1,0,0]$。令：

$$
n=\frac{u\times f}{\max(\|u\times f\|,\epsilon)}
$$

则 180 度旋转写作：

$$
q=[n_x,n_y,n_z,0]
$$

## 6. canonical sequence 的打包与解包

`pack_sequence()` 的数学形式是：

$$
S=
concat\left(
R,\ Q^{\mathrm{root}},\
reshape(Q^{C},T,4N_C),\
reshape(Q^{H},T,4N_H)
\right)
$$

其中：

$$
R\in\mathbb{R}^{T\times3},\quad
Q^{\mathrm{root}}\in\mathbb{R}^{T\times4},\quad
Q^{C}\in\mathbb{R}^{T\times21\times4},\quad
Q^{H}\in\mathbb{R}^{T\times30\times4}
$$

缺省旋转由 `identity_quats()` 给出：

$$
q_{\mathrm{id}}=[0,0,0,1]
$$

`unpack_sequence()` 反向切片：

$$
R=S[:,0:3],\qquad Q^{\mathrm{root}}=S[:,3:7]
$$

$$
Q^{C}=reshape(S[:,7:91],T,21,4)
$$

$$
Q^{H}=reshape(S[:,91:211],T,30,4)
$$

## 7. 前向运动学 FK

`forward_kinematics()` 使用 target 或 source rest offsets。对每帧 $t$：

$$
P_t(\mathrm{hips})=r_t,\qquad Q_t(\mathrm{hips})=\widehat{q_t^{\mathrm{root}}}
$$

对任意非 root 骨骼 $j$：

$$
P_t(j)=P_t(\pi(j))+R(Q_t(\pi(j)))\,o_j
$$

$$
Q_t(j)=Q_t(\pi(j))\,q_t(j)
$$

代码中的遍历顺序是 `CORE_BONES` 再 `HAND_BONES`，保证父节点已经计算。若某个局部旋转缺失，则使用 $q_{\mathrm{id}}$。

`forward_kinematics_from_sequence()` 先解包 $S$，再把每个 canonical bone 的局部四元数放入 `local_quats`，最后用 `target_rest_offsets_map()` 计算：

$$
P^{\mathrm{target}}=FK(S,\bar{o})
$$

这就是 processed/after preview 和 VRM target positions 的来源。

## 8. 世界坐标 basis

`resolve_world_basis()` 把 source world basis 转成目标 glTF/VRM basis。目标约定为 $+Y$ up、$+Z$ forward、meter。显式矩阵有三种：

$$
B_{\mathrm{IdentityYUp}}=
\begin{bmatrix}
1&0&0\\
0&1&0\\
0&0&1
\end{bmatrix}
$$

$$
B_{\mathrm{ZUpToYUp}}=
\begin{bmatrix}
1&0&0\\
0&0&1\\
0&-1&0
\end{bmatrix}
$$

$$
B_{\mathrm{NegZUpToYUp}}=
\begin{bmatrix}
1&0&0\\
0&0&-1\\
0&1&0
\end{bmatrix}
$$

位置变换由 `rotate_positions_by_matrix()` 实现：

$$
x'_t = Bx_t
$$

根旋转变换在 direct quaternion retarget 中实现为：

$$
q_t^{\mathrm{root}\prime}=q(B)\,q_t^{\mathrm{root}}
$$

这里 $q(B)$ 由 `_quat_from_rotation_matrix()` 得到。

如果没有显式 basis，`infer_clip_world_basis()` 从 source positions 估计。它先计算上身和下身中心：

$$
u_t=\frac{1}{N_U}\sum_{j\in U}P_t(j),\qquad
\ell_t=\frac{1}{N_L}\sum_{j\in L}P_t(j)
$$

其中 $U=\{\mathrm{head},\mathrm{neck},\mathrm{upperChest},\mathrm{chest}\}$，$N_U=4$；$L=\{\mathrm{leftFoot},\mathrm{rightFoot},\mathrm{leftToes},\mathrm{rightToes}\}$，$N_L=4$。锚帧为：

$$
t^\*=argmax_t \|u_t-\ell_t\|_\infty
$$

up axis 取 $u_{t^\*}-\ell_{t^\*}$ 中绝对值最大的坐标轴。left axis 来自左右骨骼对在去除 up 分量后的平均；forward axis 优先来自脚趾方向，其次 root trajectory，再其次 torso。最后矩阵是：

$$
B=
\begin{bmatrix}
\mathrm{left}^\top\\
\mathrm{up}^\top\\
\mathrm{forward}^\top
\end{bmatrix}
$$

当前各 adapter/codec 基本都显式给出 basis；推断只是 fallback。

## 9. 尺度估计

代码中有两种 scale。

### 9.1 从 rest offsets 估计

`_target_scale_from_rest_offsets(source_rest_offsets)` 用于 direct quaternion retarget。稳定链集合为 `STABLE_SCALE_CHAINS`，记为 $K$。每条链 $C\in K$ 是若干骨骼名的序列。source rest offset 为 $o_j^{\mathrm{src}}$，target rest offset 为 $\bar{o}_j$：

$$
\lambda_{\mathrm{rest}}=
\frac{\sum_{C\in K}\sum_{j\in C}\|\bar{o}_j\|_2}
{\sum_{C\in K}\sum_{j\in C}\|o_j^{\mathrm{src}}\|_2}
$$

如果分母小于 $10^{-6}$，代码返回 $1$。

### 9.2 从 positions 估计

`_target_scale_from_positions(body_positions)` 用于 position fitting。它只看第 $0$ 帧。对链中每个骨骼 $j$，父节点按代码变量 `parent` 从 $\mathrm{hips}$ 开始逐步更新。source 长度来自观测 positions：

$$
\lambda_{\mathrm{pos}}=
\frac{\sum_{C\in K}\sum_{j\in C}\|\bar{o}_j\|_2}
{\sum_{C\in K}\sum_{j\in C}\|P_0(j)-P_0(\pi_C(j))\|_2}
$$

其中 $\pi_C(j)$ 表示该稳定链内代码正在使用的 parent。分母过小时返回 $1$。

## 10. rest offset correction

`_corrections_from_rest_offsets()` 是 direct quaternion retarget 的关键。对每个骨骼 $j$，代码取 `PRIMARY_CHILD[j]`，记为 $\chi(j)$。若 child 不存在或 source/target offset 过短，则跳过。

source child offset：

$$
u_j=o_{\chi(j)}^{\mathrm{src}}
$$

target child offset：

$$
v_j=\bar{o}_{\chi(j)}
$$

correction 定义为：

$$
c_j=Rot(v_j\to u_j)
$$

注意方向是 target offset 到 source offset，与代码 `quat_from_two_vectors_xyzw(target_vec, source_vec)` 一致。

对 body/core 局部旋转，`retarget_named_quats_to_vrm()` 执行：

$$
\tilde{q}_t^j=\widehat{q_t^{j,\mathrm{src}}}
$$

若父节点 correction $c_{\pi(j)}$ 存在：

$$
\tilde{q}_t^j\leftarrow c_{\pi(j)}^{-1}\tilde{q}_t^j
$$

若当前 correction $c_j$ 存在：

$$
\tilde{q}_t^j\leftarrow \tilde{q}_t^j c_j
$$

最终：

$$
q_t^{j,\mathrm{target}}=\widehat{\tilde{q}_t^j}
$$

root rotation 若存在 $c_{\mathrm{hips}}$：

$$
q_t^{\mathrm{root,target}}=q_t^{\mathrm{root,basis}}c_{\mathrm{hips}}
$$

hand bones 使用相同公式，只是 correction 字典为 body correction 与 hand correction 的合并。

## 11. direct local quaternion retarget

`retarget_named_quats_to_vrm()` 的完整代码路径如下。

输入：

$$
r_t^{\mathrm{src}}\in\mathbb{R}^3,\quad
q_t^{\mathrm{root,src}}\in\mathbb{R}^4,\quad
\{q_t^{j,\mathrm{src}}\}_{j\in C},\quad
\{q_t^{k,\mathrm{src}}\}_{k\in H}\ \mathrm{optional}
$$

第一步缩放并归零 root：

$$
r_t^0=\lambda_{\mathrm{rest}}r_t^{\mathrm{src}}
$$

$$
r_t^1=r_t^0-r_0^0
$$

第二步用 source rest offsets 计算 source positions：

$$
P_t^{\mathrm{src}}=FK\left(r_t^1,q_t^{\mathrm{root,src}},\{q_t^{j,\mathrm{src}}\},o^{\mathrm{src}}\right)
$$

第三步 basis 归一：

$$
r_t^2=Br_t^1,\qquad P_t^{\mathrm{src,basis}}=BP_t^{\mathrm{src}},\qquad
q_t^{\mathrm{root,basis}}=q(B)q_t^{\mathrm{root,src}}
$$

第四步做 rest correction，得到 body 与 hand target quats。

第五步打包：

$$
S=pack\left(r^2,q^{\mathrm{root,target}},Q^{C,\mathrm{target}},Q^{H,\mathrm{target}}\right)
$$

第六步用 target rest offsets 做 FK：

$$
P^{\mathrm{target}}=FK(S,\bar{o})
$$

函数返回的 mode 固定为：

$$
\mathrm{mode}=\mathrm{DirectLocalQuaternionRetarget}
$$

## 12. position fitting retarget

`fit_positions_to_vrm()` 用于 HumanML3D、SuSu positions 以及 SuSu global-rotation 先构造出的 positions。输入是按 `BODY_BONES` 对齐的：

$$
X\in\mathbb{R}^{T\times N_B\times3},\qquad B=B_{\mathrm{body}},\quad N_B=22
$$

第一步 basis：

$$
X_t'(j)=BX_t(j)
$$

第二步 scale：

$$
X_t''(j)=\lambda_{\mathrm{pos}}X_t'(j)
$$

第三步 root：

$$
r_t=X_t''(\mathrm{hips})-X_0''(\mathrm{hips})
$$

第四步中心化。代码先复制 $X''$，再减第一帧 hips，并把 hips 改成 root translation：

$$
Y_t(j)=X_t''(j)-X_0''(\mathrm{hips})
$$

$$
Y_t(\mathrm{hips})=r_t
$$

第五步 root rotation。若 spine offset $\bar{o}_{\mathrm{spine}}$ 有效：

$$
d_t^{\mathrm{spine}}=Y_t(\mathrm{spine})-Y_t(\mathrm{hips})
$$

当 $\|d_t^{\mathrm{spine}}\|\ge 10^{-6}$：

$$
q_t^{\mathrm{root}}=Rot(\bar{o}_{\mathrm{spine}}\to d_t^{\mathrm{spine}})
$$

否则保持单位四元数。

第六步逐骨骼拟合。对每个 $j\in C$，取 primary child $\chi(j)$。如果 $\chi(j)$ 不在 body positions 中，则代码把该骨骼 world rotation 设成父节点 world rotation，并不写非单位局部旋转。若 child 有效：

$$
d_t^{\mathrm{world}}=Y_t(\chi(j))-Y_t(j)
$$

父节点 world rotation 已知为 $Q_t(\pi(j))$。转到父局部空间：

$$
d_t^{\mathrm{local}}=R(Q_t(\pi(j))^{-1})d_t^{\mathrm{world}}
$$

局部旋转：

$$
q_t^j=Rot(\bar{o}_{\chi(j)}\to d_t^{\mathrm{local}})
$$

世界旋转递推：

$$
Q_t(j)=Q_t(\pi(j))q_t^j
$$

最终打包：

$$
S=pack(r,q^{\mathrm{root}},Q^{C},I^{H})
$$

返回 mode：

$$
\mathrm{mode}=\mathrm{PositionFitToVrm}
$$

这条路径没有求解 twist，因为单 child direction 对绕骨骼轴的旋转不可观测。代码选择的是确定性方向拟合，而不是 IK 优化。
