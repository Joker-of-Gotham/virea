# VIREA 数据管线、转换与预览说明

本文记录当前 `virea` 中已经实现的数据读取、转换、验证和前端预览流程。目标不是让 `after` 机械复制 `before`，而是把不同来源的原始人体动作稳定转换为可由 VRM humanoid 播放的 canonical / VRM motion payload，同时保留 `before` 原始预览用于人工核查。

## 路径与环境变量

默认配置位于 `configs/project.yaml`。所有路径都可以用环境变量覆盖。

| 变量 | 含义 | 默认值 |
| --- | --- | --- |
| `VIREA_DATA_SOURCE` | 当前数据来源，取值 `demo` 或 `full` | `full` |
| `VIREA_RAW_ROOT` | 原始数据根目录 | `full`: `D:\AI-Program-Project\LLM-driven-VRM\vrm_motion\runtime\datasets\raw`；`demo`: `demo/raw` |
| `VIREA_PROCESSED_ROOT` | 转换后输出根目录 | `full`: `data/virea_processed/full`；`demo`: `demo/processed` |
| `VIREA_DATA_ROOT` | 工作区数据根目录兜底值 | `D:\AI-Program-Project\LLM-driven-VRM\vrm_motion\runtime\datasets` |
| `VIREA_VRM_MODEL_ROOT` | 用于生成真实 VRM control-rest template 的 `.vrm` 模型库 | `D:\AI-Program-Project\LLM-driven-VRM\vrm_motion\vrm_model` |
| `VIREA_LLM_DRIVEN_VRM_ROOT` | `vrm_motion.data.vrm_inspector` 所在工程根目录，可选 | 自动尝试 `D:\AI-Program-Project\LLM-driven-VRM` |
| `VIREA_TMR_SRC` | HumanML3D 263D 解码依赖路径，可选 | 自动尝试 `D:\AI-Program-Project\LLM-driven-VRM\tmp_repos\TMR\src` |

Windows PowerShell 推荐先设置：

```powershell
conda activate llm-driven-vrm
$env:PYTHONPATH = "D:\AI-Program-Project\virea\src"
```

## demo 与 full 模式

`demo` 和 `full` 使用同一套内部目录结构、adapter、codec、retarget 和 viewer。

- `demo`：自动读取 `D:\AI-Program-Project\virea\demo\raw`，默认输出到 `D:\AI-Program-Project\virea\demo\processed`，用于快速验证完整 pipeline。
- `full`：读取完整真实数据目录。运行转换时如果没有传入 `--input-root` 和 `--output-root`，CLI 会交互式要求用户输入。
- 两种模式都不会默认做等长切分或自动剪辑。只有显式传入 `--max-frames` 时才会为了调试或快速预览限制帧数；正式转换请不要传这个参数。

查看数据源：

```powershell
python -m virea.cli sources
```

交互式选择数据源、动作和转换路径：

```powershell
python -m virea.cli interactive
```

构建 demo 数据：

```powershell
python -m virea.cli build-demo --overwrite
```

## 完整转换命令

demo 模式自动确定输入和输出：

```powershell
python -m virea.cli convert `
  --data-source demo `
  --continue-on-error `
  --report demo\conversion-report.json
```

full 模式手动指定输入和输出：

```powershell
python -m virea.cli convert `
  --data-source full `
  --input-root "D:\AI-Program-Project\LLM-driven-VRM\vrm_motion\runtime\datasets\raw" `
  --output-root "D:\AI-Program-Project\virea\data\virea_processed\full" `
  --continue-on-error `
  --report data\virea_processed\full\conversion-report.json
```

如果省略 full 的路径参数，会出现交互式输入：

```text
Full raw input root [...]:
Full processed output root [...]:
```

常用调试参数：

- `--datasets grab susuinteracts`：只转换指定数据集。
- `--query keyword`：按 sample id 或文本过滤。
- `--limit-per-dataset 2`：每个数据集最多转换 2 条。
- `--max-frames 8`：仅用于 smoke/debug；正式转换不建议使用。
- `--json`：在终端打印完整 JSON 报告。

CLI 会按数据集和样本打印细粒度进度，例如：

```text
[virea] conversion start source=demo raw=... out=...
[virea] dataset susuinteracts: 1 samples
[virea] susuinteracts 1/1 ok frames=82 joints=52 elapsed=0.02s
[virea] report written: demo\conversion-report.json
```

输出结构：

```text
processed_root/
  canonical/v0.1.0/motion/<dataset>/*.npz
  canonical/v0.1.0/metadata/<dataset>/*.json
  vrm/v0.1.0/motion/<dataset>/*.npz
  vrm/v0.1.0/quality/<dataset>/*.json
```

## 处理层次

代码按清晰层次组织，避免用数据集名称堆大段 `if/else` 死逻辑。

