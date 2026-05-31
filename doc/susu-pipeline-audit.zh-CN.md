# SuSuInterActs 解析与对齐审计说明

本文记录 SuSuInterActs 当前在 VIREA 中的真实解析规则，避免后续再次把 root 或 6D 旋转空间误读。

## 结论

- `chonglu` 和 `retarget_maya` 不能共用同一套无差别转换。
- SuSu `body[:, 0:3]` 在真实文件中按绝对 root 位置使用，而不是在 pipeline 中做逐帧速度累计。
- root 三维顺序按 `X/Z/Y` 读入，再重排为 glTF / VRM 的 `X/Y/Z`。
- `chonglu` root 与 `positions[:, 0]` 可通过 `X/Z/Y` 重排和 `0.01` 缩放逐帧对齐。
- `retarget_maya` 文件混有米制 root 和厘米制 FBX root；pipeline 会按数值范围自动选择 `1.0` 或 `0.01` 有效缩放，并以首帧 root 归零。
- SuSu body/hands 的 6D rotation 先按 column-major first-two-columns 解析为世界/全局朝向，再根据 humanoid 父子拓扑转换为父节点局部四元数。
- 不再把 `retarget_maya` 的下肢强制置为 rest pose。全局转局部后下肢稳定，旧保护分支反而会干扰世界坐标基推断，造成左右轴翻转、手臂交叉和肩膀内缩。

## 实现位置

- 数据 profile 判定：[susuinteracts.py](../src/virea/data/adapters/susuinteracts.py)
- SuSu codec、root 单位判定、6D 全局转局部：[codecs.py](../src/virea/motion/codecs.py)
- 对齐质量测试：[test_alignment_quality.py](../tests/test_alignment_quality.py)

## 数值审计

抽查 60 个真实 `retarget_maya` 样本后，当前 root 轨迹统计为：

- 水平位移范围中位数约 `0.1019 m`
- 水平位移范围 95 分位约 `0.2825 m`
- 单帧最大 step 95 分位约 `0.0219 m`
- 单帧最大 step 最大值约 `0.0306 m`

这说明 root 不再被错误累计放大。肩/上臂左右顺序也保持稳定；测试会检查脚不会高于头部、左右上臂不会反转、processed motion 可由 VRM FK 精确重建。

## 验证命令

```bash
python -m pytest -q
python scripts/smoke_pipeline.py --data-source demo --max-frames 8
python scripts/smoke_pipeline.py --data-source full --max-frames 8
```
