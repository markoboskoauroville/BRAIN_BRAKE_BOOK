#!/usr/bin/env python3
"""The second voice. The same book, read by an actress, and directed.

    python3 make_audio_hume.py

WHY THIS IS NOT THE SPEECHIFY SCRIPT WITH A DIFFERENT URL

Speechify is a voice. Hume is a performer. The `description` field is read as
prose and is not matched against a list, which means the right way to use it is
to say what you would say to an actor between takes. A book read at one setting
for fifteen minutes is a book nobody finishes, so every paragraph carries its
own direction: where it lifts, where it holds still, where it must not be
warm.

Nothing about the API is invented. Endpoint, header, body shape, the base64 WAV
in generations[0].audio and the User-Agent all come from Baba's spec and from
MAHA_TRANSCRIBE_STREAMLIT/ttt/providers/hume.py, including the two findings that
cost real bugs:

    THE USER-AGENT IS NOT OPTIONAL. api.hume.ai sits behind Cloudflare and
    answers 403 "error code: 1010" without one. Measured across 21 key pairs:
    all 21 refused without, all 21 accepted with.

    HUME IS PACED, NOT RETRIED. The limit is PER MINUTE and a 429 is ordinary.
    Baba measured 31 clips: 0.2s spacing gave 16 of 31, 3s spacing was still
    refused, 12s gave 31 of 31. So a key waits 12 seconds between its own calls
    and rests ONE minute on a 429, not two: Hume's window is a minute and
    parking it longer idles a working key for nothing.

403 is dead UNLESS it carries 1010, in which case it is the missing header and
the request is soft. 401 and 402 are dead. E0300 is credit exhausted and a free
account's grant does not reset, so that key is finished for good.
"""
import os, re, json, base64, urllib.request, urllib.error, threading, queue, time, subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, 'audio_hume')
API = 'https://api.hume.ai/v0/tts'
VOICE = '1fe215ab-513c-4fc8-9233-fa64b65073ab'
UA = 'BRAIN-BRAKE-BOOK/1.0 (+https://markoboskoauroville.github.io/BRAIN_BRAKE_BOOK/)'
PACE = 12.0           # seconds a key waits between its own calls
COOL = 60.0           # a 429 rests the key for one minute, not two


def accounts():
    lines = [l.strip() for l in open('/mnt/user-data/uploads/Hume.txt') if l.strip()]
    out, i = [], 0
    while i < len(lines):
        if lines[i] in ('API key', 'Secret key'):
            i += 1; continue
        name, api, j = lines[i], None, i + 1
        while j < len(lines):
            if lines[j] == 'API key' and j + 1 < len(lines):
                api = lines[j + 1]; j += 2
            elif lines[j] == 'Secret key' and j + 1 < len(lines):
                j += 2
            else:
                break
        if api and api != '[DELETED]':
            out.append((name, api))
        i = j if j > i else i + 1
    return out


# ---------------------------------------------------------------- direction
# One base note per chapter, because a chapter is a unit of feeling, and named
# overrides for the beats that turn. Written as prose to an actor, never as a
# tag list, because the field is read as prose.
CHAPTER = {
 'chapter-one-the-mystery':
   'Warm and curious storytelling, unhurried, as if leaning in to share something you have noticed and nobody else has.',
 'chapter-two-the-old-theory':
   'Clear documentary narration, even and unhurried, laying out a reasonable idea fairly before questioning it.',
 'chapter-three-the-full-tank':
   'Quiet and precise, the tone of stating a fact that turns out to matter more than it sounds.',
 'chapter-four-the-gatekeeper':
   'Teaching voice, calm and generous, explaining something protective rather than sinister.',
 'chapter-five-the-experiment':
   'Light and affectionate, amused by a boy testing the universe in a bathtub, never mocking him.',
 'chapter-six-the-release':
   'Held back and slightly hushed, the pace easing, the way you speak when the thing you are describing is about to happen.',
 'chapter-seven-what-happens-next-is-not-a-dream':
   'Grounded and reassuring, gently insisting on something the listener might not believe.',
 'chapter-eight-the-invitation':
   'Warm and direct, speaking to the listener about their own life, kind but not soft.',
 'chapter-nine-the-passage':
   'Wondering and immersive, a little breathless, carried along rather than describing from outside.',
 'chapter-ten-the-house':
   'Calm and reverent, quiet awe, the pace slow and even, nothing hurried.',
 'chapter-eleven-the-doors':
   'Patient storytelling with a growing undertone of expectation, each room a little more still than the last.',
 'chapter-twelve-the-key-door':
   'Hushed and certain, the pace slowing, arriving somewhere rather than travelling.',
 'the-last-page':
   'Tender and reverent, the voice of someone giving something away, warm and completely unhurried.',
}
OVERRIDE = {
 'Where was that?':
   'A single quiet question, curious and genuinely open, letting it hang.',
 'It also does not survive the dog.':
   'Dry and slightly amused, the tone of a gentle objection landing.',
 'The tank is not empty. It has never once been empty. It is not allowed to be empty.':
   'Firm and deliberate, each sentence a step, the last one landed and then left alone.',
 'That last sentence is the film.':
   'Quiet, matter of fact, almost an aside to the listener.',
 'But a margin is a decision. And a decision can be revised.':
   'Low and certain, the pivot of the whole book, unhurried and slightly hushed.',
 'Every experiment said the same thing in a different voice. The wall moves.':
   'Building through the sentence and then simple and clear on the last three words.',
 'It folded.':
   'Very quiet, two words, letting the silence after them do the work.',
 'Not one of them was gold.':
   'Still and quiet, unhurried, no emphasis, letting the sentence sit.',
 'That is the discovery. Everything after it is only arriving.':
   'Calm and conclusive, warm rather than triumphant.',
 'It was a key.':
   'Hushed and simple, three words, no emphasis needed.',
 'Then the music, and then nothing.':
   'Tender and very slow, letting the last word fall away into silence.',
}


