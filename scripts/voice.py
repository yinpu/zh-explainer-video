"""Fixed LiuFei narration profile; credentials stay in the process environment."""
import os

FIXED_VOICE = {'provider':'doubao', 'model':'seed-tts-2.0',
               'speaker':'zh_male_liufei_uranus_bigtts', 'speed':0.95}
DEFAULT_VOICE = {**FIXED_VOICE,
                 'instruct':'请用自然清晰的普通话讲解技术原理，语速平稳适中，句中不要突然加速。因果和对比有自然重音，推导之间留出理解的停顿，不用播音腔或夸张情绪。'}
KEY_ENV = 'DOUBAO_API_KEY'
DOUBAO_ENDPOINT = 'https://openspeech.bytedance.com/api/v3/tts/unidirectional'


def normalize_voice(value=None):
    value = {} if value is None else value
    if not isinstance(value, dict):
        raise ValueError('voice must be an object')
    allowed = set(DEFAULT_VOICE) | {'pronunciation_dict'}
    if set(value) - allowed:
        raise ValueError('Unsupported voice field; use documented settings and environment credentials')
    for field, fixed in FIXED_VOICE.items():
        if field in value and (type(value[field]) is bool or value[field] != fixed):
            raise ValueError('Voice is fixed to Doubao LiuFei 2.0 at speed 0.95; remove conflicting voice settings')
    voice = {**DEFAULT_VOICE, **value}
    if not isinstance(voice['instruct'], str):
        raise ValueError('voice.instruct must be text')
    if 'pronunciation_dict' in voice:
        dictionary = voice['pronunciation_dict']
        if (not isinstance(dictionary,dict) or set(dictionary) != {'tone'} or
            not isinstance(dictionary['tone'],list) or
            any(not isinstance(x,str) or '/' not in x for x in dictionary['tone'])):
            raise ValueError('pronunciation_dict requires a tone list of original/pronunciation strings')
    return voice


def cloud_model(voice):
    voice = normalize_voice(voice)
    return {'provider':voice['provider'], 'path':voice['model'],
            'revision':voice['provider'] + ':' + voice['model'],
            'endpoint':DOUBAO_ENDPOINT,
            'revision_note':'Provider model ID; cloud weights may change. Cached waveform is authoritative.'}


def credential():
    key = os.environ.get(KEY_ENV, '').strip()
    if not key:
        raise RuntimeError('Missing ' + KEY_ENV + '; configure it locally before synthesis')
    return key
