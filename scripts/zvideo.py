#!/usr/bin/env python3
"""Local Mandarin explainer pipeline. Standard-library orchestration."""
import argparse
import contextlib
import fcntl
import json
import math
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
import render_gl
from timing import atomic_json, digest, file_hash, make_block_timing, validate_job, write_srt
from voice import DEFAULT_VOICE, normalize_voice, cloud_model, credential, KEY_ENV

HERE = Path(__file__).resolve().parent
DEFAULT_RUNTIME = Path.home()/'Documents/Codex/runtimes/zh-explainer-video'
MODELS = {'align':'Qwen3-ForcedAligner-0.6B-8bit','asr':'Qwen3-ASR-0.6B-8bit'}


def read(path):
    return json.loads(Path(path).read_text(encoding='utf8'))


def run(command, log=None, cwd=None, env=None):
    print('RUN '+str(command[0])+' '+str(command[1] if len(command)>1 else ''),flush=True)
    if log:
        Path(log).parent.mkdir(parents=True,exist_ok=True)
        with open(log,'a') as stream:
            result=subprocess.run([str(x) for x in command],cwd=cwd,env=env,stdout=stream,stderr=subprocess.STDOUT)
        if result.returncode:
            tail='\n'.join(Path(log).read_text(errors='replace').splitlines()[-18:])
            raise RuntimeError(f'Command failed ({result.returncode}); log: {log}\n{tail}')
    else:
        subprocess.run([str(x) for x in command],cwd=cwd,env=env,check=True)


def runtime_info(runtime):
    config=read(runtime/'runtime.json') if (runtime/'runtime.json').exists() else {}
    config.setdefault('python',str(runtime/'.venv/bin/python'))
    config.pop('manim',None)
    config.setdefault('render_python',str(runtime/'.render-venv/bin/python'))
    config.setdefault('manimgl',str(runtime/'.render-venv/bin/manimgl'))
    full=Path('/opt/homebrew/opt/ffmpeg-full/bin')
    config.setdefault('ffmpeg',str(full/'ffmpeg') if (full/'ffmpeg').is_file() else shutil.which('ffmpeg') or '/opt/homebrew/bin/ffmpeg')
    config.setdefault('ffprobe',str(full/'ffprobe') if (full/'ffprobe').is_file() else shutil.which('ffprobe') or '/opt/homebrew/bin/ffprobe')
    return config


def doctor(runtime, verify=False, verify_render=False):
    config=runtime_info(runtime)
    diagnostics={}
    checks={name:Path(config[name]).is_file() for name in ['python','render_python','manimgl','ffmpeg','ffprobe']}
    checks['latex']=bool(shutil.which('latex'))
    checks['dvisvgm']=bool(shutil.which('dvisvgm'))
    if checks['ffmpeg']:
        filters=subprocess.check_output([config['ffmpeg'],'-hide_banner','-filters'],text=True,stderr=subprocess.DEVNULL)
        checks['subtitle_filter']=any(' ass ' in line for line in filters.splitlines())
    models=read(runtime/'models.json') if (runtime/'models.json').exists() else {}
    for kind in MODELS:
        entry=models.get(kind,{})
        checks[kind]=bool(entry) and (Path(entry.get('path',''))/'config.json').is_file()
        if verify and checks[kind]:
            checks[kind+'_hashes']=all(file_hash(Path(entry['path'])/name)==sha for name,sha in entry['sha256'].items())
    if checks['python']:
        p=subprocess.run([config['python'],'-c','import mlx.core,mlx_audio,soundfile,scipy;print("ok")'],capture_output=True,text=True)
        checks['python_imports']=p.returncode==0
        if p.returncode:
            diagnostics['python_import_error']=(p.stderr or p.stdout).strip()[-2000:]
    render_details={}
    if checks['render_python']:
        try:
            render_details['identity']=render_gl.identity(config)
            checks['manimgl_version']=True
        except Exception as exc:
            checks['manimgl_version']=False
            render_details['error']=str(exc)
    if verify_render:
        try:
            render_details['media']=render_gl.probe(config,runtime/'render-probe')
            checks['render_export']=True
        except Exception as exc:
            checks['render_export']=False
            render_details['error']=str(exc)
            render_details['log']=str(runtime/'render-probe/render.log')
    report={'render':render_details,'ready':all(checks.values()),'checks':checks,'runtime':str(runtime),'executables':config}
    report['voice']={**cloud_model(DEFAULT_VOICE),'speaker':DEFAULT_VOICE['speaker'],'speed':DEFAULT_VOICE['speed'],'credential_present':bool(os.environ.get(KEY_ENV))}
    if diagnostics: report['diagnostics']=diagnostics
    print(json.dumps(report,ensure_ascii=False,indent=2))
    return report


