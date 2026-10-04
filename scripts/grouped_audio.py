"""Context-collared narration takes spanning multiple visual blocks."""
from pathlib import Path
import json
from timing import atomic_json, clean, digest, file_hash


def read(path):
    return json.loads(Path(path).read_text())


def join_options(job):
    """Optional editing choices, independent of narration grouping."""
    import math
    options=job.get('narration_join',{})
    if not isinstance(options,dict):raise ValueError('narration_join must be an object')
    enabled=options.get('trim_silence',False)
    if not isinstance(enabled,bool):raise ValueError('trim_silence must be a boolean')
    result={'trim_silence':enabled}
    for name,default in [('lead_seconds',.25),('tail_seconds',.20)]:
        value=options.get(name,default)
        if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value) or value<0:
            raise ValueError(name+' must be a finite non-negative number')
        result[name]=value
    return result


def retained_alignment(items, full_text, prefix_chars, core_chars):
    """Validate only delivered speech and its immediate boundary context.

    An aligner may extrapolate missing final words of discarded TTS context.
    Preserve the full raw alignment for audit; never clamp those timestamps
    into the delivered audio or accept extrapolated timestamps for core text.
    """
    chars=[];spans=[]
    for item in items:
        word=clean(item['text']);a=float(item['start']);b=float(item['end'])
        for i,c in enumerate(word):
            chars.append(c);spans.append((a+(b-a)*i/len(word),a+(b-a)*(i+1)/len(word)))
    if ''.join(chars)!=clean(full_text):raise ValueError('Full aligner text coverage mismatch')
    lo=max(0,prefix_chars-1);hi=min(len(chars),prefix_chars+core_chars+1)
    return ''.join(chars[lo:hi]),[{'text':chars[i],'start':spans[i][0],'end':spans[i][1]} for i in range(lo,hi)],prefix_chars-lo,hi-prefix_chars-core_chars


def prepare(config, models, job, work, state, mark, worker, create_tasks, infer_stage, stop_after):
    join=join_options(job)
    groups=job['narration_groups']; by_id={b['id']:b for b in job['blocks']}
    ids=[bid for g in groups for bid in g['blocks']]
    if ids != [b['id'] for b in job['blocks']]:
        raise ValueError('narration_groups must cover every block once, in order')
    if len({g['id'] for g in groups}) != len(groups):
        raise ValueError('Narration group IDs must be unique')
    grouped={**job,'blocks':[{'id':g['id'],'text':g.get('context_before','')+''.join(by_id[x]['text'] for x in g['blocks'])+g.get('context_after',''),'beats':[]} for g in groups]}
    grouped.pop('narration_groups',None)
    from timing import validate_job
    validate_job(grouped)
    gw=work/'groups';gw.mkdir(exist_ok=True)
    attempts=state.setdefault('group_attempts',{})
    revisions=state.setdefault('group_revisions',{})
    for b in grouped['blocks']:
        rev=digest([b['text'],job['voice'],models['tts']['revision']])
        if revisions.get(b['id']) != rev:attempts.pop(b['id'],None)
        revisions[b['id']]=rev

    for _ in range(3):
        mark('grouped-tts')
        tasks=create_tasks(grouped,models,gw,{b['id']:attempts.get(b['id'],0) for b in grouped['blocks']})
        if tasks:worker(config,'tts',{'model':models['tts']['path'],'voice':job['voice'],'tasks':tasks},gw)
        if stop_after=='tts':return True
        mark('grouped-asr');infer_stage(config,models,grouped,gw,'asr')
        bad={b['id'] for b in grouped['blocks'] if read(gw/'asr'/f'{b["id"]}.json')['cer']>.12}
        if not bad:
            mark('grouped-align');infer_stage(config,models,grouped,gw,'align')
            tasks=[]
            for g in groups:
                audio=gw/'audio'/f'{g["id"]}.wav';align=gw/'align'/f'{g["id"]}.json'
                key=digest([file_hash(audio),file_hash(align),g,job['video']['fps'],join,file_hash(Path(__file__).with_name('audio_worker.py')),file_hash(__file__)])
                blocks=[]
                for bid in g['blocks']:
                    out=work/'audio'/f'{bid}.wav'
                    blocks.append({'id':bid,'text':by_id[bid]['text'],'output':str(out),'alignment_output':str(work/'align'/f'{bid}.json')})
                valid=all((Path(b['output']).exists() and Path(b['output']).with_suffix('.json').exists() and read(Path(b['output']).with_suffix('.json')).get('group_key')==key and read(Path(b['output']).with_suffix('.json')).get('sha256')==file_hash(b['output']) and Path(b['alignment_output']).exists() and read(b['alignment_output']).get('source_group_key')==key) for b in blocks)
                if not valid:
                    text=next(b['text'] for b in grouped['blocks'] if b['id']==g['id'])
                    core_chars=sum(len(clean(by_id[bid]['text'])) for bid in g['blocks'])
                    kept_text,kept_items,prefix,suffix=retained_alignment(read(align)['items'],text,len(clean(g.get('context_before',''))),core_chars)
                    cropped_align=gw/'retained-align'/f'{g["id"]}.json'
                    atomic_json(cropped_align,{'items':kept_items,'full_alignment':str(align),'note':'Only discarded context is excluded. Retained speech timestamps remain unchanged.'})
                    tasks.append({'id':g['id'],'audio':str(audio),'alignment':str(cropped_align),'text':kept_text,'prefix_chars':prefix,'suffix_chars':suffix,'blocks':blocks,'key':key})
            if tasks:
                mark('grouped-split')
                worker(config,'split',{'tasks':tasks,'fps':job['video']['fps'],'align_revision':models['align']['revision'],'seams_output':str(work/'group-seams.json')},work)
            if join['trim_silence']:
                mark('grouped-join-trim')
                worker(config,'join_trim',{'groups':groups,'audio_dir':str(work/'audio'),'align_dir':str(work/'align'),'groups_dir':str(gw),'fps':job['video']['fps'],'align_revision':models['align']['revision'],'texts':{b['id']:b['text'] for b in job['blocks']},'lead_seconds':join['lead_seconds'],'tail_seconds':join['tail_seconds'],'report':str(work/'join-trim.json')},work)
            # Check the actual trimmed speech as well as the full take. A weak
            # overall CER must not conceal an omitted sentence in one shot.
            mark('asr');infer_stage(config,models,job,work,'asr')
            bad_blocks={b['id'] for b in job['blocks'] if read(work/'asr'/f'{b["id"]}.json')['cer']>.12}
            bad={g['id'] for g in groups if any(bid in bad_blocks for bid in g['blocks'])}
        if not bad:return False
        if any(attempts.get(gid,0)>=2 for gid in bad):
            raise RuntimeError('Narration take needs review after two retries: '+', '.join(sorted(bad)))
        for gid in bad:attempts[gid]=attempts.get(gid,0)+1
        mark('grouped-retry')
    raise RuntimeError('Grouped narration did not pass speech checks')
