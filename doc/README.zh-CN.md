# VIREA 文档索引

这套文档把 README 中不适合展开的内容拆成几层：理论目标、retarget 数学、工程设计、数据 pipeline、showcase 产物和参考基线。README 保持项目入口；`doc/` 负责把可审计的理论与工程细节讲完整。

## 阅读顺序

1. [理论与目标边界](theory.zh-CN.md)
   说明为什么 VIREA 以 VRM humanoid 作为可执行身体接口，以及它和 text-to-motion、数字人交互、具身 AI 之间的关系。

2. [Retarget 数学原理](math-retarget/README.zh-CN.md)
   从 SMPL-H、SMPL-X、BVH、HumanML3D 263D、SuSu 五类源骨骼系统出发，逐步说明从 raw tensor 到 VRM/glTF humanoid pose 的完整数学路径。

3. [工程设计](engineering-design.zh-CN.md)
   说明 DatasetAdapter、MotionCodec、retarget、pipeline、server、viewer 的模块边界，以及哪些逻辑必须保持分离。

4. [Pipeline 使用指南](pipeline.zh-CN.md)
   从环境部署、demo 构建、批量处理、质量检查到 viewer 预览，给出可执行命令。

5. [Showcase 生成说明](showcase/README.md)
   记录 7 x 7 结果视频看板的样本选择、VRM 渲染命令和产物位置。

6. [SuSu 专项审计](susu-pipeline-audit.zh-CN.md)
   记录 SuSuInterActs 在 root、坐标系、6D rotation 和畸形动作排查中的专项问题。

7. [参考资料与设计基线](references.zh-CN.md)
   记录当前实现对齐过的权威论文、数据集主页、VRM/glTF 规范和开源项目。

## Retarget 数学目录

- [VRM/glTF 目标层数学约定](math-retarget/vrm-gltf-target.zh-CN.md)
- [SMPL-H / SMPL body 到 VRM](math-retarget/smplh-to-vrm.zh-CN.md)
- [SMPL-X 到 VRM](math-retarget/smplx-to-vrm.zh-CN.md)
- [BVH / BEAT 到 VRM](math-retarget/bvh-to-vrm.zh-CN.md)
- [HumanML3D 263D 到 VRM](math-retarget/humanml3d-263d-to-vrm.zh-CN.md)
- [SuSuInterActs 到 VRM](math-retarget/susu-to-vrm.zh-CN.md)
- [Retarget 文档评审清单](math-retarget/review-checklist.zh-CN.md)

## 文档维护原则

- README 面向第一次进入仓库的人，只讲价值、效果和最短运行路径。
- 数学文档讲清楚坐标、单位、旋转、FK、rest correction、scale、dataset profile，不省略中间步骤。
- 工程文档讲模块边界，不把转换、持久化和展示逻辑混在一起。
- Pipeline 文档讲怎么跑、产物在哪、出错怎么定位。
- 数据集细节只写会影响转换正确性的事实：FPS、单位、坐标系、骨架、rotation 表达、许可证。
- Showcase 视频必须能从脚本复现，不能只手工上传。