def setup_render(runtime, python=None):
    runtime.mkdir(parents=True,exist_ok=True)
    uv=shutil.which('uv')
    if not uv: raise RuntimeError('uv is missing; see references/setup.md')
    venv=runtime/'.render-venv/bin/python'
    if not venv.exists():
        run([uv,'venv',runtime/'.render-venv','--python',python or '3.12','--cache-dir',runtime/'uv-cache'])
    run([uv,'pip','sync','--python',venv,'--cache-dir',runtime/'uv-cache',
         HERE/'render-requirements.lock.txt'])
    config=runtime_info(runtime)
    config.update(render_python=str(venv),manimgl=str(venv.parent/'manimgl'))
    atomic_json(runtime/'runtime.json',config)
    freeze=subprocess.check_output([uv,'--cache-dir',str(runtime/'uv-cache'),'pip','freeze','--python',str(venv)],text=True)
    (runtime/'render-installed-packages.txt').write_text(freeze)
    render_gl.probe(config,runtime/'render-probe')


def setup(runtime, python=None):
    runtime.mkdir(parents=True,exist_ok=True)
    uv=shutil.which('uv')
    if not uv:
        raise RuntimeError('uv is missing. Install uv, then rerun setup; see references/setup.md')
    venv=runtime/'.venv/bin/python'
    if not venv.exists():
        run([uv,'venv',runtime/'.venv','--python',python or '3.12','--cache-dir',runtime/'uv-cache'])
    run([uv,'pip','install','--python',venv,'--cache-dir',runtime/'uv-cache',
         '-r',HERE/'requirements.lock.txt'])
    run([venv,HERE/'download_models.py',runtime])
    config=runtime_info(runtime)
    config['python']=str(venv)
    atomic_json(runtime/'runtime.json',config)
    freeze=subprocess.check_output([uv,'--cache-dir',str(runtime/'uv-cache'),'pip','freeze','--python',str(venv)],text=True)
    (runtime/'installed-packages.txt').write_text(freeze)
    setup_render(runtime,python)
    if not doctor(runtime,True)['ready']:
        raise RuntimeError('Some system dependencies are missing; see doctor results')


def worker(config,mode,data,work):
    if mode=='tts':
        data={**data,'voice':normalize_voice(data['voice'])}
        credential()
    request=work/f'{mode}-request.json'
    atomic_json(request,data)
    script='cloud_tts.py' if mode=='tts' else 'join_trim.py' if mode=='join_trim' else 'audio_worker.py'
    run([config['python'],HERE/script,mode,request],work/f'{mode}.log')


def valid_cache(audio,meta,key):
    if not audio.exists() or not meta.exists(): return False
    data=read(meta)
    return data.get('key')==key and data.get('sha256')==file_hash(audio)


def load_project(project):
    job=read(project/'project.json')
    validate_job(job)
    job['voice']=normalize_voice(job.get('voice'))
    job['video']={'width':1920,'height':1080,'fps':30,**job.get('video',{})}
    return job


