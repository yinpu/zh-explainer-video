"""Verify true waveform continuity, context exclusion, and zero added gaps."""
import json,subprocess,sys,tempfile
from pathlib import Path
import numpy as np
import soundfile as sf
scratch=tempfile.TemporaryDirectory(prefix='zvideo-continuity-');root=Path(scratch.name)
scripts=Path(__file__).resolve().parent;sys.path.insert(0,str(scripts))
from timing import atomic_json,file_hash,aligned_chars
from grouped_audio import retained_alignment
items=[{'text':c,'start':i+.2,'end':i+.45} for i,c in enumerate('前甲乙后余')]
kept,kept_items,prefix,suffix=retained_alignment(items,'前甲乙后余',1,2)
assert kept=='前甲乙后' and prefix==1 and suffix==1
aligned_chars(kept_items,kept,4)
bad=[dict(x) for x in kept_items];bad[1]['end']=4.6
try:
 aligned_chars(bad,kept,4)
except ValueError:pass
else:raise AssertionError('Extrapolated core timing must be rejected')
audio=np.zeros(4*24000,dtype=np.float32)
for i in range(4):
 a=int((i+.2)*24000);b=int((i+.45)*24000)
 audio[a:b]=.1*np.sin(2*np.pi*220*np.arange(b-a)/24000)
sf.write(root/'take.wav',audio,24000,subtype='PCM_24')
atomic_json(root/'align.json',{'items':[{'text':c,'start':i+.2,'end':i+.45} for i,c in enumerate('前甲乙后')]})
blocks=[{'id':bid,'text':text,'output':str(root/f'{bid}.wav'),'alignment_output':str(root/f'{bid}-align.json')} for bid,text in [('a','甲。'),('b','乙。')]]
req={'fps':30,'align_revision':'synthetic','seams_output':str(root/'seams.json'),'tasks':[{'id':'take','audio':str(root/'take.wav'),'alignment':str(root/'align.json'),'text':'前。甲。乙。后。','prefix_chars':1,'suffix_chars':1,'blocks':blocks,'key':'test'}]}
atomic_json(root/'request.json',req)
subprocess.run([sys.executable,str(scripts/'audio_worker.py'),'split',str(root/'request.json')],check=True)
a=json.loads((root/'a.json').read_text());b=json.loads((root/'b.json').read_text())
assert a['source_end_sample']==b['source_start_sample']
original,_=sf.read(root/'take.wav',dtype='float32')
joined=np.concatenate([sf.read(root/f'{x}.wav',dtype='float32')[0] for x in ['a','b']])
np.testing.assert_array_equal(joined,original[a['source_start_sample']:b['source_end_sample']])
for bid,text in [('a','甲。'),('b','乙。')]:
 meta=json.loads((root/f'{bid}.json').read_text());align=json.loads((root/f'{bid}-align.json').read_text())
 aligned_chars(align['items'],text,meta['duration'])
assemble={'fps':30,'join_pause_seconds':0,'output':str(root/'master.wav'),'metadata':str(root/'master.json'),'tasks':[{'id':x,'audio':str(root/f'{x}.wav')} for x in ['a','b']]}
atomic_json(root/'assemble.json',assemble)
subprocess.run([sys.executable,str(scripts/'audio_worker.py'),'assemble',str(root/'assemble.json')],check=True)
master=json.loads((root/'master.json').read_text())
assert master['blocks'][0]['added_silence_samples']==0
assembled,_=sf.read(root/'master.wav',dtype='float32')
np.testing.assert_array_equal(assembled[:len(joined)],joined)
assert np.max(np.abs(assembled[len(joined):]))==0
print('PASS: no context leakage, exact shared-take reconstruction, no added internal silence')

(root/'groups/audio').mkdir(parents=True)
import shutil
shutil.copy2(root/'take.wav',root/'groups/audio/take.wav')
for bid in ['a','b']:shutil.copy2(root/f'{bid}-align.json',root/f'{bid}-saved-align.json')
# Use separate audio/align directories as the production pipeline does.
(root/'align').mkdir()
for bid in ['a','b']:shutil.copy2(root/f'{bid}-align.json',root/'align'/f'{bid}.json')
trim_req={'groups':[{'id':'take','blocks':['a','b']}],'audio_dir':str(root),'align_dir':str(root/'align'),'groups_dir':str(root/'groups'),'fps':30,'align_revision':'synthetic','texts':{'a':'甲。','b':'乙。'},'lead_seconds':.25,'tail_seconds':.2,'report':str(root/'trim-report.json')}
atomic_json(root/'trim.json',trim_req)
subprocess.run([sys.executable,str(scripts/'join_trim.py'),str(root/'trim.json')],check=True)
a=json.loads((root/'a.json').read_text());b=json.loads((root/'b.json').read_text())
assert a['source_end_sample']==b['source_start_sample']
joined=np.concatenate([sf.read(root/f'{x}.wav',dtype='float32')[0] for x in ['a','b']])
np.testing.assert_array_equal(joined,original[a['source_start_sample']:b['source_end_sample']])
for bid,text in [('a','甲。'),('b','乙。')]:
 meta=json.loads((root/f'{bid}.json').read_text());align=json.loads((root/'align'/f'{bid}.json').read_text())
 aligned_chars(align['items'],text,meta['duration'])
assert json.loads((root/'align/a.json').read_text())['items'][0]['start']<=.284
assert b['duration']-json.loads((root/'align/b.json').read_text())['items'][-1]['end']<=.234
print('PASS: quiet take-edge trimming preserves samples and aligned speech')
scratch.cleanup()
