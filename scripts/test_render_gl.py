"""Timing and render-cache behaviour without OpenGL or model inference."""
import copy
import importlib.util
import json
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

import render_gl
import zvideo
from timing import atomic_json


class TimelineTests(unittest.TestCase):
    def setUp(self):
        fake = types.ModuleType('manimlib')
        class Scene:
            def setup(self): pass
            def wait(self, duration): self.time += duration
        fake.Scene = Scene
        spec = importlib.util.spec_from_file_location('tested_scene_support', Path(__file__).with_name('scene_support.py'))
        module = importlib.util.module_from_spec(spec)
        with patch.dict(sys.modules, {'manimlib': fake}):
            spec.loader.exec_module(module)
        self.scene = module.TimelineScene()
        self.scene.time = 0
        self.scene.fps = 30
        self.scene.continuous = False
        self.scene.job = {'blocks': [{'id': 'a'}, {'id': 'b'}]}
        self.scene.timeline = {'blocks': [
            {'id': 'a', 'offset': 0, 'duration': 2, 'beats': {'focus': {'time': 1}}},
            {'id': 'b', 'offset': 2, 'duration': 3, 'beats': {'focus': {'time': 1}}}]}
        self.scene.skip_animations = False
        self.scene.camera = types.SimpleNamespace(fps=30)
        self.scene.file_writer = types.SimpleNamespace(set_progress_display_description=lambda **kw: None)

    def test_fractional_durations_emit_exact_frame_counts(self):
        s = self.scene
        for fps in [24, 30, 60]:
            s.camera.fps = fps
            for frames in [0, 1, 23, 31, 46, 62, 125, 1812, 3000]:
                with self.subTest(fps=fps, frames=frames):
                    ticks = s.get_time_progression(frames / fps)
                    self.assertEqual(len(ticks), frames)
                    self.assertTrue(all(abs(t - (i + 1) / fps) < 1e-12 for i, t in enumerate(ticks)))

    def test_preview_skip_is_preserved_and_can_be_overridden(self):
        s = self.scene
        s.skip_animations = True
        self.assertEqual(s.get_time_progression(23 / 30), [23 / 30])
        self.assertEqual(len(s.get_time_progression(23 / 30, override_skip_animations=True)), 23)

    def test_per_block_uses_local_anchor_and_fills_last_frame(self):
        s = self.scene
        s.begin_block('b')
        s.at('focus')
        self.assertEqual(s.time, 1)
        s.time = 3 - 1/30 + 1e-12
        s.finish()
        self.assertAlmostEqual(s.time, 3)

    def test_continuous_blocks_preserve_objects_and_global_clock(self):
        s = self.scene
        s.continuous = True
        marker = object()
        s.mobjects = [marker]
        s.begin_block('a'); s.finish()
        s.begin_block('b'); s.at('focus')
        self.assertEqual(s.time, 3)
        self.assertEqual(s.local_time(), 1)
        self.assertIs(s.mobjects[0], marker)
        s.finish()
        self.assertEqual(s.time, 5)

    def test_overrun_is_not_hidden(self):
        s = self.scene
        s.begin_block('a')
        s.time = 1.1
        with self.assertRaises(ValueError): s.at('focus')
        s.time = 2.1
        with self.assertRaises(ValueError): s.finish()


class RenderTests(unittest.TestCase):
    def test_cache_reuses_identical_video_and_invalidates_engine_and_settings(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); work = root/'work'; out = root/'outputs'
            work.mkdir(); out.mkdir()
            (root/'scene.py').write_text('# scene')
            (out/'narration.wav').write_bytes(b'audio')
            (work/'captions.ass').write_text('captions')
            block = {'id': 'intro', 'text': '正文'}
            job = {'blocks': [block], 'video': {'width': 1920, 'height': 1080, 'fps': 30}}
            timeline = {'duration': 2, 'blocks': [{'id': 'intro', 'duration': 2, 'beats': {}}]}
            config = {'manimgl': '/env/bin/manimgl', 'ffmpeg': '/bin/ffmpeg'}
            calls = []
            def run(cmd, *args, **kwargs):
                calls.append(cmd)
                if cmd[0] == config['manimgl']:
                    folder = Path(cmd[cmd.index('--video_dir') + 1]); folder.mkdir(parents=True, exist_ok=True)
                    name = cmd[cmd.index('--file_name') + 1]
                    (folder/(name+'.mp4')).write_bytes(('export'+str(len(calls))).encode())
                else: Path(cmd[-1]).write_bytes(b'mux')
            engine = {'engine': 'manimgl', 'version': '1.7.2', 'packages': {}}
            with patch.object(render_gl, 'identity', return_value=engine), patch.object(render_gl, 'inspect_video'), patch.object(zvideo, 'run', side_effect=run):
                zvideo.render(config,job,root,work,out,timeline)
                self.assertEqual(len(calls),2)
                calls.clear()
                zvideo.render(config,job,root,work,out,timeline)
                self.assertEqual(calls,[])
                engine['packages']['moderngl']='changed'
                zvideo.render(config,job,root,work,out,timeline)
                self.assertEqual(calls[0][0],config['manimgl'])
                calls.clear()
                (root/'custom_config.yml').write_text('text: {font: PingFang SC}')
                zvideo.render(config,job,root,work,out,timeline)
                self.assertEqual(calls[0][0],config['manimgl'])
                calls.clear()
                job['video']['width']=1280
                zvideo.render(config,job,root,work,out,timeline)
                self.assertEqual(calls[0][0],config['manimgl'])

    def test_wrong_frame_count_fails_before_mux(self):
        stream={'codec_type':'video','width':1920,'height':1080,'avg_frame_rate':'30/1','nb_frames':'59'}
        with patch('subprocess.check_output',return_value=json.dumps({'streams':[stream]})):
            with self.assertRaises(RuntimeError):
                render_gl.inspect_video({'ffprobe':'ffprobe'},Path('out.mp4'),{'width':1920,'height':1080,'fps':30},2)

    def test_numeric_fps_configuration(self):
        result=render_gl.configuration({'width':1920,'height':1080,'fps':30},Path('/cache'),{'ffmpeg':'ffmpeg'})
        self.assertIsInstance(result['camera']['fps'],int)
        self.assertEqual(result['camera']['fps'],30)


if __name__ == '__main__': unittest.main()