- `DatasetAdapter`：发现样本、读取文件、识别真实数据形式并给出 `codec_key`。
- `MotionCodec`：只处理一种明确的数据形态，例如 axis-angle body、SMPL-X fullpose、HumanML3D 263D、SuSu 6D body/hands。
- `Retarget`：负责坐标基归一化、rest-offset correction、position fitting 和 VRM FK。
- `VRM control rest audit`：从真实 `.vrm` humanoid raw rest skeleton 中拟合 `vrm_control_rest_template`，不再把 `after` 建在旧的通用 T-pose 模板上。
- `RawPreviewPipeline`：输出转换前的 source preview。
- `ProcessedPreviewPipeline`：输出 52 关节 VRM/canonical FK positions，并携带真实 `motion` payload。
- `viewer-web`：统一前端，同时展示 before、after 和真实 VRM 模型导入预览。

## Before / After 语义

- `before` 是 source preview。它只连接当前 codec 能可靠解释的源关节和源边，避免把不存在的手指、扩展骨或错误边强行连到身体上。
- `after` 是 canonical / VRM preview。它固定使用 `FK_BONES` 52 关节和 `FK_EDGES`，由 processed motion payload 按真实 VRM control-rest template 重新 FK 得到。
- `after` 不是 `before` 的复制。source skeleton 与 VRM target skeleton 的 rest bone length、关节定义和坐标基不同，因此不能要求两者绝对点位逐点相等。
- 严格的毫米级误差检查用于验证：保存后的 `sequence` 能否 FK 重建保存后的 `positions`，以及保存文件是否与 pipeline 内存结果一致。

## 真实 VRM Control-Rest Template

当前 target skeleton 的 rest offsets 会优先由本地真实 VRM 模型库生成：

```text
VIREA_VRM_MODEL_ROOT/*.vrm
  -> vrm_motion.data.vrm_inspector.inspect_vrm_avatar
  -> humanoid_bone_nodes raw world_position
  -> similarity fit to canonical body baseline
  -> averaged VRM control-rest offsets
  -> processed FK / motion.rest_offsets / frontend VRM alignment
```

这一步解决的核心问题是：不能直接把 canonical 四元数塞进任意 VRM 模型，也不能让 `after` 继续使用旧的通用骨架模板。`ProcessedPreviewPipeline` 会把同一套 `rest_offsets` 写入 `motion.rest_offsets`，前端导入 VRM 时会先根据真实模型的 authored rest skeleton 与该 target rest skeleton 求空间对齐，再驱动 `three-vrm` humanoid normalized pose。

可单独输出 audit：

```powershell
python -m virea.cli vrm-audit --out demo\vrm-control-rest-audit.json
```

报告会包含读取到的 VRM 数量、similarity scale / determinant、左右轴检查、头在胯上方检查、每个 VRM 与 control-rest template 的位置和骨向误差。若没有可用 VRM 模型或 inspector，pipeline 会回退到默认模板；但此时 `verify` 的 `vrm_control_rest_audit` 不会通过，应先配置 `VIREA_VRM_MODEL_ROOT`。

## 坐标、方向与原点

转换输出统一到：

```text
coordinate_system = gltf_y_up_z_forward
unit = meter
root starts at first-frame origin
rotation_format = quat_xyzw
```

对 axis-angle、SMPL-X、SuSu 6D 等局部旋转数据，会先用源 FK 推断 clip 的世界坐标基，再旋转到 glTF / VRM 约定。对 position-only 数据，会先把源关节映射到 canonical body，再进行 position fitting。这样可以避免 GRAB、Motion-X、SuSu 等数据集因为原始坐标轴不同而出现人物横躺、偏离原点或比例忽大忽小。

## 各数据集处理要点

### AMASS / BABEL / BEAT / GRAB

这类数据主要来自 SMPL-H / SMPL-X 风格 axis-angle 或 fullpose。

- raw 使用 22 关节 body source preview。
- processed 使用 VRM 52 关节 FK。
- root translation 会缩放并以首帧 root 为原点。
- 局部四元数会经过世界坐标基归一化和 rest-offset correction 后进入 VRM payload。

### Motion-X

Motion-X 的部分样本存在平移单位和长 root trajectory 差异。当前处理策略是：

- 人体骨架比例来自 VRM rest skeleton，不受长轨迹缩放影响。
- root trajectory 只作为 root motion 播放，不参与人物比例估计。
- `after` 由 52 关节 VRM FK 生成，而不是重用 source 点位。

### HumanML3D / position-only

HumanML3D 263D 会优先通过 Guo/HumanML 相关解码器还原 joints，再映射到 canonical body。

- raw 展示 22 关节 source body preview。
- processed 通过 position fitting 转为 VRM 52 关节 FK。
- 测试会检查 processed 不是 raw copy，并且 processed 可以由 motion payload 精确 FK 重建。

### SuSuInterActs

SuSu 有两类形态，不能共用同一套无差别转换。

