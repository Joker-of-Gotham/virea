# SuSuInterActs 到 VRM 的 retarget 数学

覆盖数据集：SuSuInterActs。对应代码：`SuSuInterActsAdapter`、`SuSu6DCodec`、`sixd_rows_to_quat_xyzw()`、`positions_from_global_rotations()`、`fit_positions_to_vrm()`。

SuSu 是当前项目中最特殊的路径。它不是 SMPL-H、SMPL-X，也不是标准 BVH。当前代码的真实输出逻辑是：

$$
\mathrm{SuSu\ body/positions}
\rightarrow
\mathrm{BODY\_BONES\ positions}
\rightarrow
\operatorname{fit\_positions\_to\_vrm}
\rightarrow
\mathrm{VRM\ body\ sequence}
$$

代码确实会把 SuSu body/hands 的 6D rotation 转为 global quaternions，并计算 global-to-local quaternions；但当前 `to_canonical()` 最终返回的是 `fit_positions_to_vrm()` 的 sequence，手部局部四元数没有写入最终 output sequence。也就是说：

$$
Q^{\mathcal{H},\mathrm{output}}=I^{\mathcal{H}}
$$

除非未来代码改成把 `hand` 合并进 `retarget["sequence"]`。

## 1. adapter 读取

motion 文件：

$$
\mathrm{path}=\mathrm{raw\_root}/\texttt{motion\_data}/(\mathrm{sample\_id}+\texttt{.npy})
$$

加载后要求是 dict。代码只保留键集合：

$$
\mathcal{K}_{\mathrm{motion}}=\{\texttt{body},\texttt{left},\texttt{right},\texttt{positions}\}
$$

每个存在的值转为 `float32`：

$$
M_k=\operatorname{float32}(\mathrm{data}[k]),\qquad k\in\mathcal{K}_{\mathrm{motion}}
$$

若存在 `body` 且 $T>1$，做 frozen 检查：

$$
\max_d \operatorname{std}_t(\mathrm{body}_{t,d}) < 10^{-6}
\Rightarrow \mathrm{ValueError}
$$

fps 固定：

$$
f=20
$$

face/audio/text：

$$
\mathrm{face}\leftarrow \mathrm{arkit\_data}/(\mathrm{sample\_id}+\texttt{.npy})
$$

$$
\mathrm{audio}\leftarrow \mathrm{wav\_data}/(\mathrm{sample\_id}+\texttt{.wav})
$$

$$
\mathrm{text}\leftarrow \mathrm{text\_data}/\texttt{motion2text.json}
$$

这些进入 motion metadata 或 annotations，不进入当前 body retarget 的数学输出。

## 2. profile 选择

adapter 的 source format/codec key：

$$
\mathrm{sample\_id}\ \mathrm{starts\ with}\ \texttt{fbx\_to\_json\_data\_susu\_retarget\_maya/}
\Rightarrow
\begin{cases}
\mathrm{source\_format}=\texttt{susu\_retarget\_maya\_6d\_body\_hands\_m\_npy}\\
\mathrm{codec\_key}=\texttt{susu\_retarget\_maya\_6d\_body\_hands}
\end{cases}
$$

$$
\mathrm{sample\_id}\ \mathrm{starts\ with}\ \texttt{fbx\_to\_json\_data\_susu\_chonglu/}
\ \mathrm{or}\ \texttt{positions}\in M
\Rightarrow
\begin{cases}
\mathrm{source\_format}=\texttt{susu\_chonglu\_6d\_body\_hands\_cm\_positions\_npy}\\
\mathrm{codec\_key}=\texttt{susu\_chonglu\_6d\_body\_hands\_cm}
\end{cases}
$$

否则：

$$
\mathrm{codec\_key}=\texttt{susu\_6d\_body\_hands}
$$

codec 内部 `_select_profile()` 再做一次 profile 决策。若构造器传入固定 profile，则直接使用。否则：

