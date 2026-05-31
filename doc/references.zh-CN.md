# 参考资料与设计基线

本页只记录会影响 VIREA 工程设计的资料入口。README 不展开这些内容，避免把项目入口写成长论文。

## VRM / Avatar Runtime

- [VRM humanoid specification](https://vrm.dev/en/vrm1/humanoid/): VIREA 以 VRM humanoid 骨架作为第一个可执行 avatar 目标。
- [VRM Animation specification](https://vrm.dev/en/vrma/): 后续导出 VRMA 时需要保持和该动画扩展的时间轴、骨骼通道兼容。
- [three-vrm](https://github.com/pixiv/three-vrm): viewer 中加载 `.vrm` 和驱动 humanoid pose 的 Web 运行时参考。

## Body Models / Motion Corpora

- [SMPL](https://smpl.is.tue.mpg.de/): AMASS、BABEL、HumanML3D 等数据生态常用的人体模型基础。
- [AMASS](https://amass.is.tue.mpg.de/) / [AMASS paper](https://arxiv.org/abs/1904.03278): 多来源 mocap 统一到 SMPL/SMPL-H 的核心参考。
- [BABEL](https://babel.is.tue.mpg.de/) / [BABEL paper](https://arxiv.org/abs/2106.09696): 对 AMASS 动作片段进行语言标签和 frame-level action 标注的参考。
- [GRAB](https://grab.is.tue.mpg.de/) / [GRAB paper](https://arxiv.org/abs/2008.11200): 全身抓取和物体交互动作的 SMPL-X 参考。
- [HumanML3D](https://github.com/EricGuo5513/HumanML3D): text-to-motion 常用的 20 fps 语言动作数据参考。
- [Motion-X](https://github.com/IDEA-Research/Motion-X) / [Motion-X paper](https://arxiv.org/abs/2307.00818): 大规模 SMPL-X whole-body motion 与文本标注参考。
- [BEAT](https://pantomatrix.github.io/BEAT/) / [BEAT paper](https://arxiv.org/abs/2203.05297): conversational gesture、audio、text、emotion、facial blendshape 的多模态参考。
- [SentiAvatar / SuSuInterActs](https://sentiavatar.github.io/) / [SuSuInterActs on Hugging Face](https://huggingface.co/datasets/Chuhaojin/SuSuInterActs): 对话式数字人动作、语音、表情和 6D skeleton motion 的参考。

## 对 VIREA 的约束

- 读取层必须保留 source fps，viewer 播放不能假设固定 30 fps。
- 坐标系、朝向、单位和 root basis 必须在 adapter/codec 层显式登记。
- source skeleton 和 VRM target skeleton 必须分离，不能把预览修正混进原始语义。
- 质量报告要同时覆盖数值异常和视觉检查线索，例如 ground penetration、direction error、jitter、limb symmetry。
- 第三方 raw dataset 的许可边界必须在文档和 `.gitignore` 中保留；仓库只提交可公开的轻量 demo evidence。