def create_tts_tasks(job,models,work,retry=None):
    tasks=[]
    voice=normalize_voice(job['voice'])
    for block in job['blocks']:
        bid=block['id']
        attempt=(retry or {}).get(bid,0)
        if retry is not None and bid not in retry: continue
        identity=digest([file_hash(HERE/'cloud_tts.py'),file_hash(HERE/'voice.py')])
        key=digest({'worker':identity,'text':block['text'],
                    'voice':voice,'model':models['tts']['revision'],'attempt':attempt})
        out=work/'audio'/f'{bid}.wav'
        if not valid_cache(out,out.with_suffix('.json'),key):
            tasks.append({'id':bid,'text':block['text'],'attempt':attempt,'key':key,'output':str(out)})
    return tasks


def infer_stage(config,models,job,work,mode):
    tasks=[]
    for block in job['blocks']:
        audio=work/'audio'/f'{block["id"]}.wav'
        out=work/mode/f'{block["id"]}.json'
        key=digest([file_hash(audio),block['text'],models[mode]['revision'],file_hash(HERE/'audio_worker.py')])
        if not out.exists() or read(out).get('key')!=key:
            tasks.append({'id':block['id'],'text':block['text'],'audio':str(audio),'output':str(out),'key':key})
    if tasks:
        worker(config,mode,{'model':models[mode]['path'],'tasks':tasks},work)


def ass_time(t):
    cs=round(t*100); h,cs=divmod(cs,360000); m,cs=divmod(cs,6000); s,cs=divmod(cs,100)
    return f'{h}:{m:02}:{s:02}.{cs:02}'


def write_ass(path,captions):
    header='''[Script Info]
ScriptType: v4.00+
PlayResX: 1920
PlayResY: 1080
WrapStyle: 2

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Arial Unicode MS,40,&H00F1F5F9,&H00FFFFFF,&H0010141B,&H9010141B,0,0,0,0,100,100,0,0,1,2,0,2,120,120,46,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
'''
    lines=[]
    for c in captions:
        txt=c['text'].replace('\\','\\\\').replace('{','\\{').replace('}','\\}').replace('\n','\\N')
        lines.append(f'Dialogue: 0,{ass_time(c["start"])},{ass_time(c["end"])},Default,,0,0,0,,{txt}')
    Path(path).write_text(header+'\n'.join(lines)+'\n',encoding='utf8')


def assemble(config,job,work,out):
    inputs=[{'id':b['id'],'audio':str(work/'audio'/f'{b["id"]}.wav')} for b in job['blocks']]
    join_pause=0 if job.get('narration_groups') else .24
    key=digest([[(i['id'],file_hash(i['audio'])) for i in inputs],job['video']['fps'],join_pause,file_hash(HERE/'audio_worker.py')])
    meta=work/'master.json'
    if (not meta.exists() or read(meta).get('key')!=key or not (out/'narration.wav').exists()
        or read(meta).get('master_sha256')!=file_hash(out/'narration.wav')):
        worker(config,'assemble',{'tasks':inputs,'fps':job['video']['fps'],'join_pause_seconds':join_pause,
                                 'output':str(work/'raw-master.wav'),'metadata':str(meta)},work)
        info=read(meta)
        # EBU R128 two-pass normalization over the complete programme.
        result=subprocess.run([config['ffmpeg'],'-hide_banner','-nostdin','-i',str(work/'raw-master.wav'),
                               '-af','loudnorm=I=-18:TP=-1.5:LRA=9:print_format=json','-f','null','-'],capture_output=True,text=True)
        if result.returncode: raise RuntimeError(result.stderr[-2000:])
        measurement=json.loads(result.stderr[result.stderr.rfind('{'):result.stderr.rfind('}')+1])
        norm=('loudnorm=I=-18:TP=-1.5:LRA=9:linear=true'
              f':measured_I={measurement["input_i"]}:measured_TP={measurement["input_tp"]}'
              f':measured_LRA={measurement["input_lra"]}:measured_thresh={measurement["input_thresh"]}'
              f':offset={measurement["target_offset"]},aresample=48000,apad,atrim=end_sample={info["samples"]*2}')
        run([config['ffmpeg'],'-y','-nostdin','-i',work/'raw-master.wav','-af',norm,
             '-ar','48000','-ac','1','-c:a','pcm_s24le',out/'narration.wav'],work/'mastering.log')
        info.update(key=key,normalization=measurement,master_sha256=file_hash(out/'narration.wav'))
        atomic_json(meta,info)
    return read(meta)


