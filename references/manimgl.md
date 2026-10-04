# ManimGL 动画编排

为固定的 ManimGL 1.7.2 和 `TimelineScene` 编写动画。以下片段放在现有场景方法中；音频锚点仍由 `at()` 控制。按概念选取方法，不要求每个视频都使用镜头运动或三维。

## 图形和推导

先决定观众要看出什么关系，再选动画。比较大小用同一尺度；同一个量在图形、标签、公式中使用一致颜色。避免让正文逐字出现代替推导，也不要把无关对象同时运动当作丰富画面。

- 创建线条和曲线用 `ShowCreation`，公式用 `Tex(r'...')`，中文用 `Text(..., font='PingFang SC')`。
- ManimGL 1.7.2 中，`Tex`、`Text`、`Dot` 的整体颜色使用 `fill_color` 或创建后 `set_color()`；仅传 `color` 可能被默认填充色覆盖。公式局部语义配色继续用 `t2c`。
- 箭头用 `Arrow(..., fill_color=..., thickness=...)`，宽度用 `set_thickness()`；1.7.2 的 `Arrow` 不支持 `tip_length` 参数。外部例子先核对固定版本的接口。
- 中文字体存在不代表所有字形渲染正确。短样片使用项目的实际标签；发现描边异常或缺笔画时，可试本机已安装的 `Arial Unicode MS`，查看画面确认后统一使用，不必重装环境。
- 当前默认 TeX 模板中，非必要的 `\!` 数学间距曾导致编译失败；优先去掉该间距或用明确的 `\hspace{...}`，保留公式含义。`Tex` 保持默认的 `use_labelled_svg=True`；1.7.2 的关闭分支调用缺失接口，不能用它修复公式排版。
- 坐标系用 `Axes(width=..., height=...)`，函数用 `axes.get_graph(...)`；沿用坐标转换 `axes.c2p(x, y)`，不靠手动像素位移假装数值关系。
- `Transform(a, b)` 保留场景中的 a；`ReplacementTransform` 和公式匹配会换成 b，后续更新必须持有新引用。
- 相关公式用 `isolate` 分离需要对应的项，配合 `t2c`、`TransformMatchingTex`；检查对应是否符合数学含义。数字替换或中文标题切换优先分两次 `play` 执行 `FadeOut(old)` 和 `FadeIn(new)`，避免中间帧重叠成错误数字、符号或文字；公式匹配用于确有语义对应的项。

原创示例：

```python
colors = {'x': BLUE, '3': YELLOW}
old = Tex(r'x+3=7', isolate=['x', '3', '7'], t2c=colors)
new = Tex(r'x=7-3', isolate=['x', '3', '7'], t2c=colors)
new.move_to(old)
self.add(old)
self.play(TransformMatchingTex(old, new), run_time=1.2)
equation = new
```

## 动态关系

用一个 `ValueTracker` 驱动关联对象，标签与图形读取同一个参数。沿函数曲线移动时，动画改变自变量，再由函数计算纵坐标；不直接在两个曲线点之间做直线插值。形状不变时用 updater 移动已有对象；需要重建形状时才用 `always_redraw`，避免每帧重编译文字与公式。依赖关系结束后调用 `clear_updaters()`，以免影响后续变换。

```python
position = ValueTracker(0)
point = Dot(fill_color=BLUE)
point.add_updater(lambda mob: mob.move_to(axes.c2p(position.get_value(), position.get_value() ** 2)))
self.add(point)
self.play(position.animate.set_value(2), run_time=2)
point.clear_updaters()
```

## 镜头与节奏

通过 `self.frame.animate` 移动或缩放镜头；三维需要时使用 `reorient`。需要留在屏幕上的标题和标签调用 `fix_in_frame()`；底部给烧录字幕留空间。镜头运动应突出局部关系，同时保留必要上下文。

相连步骤保留已有图形状态，用 `LaggedStart` 表达有顺序的出现，用 `AnimationGroup` 表达同时变化；总动画时长必须落在相邻音频锚点之间。公式变换后留出读懂的时间，避免转场挤占下一句的动作。

`TimelineScene` 已在公共层按整数帧推进动画与等待，避免浮点步长多导出一帧；无需在每个项目重复补丁。动画时长按帧取整，仍由 `at()`、`finish()` 和导出帧数检查拒绝超时，不能用最终裁切掩盖错误。

代表性短样片应覆盖实际中文标签、复杂公式和新转场；使用同一渲染环境和样式，查看静态完成帧及转场中间帧。短样片可继承 `FrameExactScene`，无需配音或项目时间轴；用 `render_gl.write_configuration()`、`environment()` 和 `command()` 复用正式渲染配置。先集中修正已发现的问题，再批量构建。当前单个 `scene.py` 的修改会使所有视觉段缓存失效，短样片验证可减少反复全片重渲染；配音缓存仍可复用。

正式导出由流水线执行。局部调试可在已配置的渲染环境使用 `manimgl scene.py Explainer -se <行号>`；需要项目和时间轴环境变量，不能把交互断点、跳过动画或 `checkpoint_paste()` 放进正式构建路径。

## 参考与边界

参考 [adithya-s-k/manim_skill 的 ManimGL 最佳实践](https://github.com/adithya-s-k/manim_skill/tree/main/skills/manimgl-best-practices) 的主题组织，以及 [ManimGL 1.7.2 官方源码](https://github.com/3b1b/manim/tree/v1.7.2)。上述示例为本 skill 原创，不复制参考仓库的视频代码。外部示例需核对固定版本的 API，并实际渲染后使用。
