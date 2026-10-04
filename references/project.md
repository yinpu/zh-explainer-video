# 项目接口

项目有 `project.json`、`scene.py`、`work/` 缓存和 `outputs/` 交付。命令传入项目目录。`assets/starter` 为最小接口范例，需要扩展为完整内容后达到默认 300–1200 秒。

编写动画前，在项目根目录维护 `scenes.md`，记录视觉论证与各场到 `blocks`、`beats` 的映射，写法见 [分镜与视觉论证](storyboarding.md)。它供创作和审阅使用，不由流水线解析或自动复制到 `outputs/`；现有项目配置接口不变。

`assets/derivative-example/` 保存约九分钟导数案例配置和原创 ManimGL 源码，可参考其坐标系、颜色、语义锚点、割线/切线及推导布局。它不包含权重或音频；新主题应重新设计讲稿和论证，不能仅替换标题。

```json
{
  "schema_version": 1,
  "title": "导数为什么代表瞬时变化率",
  "target_seconds": [300, 1200],
  "scene_file": "scene.py",
  "scene_class": "Explainer",
  "video": {"width": 1920, "height": 1080, "fps": 30},
  "blocks": [{
    "id": "intuition",
    "title": "从平均变化开始",
    "text": "这里是实际朗读的中文讲稿。关键词必须出现在文字中。",
    "beats": [{"id": "focus", "phrase": "关键词", "occurrence": 1}]
  }]
}
```

- ID 唯一，使用小写字母、数字、下划线和连字符。改写内容时保持 ID。
- `blocks` 描述视觉内容和实际朗读文本；不是必须独立配音的单元。`text` 不含 LaTeX 和字幕标签；长度由概念与镜头需要决定。字幕直接取 `text`，ASR 仅检查漏读或重复，不负责改写字幕。英文技术术语保留标准拼写，例如“词元，也叫 token”，不要为配音把 token 写成“托肯”。
- `beats` 按讲话顺序排列，`phrase` 必须在原文中，默认第一次出现，重复时指定 `occurrence`。
- `voice` 可覆盖全片 `speaker`、`temperature`、`seed`、`instruct`、`max_tokens`；默认 Serena、temperature 0.6、固定种子、自然普通话课堂讲解语气，强调逻辑重音、思考停顿与自然语调。不支持逐块更换声音；已有项目的显式 `voice.instruct` 覆盖默认值，修改默认值不会自动更新此类项目。
- `video.fps` 必须整除 24000。字幕设计坐标为 1920×1080，合成时自动缩放。
- 可添加自定义视觉字段供 scene 使用，流水线保留这些字段。

```python
from manimlib import *
from scene_support import TimelineScene

class Explainer(TimelineScene):
    def construct(self):
        circle = Circle(color=BLUE)
        self.at("focus")
        self.play(ShowCreation(circle), run_time=1)
        self.finish()
```

逐段模式中，每块运行同一 Scene，根据 `self.block['id']` 分派镜头。`self.job` 是完整配置，`self.timing` 是该块实际时长和锚点。`at` 等待到锚点，超出一个视频帧则报错；作者应调整动画时长。`finish` 补足剩余时间并拒绝超时。

需要标题时可在顶部放简短提示，底部约 0.7 个场景单位留字幕，并检查最终合成效果。主体布局随当前论证调整。公式用 `Tex`，中文用 `Text(font='PingFang SC')`。画面应让图形参与解释，避免满屏讲稿。公式变换、动态关系和镜头写法见 [动画编排](manimgl.md)。

```bash
python3 <skill>/scripts/zvideo.py build <project> --stop-after tts
python3 <skill>/scripts/zvideo.py resume <project> --stop-after audio
python3 <skill>/scripts/zvideo.py resume <project>
python3 <skill>/scripts/zvideo.py qa <project>
```

`build` 与 `resume` 都按指纹复用产物，音频额外核对 SHA-256。每项目有构建锁，防止并发写入。`work/audio` 保存逐块 WAV；`asr`、`align` 保存识别与对齐；`video` 保存静音镜头；`state.json` 保存阶段和重试次数。保留工作目录即可续跑。


## 连续旁白与连续画面