def build_timeline(job,work,out,master):
    blocks=[]; captions=[]
    for block,meta in zip(job['blocks'],master['blocks']):
        alignment=read(work/'align'/f'{block["id"]}.json')
        t=make_block_timing(block,alignment['items'],meta['duration'],meta['offset'],job['video']['fps'])
        blocks.append(t); captions.extend(t['captions'])
    timeline={'duration':master['duration'],'fps':job['video']['fps'],'blocks':blocks}
    atomic_json(out/'timeline.json',timeline)
    write_srt(out/'subtitles.srt',captions)
    write_ass(work/'captions.ass',captions)
    return timeline


def render(config,job,project,work,out,timeline):
    source=project/job.get('scene_file','scene.py')
    if not source.is_file(): raise RuntimeError('Missing authored Manim scene: '+str(source))
    engine=render_gl.identity(config)
    # All project fields may affect authored scenes; voice is excluded from visual identity.
    visual_job={k:v for k,v in job.items() if k!='voice'}
    project_config=project/'custom_config.yml'
    render_settings={'engine':engine,'adapter':file_hash(HERE/'render_gl.py'),
                     'project_config':file_hash(project_config) if project_config.exists() else None}
    atomic_json(out/'renderer.json',render_settings)
    videos=[]
    render_jobs=[({'id':'__continuous__','text':''},timeline)] if job.get('render_mode')=='continuous' else list(zip(job['blocks'],timeline['blocks']))
    for block,timing in render_jobs:
        bid=block['id']; dest=work/'video'/f'{bid}.mp4'; meta=dest.with_suffix('.json')
        local=timing if bid=='__continuous__' else {'duration':timing['duration'],'beats':{k:{f:v[f] for f in ['time','phrase']} for k,v in timing['beats'].items()}}
        key=digest([file_hash(source),file_hash(HERE/'scene_support.py'),visual_job,local,render_settings])
        if not valid_cache(dest,meta,key):
            render_dir=work/'manimgl'/bid
            settings=render_dir/'render.json'
            cache=work/'manimgl-cache'
            render_gl.write_configuration(settings,job['video'],cache,config)
            env=render_gl.environment(config,cache,HERE)
            env.update(ZVIDEO_PROJECT=str(project),ZVIDEO_BLOCK=bid,ZVIDEO_SKILL_SCRIPTS=str(HERE))
            rendered=render_dir/f'{bid}.mp4'
            rendered.unlink(missing_ok=True)
            command=render_gl.command(config,source,job.get('scene_class','Explainer'),render_dir,bid,settings)
            run(command,work/f'render-{bid}.log',cwd=project,env=env)
            if not rendered.is_file(): raise RuntimeError('Missing ManimGL export: '+str(rendered))
            render_gl.inspect_video(config,rendered,job['video'],timing['duration'])
            dest.parent.mkdir(parents=True,exist_ok=True)
            shutil.copy2(rendered,dest)
            atomic_json(meta,{'key':key,'sha256':file_hash(dest)})
        videos.append(dest)
    lines=['ffconcat version 1.0']
    for path in videos:
        escaped=str(path).replace("'","'\\''")
        lines.append("file '"+escaped+"'")
    (work/'scenes.ffconcat').write_text('\n'.join(lines)+'\n')
    key=digest([[file_hash(p) for p in videos],file_hash(out/'narration.wav'),file_hash(work/'captions.ass')])
    target=out/'video.mp4'; meta=work/'mux.json'
    if not valid_cache(target,meta,key):
        run([config['ffmpeg'],'-y','-nostdin','-safe','0','-f','concat','-i','scenes.ffconcat',
             '-i',out/'narration.wav','-vf','ass=filename=captions.ass','-c:v','libx264','-preset','fast',
             '-crf','18','-pix_fmt','yuv420p','-c:a','aac','-b:a','192k','-ar','48000',
             '-movflags','+faststart','-t',f'{timeline["duration"]:.6f}',target],work/'mux.log',cwd=work)
        atomic_json(meta,{'key':key,'sha256':file_hash(target)})
    shutil.copy2(source,out/'scene.py')
    shutil.copy2(HERE/'scene_support.py',out/'scene_support.py')


