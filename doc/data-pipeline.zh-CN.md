# VIREA 数据 Pipeline 说明

本文是数据 pipeline 的兼容入口。完整运行步骤请读 [Pipeline 使用指南](pipeline.zh-CN.md)，数学转换细节请读 [Retarget 数学原理](math-retarget/README.zh-CN.md)，模块边界请读 [工程设计](engineering-design.zh-CN.md)。

核心流程保持为：

```text
raw dataset
  -> DatasetAdapter
  -> RawClip
  -> MotionCodec.extract_source()
  -> MotionCodec.to_canonical()
  -> ProcessingPipeline artifacts
  -> PreviewReader / FastAPI
  -> viewer-web / real VRM avatar
```

其中：

- `DatasetAdapter` 负责发现样本、读取 raw 文件、声明 `source_format`、`codec_key`、fps、metadata。
- `MotionCodec.extract_source()` 生成 source/before preview，用于检查原始动作解释是否正确。
- `MotionCodec.to_canonical()` 执行 retarget，输出 VRM-centered canonical sequence。
- `ProcessingPipeline` 写入 source snapshot、canonical motion、VRM FK positions、quality report。
- `PreviewReader` 和 server 只读 artifacts，不重新做数学转换。

坐标约定统一为 glTF / VRM：`+Y` up、`+Z` forward、meter、quat `xyzw`。
