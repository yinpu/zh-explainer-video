"""Trim excess silent margins at independent takes, without retiming speech."""
import json,sys
from pathlib import Path
import numpy as np
import soundfile as sf
from timing import atomic_json,digest,file_hash


def trim(request):
    sr=24000;step=sr//request['fps'];report=[]
    for group in request['groups']:
        for bid,edge in [(group['blocks'][0],'start'),(group['blocks'][-1],'end')]:
            path=Path(request['audio_dir'])/f'{bid}.wav';meta=json.loads(path.with_suffix('.json').read_text())
            key=digest([meta['group_key'],request['lead_seconds'],request['tail_seconds'],file_hash(__file__),edge])
            if meta.get('edge_trim_keys',{}).get(edge)==key:continue
            align_path=Path(request['align_dir'])/f'{bid}.json';align=json.loads(align_path.read_text())
            original,sr0=sf.read(Path(request['groups_dir'])/'audio'/f'{group["id"]}.wav',dtype='float32');assert sr0==sr
            current_start=meta['source_start_sample']
            first=align['items'][0]['start']+current_start/sr
            last=align['items'][-1]['end']+current_start/sr
            original_start=meta.get('uncropped_source_start_sample',meta['source_start_sample'])
            original_end=meta.get('uncropped_source_end_sample',meta['source_end_sample'])
            start=meta['source_start_sample'];end=meta['source_end_sample']
            if edge=='start':
                start=max(original_start,int(np.floor((first-request['lead_seconds'])*sr/step))*step)
            else:
                end=min(original_end,int(np.ceil((last+request['tail_seconds'])*sr/step))*step)
            n=start if edge=='start' else end
            # Reject a cut through audible material. Keep the original margin
            # rather than hiding the failure with a crossfade over syllables.
            window=original[max(0,n-240):min(len(original),n+240)]
            rms=float(np.sqrt(np.mean(window*window))) if len(window) else 0
            if rms>.006:
                report.append({'block':bid,'edge':edge,'trimmed':False,'rms':rms})
                continue
            part=original[start:end]
            if end>len(original):part=np.pad(part,(0,end-len(original)))
            sf.write(path,part,sr,subtype='PCM_24')
            shift=(start-current_start)/sr
            for item in align['items']:
                item['start']-=shift;item['end']-=shift
            if align['items'][0]['start']<-.001 or align['items'][-1]['end']>len(part)/sr+.001:
                raise ValueError('Edge trimming clipped aligned speech: '+bid)
            text=request['texts'][bid]
            align['key']=digest([file_hash(path),text,request['align_revision'],file_hash(Path(__file__).with_name('audio_worker.py'))])
            atomic_json(align_path,align)
            meta.update(uncropped_source_start_sample=original_start,uncropped_source_end_sample=original_end,source_start_sample=start,source_end_sample=end,samples=len(part),duration=len(part)/sr,sha256=file_hash(path),rms_db=20*np.log10(max(float(np.sqrt(np.mean(part*part))),1e-9)),peak=float(np.max(np.abs(part))),clipped_fraction=float(np.mean(np.abs(part)>=.999)))
            meta.setdefault('edge_trim_keys',{})[edge]=key
            atomic_json(path.with_suffix('.json'),meta)
            report.append({'block':bid,'edge':edge,'trimmed':True,'rms':rms,'lead_seconds':align['items'][0]['start'],'tail_seconds':len(part)/sr-align['items'][-1]['end']})
    atomic_json(request['report'],{'changes':report,'note':'Only quiet take-edge margins are trimmed; no speech stretching or pitch modification.'})


if __name__=='__main__':trim(json.loads(Path(sys.argv[-1]).read_text()))