$$
\mathrm{profile}=
\begin{cases}
\mathrm{RETARGET\_MAYA},&\mathrm{sample\_id\ starts\ with\ RETARGET\_MAYA.path\_token}\\
\mathrm{CHONGLU},&\mathrm{sample\_id\ starts\ with\ CHONGLU.path\_token}\\
\mathrm{CHONGLU},&\mathrm{has\_positions}\\
\mathrm{RETARGET\_MAYA},&\mathrm{otherwise}
\end{cases}
$$

## 3. profile 参数

`SuSuProfile` 参数记为：

$$
\rho=(\mathrm{name},\tau_{\mathrm{path}},\alpha_{\mathrm{pos}},\alpha_{\mathrm{root}},b_{\mathrm{pos}},a_{\mathrm{root}},m_{\mathrm{root}})
$$

其中：

$$
a_{\mathrm{root}}=(0,2,1)
$$

retarget-maya：

$$
\alpha_{\mathrm{pos}}=0.01,\qquad
\alpha_{\mathrm{root}}=1.0,\qquad
b_{\mathrm{pos}}=\texttt{neg\_z\_up\_to\_y\_up}
$$

chonglu：

$$
\alpha_{\mathrm{pos}}=0.01,\qquad
\alpha_{\mathrm{root}}=0.01,\qquad
b_{\mathrm{pos}}=\texttt{identity\_y\_up}
$$

## 4. root translation

`_root_translation(body, profile)` 对 body 前三维按 `root_axes` 重排：

$$
u_t=
\left[
\mathrm{body}_{t,0},\
\mathrm{body}_{t,2},\
\mathrm{body}_{t,1}
\right]
$$

初始 scale：

$$
\gamma=\alpha_{\mathrm{root}}
$$

若 profile 是 retarget-maya，代码做自动单位判断：

$$
h_{\mathrm{med}}=\operatorname{median}_t(|u_{t,y}|)
$$

$$
m_{\max}=\max_{t,d}|u_{t,d}|
$$

$$
\gamma=
\begin{cases}
0.01,&h_{\mathrm{med}}>5\ \mathrm{or}\ m_{\max}>20\\
1.0,&\mathrm{otherwise}
\end{cases}
$$

unit metadata：

$$
\mathrm{unit}=
\begin{cases}
\texttt{cm},&\gamma=0.01\ \mathrm{by\ retarget\text{-}maya\ auto\ rule}\\
\texttt{m},&\gamma=1.0\ \mathrm{by\ retarget\text{-}maya\ auto\ rule}\\
\texttt{profile},&\mathrm{non\ retarget\text{-}maya}
\end{cases}
$$

root 输出：

$$
r_t^0=\gamma u_t
$$

$$
r_t=r_t^0-r_0^0
$$

注意这里没有速度积分。代码将 body 前三维解释为绝对 root，并做首帧归零。

## 5. 6D body rotation 重建

body rotation 切片：

$$
D^{\mathrm{body}}=
\operatorname{reshape}(\mathrm{body}_{[:,3:]},T,25,6)
$$

每个 6D 向量 $d$ 通过 `sixd_rows_to_quat_xyzw()`：

$$
a_1=d_{0:3},\qquad a_2=d_{3:6}
$$

$$
b_1=\frac{a_1}{\max(\|a_1\|,10^{-8})}
$$

$$
b_2=\frac{a_2-(b_1^\top a_2)b_1}{\max(\|a_2-(b_1^\top a_2)b_1\|,10^{-8})}
$$

$$
b_3=b_1\times b_2
$$

row-major matrix：

$$
R(d)=
\begin{bmatrix}
b_1^\top\\
b_2^\top\\
b_3^\top
\end{bmatrix}
$$

quaternion：

$$
q(d)=\operatorname{matrix\_to\_quat\_xyzw}(R(d))
$$

得到：

$$
Q^{\mathrm{body,global}}\in\mathbb{R}^{T\times25\times4}
$$

## 6. SuSu body source names 到 canonical names

source body names：

$$
\mathcal{S}_{\mathrm{body}}=[
\mathrm{pelvis},\mathrm{thigh\_r},\mathrm{calf\_r},\ldots,\mathrm{hand\_r}
]
$$

