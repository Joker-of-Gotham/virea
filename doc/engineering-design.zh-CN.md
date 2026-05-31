# 工程设计

VIREA 的工程设计围绕一个原则：转换逻辑、持久化逻辑和展示逻辑必须分离。

## 模块边界

```text
DatasetAdapter
  发现样本、读取文件、识别 source_format 和 codec_key

MotionCodec
  extract_source(): 生成 before/source preview
  to_canonical(): 生成 canonical / VRM motion

Retarget
  坐标 basis、单位、rest-offset、position fitting、VRM FK

ProcessingPipeline
  调 adapter + codec + quality，写入 artifacts

PreviewReader
  只读 artifacts，不做 retarget

FastAPI server
  提供 samples、source preview、processed preview、motion payload、quality

viewer-web
  展示 before / after / real VRM avatar，不承担数据转换职责
```

## 关键设计选择

### 1. codec 按数据形态，不按数据集硬编码

AMASS/BABEL/BEAT/GRAB/Motion-X/HumanML3D/SuSuInterActs 的外壳不同，但真正
决定转换方式的是数据形态：axis-angle body、SMPL-X fullpose、position
sequence、SuSu 6D 等。codec 负责解释这些形态。

### 2. 世界坐标 basis 必须显式

过去的“根据姿态猜上轴”容易把爬行、倒立、撑地动作旋成站立动作。现在优先用
adapter/codec 声明的 basis，例如：

- `identity_y_up`
- `z_up_to_y_up`
- `neg_z_up_to_y_up`

只有缺少声明时才回退到启发式推断。

### 3. source preview 和 processed preview 不互相复用

`before` 是 source 解释结果，用来检查原数据。`after` 是 VRM target FK 结果，
用来检查 retarget 后的可执行动作。两者 skeleton、骨长和语义都不同，不应强行
逐点相等。

### 4. FPS 是播放语义，不是 UI 常量

每个 clip 的真实 `fps` 必须进入 viewer 播放逻辑。高帧率数据在 60Hz 屏幕上应
跳帧保持真实速度，而不是因为 `setInterval` 或固定延迟变慢。

### 5. 质量报告服务于排错

quality report 记录：

- finite / schema 检查
- ground contact
- velocity / jitter
- left-right symmetry
- retarget direction error
- source / target metadata

这些指标不是最终审美分数，但能快速定位坐标、单位、骨架映射和异常样本。

## 持久化结构

```text
processed_root/
  source/v0.1.0/snapshot/<dataset>/*.npz
  canonical/v0.1.0/motion/<dataset>/*.npz
  canonical/v0.1.0/metadata/<dataset>/*.json
  vrm/v0.1.0/positions/<dataset>/*.npz
  vrm/v0.1.0/motion/<dataset>/*.npz
  vrm/v0.1.0/quality/<dataset>/*.json
```

`demo/processed` 用于本地快速验证，完整数据输出默认放在 `data/virea_processed/full`。
大型 raw/processed 数据不直接进入 Git。
