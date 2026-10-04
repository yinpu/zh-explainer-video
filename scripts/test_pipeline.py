"""Fast behaviour tests; no model downloads or inference."""
import copy
import json
import tempfile
import unittest
from pathlib import Path
from timing import aligned_chars, atomic_json, cer, clean, file_hash, make_block_timing, validate_job
from zvideo import DEFAULT_VOICE, create_tts_tasks, valid_cache


class PipelineTests(unittest.TestCase):
    def job(self):
        return {'schema_version':1,'voice':dict(DEFAULT_VOICE),'video':{'fps':30},
                'blocks':[{'id':'first','text':'先看变化，再看变化。','beats':[{'id':'second','phrase':'变化','occurrence':2}]}]}

    def test_alignment_uses_second_spoken_occurrence(self):
        block=self.job()['blocks'][0]
        chars=clean(block['text'])
        items=[{'text':c,'start':i*.2,'end':i*.2+.18} for i,c in enumerate(chars)]
        timing=make_block_timing(block,items,2,60,30)
        self.assertAlmostEqual(timing['beats']['second']['speech_time'],1.2)
        self.assertAlmostEqual(timing['beats']['second']['global_time'],61.2)
        self.assertEqual(''.join(clean(x['text']) for x in timing['captions']),chars)

    def test_missing_spoken_text_is_not_filled_with_fake_times(self):
        with self.assertRaises(ValueError):
            aligned_chars([{'text':'你好','start':0,'end':1}],'你好世界',2)

    def test_backwards_or_out_of_range_timestamps_fail(self):
        for items in [[{'text':'甲','start':1,'end':1.2},{'text':'乙','start':0,'end':.2}],
                      [{'text':'甲乙','start':0,'end':9}]]:
            with self.assertRaises(ValueError):aligned_chars(items,'甲乙',2)

    def test_duplicate_blocks_and_unspoken_anchor_fail(self):
        job=self.job();job['blocks']*=2
        with self.assertRaises(ValueError):validate_job(job)
        job=self.job();job['blocks'][0]['beats'][0]['phrase']='不在讲稿里'
        with self.assertRaises(ValueError):validate_job(job)

    def test_missing_repeated_anchor_occurrence_fails(self):
        block=self.job()['blocks'][0];block['beats'][0]['occurrence']=3
        items=[{'text':clean(block['text']),'start':0,'end':2}]
        with self.assertRaises(ValueError):make_block_timing(block,items,2,0,30)

    def test_visual_edits_reuse_audio_and_text_edits_do_not(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);job=self.job();models={'tts':{'revision':'fixed-revision'}}
            task=create_tts_tasks(job,models,root)[0]
            wav=Path(task['output']);wav.parent.mkdir();wav.write_bytes(b'cached-waveform')
            atomic_json(wav.with_suffix('.json'),{'key':task['key'],'sha256':file_hash(wav)})
            job['blocks'][0]['title']='A different visual title'
            job['video']['width']=1280
            self.assertEqual(create_tts_tasks(job,models,root),[])
            job['blocks'][0]['text']='讲稿真的改变了。'
            self.assertEqual(len(create_tts_tasks(job,models,root)),1)

    def test_captions_preserve_authored_technical_terms(self):
        block={'id':'terms','text':'词元，也叫 token。ASR 只检查发音。','beats':[]}
        text=clean(block['text'])
        items=[{'text':c,'start':i*.1,'end':i*.1+.09} for i,c in enumerate(text)]
        timing=make_block_timing(block,items,len(text)*.1,0,30)
        captions=''.join(c['text'] for c in timing['captions'])
        self.assertEqual(captions,block['text'])
        self.assertIn('token',captions)
        self.assertIn('ASR',captions)

    def test_changed_voice_instruction_invalidates_audio_cache(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);job=self.job();models={'tts':{'revision':'fixed-revision'}}
            task=create_tts_tasks(job,models,root)[0]
            wav=Path(task['output']);wav.parent.mkdir();wav.write_bytes(b'cached-waveform')
            atomic_json(wav.with_suffix('.json'),{'key':task['key'],'sha256':file_hash(wav)})
            self.assertEqual(create_tts_tasks(job,models,root),[])
            job['voice']['instruct']='请以课堂讲解的语气解释因果，突出关键概念。'
            self.assertEqual(len(create_tts_tasks(job,models,root)),1)

    def test_corrupt_audio_does_not_pass_cache(self):
        with tempfile.TemporaryDirectory() as d:
            wav=Path(d)/'audio.wav';meta=wav.with_suffix('.json');wav.write_bytes(b'original')
            atomic_json(meta,{'key':'k','sha256':file_hash(wav)})
            wav.write_bytes(b'altered')
            self.assertFalse(valid_cache(wav,meta,'k'))

    def test_transcription_comparison_ignores_punctuation_not_omission(self):
        self.assertEqual(cer('你好，AI！','你好 ai'),0)
        self.assertGreater(cer('你好世界','你好'),.12)


if __name__=='__main__':unittest.main()
