# 理论与目标边界

VIREA 的出发点不是再做一个孤立的 text-to-motion demo，而是先建立一个
可以被真实 VRM avatar 执行的动作数据底座。

## 为什么是 VRM

图像和视频生成可以展示“看起来像人在动”的画面，但它们通常不给出可执行的
身体状态。VIREA 选择 VRM humanoid，是因为它提供了一个现实可用的中间层：

- 有明确的人形骨架和骨骼命名
- 能在 Web、Unity、Blender、avatar 应用中运行
- 比像素更可控，比具体机器人形态更通用
- 适合作为数字人、虚拟陪伴、VTuber、游戏角色和具身 AI 的共同试验接口

因此，VIREA 的第一性问题是：

```text
语义意图如何变成可执行的身体运动？
```

当前阶段先回答更底层的问题：

```text
异构人体动作数据如何稳定变成 VRM humanoid motion？
```

## 数据到行为

动作数据集之间的差异不只在文件格式，还包括：

- FPS 不同
- 世界坐标上轴不同
- 单位不同
- skeleton / rest pose 不同
- rotation 表示不同
- 是否包含手、物体、文本、语音、情绪

如果这些差异没有在数据层被显式处理，后续模型训练会把错误方向、错误尺度、
错误骨架关系都学进去。VIREA 因此把 adapter、codec、retarget 和 quality
report 作为核心资产，而不是把它们当作临时预处理脚本。

## 目标和非目标

当前目标：

- 建立 7 个真实数据集的统一读取、转换和预览路径
- 输出 VRM-centered motion payload
- 用真实 `.vrm` avatar 进行可视化检查
- 为后续训练和交互运行时提供稳定样本格式

当前非目标：

- 不绑定某个特定生成模型
- 不承诺公开分发第三方 raw dataset
- 不把 viewer 里的视觉检查替代数值质量报告
- 不把 source skeleton 和 VRM target skeleton 混成一个概念

长期方向：

```text
dialogue state + emotion + intent
  -> motion planning / generation
  -> streaming VRM humanoid control
  -> interactive embodied avatar behavior
```