映射 $g_{\mathrm{susu}}$ 由 `SUSU_BODY_TO_CANONICAL` 定义，例如：

$$
g_{\mathrm{susu}}(\mathrm{pelvis})=\mathrm{hips}
$$

$$
g_{\mathrm{susu}}(\mathrm{thigh\_l})=\mathrm{leftUpperLeg},\qquad
g_{\mathrm{susu}}(\mathrm{thigh\_r})=\mathrm{rightUpperLeg}
$$

$$
g_{\mathrm{susu}}(\mathrm{spine\_01})=\mathrm{spine},\quad
g_{\mathrm{susu}}(\mathrm{spine\_03})=\mathrm{chest},\quad
g_{\mathrm{susu}}(\mathrm{spine\_05})=\mathrm{upperChest}
$$

`_susu_body_global_to_local()` 遍历 source index $i$，若 $g_{\mathrm{susu}}(s_i)$ 存在且未写过，则：

$$
Q_t^{\mathrm{global}}(g_{\mathrm{susu}}(s_i))=
Q_{t,i}^{\mathrm{body,global}}
$$

root global：

$$
q_t^{\mathrm{root,global}}=
\begin{cases}
Q_t^{\mathrm{global}}(\mathrm{hips}),&\mathrm{if\ exists}\\
[0,0,0,1],&\mathrm{otherwise}
\end{cases}
$$

## 7. global-to-local body quaternions

对每个 canonical body bone $j\neq\mathrm{hips}$，若父节点 global rotation 存在：

$$
q_t^{j,\mathrm{local}}=
\left(Q_t^{\mathrm{global}}(\pi(j))\right)^{-1}
Q_t^{\mathrm{global}}(j)
$$

否则代码退化为：

$$
q_t^{j,\mathrm{local}}=Q_t^{\mathrm{global}}(j)
$$

这些值被写入临时 `core`：

$$
Q_t^{\mathcal{C},\mathrm{temp}}[\mathrm{CORE\_INDEX}(j)]=q_t^{j,\mathrm{local}}
$$

但当前 `to_canonical()` 后面没有把这个 `core` 传入最终 `pack_sequence()`；最终 sequence 来自 `fit_positions_to_vrm()`。

## 8. hand 6D 和 global-to-local

若存在 `left` 或 `right`：

$$
D^{\mathrm{hand}}=
\operatorname{reshape}(\mathrm{motion}[\mathrm{side}],T,20,6)
$$

每个 6D 重建为 global quaternion：

$$
Q^{\mathrm{hand,global}}\in\mathbb{R}^{T\times20\times4}
$$

手指 source index 到 canonical finger name 的映射 $\psi_{\mathrm{side}}$ 来自 `_susu_hand_map()`，例如左手：

$$
\psi_{\mathrm{left}}(0)=\mathrm{leftIndexProximal},\quad
\psi_{\mathrm{left}}(1)=\mathrm{leftIndexIntermediate}
$$

$$
\psi_{\mathrm{left}}(16)=\mathrm{leftThumbProximal}
$$

对每个 finger bone $k$，若 hand parent global 存在：

$$
q_t^{k,\mathrm{local}}=
\left(Q_t^{\mathrm{hand,global}}(\pi(k))\right)^{-1}
Q_t^{\mathrm{hand,global}}(k)
$$

否则若 body parent global 存在：

$$
q_t^{k,\mathrm{local}}=
\left(Q_t^{\mathrm{body,global}}(\pi(k))\right)^{-1}
Q_t^{\mathrm{hand,global}}(k)
$$

否则：

$$
q_t^{k,\mathrm{local}}=Q_t^{\mathrm{hand,global}}(k)
$$

这些值被写入临时 `hand`，但和 body `core` 一样，当前不进入最终 `retarget["sequence"]`。

## 9. positions 可用时的主路径

`_positions_from_available_data()` 条件是：

$$
\texttt{positions}\in\mathrm{clip.motion}
\quad\mathrm{and}\quad
\operatorname{ndim}(\mathrm{positions})=3
$$

若成立：

$$
X^{\mathrm{native}}=\alpha_{\mathrm{pos}}\mathrm{positions}
$$