def qa(project,runtime):
    from pace import screen
    config=runtime_info(runtime); job=load_project(project); work=project/'work'; out=project/'outputs'
    issues=[]; warnings=[]; block_reports=[]
    timeline=read(out/'timeline.json') if (out/'timeline.json').exists() else None
    for b in job['blocks']:
        bid=b['id']; a=read(work/'audio'/f'{bid}.json')
        asr=read(work/'asr'/f'{bid}.json') if (work/'asr'/f'{bid}.json').exists() else {}
        if asr.get('cer',1)>.12: issues.append(f'{bid}: ASR discrepancy requires review (CER {asr.get("cer")})')
        if a['clipped_fraction']>.0001: issues.append(bid+': audio clipping')
        if not 20<=a['duration']<=75: warnings.append(f'{bid}: narration duration {a["duration"]:.1f}s')
        block_reports.append({'id':bid,**a,'asr':asr})
    for prev,cur in zip(block_reports,block_reports[1:]):
        if abs(prev['rms_db']-cur['rms_db'])>4:
            warnings.append(f'{prev["id"]}/{cur["id"]}: loudness shift, audition required')
        if prev['median_f0_hz'] and cur['median_f0_hz'] and abs(12*math.log2(cur['median_f0_hz']/prev['median_f0_hz']))>4:
            warnings.append(f'{prev["id"]}/{cur["id"]}: pitch distribution shift, audition required')
    duration=timeline['duration'] if timeline else 0
    seam_checks=[]
    if timeline and job.get('narration_groups'):
        master=read(work/'master.json')
        for i,(prev,cur) in enumerate(zip(timeline['blocks'],timeline['blocks'][1:])):
            pa=read(work/'audio'/f'{prev["id"]}.json');ca=read(work/'audio'/f'{cur["id"]}.json')
            added=master['blocks'][i].get('added_silence_samples',0)
            same=pa.get('source_group')==ca.get('source_group')
            seam_checks.append({'from':prev['id'],'to':cur['id'],'time':cur['offset'],'same_recording':same,'added_silence_ms':added/24000*1000,'aligned_pause_seconds':cur['captions'][0]['start']-prev['captions'][-1]['end']})
            if added:issues.append(prev['id']+': unexpected added silence in continuous narration')
            if same and pa.get('source_end_sample')!=ca.get('source_start_sample'):
                issues.append(prev['id']+'/'+cur['id']+': shared recording has missing or overlapping samples')
        recordings={b.get('source_group') for b in block_reports}
        if len(recordings)>1:
            warnings.append('Independent narration takes require listening review at their joins; shared-take cuts preserve the original waveform.')
    target=job.get('target_seconds',[300,1200])
    if not target[0]<=duration<=target[1]: issues.append(f'Duration {duration:.2f}s is outside {target}')
    anchors=[]
    if timeline:
        for b in timeline['blocks']:
            for name,beat in b['beats'].items():
                err=abs(beat['time']-beat['speech_time'])
                anchors.append({'block':b['id'],'beat':name,'phrase':beat['phrase'],'rounding_error_ms':err*1000})
                if err>.2: issues.append('Animation anchor drift '+name)
    media=None
    if (out/'video.mp4').exists():
        media=json.loads(subprocess.check_output([config['ffprobe'],'-v','error','-show_streams','-show_format','-of','json',str(out/'video.mp4')],text=True))
        video=next(x for x in media['streams'] if x['codec_type']=='video')
        audio=next(x for x in media['streams'] if x['codec_type']=='audio')
        if video['width']!=job['video']['width'] or video['height']!=job['video']['height']: issues.append('Wrong resolution')
        if abs(float(video.get('duration',duration))-duration)>1/job['video']['fps']+.005: issues.append('Video duration drift')
        if abs(float(audio.get('duration',duration))-duration)>.06: issues.append('Audio duration drift')
    else: issues.append('Final video has not been rendered')
    pace_checks=[]
    for block in timeline['blocks'] if timeline else []:
        path=work/'align'/f'{block["id"]}.json'
        if path.exists():
            pace_checks += [{'block':block['id'],**x} for x in screen(read(path)['items'],block['offset'])]
    if pace_checks: warnings.append('Local speech-rate changes detected; listen at the times in pace_checks. Alignment is only a screening signal.')
    report={'automated_pass':not issues,'listening_review':'pending','visual_review':'pending',
            'duration_seconds':duration,'issues':issues,'warnings':warnings,'blocks':block_reports,
            'anchor_checks':anchors,'anchor_check_limit':'Timestamp rounding checks do not verify perceptual alignment; audition key anchors.',
            'media':media,'seam_checks':seam_checks,'pace_checks':pace_checks}
    review_path=project/'review.json'
    if review_path.exists():
        review=read(review_path)
        # A review is valid only for the exact delivered media.
        if (out/'video.mp4').exists() and review.get('video_sha256')==file_hash(out/'video.mp4'):
            report['listening_review']=review.get('listening_review','pending')
            report['visual_review']=review.get('visual_review','pending')
            report['review_notes']=review.get('notes','')
    atomic_json(out/'qa.json',report)
    lines=[f'# {job["title"]} · 检查结果',f'时长：{duration/60:.2f} 分钟。',
           f'自动检查：{"通过" if not issues else "需处理"}。',
           f'听感验收：{report["listening_review"]}。画面验收：{report["visual_review"]}。',
           '自动音高、响度与时间戳检查不能证明音色连续或发音时间绝对准确。']
    if issues: lines+=['\n需要处理：']+['- '+x for x in issues]
    if warnings: lines+=['\n复查提示：']+['- '+x for x in warnings]
    (out/'检查结果.md').write_text('\n\n'.join(lines),encoding='utf8')
    print(json.dumps({k:v for k,v in report.items() if k not in ['blocks','media','anchor_checks']},ensure_ascii=False,indent=2))
    return report


