from manimlib import *
from scene_support import TimelineScene

BG='#10141B'; FG='#EAF0F6'; MUTED='#8392A5'; BLUE='#58C4DD'; YELLOW='#FFE47A'; GREEN='#83C167'; RED='#FC887B'
FONT='PingFang SC'


def label(text,size=26,color=FG):
    return Text(text,font=FONT,font_size=size,fill_color=color)


class Explainer(TimelineScene):
    def construct(self):
        self.add(Rectangle(width=14.23,height=.055,stroke_width=0,fill_color=BLUE,fill_opacity=1).to_edge(UP,buff=0))
        order=[b['id'] for b in self.job['blocks']].index(self.block['id'])+1
        self.add(label('变化的数学  /  THE MATHEMATICS OF CHANGE',15,MUTED).to_corner(UL,buff=.42))
        self.add(label(f'{order:02} / {len(self.job["blocks"]):02}',16,MUTED).to_corner(UR,buff=.42))
        self.add(label(self.block['title'],35).move_to([0,2.78,0]))
        getattr(self,'draw_'+self.block['kind'])()
        self.finish()

    def graph(self,wide=False):
        if wide:
            axes=Axes(x_range=[-3,3,1],y_range=[0,9,3],width=7.0,height=4.4,
                      axis_config={'color':MUTED,'stroke_width':1.5,'include_tip':True,'tip_config':{'width':.12,'length':.12}})
            axes.move_to([-2.2,-.35,0])
            graph=axes.get_graph(lambda x:x*x,x_range=[-2.9,2.9],color=BLUE,stroke_width=4)
        else:
            axes=Axes(x_range=[0,4,1],y_range=[0,12,2],width=7.0,height=4.4,
                      axis_config={'color':MUTED,'stroke_width':1.5,'include_tip':True,'tip_config':{'width':.12,'length':.12}})
            axes.move_to([-2.2,-.35,0])
            graph=axes.get_graph(lambda x:x*x,x_range=[0,3.35],color=BLUE,stroke_width=4)
        xlab=Tex('x' if wide else 't',font_size=27,fill_color=MUTED).next_to(axes.x_axis.get_end(),RIGHT,buff=.12)
        ylab=Tex('f(x)' if wide else 's(t)',font_size=27,fill_color=MUTED).next_to(axes.y_axis.get_end(),UP,buff=.1)
        nums=VGroup()
        for x in ([-2,-1,1,2] if wide else [1,2,3]):
            nums.add(Tex(str(x),font_size=20,fill_color=MUTED).next_to(axes.c2p(x,0),DOWN,buff=.12))
        for y in ([3,6] if wide else [4,8]):
            nums.add(Tex(str(y),font_size=20,fill_color=MUTED).next_to(axes.c2p(0,y),LEFT,buff=.12))
        self.axes=axes;self.curve=graph
        return VGroup(axes,xlab,ylab,nums),graph

    def panel(self,*lines,color=FG):
        group=VGroup(*[label(t,25,color) for t in lines]).arrange(DOWN,buff=.26)
        group.move_to([3.55,.6,0])
        return group

    def eq(self,tex,y=0,color=FG,size=34):
        return Tex(tex,font_size=size,fill_color=color).move_to([3.55,y,0])

    def dot(self,x,color=YELLOW):
        return Dot(self.axes.c2p(x,x*x),radius=.075,fill_color=color)

    def tangent(self,x,color=GREEN):
        lo=max(self.axes.x_range[0],x-.7);hi=min(self.axes.x_range[1],x+.7)
        if x!=0:
            bounds=sorted([x+(self.axes.y_range[0]+.02-x*x)/(2*x),
                           x+(self.axes.y_range[1]-.2-x*x)/(2*x)])
            lo=max(lo,bounds[0]);hi=min(hi,bounds[1])
        return Line(self.axes.c2p(lo,x*x+2*x*(lo-x)),self.axes.c2p(hi,x*x+2*x*(hi-x)),color=color,stroke_width=4)

    def draw_question(self):
        road=Line([-5,-.15,0],[5,-.15,0],color=MUTED,stroke_width=2)
        car=VGroup(RoundedRectangle(width=.8,height=.35,corner_radius=.1,color=BLUE,fill_opacity=1),
                   Dot([-.25,-.2,0],radius=.095,fill_color=FG),Dot([.25,-.2,0],radius=.095,fill_color=FG)).move_to([-5,.15,0])
        start=label('起点',21,MUTED).next_to(road.get_start(),DOWN,buff=.4)
        end=label('20 米',21,MUTED).next_to(road.get_end(),DOWN,buff=.4)
        self.add(road,car,start,end)
        self.at('average')
        average=Tex(r'\bar v=\frac{20\ \mathrm{m}}{10\ \mathrm{s}}=2\ \mathrm{m/s}',font_size=45,fill_color=BLUE).move_to([0,1.25,0])
        self.play(Write(average),car.animate.move_to([5,.15,0]),run_time=2.2)
        self.at('instant')
        ask=label('第 5 秒这一刻呢？',38,YELLOW).move_to([0,-1.45,0])
        self.play(FadeIn(ask,shift=UP*.15),run_time=.8)
        self.at('bridge')
        bridge=VGroup(label('一段时间',28,BLUE),Arrow(LEFT,RIGHT,color=MUTED).scale(.65),label('一个时刻',28,GREEN)).arrange(RIGHT,buff=.5).move_to([0,-2.45,0])
        self.play(FadeIn(bridge),run_time=1)

    def draw_graph(self):
        axes,curve=self.graph()
        self.at('axes');self.play(ShowCreation(axes),run_time=1.8)
        note=self.panel('横轴：时间 / 秒','纵轴：路程 / 米')
        self.play(FadeIn(note),run_time=.6)
        self.at('formula');formula=self.eq('s(t)=t^2',y=1.7,color=BLUE,size=43)
        self.play(Write(formula),ShowCreation(curve),run_time=1.8)
        self.at('points')
        dots=VGroup(*[self.dot(x) for x in [1,2,3]])
        labels=VGroup(*[Tex(f'({x},{x*x})',font_size=23,fill_color=YELLOW).next_to(self.dot(x),LEFT if x==3 else RIGHT,buff=.14) for x in [1,2,3]])
        self.play(LaggedStart(*[FadeIn(d) for d in dots],lag_ratio=.25),FadeIn(labels),run_time=1.5)
        self.at('curve');self.play(Indicate(curve,color=GREEN),run_time=1)

    def draw_secant(self):
        axes,curve=self.graph();self.add(axes,curve)
        self.at('points');a=self.dot(2);b=self.dot(3)
        self.play(FadeIn(a),FadeIn(b),run_time=.7)
        self.at('triangle')
        h=DashedLine(self.axes.c2p(2,4),self.axes.c2p(3,4),color=YELLOW)
        v=DashedLine(self.axes.c2p(3,4),self.axes.c2p(3,9),color=YELLOW)
        dh=label('1 秒',21,YELLOW).next_to(h,DOWN,buff=.14);dv=label('5 米',21,YELLOW).next_to(v,RIGHT,buff=.14)
        self.play(ShowCreation(h),ShowCreation(v),FadeIn(dh),FadeIn(dv),run_time=1)
        self.at('line');sec=Line(self.axes.c2p(1.5,1.5),self.axes.c2p(3.4,11),color=GREEN,stroke_width=4)
        self.play(ShowCreation(sec),run_time=1)
        self.at('ratio');eq=self.eq(r'\frac{\Delta s}{\Delta t}=\frac{9-4}{3-2}=5',y=.8,color=GREEN,size=32)
        self.play(Write(eq),FadeIn(self.panel('平均变化率').move_to([3.55,1.7,0])),run_time=1.1)
        self.play(FadeIn(label('还不是 t = 2 的瞬时速度',21,MUTED).move_to([3.55,-.5,0])),run_time=.7)

    def draw_shrink(self):
        axes,curve=self.graph();self.add(axes,curve,self.dot(2))
        h=ValueTracker(1)
        moving=always_redraw(lambda:self.dot(2+h.get_value(),RED))
        line=always_redraw(lambda:Line(self.axes.c2p(1.5,4-(4+h.get_value())*.5),self.axes.c2p(3.2,4+(4+h.get_value())*1.2),color=GREEN,stroke_width=4))
        self.add(line,moving)
        table=VGroup(label('时间间隔',21,MUTED),label('平均速度',21,MUTED)).arrange(RIGHT,buff=.6).move_to([3.55,1.65,0])
        self.add(table)
        rows=[]
        for i,(left,right) in enumerate([('1','5'),('0.5','4.5'),('0.1','4.1'),('0.01','4.01')]):
            row=VGroup(Tex(left,font_size=30,fill_color=YELLOW),Tex(right,font_size=30,fill_color=GREEN)).arrange(RIGHT,buff=1.25).move_to([3.55,.9-i*.65,0]);rows.append(row)
        self.add(rows[0])
        for anchor,value,row in [('half',.5,rows[1]),('small',.1,rows[2]),('tiny',.01,rows[3])]:
            self.at(anchor);self.play(h.animate.set_value(value),FadeIn(row),run_time=1.8)
        self.at('limit');answer=Tex(r'\longrightarrow\ 4',font_size=39,fill_color=GREEN).move_to([3.55,-2.05,0])
        self.play(Write(answer),run_time=.8)
        # Freeze updater-generated geometry before long static hold.
        moving.clear_updaters();line.clear_updaters()

    def draw_tangent(self):
        axes,curve=self.graph();self.add(axes,curve,self.dot(2))
        self.at('tangent');tangent=self.tangent(2);self.play(ShowCreation(tangent),run_time=1)
        self.at('four');eq=self.eq(r"s'(2)=4\ \mathrm{m/s}",y=1.2,color=GREEN,size=37)
        self.play(Write(eq),run_time=1)
        self.at('definition');definition=self.eq(r"s'(t)=\lim_{h\to0}\frac{s(t+h)-s(t)}{h}",y=-.1,size=29)
        self.play(Write(definition),run_time=1.5)
        self.play(FadeIn(label('趋近于零 ≠ 直接除以零',22,YELLOW).move_to([3.55,-1.35,0])),run_time=.6)
        self.at('both');self.play(FadeIn(label('左右两边，趋向同一个值',21,MUTED).move_to([3.55,-2,0])),run_time=.7)

    def draw_algebra(self):
        lines=[r'\frac{(2+h)^2-2^2}{h}',r'=\frac{4+4h+h^2-4}{h}',r'=4+h\quad(h\ne0)',r'\xrightarrow{h\to0}\ 4']
        eqs=VGroup(*[Tex(x,font_size=43,fill_color=GREEN if i==3 else FG) for i,x in enumerate(lines)]).arrange(DOWN,buff=.48).move_to([-.5,-.2,0])
        for anchor,eq in zip(['quotient','expand','cancel','answer'],eqs):
            self.at(anchor);self.play(Write(eq),run_time=1.2)
        box=SurroundingRectangle(eqs[-1],color=GREEN,buff=.18)
        self.play(ShowCreation(box),run_time=.7)

    def draw_general(self):
        axes,curve=self.graph();self.add(axes,curve)
        self.at('formula');eq=self.eq(r'f(x)=x^2\quad\Rightarrow\quad f\prime(x)=2x',y=1.4,color=GREEN,size=28)
        self.play(Write(eq),run_time=1.2)
        position=ValueTracker(1)
        dot=self.dot(1).add_updater(lambda m:m.move_to(self.axes.c2p(position.get_value(),position.get_value()**2)))
        tan=always_redraw(lambda:self.tangent(position.get_value()))
        value=self.eq("f'(1)=2",y=0,color=YELLOW,size=39)
        self.at('one');self.play(FadeIn(dot),ShowCreation(tan),Write(value),run_time=1)
        for anchor,x in [('two',2),('three',3)]:
            self.at(anchor)
            next_value=self.eq(f"f'({x})={2*x}",y=0,color=YELLOW,size=39)
            self.play(position.animate.set_value(x),FadeOut(value),run_time=1)
            self.play(FadeIn(next_value),run_time=.4)
            value=next_value
        dot.clear_updaters();tan.clear_updaters()
        self.play(FadeIn(label('一把会移动的斜率尺',23,MUTED).move_to([3.55,-1.35,0])),run_time=.7)

    def draw_sign(self):
        axes,curve=self.graph(wide=True);self.add(axes,curve)
        text=None;tan=None;dot=None;position=ValueTracker(1.5)
        for anchor,x,tex,desc in [('positive',1.5,"f'(x)>0",'向右看：上升'),('negative',-1.5,"f'(x)<0",'向右看：下降'),('zero',0,"f'(x)=0",'此处切线水平')]:
            self.at(anchor)
            nxt=VGroup(self.eq(tex,y=1,color=GREEN,size=40),label(desc,25).move_to([3.55,0,0]))
            if text is None:
                tan=always_redraw(lambda:self.tangent(position.get_value()))
                dot=self.dot(x).add_updater(lambda m:m.move_to(self.axes.c2p(position.get_value(),position.get_value()**2)))
                text=nxt
                self.play(ShowCreation(tan),FadeIn(dot),FadeIn(text),run_time=1)
            else:
                self.play(position.animate.set_value(x),FadeOut(text),run_time=.8)
                self.play(FadeIn(nxt),run_time=.4)
                text=nxt
        dot.clear_updaters();tan.clear_updaters()
        self.at('caution');warn=VGroup(label('导数为零',24,YELLOW),label('不一定是极值',24,YELLOW)).arrange(DOWN,buff=.18).move_to([3.55,-1.5,0])
        self.play(FadeIn(warn),run_time=.8)

    def draw_linear(self):
        axes,curve=self.graph();self.add(axes,curve,self.dot(2))
        self.at('tangent');self.play(ShowCreation(self.tangent(2)),run_time=1)
        formula=self.eq(r'\Delta f\approx f\prime(x)\,\Delta x',y=1.6,color=GREEN,size=35)
        self.play(Write(formula),run_time=1)
        self.at('step');calc=self.eq(r'\Delta f\approx4\times0.05=0.2',y=.6,color=FG,size=29)
        self.play(Write(calc),run_time=1)
        self.at('estimate');est=self.eq(r'2.05^2\approx4.2',y=-.4,color=YELLOW,size=39)
        self.play(Write(est),run_time=1)
        self.at('error');err=VGroup(label('精确值  4.2025',23,MUTED),label('误差仅  0.0025',23,GREEN)).arrange(DOWN,buff=.18).move_to([3.55,-1.7,0])
        self.play(FadeIn(err),run_time=.8)

    def draw_descent(self):
        axes=Axes(x_range=[0,6,1],y_range=[0,10,2],width=7,height=4.4,axis_config={'color':MUTED,'stroke_width':1.5,'tip_config':{'width':.12,'length':.12}}).move_to([-2.2,-.35,0])
        curve=axes.get_graph(lambda w:(w-3)**2,x_range=[.1,5.9],color=BLUE,stroke_width=4)
        self.add(axes,curve,Tex('w',font_size=25,fill_color=MUTED).next_to(axes.x_axis.get_end(),RIGHT),Tex('L(w)',font_size=25,fill_color=MUTED).next_to(axes.y_axis.get_end(),UP))
        self.at('loss');self.play(Write(self.eq(r'L(w)=(w-3)^2',y=1.6,color=BLUE,size=34)),run_time=1)
        position=ValueTracker(1)
        dot=Dot(axes.c2p(1,4),fill_color=YELLOW,radius=.09)
        dot.add_updater(lambda m:m.move_to(axes.c2p(position.get_value(),(position.get_value()-3)**2)))
        self.at('left');left=Arrow(axes.c2p(.8,4),axes.c2p(2,4),color=GREEN,buff=0)
        sign=self.eq(r'L\prime(w)<0\ \Rightarrow\ \rightarrow',y=.35,color=GREEN,size=30)
        self.play(FadeIn(dot),GrowArrow(left),Write(sign),run_time=1)
        self.at('right');right=Arrow(axes.c2p(5.2,4),axes.c2p(4,4),color=GREEN,buff=0)
        next_sign=self.eq(r'L\prime(w)>0\ \Rightarrow\ \leftarrow',y=.35,color=GREEN,size=30)
        self.play(position.animate.set_value(5),FadeOut(left),FadeOut(sign),run_time=.6)
        self.play(FadeIn(right),FadeIn(next_sign),run_time=.4)
        left=right
        self.at('update');rule=self.eq(r'w_{\mathrm{new}}=w-\eta L\prime(w)',y=-1,color=YELLOW,size=30)
        self.play(Write(rule),FadeOut(left),run_time=1)
        self.at('repeat');w=5
        for _ in range(5):
            w=w-.2*2*(w-3)
            self.play(position.animate.set_value(w),run_time=.55)
        dot.clear_updaters()
        self.play(FadeIn(label('每一步，都重新计算局部斜率',20,MUTED).move_to([3.55,-2,0])),run_time=.7)

    def draw_recap(self):
        steps=VGroup(label('两个点',32,BLUE),label('缩短间隔',32,YELLOW),label('一个位置的局部变化',32,GREEN)).arrange(DOWN,buff=.8).move_to([-2.6,-.1,0])
        self.at('average');self.play(FadeIn(steps[0]),run_time=.8)
        self.at('limit');self.play(FadeIn(steps[1]),FadeIn(steps[2]),run_time=1)
        self.at('result');formula=Tex(r'f(x)=x^2\qquad f\prime(x)=2x',font_size=39,fill_color=GREEN).move_to([2.3,.6,0])
        self.play(Write(formula),run_time=1)
        self.at('end');end=VGroup(label('从平均变化',30,FG),label('走向瞬时变化',30,GREEN)).arrange(DOWN,buff=.3).move_to([2.3,-1.1,0])
        self.play(FadeIn(end),run_time=1)
