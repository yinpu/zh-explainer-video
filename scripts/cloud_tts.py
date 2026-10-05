"""Doubao LiuFei TTS. Network failures never switch voices or retry billing."""
import base64
import http.client
import json
import sys
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path
from timing import atomic_json, file_hash
from voice import normalize_voice, cloud_model, credential


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None  # Credentials only go to the configured official endpoint.


def request_spec(voice, text, key):
    voice = normalize_voice(voice)
    params = {'text':text, 'speaker':voice['speaker'],
              'audio_params':{'format':'pcm','sample_rate':24000,'speech_rate':-5}}
    additions = {}
    if voice.get('instruct'):
        additions['context_texts'] = [voice['instruct']]
    if 'pronunciation_dict' in voice:
        additions['pronunciation_dict'] = voice['pronunciation_dict']
    if additions:
        params['additions'] = json.dumps(additions, ensure_ascii=False)
    headers = {'Content-Type':'application/json', 'X-Api-Key':key,
               'X-Api-Resource-Id':voice['model'], 'X-Api-Request-Id':str(uuid.uuid4())}
    return cloud_model(voice)['endpoint'], headers, {'req_params':params}


def safe_code(code):
    return str(code) if type(code) is int else 'unknown'


def decode_doubao(response):
    chunks = []
    # The HTTP endpoint returns newline-delimited JSON over chunked transport.
    for line in response:
        if not line.strip():
            continue
        item = json.loads(line)
        code = item.get('code')
        if code not in (0, 20000000):
            raise RuntimeError('Doubao synthesis failed (provider status code ' + safe_code(code) + ')')
        if item.get('data'):
            chunks.append(base64.b64decode(item['data'], validate=True))
        if code == 20000000:
            break
    if not chunks:
        raise RuntimeError('Doubao returned empty audio')
    data = b''.join(chunks)
    if len(data) % 2:
        raise RuntimeError('Doubao returned incomplete PCM samples')
    return data


def synthesize(voice, text):
    voice = normalize_voice(voice)
    key = credential()
    if not isinstance(text,str) or not text.strip():
        raise ValueError('Empty narration')
    url, headers, body = request_spec(voice, text, key)
    request = urllib.request.Request(url, data=json.dumps(body,ensure_ascii=False).encode(),headers=headers,method='POST')
    try:
        with urllib.request.build_opener(NoRedirect).open(request, timeout=180) as response:
            return decode_doubao(response)
    except urllib.error.HTTPError as exc:
        raise RuntimeError(voice['provider'] + ' HTTP ' + str(exc.code) + '; check account, credentials and quota') from None
    except (urllib.error.URLError, TimeoutError, OSError, http.client.HTTPException):
        raise RuntimeError(voice['provider'] + ' connection failed; no automatic retry or provider fallback') from None
    except (ValueError, KeyError, TypeError, AttributeError):
        raise RuntimeError(voice['provider'] + ' returned an invalid audio response') from None


def save_audio(data, task, voice, elapsed):
    import numpy as np
    import soundfile as sf
    audio = np.frombuffer(data,dtype='<i2').astype(np.float32)/32768
    sr = 24000
    if sr != 24000 or audio.ndim != 1 or len(audio) < 2400 or not np.isfinite(audio).all():
        raise RuntimeError('Expected finite mono 24000 Hz audio of at least 0.1 seconds')
    if np.max(np.abs(audio)) < .001:
        raise RuntimeError('Provider returned silence')
    out = Path(task['output']); out.parent.mkdir(parents=True, exist_ok=True)
    temp = out.with_suffix('.tmp.wav')
    sf.write(temp,audio,sr,subtype='PCM_24'); temp.replace(out)
    pitches = []
    for i in range(0,len(audio)-1440,2400):
        frame = audio[i:i+1440].astype(float)
        if np.sqrt(np.mean(frame*frame)) < .012:
            continue
        frame = (frame-frame.mean())*np.hanning(len(frame))
        corr = np.fft.irfft(np.abs(np.fft.rfft(frame,n=4096))**2)[:1440]
        peak = 48 + np.argmax(corr[48:240])
        if corr[peak] > .55*max(corr[0],1e-10):
            pitches.append(sr/peak)
    metadata = {'key':task['key'],'sample_rate':sr,'samples':len(audio),'duration':len(audio)/sr,
                'elapsed_seconds':elapsed,'provider':voice['provider'],'model':voice['model'],
                'speaker':voice['speaker'],
                'rms_db':20*np.log10(max(float(np.sqrt(np.mean(audio*audio))),1e-9)),
                'peak':float(np.max(np.abs(audio))), 'clipped_fraction':float(np.mean(np.abs(audio)>=.999)),
                'median_f0_hz':float(np.median(pitches)) if pitches else None,'sha256':file_hash(out)}
    atomic_json(out.with_suffix('.json'),metadata)


def tts(request):
    voice = normalize_voice(request['voice'])
    credential()  # Check before any output files or API calls.
    for task in request['tasks']:
        print('TTS ' + task['id'], flush=True)
        start = time.monotonic()
        data = synthesize(voice,task['text'])
        save_audio(data,task,voice,time.monotonic()-start)


if __name__ == '__main__':
    try:
        tts(json.loads(Path(sys.argv[-1]).read_text()))
    except Exception as exc:
        print('ERROR: ' + str(exc), file=sys.stderr)
        sys.exit(1)
