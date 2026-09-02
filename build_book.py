#!/usr/bin/env python3
"""Assemble BOOK.md into the one page web book.

    python3 build_book.py

Writes index.html. One file, no framework, no build step needed to READ it, per
MANTRA_MANIFEST/modules/illustrated-book.md. The build only assembles.

Two things this book has that the other nine do not.

    IT REMEMBERS WHERE YOU WERE. Scroll position and the last chapter you
    reached are kept in localStorage and restored on return, because a book of
    this length is read in more than one sitting and losing your place is the
    fastest way to not finish something.

    IT READS ITSELF ALOUD. The audiobook sits in audio/, one file per chapter,
    and the player shows elapsed and remaining time for the chapter and for the
    whole book. Baba is dyslexic and listens more than he reads; the audio is
    not a garnish on this book, it is how it will mostly be consumed.
"""
import os, re, json, html

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, 'BOOK.md')
OUT = os.path.join(HERE, 'index.html')


def chapters(md):
    """Split on ## and ### into parts and chapters, in order."""
    out, cur = [], None
    for line in md.splitlines():
        if line.startswith('## PART') or line.startswith('## THE LAST PAGE'):
            if cur:
                out.append(cur)
            cur = {'kind': 'part', 'title': line[3:].strip(), 'body': []}
            out.append(cur)
            cur = None
            continue
        if line.startswith('### '):
            if cur:
                out.append(cur)
            cur = {'kind': 'chapter', 'title': line[4:].strip(), 'body': []}
            continue
        if cur is not None:
            cur['body'].append(line)
    if cur:
        out.append(cur)
    return out


def para(lines):
    blocks, buf = [], []
    for l in lines:
        if l.strip() == '---':
            continue
        if not l.strip():
            if buf:
                blocks.append(' '.join(buf))
                buf = []
        else:
            buf.append(l.strip())
    if buf:
        blocks.append(' '.join(buf))
    return blocks


def slug(t):
    return re.sub(r'[^a-z0-9]+', '-', t.lower()).strip('-')


md = open(SRC, encoding='utf-8').read()
title = 'THE BRAIN BRAKE'
subtitle = 'The book the film was made from'
secs = chapters(md)

# PLATES. Sparse on purpose: Baba, 2.9.2026, "be very sparse with image, here
# and there some image, but not much." One at the top, one at the passage, one
# at the door, one at the end. Four in three thousand words. The book is read,
# not looked at.
PLATES = {
    'chapter-nine-the-passage': (
        'https://raw.githubusercontent.com/markoboskoauroville/BRAIN_BRAKE_ORIGINALS/main/BB_C_9/9-1-GANESHA-v1.png',
        'A form arriving out of bare paper, which is how everything in this story arrives.'),
    'chapter-eleven-the-doors': (
        'https://raw.githubusercontent.com/markoboskoauroville/BRAIN_BRAKE_ORIGINALS/main/BB_C_8/8-0-A-v4.png',
        'A corridor of doors, before the names came off them.'),
    'chapter-twelve-the-key-door': (
        'https://raw.githubusercontent.com/markoboskoauroville/BRAIN_BRAKE_ORIGINALS/main/BB_C_19/19-0-A-v1.png',
        'A small brain at a wall of dials, on shift, and not expecting visitors.'),
}
HERO = ('https://raw.githubusercontent.com/markoboskoauroville/BRAIN_BRAKE_ORIGINALS/main/BB_C_16/16-0-A-v1.png',
        'The house he wakes up inside.')

body, toc, chlist = [], [], []
for s in secs:
    if s['kind'] == 'part':
        sid = slug(s['title'])
        body.append('<h2 class=part id="%s">%s</h2>' % (sid, html.escape(s['title'])))
        toc.append('<div class=tocpart>%s</div>' % html.escape(s['title']))
        continue
    sid = slug(s['title'])
    chlist.append({'id': sid, 'title': s['title']})
    body.append('<section class=chapter id="%s" data-ch="%s">' % (sid, sid))
    body.append('<h3 class="ch-head">%s</h3>' % html.escape(s['title']))
    if sid in PLATES:
        u, cap = PLATES[sid]
        body.append('<figure class=plate><img loading=lazy src="%s" alt="">'
                    '<figcaption>%s</figcaption></figure>' % (u, html.escape(cap)))
    for b in para(s['body']):
        body.append('<p>%s</p>' % html.escape(b))
    body.append('</section>')
    toc.append('<a href="#%s">%s</a>' % (sid, html.escape(s['title'])))