当多个镜头构成同一段连续解释时，可组合配音；需要跨镜头保留图形对象时，可选择连续渲染。这是两个独立选项，可以只启用其中一个。以下示例假设 `blocks` 已包含所列 ID：

```json
{
  "render_mode": "continuous",
  "narration_groups": [
    {"id": "take_1", "blocks": ["intuition", "representation"],
     "context_before": "", "context_after": "下一段开头的一句完整话。"},
    {"id": "take_2", "blocks": ["computation"],
     "context_before": "上一段结尾的一句完整话。", "context_after": ""}
  ]
}
```

`narration_groups` 必须按顺序恰好覆盖全部 `blocks`，ID 唯一。合成文本为前文 + 各视觉段正文 + 后文。上下文用真实相邻的一两句，不是额外配音指令。末段也可保留一句不交付的自然后文，避免合成的结束效应截断正文尾字。后文不是成片结尾的延长或新内容。原音频、整体 ASR 和对齐保存在 `work/groups/`；流水线在实际对齐停顿处裁去上下文，将正文切成帧边界对齐的视觉段，保存原录音 ID 与采样索引。只校验实际交付的正文及紧邻裁切边界的发音时间；若较远的弃用后文被对齐器外推，保留原对齐供审计，不把外推时间夹到正文。正文时间越界必须失败。

同一录音内部的各段拼回后波形连续，母带不会再次添加 0.24 秒间隔。独立录音默认保留对齐裁切后的自然停顿。只有停顿偏长时，才按需要启用安静边缘裁切：

```json
{
  "narration_join": {
    "trim_silence": true,
    "lead_seconds": 0.25,
    "tail_seconds": 0.20
  }
}
```

`trim_silence` 默认 false。起句、尾句余量是可调的起始值，不是所有视频的目标节奏；根据语气、句末呼吸和章节意图选择。`join_trim.py` 只裁短安静边缘，遇到有声切点保留原余量并记录，不跨有声字句做淡化。修改或关闭裁切设置会从原录音重新派生片段，不累积剪短；无需重新配音。

按语义、生成稳定性、实测时长与峰值内存确定录音段大小，不要求固定秒数或固定镜头数量；`voice.max_tokens` 是生成上限（默认 2048），不是时长目标。增加上限不能解决内存不足。改正文或上下文时只重做关联录音段；不要单独重配其中一个镜头破坏同一录音的连续性。

连续画面只运行一次 Scene。此时 `self.timeline` 是完整时间轴，`begin_block(id)` 更新当前视觉段，`at` 自动使用全片偏移，`local_time()` 返回当前段已播放时长。示意：

```python
class Explainer(TimelineScene):
    def construct(self):
        circle = Circle(color=BLUE)
        for block in self.job['blocks']:
            self.begin_block(block['id'])
            # 根据实际锚点移动、变形或补充对象；不在此 clear()。
            self.draw(block, circle)
            self.finish()
```

连续渲染适合对象状态需要跨镜头延续的推导；逐段渲染适合独立章节、不同场景和需要局部重渲染的内容，两者都可做连贯讲解。`render_mode` 缺省为逐段渲染。转场需要结合叙事判断，章节重置并非错误；应避免无意的重新开场。

文本与标题的过渡应检查中间帧。不同字形直接插值可能产生碎字，可选择淡化或切换；同一文本的位置、大小、透明度变化可以保留原对象。图形采用何种过渡，以表达关系和保持可读为准。


## 渲染输出与复用

流水线通过固定 ManimGL 1.7.2 的 `-w` 导出，无需交互窗口。帧率以数值写入每次渲染的配置文件（该版本 CLI 的 `--fps` 会产生字符串），并用 ffprobe 核对实际帧率、尺寸和帧数。场景必须保留 `TimelineScene` 的计时，不使用跳过动画或 `embed()` 完成正式构建。

`runtime.json` 的 `render_python`、`manimgl` 指向独立 `.render-venv`。视频缓存包含渲染包版本、场景源码、时间轴、项目配置及本地 `custom_config.yml` 指纹；`outputs/renderer.json` 记录引擎信息。只改画面继续复用声音。自定义场景若读取外部资产或辅助模块，其改变后应删除对应 `work/video/<id>.json` 触发重渲染。
