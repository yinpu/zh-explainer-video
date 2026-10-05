"""Fixed-voice, transport, cache and waveform tests without paid service calls."""
import copy
import io
import json
import os
import tempfile
import unittest
import urllib.error
import base64
from pathlib import Path
from unittest.mock import patch

from cloud_tts import request_spec, decode_doubao, synthesize, save_audio
from voice import DEFAULT_VOICE, normalize_voice, cloud_model
from zvideo import create_tts_tasks, load_project, build, worker
from timing import atomic_json, file_hash
from pace import screen
from with_credentials import environment


class CloudTests(unittest.TestCase):
    def test_default_project_uses_fixed_voice(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d);atomic_json(p/'project.json',{'schema_version':1,'blocks':[{'id':'a','text':'你好'}]})
            voice=load_project(p)['voice']
            self.assertEqual(voice,DEFAULT_VOICE)
            self.assertEqual(voice['speaker'],'zh_male_liufei_uranus_bigtts')
            self.assertEqual(voice['speed'],.95)

    def test_conflicting_voice_and_unsupported_fields_fail(self):
        for value in [{'provider':'other'},{'speaker':'other'},{'speed':1.0},
                      {'model':'other'},{'speed':float('nan')},{'temperature':.6},
                      {'api_key':'secret-marker'},{'headers':{'secret':'secret-marker'}}]:
            with self.assertRaises(ValueError) as e:normalize_voice(value)
            self.assertNotIn('secret-marker',str(e.exception))
        self.assertEqual(normalize_voice({'speed':.95}),DEFAULT_VOICE)

    def test_fixed_request_and_separate_instructions(self):
        voice=normalize_voice({'instruct':'自然讲解','pronunciation_dict':{'tone':['词元/词元']}})
        url,headers,body=request_spec(voice,'正文','test-secret')
        self.assertEqual(url,'https://openspeech.bytedance.com/api/v3/tts/unidirectional')
        self.assertEqual(headers['X-Api-Resource-Id'],'seed-tts-2.0')
        self.assertEqual(headers['X-Api-Key'],'test-secret')
        params=body['req_params']
        self.assertEqual(params['speaker'],'zh_male_liufei_uranus_bigtts')
        self.assertEqual(params['audio_params'],{'format':'pcm','sample_rate':24000,'speech_rate':-5})
        self.assertEqual(json.loads(params['additions'])['context_texts'],['自然讲解'])
        self.assertEqual(params['text'],'正文')
        self.assertNotIn('seed',params)
        with self.assertRaises(ValueError):request_spec({'speed':1.0},'正文','test-secret')

    def test_stream_chunks_and_late_errors(self):
        parts=[b'\x00\x01',b'\x02\x03']
        lines=[json.dumps({'code':0,'data':base64.b64encode(x).decode()}).encode()+b'\n' for x in parts]
        self.assertEqual(decode_doubao(io.BytesIO(b''.join(lines))),b''.join(parts))
        self.assertEqual(decode_doubao(io.BytesIO(b''.join(lines)+b'{"code":20000000}\n')),b''.join(parts))
        for tail in [b'{"code":500,"message":"secret-marker"}\n', b'not-json\n']:
            with self.assertRaises((RuntimeError,ValueError)) as e:decode_doubao(io.BytesIO(lines[0]+tail))
            self.assertNotIn('secret-marker',str(e.exception))
        with self.assertRaises(RuntimeError):decode_doubao(io.BytesIO(b''))
        odd=json.dumps({'code':0,'data':base64.b64encode(b'1').decode()}).encode()
        with self.assertRaises(RuntimeError):decode_doubao(io.BytesIO(odd))

    def test_missing_key_no_network_and_safe_transport_errors(self):
        with patch.dict(os.environ,{},clear=True),patch('cloud_tts.urllib.request.build_opener') as opener:
            with self.assertRaisesRegex(RuntimeError,'DOUBAO_API_KEY'):synthesize({},'测试')
            opener.assert_not_called()
        for error in [urllib.error.HTTPError('https://example',401,'secret-marker',{},None),
                      urllib.error.URLError('secret-marker')]:
            with patch.dict(os.environ,{'DOUBAO_API_KEY':'secret-marker'}),patch('cloud_tts.urllib.request.build_opener') as opener:
                opener.return_value.open.side_effect=error
                with self.assertRaises(RuntimeError) as e:synthesize({},'测试')
                self.assertNotIn('secret-marker',str(e.exception))
                self.assertEqual(opener.return_value.open.call_count,1)

    def test_cache_reuse_and_text_style_pronunciation_changes(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);voice=normalize_voice()
            job={'voice':voice,'blocks':[{'id':'a','text':'原文'}]};models={'tts':cloud_model(voice)}
            task=create_tts_tasks(job,models,root)[0];wav=Path(task['output'])
            wav.parent.mkdir();wav.write_bytes(b'wave');atomic_json(wav.with_suffix('.json'),{'key':task['key'],'sha256':file_hash(wav)})
            job['blocks'][0]['title']='画面修改'
            self.assertEqual(create_tts_tasks(job,models,root),[])
            for field,value in [('instruct','温和讲解'),('pronunciation_dict',{'tone':['原文/原文']})]:
                changed=copy.deepcopy(job);changed['voice'][field]=value
                self.assertTrue(create_tts_tasks(changed,models,root))
            changed=copy.deepcopy(job);changed['blocks'][0]['text']='另一份讲稿'
            self.assertTrue(create_tts_tasks(changed,models,root))
            self.assertTrue(create_tts_tasks(job,models,root,{'a':1}))
            with self.assertRaises(ValueError):
                create_tts_tasks({**job,'voice':{'speed':1}},models,root)

    def test_grouped_and_ungrouped_build_without_local_tts(self):
        for grouped in (False,True):
            with tempfile.TemporaryDirectory() as d:
                root=Path(d);project=root/'project';runtime=root/'runtime';project.mkdir();runtime.mkdir()
                job={'schema_version':1,'blocks':[{'id':'a','text':'甲。'},{'id':'b','text':'乙。'}]}
                if grouped:job['narration_groups']=[{'id':'whole','blocks':['a','b'],'context_after':'后文。'}]
                atomic_json(project/'project.json',job)
                with patch('zvideo.worker') as worker_mock:
                    build(project,runtime,'tts')
                    args=worker_mock.call_args.args
                    self.assertEqual(args[1],'tts');self.assertEqual(args[2]['voice'],DEFAULT_VOICE)
                    self.assertEqual(args[2]['model'],'seed-tts-2.0')
                    self.assertEqual(len(args[2]['tasks']),1 if grouped else 2)
                    if grouped:self.assertEqual(args[2]['tasks'][0]['text'],'甲。乙。后文。')

    def test_worker_uses_cloud_and_never_saves_credential(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            with patch.dict(os.environ,{'DOUBAO_API_KEY':'secret-marker'}),patch('zvideo.run') as run:
                worker({'python':'python3'},'tts',{'voice':{},'tasks':[]},root)
                self.assertEqual(Path(run.call_args.args[0][1]).name,'cloud_tts.py')
                request=(root/'tts-request.json').read_text()
                self.assertNotIn('secret-marker',request)
                self.assertEqual(json.loads(request)['voice']['speed'],.95)

    def test_pcm_waveform_and_metadata(self):
        try:
            import numpy as np
            import soundfile as sf
        except ImportError:self.skipTest('Use shared audio Python for waveform verification')
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'sample.wav'
            samples=(np.sin(np.arange(4800)*.06)*8000).astype('<i2')
            save_audio(samples.tobytes(),{'key':'cache-key','output':str(path)},normalize_voice(),1)
            audio,sr=sf.read(path,dtype='float32')
            self.assertEqual(sr,24000);self.assertEqual(len(audio),len(samples))
            np.testing.assert_allclose(audio,samples/32768,atol=1/2**23)
            meta=json.loads(path.with_suffix('.json').read_text())
            self.assertEqual(meta['sha256'],file_hash(path))

    def test_pace_flags_are_only_listening_hints(self):
        items=[];t=0
        for i in range(140):
            dt=.12 if 60<=i<90 else .25
            items.append({'text':'字','start':t,'end':t+dt});t+=dt
        results=screen(items,100)
        self.assertTrue(results)
        self.assertTrue(all(x['start']>=100 and x['review']=='audition_required' for x in results))
        self.assertEqual(screen([{'text':'token','start':0,'end':1}]*50),[])

    def test_private_loader_permissions_and_only_required_key(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'credentials.json'
            path.write_text(json.dumps({'DOUBAO_API_KEY':'stored-secret'}));path.chmod(0o600)
            with patch.dict(os.environ,{'DOUBAO_API_KEY':'explicit-env'},clear=True):
                env=environment(path)
                self.assertEqual(env['DOUBAO_API_KEY'],'explicit-env')
            path.write_text(json.dumps({'DOUBAO_API_KEY':'stored-secret','UNSUPPORTED':'unused'}))
            with self.assertRaises(ValueError):environment(path)
            path.chmod(0o644)
            with self.assertRaises(ValueError):environment(path)


if __name__=='__main__':unittest.main()
