# zh-explainer-video

用本地 ManimGL 与固定中文音色制作数学、算法和计算机原理讲解视频的 Codex skill。

默认生成 5–20 分钟、1920×1080、30 fps 的横屏视频，采用深色背景、中文烧录字幕、无背景音乐。通过图形直觉和连续推导解释概念，保留可编辑、可续跑的完整工程。

## 功能

- 固定 ManimGL 1.7.2，使用 `TimelineScene` 按实际音频时间轴编排动画。
- 本地 Qwen3-TTS 1.7B CustomVoice MLX 8-bit 配音，默认 Serena 普通话。
- 本地 ASR 检查漏读与重复，ForcedAligner 生成字幕和动画锚点。
- 支持跨镜头配音 `narration_groups` 与连续画面 `render_mode: continuous`。
- 缓存音频与中间结果，修改画面可复用配音，中断后可继续构建。
- 导出 MP4、WAV、SRT、讲稿、源码、时间轴及质量检查结果。

## 环境

面向 Apple Silicon macOS，建议至少 16 GB 内存。语音环境和渲染环境相互独立，模型保存在共享运行目录，首次安装需要下载数 GB 模型。

需要 Python 3.12、uv、支持 ASS 字幕的 FFmpeg、Cairo、Pango；公式渲染需要 LaTeX 和 dvisvgm。安装细节见 [环境准备](references/setup.md)。

## 安装

将仓库放入本地 skills 目录；目标目录已存在时，请先保留已有版本。

```bash
git clone https://github.com/yinpu/zh-explainer-video.git ~/.codex/skills/zh-explainer-video
```

检查环境，再按 [环境准备](references/setup.md) 补齐系统工具并安装独立运行环境：

```bash
python3 ~/.codex/skills/zh-explainer-video/scripts/zvideo.py doctor
python3 ~/.codex/skills/zh-explainer-video/scripts/zvideo.py setup
python3 ~/.codex/skills/zh-explainer-video/scripts/zvideo.py doctor --verify-models --verify-render
```

共享运行环境默认位于 `~/Documents/Codex/runtimes/zh-explainer-video`，可通过 `--runtime` 或 `ZVIDEO_RUNTIME` 覆盖。安装不会将模型复制到仓库中。

## 使用

在 Codex 中调用：

> 使用 $zh-explainer-video 制作一部十分钟的中文视频，面向高中生解释导数为什么表示瞬时变化率，用连续动画展示割线如何趋近切线。

完整工作流与声音、字幕、画面规范见 [SKILL.md](SKILL.md)。项目接口见 [项目说明](references/project.md)，动画编排见 [ManimGL 指南](references/manimgl.md)。

命令行入口：

```bash
python3 ~/.codex/skills/zh-explainer-video/scripts/zvideo.py build /path/to/project --stop-after audio
python3 ~/.codex/skills/zh-explainer-video/scripts/zvideo.py build /path/to/project
python3 ~/.codex/skills/zh-explainer-video/scripts/zvideo.py resume /path/to/project
python3 ~/.codex/skills/zh-explainer-video/scripts/zvideo.py qa /path/to/project
```

`assets/starter` 提供最小接口示例，`assets/derivative-example` 提供导数示例。请将示例复制到单独的项目目录后修改，正式视频应围绕主题绘制图形并展开完整讲解。

质量要求见 [质量检查](references/quality.md)。自动检查通过后，仍需查看画面并试听声音接缝。

## 目录

```text
SKILL.md                 skill 指令
agents/openai.yaml       界面配置
scripts/                 构建、配音、对齐、渲染与测试脚本
references/              环境、项目、动画和质量文档
assets/starter/          最小项目示例
assets/derivative-example/ 导数项目示例
```

## 验证脚本

以下测试不下载模型，也不执行语音模型推理：

```bash
python3 -B -m unittest discover -s scripts -p 'test_pipeline.py'
python3 -B -m unittest discover -s scripts -p 'test_render_gl.py'
~/Documents/Codex/runtimes/zh-explainer-video/.venv/bin/python -B scripts/test_grouped_audio.py
```

最后一项需要运行环境中的 NumPy 与 soundfile，用于验证连续录音裁切、上下文排除和波形拼接。
