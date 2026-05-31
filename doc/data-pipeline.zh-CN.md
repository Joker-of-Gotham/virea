# VIREA 数据 Pipeline 说明

本文档已精简为 pipeline 指南的兼容入口。最新说明请阅读：

- [Pipeline 使用指南](pipeline.zh-CN.md)
- [工程设计](engineering-design.zh-CN.md)
- [Showcase 生成说明](showcase/README.md)

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

坐标约定统一为 glTF / VRM：`+Y` up、`+Z` forward、meter、quat `xyzw`。