- `chonglu`：包含真实 source positions。实测 `body[:, 0:3]` 与 `positions[:, 0]` 在 X/Z/Y 轴重排和 `0.01` 缩放后逐帧一致，因此优先按真实 positions 映射到 canonical body，再 position fitting 到 VRM。
- `retarget_maya`：没有可信绝对 source positions。真实文件中的 `body[:, 0:3]` 不能按 README 字面描述做速度累计；pipeline 会按绝对 root 位置处理，使用 X/Z/Y 到 glTF X/Y/Z 的轴重排、首帧归零，并根据数值范围自动判定米制或厘米制。
- SuSu body/hands 的 6D rotation 使用 column-major first-two-columns 约定解析为世界/全局朝向，再按 humanoid 父子关系转换为 VRM FK 所需的父节点局部四元数。

当前 SuSu body 顺序固定为：

```text
pelvis,
thigh_r, calf_r, foot_r, ball_r,
thigh_l, calf_l, foot_l, ball_l,
spine_01, spine_02, spine_03, spine_04, spine_05,
neck_01, neck_02, head,
clavicle_l, upperarm_l, lowerarm_l,
clavicle_r, upperarm_r, lowerarm_r,
hand_l, hand_r
```

对于没有 positions 的 `retarget_maya`，不再把下肢强制置为 rest pose。此前的保护分支会干扰世界坐标基推断并造成左右轴翻转，进而表现为手臂交叉、肩膀内缩。当前版本在全局 6D 转局部四元数后使用完整 body 链，同时通过测试检查脚不会高于头、左右上臂分离正常、root 轨迹没有累计放大。

## 前端预览

启动 demo：

```powershell
python -m virea.cli serve --data-source demo --host 127.0.0.1 --port 8014
```

启动 full：

```powershell
python -m virea.cli serve --data-source full --host 127.0.0.1 --port 8014
```

浏览器打开：

```text
http://127.0.0.1:8014/
```

交互能力：

- before / after 两个 canvas 都支持拖拽 360 度旋转、滚轮缩放、双击重置视角。
- `Show trails` 只显示 root 轨迹，不参与人体缩放或转换计算。
- `Show hands` 可切换手部细关节显示，避免默认视图被手指点云遮挡。
- 明/暗主题可在标题区域切换。
- VRM import 区域只显示导入的真实 `.vrm/.glb/.gltf` 模型，不再叠加 processed skeleton overlay。
- 导入 VRM 后，前端会用真实模型 raw humanoid rest skeleton 对齐 processed `motion.rest_offsets`，主时间轴和 VRM 面板内的 `VRM Frame` / `Play` 会同步驱动模型动作。
- 拖拽 VRM canvas 可全方位 orbit，滚轮缩放，`Reset View` 重置相机。

## 验证命令

推荐运行：

```powershell
$env:PYTHONPATH = "D:\AI-Program-Project\virea\src"
python -m compileall -q src
python -m pytest
python scripts/smoke_pipeline.py --data-source demo --max-frames 8
python scripts/smoke_pipeline.py --data-source full --max-frames 8
python -m virea.cli vrm-audit --out demo\vrm-control-rest-audit.json
python -m virea.cli verify --data-source demo --max-frames 32 --out demo\verification-report.json
```

验证重点：

- raw / processed 均为有限数值。
- 不存在异常长边，避免“弹簧线”或非身体连线。
- processed 始终是 `FK_BONES` 52 关节 VRM skeleton。
- `vrm_control_rest_audit` 必须读取真实 VRM 模型并通过左右轴、头/胯方向和 similarity fit 检查。
- processed motion payload FK 重建 after positions 的误差在毫米级阈值内。
- persisted `.npz` 中的 sequence、positions、root translation、rotation 与内存结果一致。
- SuSu `retarget_maya` 使用绝对 root、自适应单位、全局 6D 转局部四元数；测试会检查脚不会高于头部、左右上臂不反转、root step 没有异常累计放大。
- HumanML3D raw 是 source preview，processed 是 VRM FK，不再互相复制。

前端脚本静态检查：

```powershell
node --check apps/viewer-web/app.js
node --check apps/viewer-web/vrm-viewer.js
node --check apps/viewer-web/vrm-canonical-alignment.js
```

如果本机 Node 对 ES module 直接检查异常，应以浏览器实际加载 `/`、`/ui/app.js`、`/ui/vrm-viewer.js` 和 importmap vendor 文件为准。

## 常见问题

如果人物完全不动：

- 检查是否选择了过短或静止样本。
- 检查 `Max frames` 是否被设置得太小。
- 导入 VRM 后使用 VRM 面板内的 `VRM Frame` 滑块确认模型是否随帧变化。

如果 full 数据没有样本：

- 运行 `python -m virea.cli sources` 查看 raw root 是否存在。
- 检查 `VIREA_RAW_ROOT` 是否覆盖到了错误目录。

如果 VRM 模型没有动作：

- 确认导入的是 `.vrm`，普通 `.glb/.gltf` 只能静态显示。
- 查看 `modelStatus` 是否报告 humanoid bones 数量。
- 确认当前 sample 的 processed metadata 中包含 `motion` payload。

如果要正式转换全量数据：

- 不要传 `--max-frames`。
- 建议指定 `--report`。
- 建议先用 `--limit-per-dataset 1` 做一次 smoke，再运行全量。
