# Pipeline 使用指南

本文从环境部署到 viewer 预览，给出当前可运行的最短路径。

## 1. 环境部署

Windows PowerShell:

```powershell
git clone git@github.com:Joker-of-Gotham/virea.git
cd virea

python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
```

如果使用本机完整数据源：

```powershell
$env:VIREA_RAW_ROOT = "<path-to-full-raw-datasets>"
```

如果仓库内没有 `vendor/three` 和 `vendor/three-vrm`，viewer 的 JS 依赖也通过
环境变量提供：

```powershell
$env:VIREA_THREE_ROOT = "<path-to-node_modules-three>"
$env:VIREA_THREE_VRM_ROOT = "<path-to-node_modules-three-vrm>"
```

## 2. 构建 demo fixture

`demo` 使用和 `full` 相同的目录结构，但只复制少量样本，方便端到端调试。

```powershell
python -m virea.cli build-demo --samples-per-dataset 7 --overwrite
```

说明：

- `demo/raw` 是从本机 full 数据源复制出来的本地 fixture。
- 第三方 raw dataset 可能有许可限制，默认仍由 `.gitignore` 排除。
- README 中的结果视频是轻量可提交展示产物，不等价于公开 raw dataset。

## 3. 批量处理

处理 demo：

```powershell
python -m virea.cli process --data-source demo --workers 8 --force
```

处理 full 中的指定数据集：

```powershell
python -m virea.cli process `
  --data-source full `
  --datasets motionx susuinteracts `
  --workers 8 `
  --force
```

常用参数：

- `--datasets`: 限制数据集
- `--query`: 按 sample id / 文本过滤
- `--limit-per-dataset`: 每个数据集最多处理多少条
- `--max-frames`: 仅用于调试或快速预览，正式处理建议省略
- `--skip-existing` / `--force`: 控制是否跳过已存在 artifacts

## 4. 启动 viewer

```powershell
python -m virea.cli serve --data-source demo
```

打开 CLI 输出的 server URL。

操作顺序：

1. 选择 `demo` 或 `full`
2. 选择数据集和样本
3. 查看 before/source preview
4. 查看 after/VRM preview
5. 导入本地 `.vrm`，或设置 `VIREA_SHOWCASE_VRM`
6. 点击 Play，以 clip 的真实 fps 播放

## 5. 生成结果看板

先选择每个数据集的高质量样本：

```powershell
python scripts/select_showcase_samples.py `
  --metadata-root demo\processed\canonical\v0.1.0\metadata `
  --per-dataset 7 `
  --out doc\showcase\showcase-samples.json
```

再用浏览器录制真实 VRM avatar：

```powershell
$env:PLAYWRIGHT_MODULE = "<path-to-playwright-index.mjs>"
$env:VIREA_SHOWCASE_SERVER = "<viewer-server-url>"
$env:VIREA_SHOWCASE_VRM = "<path-to-avatar.vrm>"

node scripts/render_showcase.mjs `
  --data-source demo `
  --manifest doc\showcase\showcase-samples.json `
  --out-dir doc\showcase\videos
```

当前仓库中的 49 个 WebM 结果视频就是用上述流程生成。

## 6. 验证

```powershell
python -m compileall -q src
python -m pytest -q
node --check apps/viewer-web/app.js
node --check apps/viewer-web/vrm-viewer.js
python scripts/smoke_pipeline.py --data-source demo --max-frames 8
python scripts/smoke_pipeline.py --data-source full --max-frames 8
```

当前 CLI 支持 `process`、`serve`、`build-demo`。如果旧文档里出现 `verify` 或
`convert` 子命令，应以当前 CLI 为准。
