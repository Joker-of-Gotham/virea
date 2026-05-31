# Showcase 生成说明

本目录保存 README 中 7 x 7 结果视频看板的轻量展示产物。

## 内容

- `showcase-samples.json`: 每个数据集选出的 7 条样本及质量摘要
- `videos/*.webm`: 用真实 VRM avatar 录制的 VP8 WebM 结果视频
- `gifs/*.gif`: README 直接展示用的动画预览，点击后打开对应 WebM

视频使用的本地模型：

```text
C:\Users\explo\Downloads\VRM-Model-1.vrm
```

模型文件不入库，只提交渲染后的视频。

## 选择策略

`scripts/select_showcase_samples.py` 会读取
`demo/processed/canonical/v0.1.0/metadata/<dataset>/*.json`，按以下信号排序：

- retarget direction error 越低越好
- ground penetration 越少越好
- jittery joints 越少越好
- clip 不应过短
- 左右对称异常不应过大

生成：

```powershell
python scripts/select_showcase_samples.py `
  --metadata-root demo\processed\canonical\v0.1.0\metadata `
  --per-dataset 7 `
  --out doc\showcase\showcase-samples.json
```

## 录制策略

`scripts/render_showcase.mjs` 会打开本地 viewer，加载真实 `.vrm`，逐条 sample
载入 processed motion payload，从 `modelCanvas` 录制视频。

```powershell
node scripts/render_showcase.mjs `
  --server http://127.0.0.1:8014 `
  --data-source demo `
  --manifest doc\showcase\showcase-samples.json `
  --out-dir doc\showcase\videos `
  --vrm "C:\Users\explo\Downloads\VRM-Model-1.vrm"
```

默认输出 VP8 WebM，便于浏览器播放和轻量提交。GitHub 仓库 README 对内嵌
video 标签支持不稳定，因此根 README 使用 GIF 预览作为看板内联媒体，并保留
WebM 作为原始结果视频。

## README GIF 预览

如果需要重新生成 README 中的 GIF 预览，可以用任意本机 `ffmpeg`：

```powershell
New-Item -ItemType Directory -Force doc\showcase\gifs | Out-Null
Get-ChildItem doc\showcase\videos -Filter *.webm | ForEach-Object {
  ffmpeg -y -i $_.FullName `
    -vf "fps=8,scale=160:-1:flags=lanczos,split[s0][s1];[s0]palettegen=max_colors=64[p];[s1][p]paletteuse=dither=bayer:bayer_scale=4" `
    ("doc\showcase\gifs\" + $_.BaseName + ".gif")
}
```
