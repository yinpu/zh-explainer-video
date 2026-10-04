"""Four-second probe for glyphs, nested TeX and fractional frame export."""
from manimlib import *
from scene_support import FrameExactScene


class RenderProbe(FrameExactScene):
    def construct(self):
        title = Text('小明观察向量的值 · PingFang SC', font='PingFang SC', font_size=32).to_edge(UP)
        title.fix_in_frame()
        import manimpango
        if 'Arial Unicode MS' in manimpango.list_fonts():
            fallback = Text('小明观察向量的值 · Arial Unicode MS', font='Arial Unicode MS', font_size=28).move_to([0, 2.2, 0])
            fallback.fix_in_frame()
            self.add(fallback)
        first = Tex(r'f(x)=\left(\frac{x+x}{\sqrt{2}}\right)', isolate=['x', '2'], t2c={'x': BLUE}).shift(UP * .5)
        second = Tex(r'f(x)=\frac{2x}{\sqrt{2}}', isolate=['x', '2'], t2c={'x': BLUE}).shift(UP * .5)
        amount = ValueTracker(-2)
        dot = Dot(fill_color=YELLOW).add_updater(lambda m: m.move_to([amount.get_value(), -1, 0]))
        self.add(title, first, dot, Line([-3, -1, 0], [3, -1, 0]))
        self.play(TransformMatchingTex(first, second), run_time=1)
        self.play(amount.animate.set_value(2), run_time=1)
        dot.clear_updaters()
        self.play(self.frame.animate.scale(.85).shift(RIGHT * .3), run_time=1)
        # 23/30 is a known extra-endpoint case in ManimGL's floating arange.
        self.wait(23 / 30)
        self.wait(7 / 30)