接着 `_canonical_body_from_source_positions()` 只取前 $25$ 个 source body joints：

$$
X^{\mathrm{body}}=X^{\mathrm{native}}_{[:,0:\min(25,J),:]}
$$

按 `SUSU_BODY_TO_CANONICAL` 映射到 canonical names。若映射到 $m$ 个 canonical joints：

$$
Y\in\mathbb{R}^{T\times m\times3}
$$

然后：

$$
B_{\mathrm{pos}}=
\operatorname{body\_positions\_from\_fk\_positions}(Y,\mathcal{M})
\in\mathbb{R}^{T\times22\times3}
$$

调用：

$$
\operatorname{fit\_positions\_to\_vrm}
\left(
B_{\mathrm{pos}},
\mathrm{world\_basis}=b_{\mathrm{pos}}
\right)
$$

其中：

$$
b_{\mathrm{pos}}=
\begin{cases}
\texttt{neg\_z\_up\_to\_y\_up},&\mathrm{retarget\text{-}maya}\\
\texttt{identity\_y\_up},&\mathrm{chonglu}
\end{cases}
$$

position fitting 展开为：

$$
X'_t(j)=B(b_{\mathrm{pos}})B_{\mathrm{pos},t}(j)
$$

$$
X''_t(j)=\lambda_{\mathrm{pos}}X'_t(j)
$$

$$
r_t=X''_t(\mathrm{hips})-X''_0(\mathrm{hips})
$$

$$
q_t^{\mathrm{root}}=\operatorname{Rot}(\bar{o}_{\mathrm{spine}}\to X''_t(\mathrm{spine})-X''_t(\mathrm{hips}))
$$

对 core bone：

$$
q_t^j=
\operatorname{Rot}
\left(
\bar{o}_{\chi(j)}
\to
R(Q_t(\pi(j))^{-1})(X''_t(\chi(j))-X''_t(j))
\right)
$$

最终：

$$
S=\operatorname{pack}(r,q^{\mathrm{root}},Q^{\mathcal{C}},I^{\mathcal{H}})
$$

## 10. positions 不可用时的路径

如果没有 `positions`，代码用 global body rotations 构造 positions：

$$
X=\operatorname{positions\_from\_global\_rotations}
\left(
r,
Q^{\mathrm{body,global}},
\mathrm{fixed\_aim\_axes}=\varnothing
\right)
$$

注意当前 `use_fixed_axes=False`，所以即使定义了 `SUSU_MAYA_AIM_AXES`，也不会传入。

### 10.1 aim axis 推断

候选本地轴集合：

$$
\mathcal{A}=\{[1,0,0],[-1,0,0],[0,1,0],[0,-1,0],[0,0,1],[0,0,-1]\}
$$

对 child bone $j$，期望解剖方向为 $e_j$，来自 `_ANATOMICAL_WORLD_DIRECTIONS`，归一化：

$$
\hat{e}_j=\frac{e_j}{\|e_j\|}
$$

父节点 global rotation 为 $Q_t(\pi(j))$。每个候选轴 $a\in\mathcal{A}$ 的得分：

$$
\operatorname{score}(a)=
\frac{1}{T}\sum_{t=0}^{T-1}
\left(R(Q_t(\pi(j)))a\right)^\top\hat{e}_j
$$

选择：

$$
a_j^\*=\arg\max_{a\in\mathcal{A}}\operatorname{score}(a)
$$

### 10.2 从 global rotation 构造 positions

初始化：

$$
X_t(\mathrm{hips})=r_t-r_0
$$

对每个非 root bone $j$：

若父节点 global rotation 不存在：

$$
X_t(j)=X_t(\pi(j))
$$

否则取 target/default rest offset 长度：

$$
\ell_j=\|\mathrm{DEFAULT\_REST\_OFFSETS}[j]\|
$$

若 $\ell_j<10^{-6}$：

$$
X_t(j)=X_t(\pi(j))
$$

否则：

$$
d_t(j)=R(Q_t^{\mathrm{global}}(\pi(j)))a_j^\*
$$