def build(project,runtime,stop_after=None):
    project=project.resolve(); job=load_project(project); config=runtime_info(runtime)
    models=read(runtime/'models.json') if (runtime/'models.json').exists() else {}
    remote=cloud_model(job['voice'])
    models={kind:entry for kind,entry in models.items() if kind in MODELS}
    models['tts']=remote
    required=['tts'] if stop_after=='tts' else ['tts','asr','align']
    if any(kind not in models for kind in required):
        raise RuntimeError('Missing model configuration; run doctor and see references/setup.md')
    work=project/'work'; out=project/'outputs'
    work.mkdir(parents=True,exist_ok=True); out.mkdir(parents=True,exist_ok=True)
    state_path=work/'state.json'
    state=read(state_path) if state_path.exists() else {'attempts':{}}
    # Editing one block must not reset another block's successful recording attempt.
    prior_revisions=state.setdefault('block_revisions',{})
    for block in job['blocks']:
        bid=block['id']
        revision=digest([block['text'],job['voice'],models['tts']['revision']])
        if bid in prior_revisions and prior_revisions[bid]!=revision:
            state['attempts'].pop(bid,None)
        prior_revisions[bid]=revision
    def mark(stage):
        state.pop('error',None)
        state['stage']=stage; state['updated_at']=time.time(); atomic_json(state_path,state)
    lock=open(work/'build.lock','a')
    try:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    except BlockingIOError:
        raise RuntimeError('Another build is already running for this project')
    try:
        if job.get('narration_groups'):
            from grouped_audio import prepare
            if prepare(config,models,job,work,state,mark,worker,create_tts_tasks,infer_stage,stop_after):
                mark('tts-complete'); return
        else:
            for pass_index in range(3):
                mark('tts')
                attempts={b['id']:state['attempts'].get(b['id'],0) for b in job['blocks']}
                tasks=create_tts_tasks(job,models,work,attempts)
                if tasks: worker(config,'tts',{'model':models['tts']['path'],'voice':job['voice'],'tasks':tasks},work)
                if stop_after=='tts': mark('tts-complete'); return
                mark('asr'); infer_stage(config,models,job,work,'asr')
                bad=[b['id'] for b in job['blocks'] if read(work/'asr'/f'{b["id"]}.json')['cer']>.12]
                if not bad: break
                can_retry=[bid for bid in bad if state['attempts'].get(bid,0)<2]
                if not can_retry: raise RuntimeError('Narration discrepancy after two retries: '+', '.join(bad))
                for bid in can_retry: state['attempts'][bid]=state['attempts'].get(bid,0)+1
                atomic_json(state_path,state)
            remaining=[b['id'] for b in job['blocks'] if read(work/'asr'/f'{b["id"]}.json')['cer']>.12]
            if remaining: raise RuntimeError('Narration needs review: '+', '.join(remaining))
        mark('align'); infer_stage(config,models,job,work,'align')
        mark('assemble'); master=assemble(config,job,work,out)
        timeline=build_timeline(job,work,out,master)
        (out/'讲稿.txt').write_text(job['title']+'\n\n'+'\n\n'.join(b['text'] for b in job['blocks']),encoding='utf8')
        atomic_json(out/'project.json',job)
        atomic_json(out/'provenance.json',{'models':models,'voice':job['voice'],'runtime':config})
        if stop_after=='audio': mark('audio-complete'); return
        minimum,maximum=job.get('target_seconds',[300,1200])
        if not minimum<=timeline['duration']<=maximum:
            raise RuntimeError(f'Actual narration is {timeline["duration"]:.1f}s; edit script to fit {minimum}–{maximum}s before rendering')
        mark('render'); render(config,job,project,work,out,timeline)
        mark('qa'); report=qa(project,runtime)
        mark('complete' if report['automated_pass'] else 'needs-review')
        if not report['automated_pass']: raise RuntimeError('QA needs attention; see outputs/qa.json')
    except BaseException as exc:
        state['error']=str(exc); atomic_json(state_path,state); raise
    finally:
        lock.close()


