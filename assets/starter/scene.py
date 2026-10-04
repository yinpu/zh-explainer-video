from manimlib import *
from scene_support import TimelineScene

class Explainer(TimelineScene):
    def construct(self):
        self.add(Text(self.block['title'],font='PingFang SC',font_size=35).to_edge(UP,buff=.5))
        circle=Circle(radius=1,color='#58C4DD')
        self.at('circle')
        self.play(ShowCreation(circle),run_time=.8)
        self.at('change')
        self.play(circle.animate.scale(1.8),run_time=1.5)
        self.finish()