$$
\hat{d}_t(j)=\frac{d_t(j)}{\max(\|d_t(j)\|,10^{-8})}
$$

$$
X_t(j)=X_t(\pi(j))+\ell_j\hat{d}_t(j)
$$

随后调用：

$$
\operatorname{fit\_positions\_to\_vrm}
\left(
X,
\mathrm{world\_basis}=\texttt{identity\_y\_up}
\right)
$$

也就是说，无 positions 时，6D/global rotations 并不是直接输出到 VRM，而是先转成 body positions，再走 position fitting。

## 11. 最终输出和 metadata

两条路径最终都返回 `fit_positions_to_vrm()` 的结果：

$$
S_{\mathrm{output}}=S_{\mathrm{position\_fit}}
$$

$$
P^{\mathrm{target}}=\operatorname{FK}(S_{\mathrm{output}},\bar{o})
$$

metadata 记录：

$$
\mathrm{retarget\_mode}=\texttt{position\_fit\_to\_vrm}
$$

$$
\mathrm{rotation\_6d\_layout}=\texttt{row\_major\_first\_two\_rows}
$$

$$
\mathrm{rotation\_space}=\texttt{global\_6d\_converted\_to\_parent\_local\_quaternions}
$$

最后一个字段描述了中间计算；当前 output sequence 仍以 positions fitting 为准。

hand 输出：

$$
Q^{\mathcal{H},\mathrm{output}}=I^{\mathcal{H}}
$$

这是当前实现边界，后续若要让 SuSu 手指驱动 VRM，需要在 `fit_positions_to_vrm()` 输出 sequence 后重新注入 `hand` quaternions 或另写 direct body/hand retarget。

## 12. source preview

`extract_source()` 也分两条。

若有 positions：

$$
X^{\mathrm{native}}=\alpha_{\mathrm{pos}}\mathrm{positions}
$$

$$
B_{\mathrm{pos}}=\operatorname{body\_positions\_from\_fk\_positions}(X^{\mathrm{native}},\mathcal{M})
$$

调用 `source_positions_normalized()`：

$$
\hat{X}=B(b_{\mathrm{pos}})B_{\mathrm{pos}}
$$

$$
\hat{X}'=\lambda_{\mathrm{pos}}\hat{X}
$$

$$
\hat{X}'_t(j)\leftarrow
\hat{X}'_t(j)-\hat{X}'_0(\mathrm{hips})
$$

若无 positions：

$$
X=\operatorname{positions\_from\_global\_rotations}(r,Q^{\mathrm{body,global}})
$$

然后只做 source preview scale 和 root center：

$$
\hat{X}=\lambda_{\mathrm{pos}}X
$$

$$
\hat{X}_t(j)\leftarrow \hat{X}_t(j)-\hat{X}_0(\mathrm{hips})
$$

这条 source preview 不再额外做 world basis 旋转，metadata 中写：

$$
\mathrm{declared\_world\_basis}=\texttt{identity\_y\_up}
$$

## 13. 当前实现的风险边界

严格按代码，SuSu 当前需要重点审计：

1. root 是绝对位置而非速度积分：

$$
r_t=\gamma\,\mathrm{body}_{t,(0,2,1)}-\gamma\,\mathrm{body}_{0,(0,2,1)}
$$

2. retarget-maya 自动单位规则可能改变 $\gamma$：

$$
\gamma\in\{1.0,0.01\}
$$

3. 6D layout 是 row-major first-two-rows：

$$
R(d)=
\begin{bmatrix}
b_1^\top\\
b_2^\top\\
(b_1\times b_2)^\top
\end{bmatrix}
$$

4. 当前 output sequence 不是直接使用 SuSu hand local quats：

$$
Q^{\mathcal{H},\mathrm{output}}=I^{\mathcal{H}}
$$

5. 有 positions 时，positions 优先级高于 6D rotation：

$$
\texttt{positions}\ \mathrm{available}
\Rightarrow
S_{\mathrm{output}}=\operatorname{fit\_positions\_to\_vrm}(\mathrm{positions})
$$

