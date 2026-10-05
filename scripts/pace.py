"""Locate Chinese speech-rate changes for listening; never grade perceived quality."""
import math
import re
import statistics


def screen(items, offset=0):
    # Treat Chinese syllables as comparable units; skip Latin-heavy/uncertain spans.
    windows=[]
    for i in range(0, max(0,len(items)-19), 10):
        span=items[i:i+20]
        text=''.join(x['text'] for x in span)
        count=len(re.findall(r'[\u4e00-\u9fff]',text))
        duration=span[-1]['end']-span[0]['start']
        if count!=len(text) or count<20 or not math.isfinite(duration) or duration<=0:
            continue
        # Long pauses belong to phrasing, not syllable-rate instability.
        if any(b['start']-a['end']>.7 for a,b in zip(span,span[1:])):
            continue
        windows.append({'start':offset+span[0]['start'],'end':offset+span[-1]['end'],
                        'characters_per_second':count/duration,'text':text})
    if len(windows)<3:
        return []
    typical=statistics.median(x['characters_per_second'] for x in windows)
    flagged=[]
    for window in windows:
        if window['characters_per_second']>max(6,typical*1.35):
            if flagged and window['start']<flagged[-1]['end']:
                continue
            flagged.append({**window,'relative_rate':window['characters_per_second']/typical,
                            'review':'audition_required'})
    return flagged
