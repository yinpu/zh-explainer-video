"""Each invocation loads one MLX model only; all inference is offline."""
import argparse
import gc
import json
import os
import time
from pathlib import Path

os.environ['HF_HUB_OFFLINE'] = '1'
os.environ['TRANSFORMERS_OFFLINE'] = '1'
os.environ['TOKENIZERS_PARALLELISM'] = 'false'
from timing import atomic_json, file_hash, cer


def tts(request):
    import mlx.core as mx
    import numpy as np
    import soundfile as sf
    from mlx_audio.tts.utils import load_model
    start = time.monotonic()
    model = load_model(request['model'])
    load_seconds = time.monotonic() - start
    for task in request['tasks']:
        print('TTS ' + task['id'], flush=True)
        mx.random.seed(task['seed'])
        start = time.monotonic()
        limit=request['voice'].get('max_tokens',2048)
        results = list(model.generate_custom_voice(
            text=task['text'], speaker=request['voice']['speaker'], language='Chinese',
            instruct=request['voice']['instruct'], temperature=request['voice']['temperature'],
            top_k=50, top_p=.95, repetition_penalty=1.05,
            max_tokens=limit, stream=False, verbose=False))
        if len(results) != 1:
            raise RuntimeError('Expected a single contiguous waveform per semantic block')
        result = results[0]
        audio = np.asarray(result.audio, dtype=np.float32).reshape(-1)
        if result.sample_rate != 24000 or len(audio) < 2400 or not np.isfinite(audio).all():
            raise RuntimeError('Invalid TTS waveform')
        if result.token_count >= limit:
            raise RuntimeError('TTS hit generation limit; shorten this semantic block')
        if np.max(np.abs(audio)) < .001:
            raise RuntimeError('TTS produced silence')
        # Remove only excessive edge silence; retain a natural lead/tail.
        windows = np.array([np.sqrt(np.mean(x*x)) for x in np.array_split(audio, max(1,len(audio)//240))])
        active = np.flatnonzero(windows > max(.001, float(windows.max()) * .015))
        lo = max(0, int(active[0] * len(audio)/len(windows)) - 2400)
        hi = min(len(audio), int((active[-1]+1)*len(audio)/len(windows)) + 4800)
        audio = audio[lo:hi]
        out = Path(task['output'])
        out.parent.mkdir(parents=True, exist_ok=True)
        sf.write(out, audio, 24000, subtype='PCM_24')
        # Pitch is only a screening statistic; Mandarin pitch varies naturally.
        pitch = []
        for i in range(0, len(audio)-1440, 2400):
            frame = audio[i:i+1440].astype(float)
            if np.sqrt(np.mean(frame*frame)) < .012:
                continue
            frame = (frame-frame.mean()) * np.hanning(len(frame))
            corr = np.fft.irfft(np.abs(np.fft.rfft(frame, n=4096))**2)[:1440]
            low, high = 48, 240
            peak = low + np.argmax(corr[low:high])
            if corr[peak] > .55 * max(corr[0], 1e-10):
                pitch.append(24000 / peak)
        metadata = {'key':task['key'], 'seed':task['seed'], 'sample_rate':24000,
                    'samples':len(audio), 'duration':len(audio)/24000,
                    'elapsed_seconds':time.monotonic()-start, 'model_load_seconds':load_seconds,
                    'peak_memory_gb':float(mx.get_peak_memory())/1e9,
                    'rms_db':20*np.log10(max(float(np.sqrt(np.mean(audio*audio))),1e-9)),
                    'peak':float(np.max(np.abs(audio))),
                    'clipped_fraction':float(np.mean(np.abs(audio)>=.999)),
                    'median_f0_hz':float(np.median(pitch)) if pitch else None,
                    'sha256':file_hash(out)}
        atomic_json(out.with_suffix('.json'),metadata)
        print(json.dumps({'id':task['id'],**metadata},ensure_ascii=False),flush=True)
        del audio, result, results
        gc.collect()
        mx.clear_cache()


def speech(request, mode):
    import mlx.core as mx
    from mlx_audio.stt.utils import load_model
    model = load_model(request['model'])
    for task in request['tasks']:
        start = time.monotonic()
        print(mode.upper()+' '+task['id'],flush=True)
        if mode == 'align':
            result = model.generate(task['audio'], text=task['text'], language='Chinese')
            data = {'items':[{'text':i.text,'start':i.start_time,'end':i.end_time} for i in result]}
        else:
            result = model.generate(task['audio'], language='Chinese', max_tokens=max(1024,len(task['text'])*3), temperature=0)
            transcript = result.text
            data = {'transcript':transcript, 'cer':cer(task['text'],transcript)}
        data.update(key=task['key'], elapsed_seconds=time.monotonic()-start,
                    peak_memory_gb=float(mx.get_peak_memory())/1e9)
        atomic_json(task['output'],data)
        print(json.dumps({'id':task['id'],**{k:v for k,v in data.items() if k!='items'}},ensure_ascii=False),flush=True)
        del result
        gc.collect()
        mx.clear_cache()


def assemble(request):
    import numpy as np
    import soundfile as sf
    fps = request['fps']
    step = 24000 // fps
    offset, blocks = 0, []
    with sf.SoundFile(request['output'],mode='w',samplerate=24000,channels=1,subtype='PCM_24') as output:
        for i, task in enumerate(request['tasks']):
            audio, sr = sf.read(task['audio'],dtype='float32')
            assert sr==24000 and audio.ndim==1
            gap = .6 if i==len(request['tasks'])-1 else request.get('join_pause_seconds',.24)
            padded = int(np.ceil((len(audio)+round(gap*sr))/step))*step
            output.write(audio)
            output.write(np.zeros(padded-len(audio),dtype=np.float32))
            blocks.append({'id':task['id'],'offset':offset/sr,'duration':padded/sr,
                           'samples':padded,'audio_samples':len(audio),'added_silence_samples':padded-len(audio),'sha256':file_hash(task['audio'])})
            offset += padded
    atomic_json(request['metadata'],{'sample_rate':24000,'samples':offset,'duration':offset/24000,'blocks':blocks})


def split(request):
    import numpy as np
    import soundfile as sf
    from timing import aligned_chars, clean, digest
    step=24000//request['fps'];seams=[]
    for task in request['tasks']:
        audio,sr=sf.read(task['audio'],dtype='float32');assert sr==24000 and audio.ndim==1
        alignment=json.loads(Path(task['alignment']).read_text())
        chars,spans=aligned_chars(alignment['items'],task['text'],len(audio)/sr)
        def boundary(index):
            if index==0:return 0
            if index==len(chars):return int(np.ceil(len(audio)/step))*step
            a,b=spans[index-1][1],spans[index][0]
            center=(a+b)/2
            lo=int(np.ceil(a*sr/step));hi=int(np.floor(b*sr/step))
            candidates=[n*step for n in range(lo,hi+1)] if hi>=lo else [round(center*sr/step)*step]
            def energy(n):
                segment=audio[max(0,n-120):min(len(audio),n+120)]
                return float(np.mean(segment*segment)) if len(segment) else 0
            return min(candidates,key=lambda n:energy(n)+1e-8*abs(n/sr-center))
        cursor=task['prefix_chars'];cuts=[boundary(cursor)]
        for block in task['blocks']:
            cursor+=len(clean(block['text']));cuts.append(boundary(cursor))
        if cursor+task['suffix_chars']!=len(chars):raise ValueError('Group context coverage mismatch')
        char_cursor=task['prefix_chars']
        for i,block in enumerate(task['blocks']):
            start,end=cuts[i],cuts[i+1]
            if end<=start:raise ValueError('Non-monotonic group cuts')
            part=np.pad(audio[start:min(end,len(audio))],(0,max(0,end-len(audio))))
            dest=Path(block['output']);dest.parent.mkdir(parents=True,exist_ok=True)
            sf.write(dest,part,sr,subtype='PCM_24')
            pitches=[]
            for k in range(0,len(part)-1440,2400):
                frame=part[k:k+1440].astype(float)
                if np.sqrt(np.mean(frame*frame))<.012:continue
                frame=(frame-frame.mean())*np.hanning(len(frame));corr=np.fft.irfft(np.abs(np.fft.rfft(frame,n=4096))**2)[:1440]
                peak=48+np.argmax(corr[48:240])
                if corr[peak]>.55*max(corr[0],1e-10):pitches.append(sr/peak)
            meta={'key':digest([task['key'],block['id']]),'group_key':task['key'],'source_group':task['id'],'source_start_sample':start,'source_end_sample':end,'sample_rate':sr,'samples':len(part),'duration':len(part)/sr,'sha256':file_hash(dest),'rms_db':20*np.log10(max(float(np.sqrt(np.mean(part*part))),1e-9)),'peak':float(np.max(np.abs(part))),'clipped_fraction':float(np.mean(np.abs(part)>=.999)),'median_f0_hz':float(np.median(pitches)) if pitches else None}
            atomic_json(dest.with_suffix('.json'),meta)
            count=len(clean(block['text']));items=[]
            for k in range(char_cursor,char_cursor+count):
                a,b=spans[k]
                if a<start/sr-.04 or b>end/sr+.04:raise ValueError('Crop overlaps aligned speech: '+block['id'])
                items.append({'text':chars[k],'start':max(0,a-start/sr),'end':min(len(part)/sr,max(0,b-start/sr))})
            char_cursor+=count
            align_key=digest([file_hash(dest),block['text'],request['align_revision'],file_hash(__file__)])
            atomic_json(block['alignment_output'],{'items':items,'key':align_key,'source_group_key':task['key'],'source_group':task['id']})
        for name,n in [('start',cuts[0]),('end',cuts[-1])]:
            win=audio[max(0,n-120):min(len(audio),n+120)]
            seams.append({'group':task['id'],'edge':name,'source_time':n/sr,'rms_db':20*np.log10(max(float(np.sqrt(np.mean(win*win))) if len(win) else 0,1e-9))})
        print('SPLIT '+task['id']+' '+str(cuts),flush=True)
    atomic_json(request['seams_output'],{'edges':seams,'note':'Context is cropped at alignment-derived pauses. Listening review remains required.'})


if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('mode',choices=['tts','align','asr','assemble','split'])
    p.add_argument('request')
    args=p.parse_args()
    request=json.loads(Path(args.request).read_text())
    if args.mode=='tts': tts(request)
    elif args.mode=='assemble': assemble(request)
    elif args.mode=='split':split(request)
    else: speech(request,args.mode)
