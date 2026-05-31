# VIREA 文档索引

这套文档把 README 中不该展开的内容拆成几层：理论逻辑、工程设计、数据
pipeline、展示产物和参考基线。README 只保留项目入口、核心效果和最短运行路径。

## 阅读顺序

1. [理论与目标边界](theory.zh-CN.md)
   说明为什么 VIREA 以 VRM humanoid 作为可执行身体接口，以及它和
   text-to-motion、数字人交互、具身智能之间的关系。

2. [工程设计](engineering-design.zh-CN.md)
   说明模块边界：dataset adapter、codec、retarget、pipeline、server、viewer
   分别负责什么，哪些逻辑必须保持分离。

3. [Pipeline 使用指南](pipeline.zh-CN.md)
   从环境部署、demo 构建、批量处理、质量检查到 viewer 预览，给出可以直接
   复制执行的命令。

4. [Showcase 生成说明](showcase/README.md)
   记录 7 x 7 结果视频看板的样本选择、VRM 渲染命令和产物位置。

5. [SuSu 专项审计](susu-pipeline-audit.zh-CN.md)
   记录 SuSuInterActs 在 root、坐标系、6D rotation 和畸形动作排查中的问题。

6. [参考资料与设计基线](references.zh-CN.md)
   记录当前实现对齐过的权威论文、数据集主页、VRM 规范和开源项目。

## 文档维护原则

- README 面向第一次进入仓库的人，只讲价值、效果和最短路径。
- 设计文档讲为什么这样拆模块，不写流水账。
- Pipeline 文档讲怎么跑、产物在哪、出错怎么定位。
- 数据集细节只写会影响转换正确性的事实：FPS、单位、坐标系、骨架、许可。
- 所有展示视频都要能从脚本复现，不能只手工上传。