def slug(t):
    return re.sub(r'[^a-z0-9]+', '-', t.lower()).strip('-')


def segments():
    md = open(os.path.join(HERE, 'BOOK.md'), encoding='utf-8').read()
    out, ch, buf = [], 'front-matter', []
    def flush():
        if buf:
            t = ' '.join(x.strip() for x in buf).strip()
            if t and not t.startswith('#'):
                out.append([ch, t])
        buf.clear()
    for line in md.splitlines():
        if line.startswith('### ') or line.startswith('## '):
            flush(); ch = slug(line.lstrip('#').strip()); continue
        if line.strip() in ('', '---'):
            flush()
        else:
            buf.append(line)
    flush()
    fin = []
    for c, t in out:
        while len(t) > 2000:
            cut = t.rfind('. ', 0, 2000); cut = cut + 1 if cut > 400 else 2000
            fin.append([c, t[:cut].strip()]); t = t[cut:].strip()
        fin.append([c, t])
    return [(c, i, t) for i, (c, t) in enumerate(fin)]


def direct(ch, text):
    return OVERRIDE.get(text.strip(),
                        CHAPTER.get(ch, 'Clear, warm narration, unhurried.'))


ACC = accounts()
ready = {a: 0.0 for _, a in ACC}     # earliest time each key may be used again
dead = set()
lock = threading.Lock()
done, failed = {}, []
segs = segments()
q = queue.Queue()
for s in segs:
    q.put((s, 0))
os.makedirs(OUT, exist_ok=True)


def take_key():
    """The next key that is allowed to speak, or how long to wait for one."""
    while True:
        with lock:
            now = time.time()
            live = [(t, k) for k, t in ready.items() if k not in dead]
            if not live:
                return None, 0
            live.sort()
            t, k = live[0]
            if t <= now:
                ready[k] = now + PACE
                return k, 0
            return None, t - now


def synth(key, text, description):
    body = json.dumps({
        'utterances': [{'text': text, 'voice': {'id': VOICE},
                        'description': description}],
        'format': {'type': 'wav'}, 'num_generations': 1}).encode()
    req = urllib.request.Request(API, data=body, method='POST', headers={
        'X-Hume-Api-Key': key, 'Content-Type': 'application/json',
        'Accept': 'application/json', 'User-Agent': UA})
    with urllib.request.urlopen(req, timeout=180) as r:
        d = json.load(r)
    return base64.b64decode(d['generations'][0]['audio'])


def worker(n):
    while True:
        try:
            (ch, i, text), attempt = q.get_nowait()
        except queue.Empty:
            return
        mp3 = os.path.join(OUT, '%04d.mp3' % i)
        if os.path.exists(mp3) and os.path.getsize(mp3) > 800:
            q.task_done(); continue
        key, wait = take_key()
        if key is None:
            if wait:
                time.sleep(min(wait, 5))
                q.put(((ch, i, text), attempt))
            else:
                failed.append((i, 'no keys left'))
            q.task_done(); continue
        try:
            wav = synth(key, text, direct(ch, text))
            tmp = os.path.join(OUT, '%04d.wav' % i)
            open(tmp, 'wb').write(wav)
            # WAV at fifteen minutes is well over a hundred megabytes and this
            # repository publishes a Pages site. Converted here, and the wav
            # removed, so nothing large ever reaches a commit.
            subprocess.run(['ffmpeg', '-y', '-v', 'error', '-i', tmp,
                            '-codec:a', 'libmp3lame', '-b:a', '64k', mp3], check=True)
            os.remove(tmp)
            with lock:
                done[i] = True
        except urllib.error.HTTPError as e:
            body = ''
            try:
                body = e.read().decode()[:200]
            except Exception:
                pass
            with lock:
                if e.code in (401, 402):
                    dead.add(key)
                elif e.code == 403 and '1010' not in body:
                    dead.add(key)
                elif e.code == 400 and 'E0300' in body:
                    dead.add(key)          # credit granted once, never resets
                elif e.code == 429:
                    ready[key] = time.time() + COOL
            if attempt < 8:
                q.put(((ch, i, text), attempt + 1))
            else:
                failed.append((i, '%s %s' % (e.code, body[:60])))
        except Exception as e:
            if attempt < 8:
                q.put(((ch, i, text), attempt + 1))
            else:
                failed.append((i, str(e)[:60]))
        q.task_done()


print('%d paragraphs, %d Hume accounts with a live key' % (len(segs), len(ACC)))
t0 = time.time()
ths = [threading.Thread(target=worker, args=(n,), daemon=True) for n in range(len(ACC))]
[t.start() for t in ths]
[t.join() for t in ths]
print('made %d of %d in %.0f s' % (len(done), len(segs), time.time() - t0))
print('keys dropped: %d' % len(dead))
if failed:
    print('FAILED %d:' % len(failed))
    for i, why in failed[:12]:
        print('   %d: %s' % (i, why))
