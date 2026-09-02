#!/usr/bin/env python3
"""Read the book aloud, one paragraph per file, across every key at once.

    python3 make_audio.py

WHY PARAGRAPHS AND NOT CHAPTERS

The reader never learns the book is in pieces. Segmenting is invisible: the
player queues the next file while the current one plays, so it runs continuously
from the first line to the last. What segmenting buys is everything else. A
failed request costs one paragraph and not one chapter. A rewritten paragraph is
regenerated alone. Twenty one keys can work at once because there are two
hundred small jobs rather than thirteen big ones. And the first paragraph is
playable before the last one is made.

THE KEYS

Baba administers 21 Speechify accounts and said to use them in parallel. Each
worker takes the next paragraph and the next key in rotation. If a key fails,
the paragraph goes back in the queue and is tried on a DIFFERENT key, up to
three keys deep, so one dead account cannot lose a paragraph. Keys that fail
repeatedly are dropped from rotation for the rest of the run rather than being
tried two hundred times.

Nothing here is invented. The endpoint, the payload, the base64 field and the
2000 character cap come from MAHA_TRANSCRIBE_STREAMLIT/ttt/providers/speechify.py,
including the trap recorded there: simba-3.2 answers HTTP 400 for any voice whose
id does not end in _32, so the model belongs to the seat and is never hardcoded.
Beatrice on simba-3.2, per Baba.
"""
import os, re, json, base64, urllib.request, urllib.error, threading, queue, time

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, 'audio')
API = 'https://api.speechify.ai/v1/audio/speech'
VOICE = 'beatrice_32'
MODEL = 'simba-3.2'          # correct for a _32 seat, see the trap above
CAP = 2000                   # hard limit on `input`, from the provider
WORKERS = 5
TRIES = 5


def keys():
    src = '/mnt/user-data/uploads/speechify_api.txt'
    return [l.strip() for l in open(src) if re.fullmatch(r'sk[A-Za-z0-9_\-]{20,}', l.strip())]


def slug(t):
    return re.sub(r'[^a-z0-9]+', '-', t.lower()).strip('-')


def segments():
    """(chapter_id, index, text) for every paragraph, in reading order."""
    md = open(os.path.join(HERE, 'BOOK.md'), encoding='utf-8').read()
    segs, ch, buf = [], 'front-matter', []
    def flush():
        if buf:
            t = ' '.join(x.strip() for x in buf).strip()
            if t and not t.startswith('#'):
                segs.append([ch, t])
        buf.clear()
    for line in md.splitlines():
        if line.startswith('### ') or line.startswith('## '):
            flush()
            ch = slug(line.lstrip('#').strip())
            continue
        if line.strip() in ('', '---'):
            flush()
        else:
            buf.append(line)
    flush()
    # split anything over the cap on sentence boundaries
    out = []
    for c, t in segs:
        while len(t) > CAP:
            cut = t.rfind('. ', 0, CAP)
            cut = cut + 1 if cut > 400 else CAP
            out.append([c, t[:cut].strip()])
            t = t[cut:].strip()
        out.append([c, t])
    return [(c, i, t) for i, (c, t) in enumerate(out)]


def synth(key, text):
    body = json.dumps({'input': text, 'voice_id': VOICE,
                       'audio_format': 'mp3', 'model': MODEL}).encode()
    req = urllib.request.Request(API, data=body, method='POST', headers={
        'Authorization': 'Bearer ' + key, 'Content-Type': 'application/json',
        'Accept': 'application/json'})
    with urllib.request.urlopen(req, timeout=120) as r:
        d = json.load(r)
    audio = base64.b64decode(d['audio_data'])
    marks = d.get('speech_marks') or {}
    secs = _dur(marks)
    return audio, secs


def _dur(node, best=0.0):
    if isinstance(node, dict):
        e = node.get('end_time')
        if isinstance(e, (int, float)):
            best = max(best, e / 1000.0)
        for c in (node.get('chunks') or []):
            best = _dur(c, best)
    return best


KEYS = keys()
bad = set()
lock = threading.Lock()
done, failed = {}, []
q = queue.Queue()
segs = segments()
for s in segs:
    q.put((s, 0))
os.makedirs(OUT, exist_ok=True)


def worker(n):
    while True:
        try:
            (ch, i, text), attempt = q.get_nowait()
        except queue.Empty:
            return
        name = '%04d.mp3' % i
        path = os.path.join(OUT, name)
        if os.path.exists(path) and os.path.getsize(path) > 800:
            q.task_done(); continue
        with lock:
            live = [k for k in KEYS if k not in bad]
        if not live:
            failed.append((i, 'no keys left')); q.task_done(); continue
        key = live[(i + attempt * 7 + n) % len(live)]
        try:
            audio, secs = synth(key, text)
            open(path, 'wb').write(audio)
            with lock:
                done[i] = {'ch': ch, 'sec': round(secs, 2), 'bytes': len(audio),
                           'words': len(text.split())}
        except Exception as e:
            code = getattr(e, 'code', None)
            if code in (401, 403):
                with lock:
                    bad.add(key)
            if attempt + 1 < TRIES:
                q.put(((ch, i, text), attempt + 1))
            else:
                failed.append((i, '%s' % (code or e)))
            time.sleep(2.5 + attempt * 2.0)
        q.task_done()


print('%d paragraphs, %d keys, %d workers' % (len(segs), len(KEYS), WORKERS))
t0 = time.time()
ths = [threading.Thread(target=worker, args=(n,), daemon=True) for n in range(WORKERS)]
[t.start() for t in ths]
[t.join() for t in ths]

order = []
for ch, i, text in segs:
    d = done.get(i)
    if d:
        order.append({'f': '%04d.mp3' % i, 'ch': ch, 'sec': d['sec']})
json.dump({'segments': order,
           'total': round(sum(o['sec'] for o in order), 2)},
          open(os.path.join(OUT, 'durations.json'), 'w'), indent=1)

total = sum(o['sec'] for o in order)
print('made %d of %d paragraphs in %.0f s' % (len(order), len(segs), time.time() - t0))
print('runtime %d min %02d s' % (total // 60, total % 60))
print('keys dropped as dead: %d' % len(bad))
if failed:
    print('FAILED %d:' % len(failed))
    for i, why in failed[:10]:
        print('   paragraph %d: %s' % (i, why))