words = len(md.split())
mins = round(words / 200.0)

page = """<!doctype html><html lang=en><head>
<meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1">
<title>%(title)s — %(subtitle)s</title>
<link rel=preconnect href="https://fonts.googleapis.com">
<link rel=preconnect href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,600;9..144,800&family=Newsreader:ital,wght@0,300;0,400;1,400&family=IBM+Plex+Mono:wght@400;600&display=swap" rel=stylesheet>
<style>
:root{--bg:#16110D;--ink:#E9DFD1;--dim:#9C9084;--gold:#E8A64B;--rule:#2E2620;--panel:#1E1813}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);
  font:300 19px/1.75 Newsreader,Georgia,serif;-webkit-text-size-adjust:100%%}
.wrap{max-width:660px;margin:0 auto;padding:0 22px 120px}
.masthead{padding:64px 0 26px;text-align:center}
.eyebrow{font:600 10.5px/1 "IBM Plex Mono",monospace;letter-spacing:.30em;color:var(--gold);
  text-transform:uppercase}
h1{font:800 clamp(34px,9vw,58px)/1.02 Fraunces,serif;margin:16px 0 10px;letter-spacing:-.02em}
.dek{color:var(--dim);font-style:italic;margin:0}
.byline{font:600 10.5px/1.6 "IBM Plex Mono",monospace;letter-spacing:.16em;color:var(--dim);
  margin-top:20px;text-transform:uppercase}
.rule{height:1px;background:var(--rule);margin:34px 0}
.contents{background:var(--panel);border:1px solid var(--rule);border-radius:12px;padding:20px 22px}
.contents a{display:block;color:var(--ink);text-decoration:none;padding:5px 0;font-size:16.5px}
.contents a:hover{color:var(--gold)}
.tocpart{font:600 10.5px/1 "IBM Plex Mono",monospace;letter-spacing:.2em;color:var(--gold);
  text-transform:uppercase;margin:16px 0 8px}
.tocpart:first-child{margin-top:0}
h2.part{font:600 11px/1 "IBM Plex Mono",monospace;letter-spacing:.26em;color:var(--gold);
  text-transform:uppercase;margin:76px 0 0;text-align:center}
.chapter{margin:44px 0 0;scroll-margin-top:78px}
.ch-head{font:600 clamp(23px,5.4vw,30px)/1.2 Fraunces,serif;margin:0 0 18px;letter-spacing:-.01em}
p{margin:0 0 20px}
.plate{margin:0 0 24px}
.plate img{width:100%%;display:block;border-radius:10px;border:1px solid var(--rule);
  filter:saturate(.85) brightness(.94)}
.plate figcaption{color:var(--dim);font-size:14px;font-style:italic;margin-top:9px;text-align:center}
.colophon{color:var(--dim);font-size:15px;margin-top:70px;border-top:1px solid var(--rule);
  padding-top:26px}
/* the player */
.player{position:fixed;left:0;right:0;bottom:0;background:rgba(22,17,13,.96);
  border-top:1px solid var(--rule);backdrop-filter:blur(10px);z-index:9;
  padding:9px 14px calc(9px + env(safe-area-inset-bottom))}
.pin{max-width:660px;margin:0 auto;display:flex;align-items:center;gap:12px}
.pb{background:var(--gold);color:#16110D;border:0;border-radius:999px;width:42px;height:42px;
  font-size:17px;cursor:pointer;flex:none}
.pmeta{flex:1;min-width:0}
.pt{font:600 11px/1.35 "IBM Plex Mono",monospace;letter-spacing:.08em;color:var(--ink);
  white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.ptime{font:400 10.5px/1.5 "IBM Plex Mono",monospace;color:var(--dim)}
.bar{height:4px;background:var(--rule);border-radius:3px;margin-top:5px;cursor:pointer}
.bar i{display:block;height:100%%;width:0;background:var(--gold);border-radius:3px}
.resume{position:fixed;left:50%%;transform:translateX(-50%%);bottom:80px;background:var(--panel);
  border:1px solid var(--gold);color:var(--ink);border-radius:999px;padding:9px 18px;font-size:14px;
  cursor:pointer;z-index:10;display:none}
</style></head><body>
<div class=wrap>
<header class=masthead>
  <div class=eyebrow>Breakthrough Junior Challenge 2026</div>
  <h1>%(title)s</h1>
  <p class=dek>%(subtitle)s</p>
  <div class=byline>%(words)s words &nbsp;·&nbsp; about %(mins)s minutes</div>
</header>
<figure class=plate><img src="%(hero)s" alt=""><figcaption>%(herocap)s</figcaption></figure>
<div class=rule></div>
<nav class=contents>%(toc)s</nav>
%(body)s
<div class=colophon>
  <p>Written by Marko Boško for THE BRAIN BRAKE, a two minute film for the Breakthrough Junior
  Challenge 2026, presented by Manan Periwal, animated by Kristijan Kaurić, produced by Neha
  Sonthalia Periwal, photographed by Aurovenkatesh.</p>
  <p>The film had to say this in two minutes. The book did not.</p>
  <p>Dedicated to Ganesha, remover of obstacles.</p>
</div>
</div>

<button class=resume id=resume>Continue where you left off</button>

<div class=player id=player>
  <div class=pin>
    <button class=pb id=pb>&#9654;</button>
    <div class=pmeta>
      <div class=pt id=pt>Audiobook</div>
      <div class=ptime><span id=el>0:00</span> &nbsp;·&nbsp; <span id=rem>-0:00</span> left
        &nbsp;·&nbsp; <span id=tot>0:00</span> total</div>
      <div class=bar id=bar><i id=fill></i></div>
    </div>
  </div>
</div>

<script>
const CH = %(chjson)s;
const KEY = 'brainbrake.book.v1';

/* ---- remember the place -------------------------------------------------
   A book read on a bus is read in pieces. Scroll position alone is fragile,
   because the page reflows on a different screen, so the chapter is stored
   too and used as the anchor when the pixel offset no longer means anything. */
function save(){
  let seen = CH[0].id;
  for (const c of CH){
    const el = document.getElementById(c.id);
    if (el && el.getBoundingClientRect().top < window.innerHeight*0.5) seen = c.id;
  }
  localStorage.setItem(KEY, JSON.stringify({y:window.scrollY, ch:seen,
    seg:(SEG.i||0), at:Date.now()}));
}
let t=null;
addEventListener('scroll', ()=>{ clearTimeout(t); t=setTimeout(save,300); }, {passive:true});

const saved = JSON.parse(localStorage.getItem(KEY)||'null');
const resume = document.getElementById('resume');
if (saved && saved.y > 600){
  resume.style.display='block';
  resume.onclick = ()=>{
    const el = document.getElementById(saved.ch);
    if (el) el.scrollIntoView({behavior:'smooth'});
    else window.scrollTo({top:saved.y, behavior:'smooth'});
    resume.style.display='none';
  };
  setTimeout(()=>{ resume.style.display='none'; }, 12000);
}

/* ---- the audiobook ------------------------------------------------------
   The book is cut into paragraphs, one file each, and THE READER NEVER FINDS
   THIS OUT. Two elements alternate: while one plays, the next is already
   loaded on the other, so the join is a swap and not a fetch. All timing is
   reported against the WHOLE BOOK, because the paragraph a listener happens
   to be inside is not a fact about their afternoon; the twelve minutes left
   is. Segmenting buys a lot and it should cost nothing. */
const SEG = {list:[], i:0, before:[], total:0, playing:false};
const A = [new Audio(), new Audio()];
A.forEach(a=>{ a.preload='auto'; });
let cur = 0;

const pb=document.getElementById('pb'), pt=document.getElementById('pt');
const el=document.getElementById('el'), rem=document.getElementById('rem');
const tot=document.getElementById('tot'), fill=document.getElementById('fill');
const bar=document.getElementById('bar');

const mmss = s => Math.floor(Math.abs(s)/60) + ':' +
  String(Math.floor(Math.abs(s)%%60)).padStart(2,'0');

function chapterOf(i){
  const id = SEG.list[i] ? SEG.list[i].ch : '';
  const c = CH.find(x=>x.id===id);
  return c ? c.title : 'Audiobook';
}
function elapsed(){
  const a = A[cur];
  return (SEG.before[SEG.i]||0) + (a.currentTime||0);
}
function tick(){
  const e = elapsed(), T = SEG.total;
  el.textContent = mmss(e);
  rem.textContent = '-' + mmss(Math.max(0, T - e));
  tot.textContent = mmss(T);
  fill.style.width = T ? (100*e/T)+'%%' : '0%%';
  pt.textContent = chapterOf(SEG.i);
}
function src(i){ return 'audio/' + SEG.list[i].f; }
function prime(){
  const n = SEG.i + 1;
  if (n < SEG.list.length) A[1-cur].src = src(n);   /* fetched during playback */
}
function go(i, play){
  if (i >= SEG.list.length){ SEG.playing=false; pb.innerHTML='&#9654;'; return; }
  SEG.i = i;
  const a = A[cur];
  if (!a.src.endsWith(SEG.list[i].f)) a.src = src(i);
  if (play) a.play().catch(()=>{});
  prime(); tick(); save();
}
A.forEach(a=>{
  a.addEventListener('timeupdate', ()=>{ if (a===A[cur]) tick(); });
  a.addEventListener('ended', ()=>{
    if (a!==A[cur]) return;
    cur = 1-cur;                       /* the next file is already loaded */
    go(SEG.i+1, SEG.playing);
  });
});
pb.onclick = ()=>{
  if (!SEG.list.length) return;
  if (A[cur].paused){ SEG.playing=true; A[cur].play().catch(()=>{});
                      pb.innerHTML='&#10073;&#10073;'; }
  else { SEG.playing=false; A[cur].pause(); pb.innerHTML='&#9654;'; }
};
/* the bar is the WHOLE BOOK, so a drag lands in the right paragraph and the
   right offset inside it. The listener is scrubbing a book, not a file. */
bar.onclick = e=>{
  if (!SEG.total) return;
  const r = bar.getBoundingClientRect();
  const want = SEG.total * ((e.clientX - r.left) / r.width);
  let i = 0;
  while (i+1 < SEG.list.length && SEG.before[i+1] <= want) i++;
  A[cur].src = src(i); SEG.i = i;
  A[cur].currentTime = Math.max(0, want - SEG.before[i]);
  if (SEG.playing) A[cur].play().catch(()=>{});
  prime(); tick();
};

fetch('audio/durations.json').then(r=>r.json()).then(d=>{
  SEG.list = d.segments; SEG.total = d.total;
  let run = 0;
  SEG.before = SEG.list.map(s=>{ const b = run; run += s.sec; return b; });
  const start = (saved && saved.seg && saved.seg < SEG.list.length) ? saved.seg : 0;
  go(start, false);
}).catch(()=>{ pt.textContent = 'Audiobook not available'; });
</script>
</body></html>""" % {
    'title': title, 'subtitle': subtitle,
    'toc': ''.join(toc), 'body': '\n'.join(body),
    'words': '{:,}'.format(words), 'mins': mins,
    'hero': HERO[0], 'herocap': html.escape(HERO[1]),
    'chjson': json.dumps(chlist),
}

open(OUT, 'w', encoding='utf-8').write(page)
print('index.html written')
print('  %d words, %d chapters, %d plates' % (words, len(chlist), len(PLATES) + 1))
print('  audio expected at audio/<chapter-id>.mp3 plus audio/durations.json')
