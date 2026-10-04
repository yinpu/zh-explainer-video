"""ManimGL-only rendering helpers; orchestration uses the standard library."""
import json
import os
import subprocess
from pathlib import Path

VERSION = '1.7.2'
STYLE = {'background_color': '#10141B', 'font': 'PingFang SC', 'frame_height': 8.0,
         'video_codec': 'libx264', 'pixel_format': 'yuv420p'}


def environment(config, cache, scripts=None):
    env = os.environ.copy()
    paths = [str(Path(config['manimgl']).parent), str(Path(config['ffmpeg']).parent)]
    if Path('/Library/TeX/texbin').is_dir():
        paths.append('/Library/TeX/texbin')
    env['PATH'] = os.pathsep.join(paths + [env.get('PATH', '')])
    env['MPLCONFIGDIR'] = str(cache / 'matplotlib')
    if scripts:
        env['PYTHONPATH'] = str(scripts) + os.pathsep + env.get('PYTHONPATH', '')
    return env


def identity(config):
    code = ('import importlib.metadata as m,json; '
            'print(json.dumps({d.metadata["Name"].lower():d.version for d in m.distributions()}))')
    packages = json.loads(subprocess.check_output([config['render_python'], '-c', code], text=True))
    if packages.get('manimgl') != VERSION:
        raise RuntimeError(f'ManimGL {VERSION} is required; run setup-render')
    return {'engine': 'manimgl', 'version': VERSION, 'packages': packages, 'style': STYLE}


def configuration(video, cache, config):
    return {
        'directories': {'cache': str(cache), 'mirror_module_path': False},
        'camera': {'resolution': str((video['width'], video['height'])),
                   'fps': video['fps'], 'background_color': STYLE['background_color']},
        'text': {'font': STYLE['font']},
        'tex': {'template': 'default'},
        'sizes': {'frame_height': STYLE['frame_height']},
        'file_writer': {'ffmpeg_bin': config['ffmpeg'], 'video_codec': STYLE['video_codec'],
                        'pixel_format': STYLE['pixel_format']},
    }


def command(config, source, scene, output_dir, name, config_path):
    # In 1.7.2 --fps is parsed as a string. Set numeric fps in the config instead.
    return [config['manimgl'], str(source), scene, '-w', '--video_dir', str(output_dir),
            '--file_name', name, '--config_file', str(config_path)]


def write_configuration(path, video, cache, config):
    path.parent.mkdir(parents=True, exist_ok=True)
    cache.mkdir(parents=True, exist_ok=True)
    # JSON is valid YAML, so the standard-library runner needs no YAML dependency.
    path.write_text(json.dumps(configuration(video, cache, config), indent=2), encoding='utf8')


def inspect_video(config, path, video, duration):
    info = json.loads(subprocess.check_output(
        [config['ffprobe'], '-v', 'error', '-show_streams', '-of', 'json', str(path)], text=True))
    stream = next(s for s in info['streams'] if s['codec_type'] == 'video')
    num, den = map(int, stream['avg_frame_rate'].split('/'))
    if (stream['width'], stream['height']) != (video['width'], video['height']) or num / den != video['fps']:
        raise RuntimeError('ManimGL exported the wrong resolution or frame rate')
    expected_frames = round(duration * video['fps'])
    if int(stream['nb_frames']) != expected_frames:
        raise RuntimeError(f'ManimGL exported {stream["nb_frames"]} frames; expected {expected_frames}')
    return stream


def probe(config, directory):
    directory.mkdir(parents=True, exist_ok=True)
    identity(config)
    video = {'width': 1280, 'height': 720, 'fps': 30}
    settings = directory / 'render.json'
    cache = directory / 'cache'
    write_configuration(settings, video, cache, config)
    env = environment(config, cache, Path(__file__).parent)
    fonts = subprocess.check_output([config['render_python'], '-c',
        'import manimpango,json;print(json.dumps(manimpango.list_fonts()))'], text=True, env=env)
    if STYLE['font'] not in json.loads(fonts):
        raise RuntimeError('Missing Chinese font: ' + STYLE['font'])
    output = directory / 'probe.mp4'
    output.unlink(missing_ok=True)
    with (directory / 'render.log').open('w') as log:
        subprocess.run(command(config, Path(__file__).with_name('render_probe.py'), 'RenderProbe',
                               directory, 'probe', settings), cwd=directory, env=env,
                       stdout=log, stderr=subprocess.STDOUT, check=True, timeout=180)
    return inspect_video(config, output, video, 4.0)
