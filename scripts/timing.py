"""Pure timing, caption and cache helpers (no model dependencies)."""
import hashlib
import json
import math
import re
from pathlib import Path

VERSION = 1


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def file_hash(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for data in iter(lambda: f.read(1024 * 1024), b''):
            h.update(data)
    return h.hexdigest()


def atomic_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + '.tmp')
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf8')
    tmp.replace(path)


def clean(text):
    return ''.join(c.lower() for c in text if c.isalnum())


def cer(reference, hypothesis):
    a, b = clean(reference), clean(hypothesis)
    row = list(range(len(b) + 1))
    for i, x in enumerate(a, 1):
        nxt = [i]
        for j, y in enumerate(b, 1):
            nxt.append(min(nxt[-1] + 1, row[j] + 1, row[j-1] + (x != y)))
        row = nxt
    return row[-1] / max(1, len(a))


def validate_job(job):
    if job.get('schema_version') != VERSION:
        raise ValueError('project.json requires schema_version: 1')
    if not job.get('blocks'):
        raise ValueError('At least one narration block is required')
    seen = set()
    for block in job['blocks']:
        bid = block.get('id', '')
        if not re.fullmatch(r'[a-z0-9_-]+', bid) or bid in seen:
            raise ValueError('Block IDs must be unique safe identifiers: ' + bid)
        seen.add(bid)
        if not block.get('text', '').strip():
            raise ValueError('Empty narration: ' + bid)
        names = set()
        for beat in block.get('beats', []):
            if beat['id'] in names:
                raise ValueError('Duplicate beat in ' + bid)
            names.add(beat['id'])
            phrase = clean(beat['phrase'])
            if not phrase or phrase not in clean(block['text']):
                raise ValueError(f'Anchor phrase missing in {bid}: {beat["phrase"]}')
    fps = job.get('video', {}).get('fps', 30)
    if not isinstance(fps, int) or fps < 1 or 24000 % fps:
        raise ValueError('fps must divide the native 24000 Hz sample rate')
    if job.get('render_mode','per_block') not in ['per_block','continuous']:
        raise ValueError('render_mode must be per_block or continuous')
    if 'narration_groups' in job:
        groups=job['narration_groups']
        group_ids=[g.get('id','') for g in groups]
        if len(set(group_ids))!=len(group_ids) or any(not re.fullmatch(r'[a-z0-9_-]+',gid) for gid in group_ids):
            raise ValueError('Narration group IDs must be unique safe identifiers')
        if any(not g.get('blocks') for g in groups) or [bid for g in groups for bid in g['blocks']] != [b['id'] for b in job['blocks']]:
            raise ValueError('narration_groups must cover every block once, in order')


def aligned_chars(items, reference, duration):
    chars, spans = [], []
    previous = 0.0
    for item in items:
        word = clean(item['text'])
        if not word:
            continue
        start, end = float(item['start']), float(item['end'])
        if not math.isfinite(start + end) or start < -0.05 or end > duration + .15 or end < start:
            raise ValueError('Invalid alignment timestamp')
        if start < previous - .16:
            raise ValueError('Non-monotonic alignment')
        start = max(previous, start)
        end = max(start, end)
        for i, c in enumerate(word):
            chars.append(c)
            spans.append((start + (end-start)*i/len(word), start + (end-start)*(i+1)/len(word)))
        previous = end
    if ''.join(chars) != clean(reference):
        raise ValueError('Aligner text does not exactly cover narration; inspect before timing')
    return ''.join(chars), spans


def make_block_timing(block, items, duration, offset, fps):
    text, spans = aligned_chars(items, block['text'], duration)
    beats = {}
    last = -1
    for beat in block.get('beats', []):
        phrase = clean(beat['phrase'])
        at, occurrence = -1, beat.get('occurrence', 1)
        for _ in range(occurrence):
            at = text.find(phrase, at + 1)
            if at < 0:
                raise ValueError('Anchor occurrence not found: ' + beat['id'])
        t = spans[at][0]
        if t < last:
            raise ValueError('Beats must follow narration order')
        last = t
        frame = round(t * fps)
        beats[beat['id']] = {'phrase': beat['phrase'], 'speech_time': t,
                             'time': frame / fps, 'global_time': offset + frame / fps}
    # Preserve authored punctuation while bounding subtitle lines.
    chunks = []
    for phrase in re.findall(r'[^，。！？；：、,!?;:\n]+[，。！？；：、,!?;:]?', block['text']):
        phrase = phrase.strip()
        while len(phrase) > 23:
            chunks.append(phrase[:22])
            phrase = phrase[22:]
        if phrase:
            chunks.append(phrase)
    captions, cursor = [], 0
    for phrase in chunks:
        count = len(clean(phrase))
        if not count:
            continue
        start = spans[cursor][0]
        end = spans[cursor + count - 1][1]
        captions.append({'text': phrase, 'start': offset + start,
                         'end': offset + max(start+.08, end)})
        cursor += count
    return {'id': block['id'], 'offset': offset, 'duration': duration,
            'beats': beats, 'captions': captions}


def srt_timestamp(seconds):
    total = round(seconds * 1000)
    h, remainder = divmod(total, 3600000)
    m, remainder = divmod(remainder, 60000)
    s, ms = divmod(remainder, 1000)
    return f'{h:02}:{m:02}:{s:02},{ms:03}'


def write_srt(path, captions):
    parts = []
    for i, cap in enumerate(captions, 1):
        parts.append(f'{i}\n{srt_timestamp(cap["start"])} --> {srt_timestamp(cap["end"])}\n{cap["text"]}\n')
    Path(path).write_text('\n'.join(parts), encoding='utf8')
