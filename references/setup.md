# 本地环境准备

目标：Apple Silicon macOS，建议至少 16 GB 内存。安装需要网络；生成使用本地模型，不调用云端语音接口。

```bash
python3 <skill>/scripts/zvideo.py doctor
python3 <skill>/scripts/zvideo.py setup
python3 <skill>/scripts/zvideo.py doctor --verify-models
```

`setup` 创建专用 Python 3.12 语音环境 `.venv`，按 `scripts/requirements.lock.txt` 安装已验证的完整依赖版本，下载模型并验证 LFS SHA-256，保存模型 revision、文件校验值和安装包清单。`requirements.txt` 列出直接依赖。已有模型沿用记录的版本，不追随最新版本。

基础工具缺失时只补齐缺项：

```bash
brew install uv ffmpeg-full cairo pango pkg-config
python3 <skill>/scripts/zvideo.py setup-render
python3 <skill>/scripts/zvideo.py doctor --verify-render
```

公式需要 `latex`、`dvisvgm`。已有 TeX 优先复用；缺失且需要公式时安装 `brew install --cask mactex-no-gui`，将 `/Library/TeX/texbin` 加入 PATH。MacTeX 下载较大，不重复安装。中文标签用 Pango `Text`，默认 `PingFang SC`，字幕用 `Arial Unicode MS`。用独立渲染环境的 `manimpango.list_fonts()` 核对字体。

流水线入口可继续使用 `python3`。自行编写依赖第三方库的辅助脚本时，使用 `runtime.json` 对应的虚拟环境；图像抽帧检查所需的 Pillow 位于渲染环境，不假设系统 Python 与两个虚拟环境有相同依赖。

`setup` 不修改系统 Python，也不自动升级系统工具。`doctor` 指出缺项。运行目录 `runtime.json` 可指定 python、render_python、manimgl、ffmpeg、ffprobe 绝对路径。

FFmpeg 必须包含 `ass` 字幕滤镜；新版 Homebrew 普通 `ffmpeg` 可能不包含它。流水线优先使用 `/opt/homebrew/opt/ffmpeg-full/bin/ffmpeg`，无需覆盖系统默认 FFmpeg。用 `ffmpeg -h filter=ass` 或 `doctor` 验证。

模型固定为以下 MLX 8-bit 版本，存入共享运行目录 `models/`：

- `mlx-community/Qwen3-TTS-12Hz-1.7B-CustomVoice-8bit`
- `mlx-community/Qwen3-ForcedAligner-0.6B-8bit`
- `mlx-community/Qwen3-ASR-0.6B-8bit`

总下载量约数 GB，另需渲染缓存空间。首次性能以本机样片实测为准。

## 独立渲染环境

`setup-render` 用 Python 3.12 创建 `.render-venv`，按 `scripts/render-requirements.lock.txt` 同步固定依赖；直接依赖见 `render-requirements.txt`。版本固定为 ManimGL 1.7.2。该命令不安装或更新语音模型，成功后在共享 runtime 保存路径与渲染包清单，并实际导出四秒检查片。

`doctor --verify-render` 验证版本、OpenGL 上下文、含分数与根号的 LaTeX、动态图形、镜头移动及分数帧时长，检查 720p/30 fps 的 MP4 帧数。检查片包含 PingFang SC 的代表性中文字，安装 Arial Unicode MS 时也展示对照行；字体是否正确仍需查看画面。片段和日志保存在共享 runtime 的 `render-probe/`；普通 `doctor` 只做较轻的依赖检查，不能据此宣称已通过实际导出验证。

## 故障处理

- OpenGL 上下文创建失败：查看 `render-probe/render.log`；若受沙箱 GPU 访问限制，申请所需执行权限后重试。不能静默换引擎，也不能仅凭安装成功声称可渲染。
- `No Metal device available`：沙箱无法访问 GPU，通过执行工具申请本地 GPU 所需权限后重试，不更换云端配音。
- `doctor` 的 `python_imports` 失败时查看 `diagnostics.python_import_error`；若是 GPU 访问限制，先处理执行权限，不能据此判定需要重新安装依赖或模型。
- 下载中断：程序最多重试三次，复用缓存；仍失败时保留文件并指出原因，不关闭 TLS 校验。
- 内存不足：关闭并行模型任务，按 TTS → ASR → 对齐运行；长语义块在完整句子边界拆开，不静默降级声音。
- 对齐失败：核对 ASR 文本、字符覆盖和时间戳，不用均匀时间分配假装通过。

来源：[ManimGL](https://3b1b.github.io/manim/getting_started/installation.html)、[Qwen3-TTS](https://github.com/QwenLM/Qwen3-TTS)、[Qwen3-ASR](https://github.com/QwenLM/Qwen3-ASR)、[MLX Audio](https://github.com/Blaizzy/mlx-audio)。
