"""Manim scene base with audio-derived local time and overflow checks."""
import json
import os
from pathlib import Path
from manimlib import Scene


class FrameExactScene(Scene):
    def get_time_progression(self, run_time, n_iterations=None, desc='', override_skip_animations=False):
        if self.skip_animations and not override_skip_animations:
            return [run_time]
        self.file_writer.set_progress_display_description(sub_desc=desc)
        fps = self.camera.fps
        # Floating np.arange(0, frames / fps, 1 / fps) can emit an extra frame.
        # Advance by integer frame indices; keep preview skipping and audio timing.
        return [index / fps for index in range(1, round(run_time * fps) + 1)]


class TimelineScene(FrameExactScene):
    def setup(self):
        super().setup()
        self.project=Path(os.environ['ZVIDEO_PROJECT'])
        self.job=json.loads((self.project/'project.json').read_text())
        bid=os.environ['ZVIDEO_BLOCK']
        timeline=json.loads((self.project/'outputs/timeline.json').read_text())
        self.timeline=timeline
        self.continuous=bid=='__continuous__'
        if self.continuous:bid=self.job['blocks'][0]['id']
        self.begin_block(bid)
        self.fps=timeline['fps']

    def begin_block(self,bid):
        self.block=next(b for b in self.job['blocks'] if b['id']==bid)
        self.timing=next(b for b in self.timeline['blocks'] if b['id']==bid)
        self.time_offset=self.timing['offset'] if self.continuous else 0

    def local_time(self):
        return self.time-self.time_offset

    def at(self,beat):
        target=self.time_offset+self.timing['beats'][beat]['time']
        remaining=target-self.time
        if remaining < -1/self.fps-.001:
            raise ValueError(f'Animation overran anchor {beat}: {remaining:.3f}s')
        frames=round(remaining*self.fps)
        if frames > 0:
            self.wait(frames/self.fps)

    def finish(self):
        remaining=self.time_offset+self.timing['duration']-self.time
        if remaining < -1/self.fps-.001:
            raise ValueError('Animation exceeds narration block')
        frames=round(remaining*self.fps)
        if frames > 0:
            self.wait(frames/self.fps)
