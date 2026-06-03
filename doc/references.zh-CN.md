# 参考资料与设计基线

本页记录会影响 VIREA 工程设计和 retarget 数学的资料入口。README 不展开这些内容，避免把项目入口写成长论文。

## VRM / glTF / Avatar Runtime

- [glTF 2.0 specification](https://registry.khronos.org/glTF/specs/2.0/glTF-2.0.html): glTF 的 node hierarchy、TRS transform、unit quaternion、skin、joint 和 inverse bind matrix 是 VRM avatar 执行骨骼动画的底层基础。
- [VRM 1.0 humanoid specification](https://github.com/vrm-c/vrm-specification/blob/master/specification/VRMC_vrm-1.0/humanoid.md): VRM 用 humanoid metadata 把语义骨骼名映射到 glTF node。
- [VRM Animation specification](https://vrm.dev/en/vrma/): 后续导出 VRMA 时需要保持和该动画扩展的时间轴、骨骼通道兼容。
- [three-vrm](https://github.com/pixiv/three-vrm): viewer 中加载 `.vrm` 和驱动 humanoid pose 的 Web 运行时参考。

## Body Models / Motion Corpora

- [SMPL](https://smpl.is.tue.mpg.de/): AMASS、BABEL、HumanML3D 等数据生态常用的人体模型基础。
- [SMPL+H / MANO](https://arxiv.org/abs/2201.02610): SMPL+H 将 MANO 手模型连接到 SMPL body，是理解 SMPL-H 手部语义的重要参考。
- [SMPL-X](https://arxiv.org/abs/1904.05866): SMPL-X 扩展 SMPL，包含完整手部和表情，是 GRAB、Motion-X 等 whole-body 数据的基础。
- [AMASS](https://amass.is.tue.mpg.de/) / [AMASS paper](https://arxiv.org/abs/1904.03278): 多来源 mocap 统一到 SMPL/SMPL-H 的核心参考。
- [BABEL](https://babel.is.tue.mpg.de/) / [BABEL paper](https://arxiv.org/abs/2106.09696): 对 AMASS 动作片段进行 sequence/frame-level 语言标签的参考。
- [GRAB](https://grab.is.tue.mpg.de/) / [GRAB paper](https://arxiv.org/abs/2008.11200): 全身抓取和物体交互动作的 SMPL-X 参考。
- [HumanML3D](https://github.com/EricGuo5513/HumanML3D) / [HumanML3D paper](https://openaccess.thecvf.com/content/CVPR2022/papers/Guo_Generating_Diverse_and_Natural_3D_Human_Motions_From_Text_CVPR_2022_paper.pdf): text-to-motion 常用的 20 fps 语言动作数据和 263D feature 表达参考。
- [Motion-X](https://motion-x-dataset.github.io/) / [Motion-X paper](https://arxiv.org/abs/2307.00818): 大规模 SMPL-X whole-body motion 与文本标注参考。
- [BEAT](https://pantomatrix.github.io/BEAT/) / [BEAT paper](https://arxiv.org/abs/2203.05297): conversational gesture、audio、text、emotion、facial blendshape 的多模态参考。
- [SentiAvatar / SuSuInterActs](https://sentiavatar.github.io/) / [SuSuInterActs on Hugging Face](https://huggingface.co/datasets/Chuhaojin/SuSuInterActs): 对话式数字人动作、语音、表情和 6D skeleton motion 的参考。

## Rotation / Kinematics

- [6D rotation representation](https://arxiv.org/abs/1812.07035): SuSu 6D rotation 与 HumanML3D 263D 中连续旋转表示的数学背景。
- [BVH structure overview](https://mocaponline.com/blogs/mocap-news/bvh-animation-guide): BVH hierarchy、offset、channels、frame time 的格式背景；BEAT 当前使用上游整理后的 BVH-derived axis-angle pack。

## 对 VIREA 的约束

- 读取层必须保留 source fps，viewer 播放不能假设固定 30 fps。
- 坐标系、朝向、单位和 root basis 必须在 adapter/codec 层显式登记。
- source skeleton 和 VRM target skeleton 必须分离，不能把预览修正混进原始语义。
- 旋转路径和位置路径要分开：axis-angle/fullpose 可以直接做 local quaternion retarget；263D/positions 需要 position fitting。
- 质量报告要同时覆盖数值异常和视觉检查线索，例如 ground penetration、direction error、jitter、limb symmetry。
- 第三方 raw dataset 与 VRM model 的许可证边界必须在文档和 `.gitignore` 中保留；仓库只提交可公开的轻量 demo evidence。