def main():
    parser=argparse.ArgumentParser(description='本地中文原理讲解视频')
    parser.add_argument('--runtime',type=Path,default=Path(os.environ.get('ZVIDEO_RUNTIME',DEFAULT_RUNTIME)))
    sub=parser.add_subparsers(dest='command',required=True)
    p=sub.add_parser('doctor');p.add_argument('--verify-models',action='store_true');p.add_argument('--verify-render',action='store_true')
    p=sub.add_parser('setup');p.add_argument('--python')
    p=sub.add_parser('setup-render');p.add_argument('--python')
    for name in ['build','resume','qa']:
        p=sub.add_parser(name);p.add_argument('project',type=Path)
        if name!='qa':p.add_argument('--stop-after',choices=['tts','audio'])
    args=parser.parse_args()
    if args.command=='doctor':
        return 0 if doctor(args.runtime,args.verify_models,args.verify_render)['ready'] else 1
    if args.command=='setup':setup(args.runtime,args.python)
    elif args.command=='setup-render':setup_render(args.runtime,args.python)
    elif args.command=='qa':return 0 if qa(args.project.resolve(),args.runtime)['automated_pass'] else 1
    else:build(args.project,args.runtime,args.stop_after)
    return 0


if __name__=='__main__':
    try:sys.exit(main())
    except Exception as exc:
        print('ERROR: '+str(exc),file=sys.stderr);sys.exit(1)
