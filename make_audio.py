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
import os, re, json, hashlib, subprocess, base64, urllib.request, urllib.error, threading, queue, time

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, 'audio')
API = 'https://api.speechify.ai/v1/audio/speech'
VOICE = 'beatrice_32'
MODEL = 'simba-3.2'          # correct for a _32 seat, see the trap above
CAP = 2000                   # hard limit on `input`, from the provider
WORKERS = 6
TRIES = 6


def keys():
    src = '/mnt/user-data/uploads/speechify_api.txt'
    return [l.strip() for l in open(src) if re.fullmatch(r'sk[A-Za-z0-9_\-]{20,}', l.strip())]


def _probe(path):
    """How long this file actually is, measured, in seconds."""
    out = subprocess.run(['ffprobe', '-v', 'error', '-show_entries',
                          'format=duration', '-of', 'csv=p=0', path],
                         capture_output=True, text=True).stdout.strip()
    try:
        return float(out)
    except ValueError:
        return 0.0


def key_of(text):
    """A paragraph's audio is named after ITS OWN TEXT, never its position.

    2.9.2026. Files used to be 0000.mp3, 0001.mp3 and so on. Then chapter nine
    gained two paragraphs, every index after it shifted, and 42 of 85 files were
    suddenly sitting under a number that meant different text. Nothing was wrong
    with the audio; the numbering had moved underneath it. So 42 paragraphs were
    re-voiced when about six had changed.

    With a content hash, inserting a paragraph renames nothing. Only text that
    actually changed has to be spoken again, which is what one file per paragraph
    was supposed to buy in the first place. Old files for edited paragraphs
    simply stop being referenced and can be swept.
    """
    return hashlib.sha256(text.encode()).hexdigest()[:16]


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
    marks = _flat(d.get('speech_marks') or {})
    secs = max((m[1] for m in marks), default=0.0)
    return audio, secs, marks


def _flat(node, out=None):
    """Speechify's exact word marks, flattened. Chunks nest, a sentence chunk
    holding word chunks, so this recurses. Kept as [start, end, char_start,
    char_end] in SECONDS and CHARACTER OFFSETS into the text we sent.

    The character offsets are the whole point and they are why the highlight
    is matched BY POSITION and never by text. word-timing.md §2: a passage says
    "the" twenty times, and looking the current word up by its letters lands on
    the first one every time. It reads exactly like a timing bug and no amount
    of timing tuning touches it."""
    if out is None:
        out = []
    if isinstance(node, dict):
        if node.get('type') == 'word':
            v = node.get('value') or ''
            st, en = node.get('start_time'), node.get('end_time')
            if any(c.isalnum() for c in v) and st is not None and en is not None:
                out.append([round(st / 1000.0, 3), round(en / 1000.0, 3),
                            int(node.get('start', 0)), int(node.get('end', 0))])
        for c in (node.get('chunks') or []):
            _flat(c, out)
    out.sort(key=lambda m: m[0])
    return out


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
        name = key_of(text) + '.mp3'
        path = os.path.join(OUT, name)
        # A paragraph is finished only when BOTH the audio and its marks exist.
        # The first version tested the mp3 alone, so a re-run skipped every
        # paragraph and produced no marks at all while reporting success.
        if os.path.exists(path) and os.path.getsize(path) > 800 \
                and os.path.exists(os.path.join(OUT, key_of(text) + '.json')):
            q.task_done(); continue
        with lock:
            live = [k for k in KEYS if k not in bad]
        if not live:
            failed.append((i, 'no keys left')); q.task_done(); continue
        key = live[(i + attempt * 7 + n) % len(live)]
        try:
            audio, secs, marks = synth(key, text)
            open(path, 'wb').write(audio)
            json.dump(marks, open(os.path.join(OUT, key_of(text) + '.json'), 'w'))
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

# THE MANIFEST IS BUILT FROM WHAT IS ON DISK, NEVER FROM WHAT THIS RUN MADE.
# 2.9.2026, twice in one day. A run that correctly makes nothing, because every
# paragraph is already voiced, used to rewrite durations.json with nothing in it.
# Nothing errors, every mp3 is present, and the page says the book is zero
# seconds long. So the manifest is written by walking the segments and asking the
# FILES how long they are.
order = []
for ch, i, text in segs:
    f = os.path.join(OUT, key_of(text) + '.mp3')
    if not os.path.exists(f):
        continue
    # and the DURATION comes from the file too, not from this run's results,
    # which are empty for anything that was already voiced. Asking the audio is
    # the only answer that is true whether or not this run made it.
    sec = done.get(i, {}).get('sec') or _probe(f)
    # the TEXT and the WORD MARKS belong in the manifest too. The page needs the
    # text to wrap each word and the marks to know when to light it, and both
    # come from disk for the same reason the duration does: they are true
    # whether or not this run made the file.
    mk = os.path.join(OUT, key_of(text) + '.json')
    marks = json.load(open(mk)) if os.path.exists(mk) else []
    order.append({'f': key_of(text) + '.mp3', 'ch': ch, 'sec': round(sec, 2),
                  'text': text, 'marks': marks})
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
