#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Builds the PHAEMA e-learning into static/training/index.html, served by PHAEMA at /static/training/index.html.

    python3 training/build.py

Content is in course.py. Step screenshots are in static/training/img/, named <module>-<step>.jpg, and the
highlight boxes (fractions of the screen) are in boxes.json. Re-capture them after changing a screen."""
import json
import sys
from pathlib import Path

import course

HERE = Path(__file__).parent
boxes = json.loads((HERE / "boxes.json").read_text())


def data():
    out = []
    for c in course.COURSES:
        mods = []
        for m in c["modules"]:
            steps = [{"img": f"img/{m['id']}-{i + 1}.jpg", "box": boxes.get(f"{m['id']}-{i + 1}"), "title": t, "text": x}
                     for i, (_u, _url, _sel, t, x) in enumerate(m["steps"])]
            mods.append({"id": m["id"], "title": m["title"], "minutes": m["minutes"], "intro": m["intro"],
                         "steps": steps, "exercise": m["exercise"], "quiz": m["quiz"]})
        out.append({"id": c["id"], "title": c["title"], "who": c["who"], "modules": mods})
    return out


HEAD = r'''<title>PHAEMA Training</title>
<meta name="claude:viewport-fit-sides" content="cover">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Atkinson+Hyperlegible:ital,wght@0,400;0,700;1,400&family=Bricolage+Grotesque:opsz,wght@12..96,600;12..96,800&display=swap">
<style>
/* Layout: a course player. Home lists roles; a role lists modules; a module plays walkthrough steps, an exercise
   on the demonstration data, then a short quiz. Highlights use the red "edged on the plan" line of the PHAEMA brand. */
:root {
  --paper: #f6f8f7; --sheet: #ffffff; --ink: #13233a; --muted: #4a5864; --line: #cfd6d8; --edge: #d42a25;
  --survey: #2c6a3e; --survey-tint: #e3efe6; --link: #1b5c89; --warn-tint: #fbe9e7; --focus: #ffdd00; --band: #0d1b2c;
  --on-survey: #ffffff;
  --display: "Bricolage Grotesque", "Arial Narrow", Arial, sans-serif;
  --body: "Atkinson Hyperlegible", Verdana, Arial, sans-serif;
}
@media (prefers-color-scheme: dark) { :root:not([data-theme="light"]) {
  --paper: #0e151d; --sheet: #15202b; --ink: #e6ecef; --muted: #a9b5be; --line: #2d3b48; --edge: #ff6f69;
  --survey: #7fc78f; --survey-tint: #1d3326; --link: #86bfe9; --warn-tint: #3a1f1d; --on-survey: #0e151d; color-scheme: dark; } }
:root[data-theme="dark"] {
  --paper: #0e151d; --sheet: #15202b; --ink: #e6ecef; --muted: #a9b5be; --line: #2d3b48; --edge: #ff6f69;
  --survey: #7fc78f; --survey-tint: #1d3326; --link: #86bfe9; --warn-tint: #3a1f1d; --on-survey: #0e151d; color-scheme: dark; }
* { box-sizing: border-box; }
body { margin: 0; background: var(--paper); color: var(--ink); font: 1.0625rem/1.55 var(--body); }
.wrap { max-width: 1180px; margin: 0 auto; padding-left: max(16px, env(safe-area-inset-left, 0px)); padding-right: max(16px, env(safe-area-inset-right, 0px)); }
h1, h2, h3 { font-family: var(--display); line-height: 1.1; text-wrap: balance; margin: 0 0 .4em; }
h1 { font-size: clamp(2rem, 4.5vw, 3.2rem); font-weight: 800; letter-spacing: -.015em; }
h2 { font-size: clamp(1.4rem, 2.6vw, 1.9rem); font-weight: 800; }
h3 { font-size: 1.2rem; font-weight: 600; }
p { margin: 0 0 1em; max-width: 68ch; }
a { color: var(--link); }
button { font: inherit; cursor: pointer; }
:focus-visible { outline: 3px solid var(--focus); outline-offset: 0; box-shadow: 0 0 0 6px #0b0c0c; }
.top { background: var(--band); color: #f1f5f3; }
body::before { content: ""; position: fixed; inset: 0 0 auto; height: env(safe-area-inset-top, 0px); z-index: 10; background: var(--band); }
.top__inner { display: flex; flex-wrap: wrap; gap: 8px 20px; align-items: center; justify-content: space-between; padding-block: 14px; }
.brand { color: #f1f5f3; text-decoration: none; font-family: var(--display); font-weight: 800; font-size: 1.3rem; letter-spacing: .12em; display: inline-flex; gap: 10px; align-items: center; }
.brand small { font-family: var(--body); letter-spacing: 0; font-weight: 400; font-size: 1rem; color: #b9c6cf; }
.brand i { width: 18px; height: 14px; border: 2.5px solid #ff5b4f; display: inline-block; }
.crumbs { font-size: .95rem; color: #b9c6cf; }
.crumbs a { color: #9fd0f5; }
main { padding-block: 32px 64px; }
.lede { font-size: 1.2rem; color: var(--muted); }
.btn { display: inline-flex; align-items: center; gap: 8px; border: 0; padding: 11px 18px; font-weight: 700; border-radius: 3px; text-decoration: none; }
.btn--go { background: var(--survey); color: var(--on-survey); box-shadow: 0 3px 0 rgba(0,0,0,.35); }
.btn--plain { background: transparent; color: var(--link); box-shadow: inset 0 0 0 2px var(--link); }
.btn[disabled] { opacity: .45; cursor: default; }
.bar { height: 8px; background: var(--line); border-radius: 99px; overflow: hidden; }
.bar > span { display: block; height: 100%; background: var(--survey); border-radius: 99px; }

/* Home: roles */
.roles { display: grid; grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); gap: 18px; margin-top: 24px; }
.role { background: var(--sheet); border: 1px solid var(--line); padding: 22px; display: flex; flex-direction: column; gap: 10px; text-decoration: none; color: var(--ink); position: relative; }
.role:hover { border-color: var(--ink); }
.role h2 { font-size: 1.45rem; margin: 0; }
.role p { margin: 0; color: var(--muted); font-size: 1rem; }
.role__meta { display: flex; justify-content: space-between; font-size: .95rem; color: var(--muted); margin-top: auto; padding-top: 10px; }
.role__done { position: absolute; top: 14px; right: 14px; font-size: .85rem; font-weight: 700; color: var(--survey); border: 2px solid var(--survey); padding: 1px 8px; }

/* Course: modules */
.modules { list-style: none; padding: 0; margin: 24px 0; display: grid; gap: 10px; }
.mod { display: grid; grid-template-columns: 44px minmax(0, 1fr) auto; gap: 16px; align-items: center; background: var(--sheet); border: 1px solid var(--line); padding: 16px 18px; }
.mod__n { width: 44px; height: 44px; display: grid; place-items: center; font-family: var(--display); font-weight: 800; font-size: 1.2rem; border: 2px solid var(--line); border-radius: 50%; }
.mod.done .mod__n { background: var(--survey); color: var(--on-survey); border-color: var(--survey); }
.mod h3 { margin: 0 0 2px; }
.mod p { margin: 0; color: var(--muted); font-size: .98rem; }
.mod__state { font-size: .9rem; color: var(--muted); text-align: right; display: grid; gap: 6px; justify-items: end; }

/* Player */
.player { display: grid; grid-template-columns: minmax(0, 1.75fr) minmax(280px, 1fr); gap: 28px; align-items: start; margin-top: 20px; }
.shot { position: relative; overflow: hidden; background: var(--sheet); border: 1px solid var(--line); box-shadow: 0 16px 40px rgba(13,27,44,.16); }
.shot img { display: block; width: 100%; height: auto; }
.hl { position: absolute; border: 3px solid var(--edge); box-shadow: 0 0 0 9999px rgba(13,27,44,.42); border-radius: 2px; pointer-events: none; }
@media (prefers-reduced-motion: no-preference) { .hl { transition: all .45s cubic-bezier(.2,.7,.2,1); } .hl.pulse { animation: pulse 1.6s ease-out 1; } }
@keyframes pulse { 0% { outline: 0 solid rgba(212,42,37,.55); } 100% { outline: 14px solid rgba(212,42,37,0); } }
.panel { background: var(--sheet); border: 1px solid var(--line); padding: 22px; position: sticky; top: 16px; }
.phase { font-size: .9rem; color: var(--muted); margin-bottom: 6px; }
.dots { display: flex; gap: 6px; flex-wrap: wrap; margin: 14px 0 18px; }
.dots button { width: 28px; height: 8px; border: 0; padding: 0; background: var(--line); border-radius: 99px; }
.dots button.seen { background: var(--muted); }
.dots button[aria-current="step"] { background: var(--edge); }
.nav { display: flex; justify-content: space-between; gap: 10px; flex-wrap: wrap; }
.choices { display: grid; gap: 8px; margin: 14px 0; padding: 0; border: 0; }
.choices legend { font-weight: 700; margin-bottom: 8px; padding: 0; }
.choice { display: flex; gap: 10px; align-items: flex-start; border: 2px solid var(--line); padding: 10px 12px; background: var(--paper); cursor: pointer; }
.choice input { margin-top: 4px; accent-color: var(--survey); width: 18px; height: 18px; flex: none; }
.choice.right { border-color: var(--survey); background: var(--survey-tint); }
.choice.wrong { border-color: var(--edge); background: var(--warn-tint); }
.feedback { border-left: 4px solid var(--survey); padding: 8px 12px; background: var(--survey-tint); margin: 10px 0; }
.feedback.no { border-color: var(--edge); background: var(--warn-tint); }
.hint { font-size: .95rem; color: var(--muted); }
.result { text-align: left; background: var(--sheet); border: 1px solid var(--line); padding: 28px; margin-top: 20px; }
.score { font-family: var(--display); font-weight: 800; font-size: 3.4rem; line-height: 1; color: var(--survey); }
.trythis { background: var(--band); color: #f1f5f3; padding: 22px; margin-bottom: 18px; }
.trythis h3 { color: #fff; }
.trythis p { color: #dbe4ea; }
.foot { color: var(--muted); font-size: .9rem; padding-block: 24px 40px; border-top: 1px solid var(--line); }
.linkbtn { background: none; border: 0; padding: 0; color: var(--link); text-decoration: underline; }
@media (max-width: 860px) {
  .player { grid-template-columns: minmax(0, 1fr); }
  .panel { position: static; }
  .mod { grid-template-columns: 36px minmax(0, 1fr); }
  .mod__state { grid-column: 2; justify-items: start; text-align: left; }
}
</style>
'''

BODY = r'''<header class="top"><div class="wrap top__inner">
  <a class="brand" href="#home"><i aria-hidden="true"></i>PHAEMA <small>Training</small></a>
  <nav class="crumbs" id="crumbs" aria-label="Where you are"></nav>
</div></header>
<main id="app" class="wrap" tabindex="-1"></main>
<footer class="wrap foot"><a href="/help/">Back to the PHAEMA manual</a>. Exercises use the fictional Exampleton and Northfield demonstration data. Your progress is saved in this browser only. PHAEMA is free software under the AGPL-3.0.</footer>
<script>
var COURSES = __DATA__;
(function () {
  var app = document.getElementById('app'), crumbs = document.getElementById('crumbs');
  var KEY = 'phaema_training_v1', state = {};
  try { state = JSON.parse(localStorage.getItem(KEY) || '{}') || {}; } catch (e) { state = {}; }
  function save() { try { localStorage.setItem(KEY, JSON.stringify(state)); } catch (e) {} }
  function esc(s) { return String(s).replace(/[&<>"]/g, function (c) { return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]; }); }
  function course(id) { return COURSES.filter(function (c) { return c.id === id; })[0]; }
  function done(mid) { return state[mid] && state[mid].done; }
  function mins(c) { return c.modules.reduce(function (a, m) { return a + m.minutes; }, 0); }
  function doneCount(c) { return c.modules.filter(function (m) { return done(m.id); }).length; }

  function home() {
    crumbs.innerHTML = '';
    var cards = COURSES.map(function (c) {
      var n = doneCount(c), t = c.modules.length;
      return '<a class="role" href="#' + c.id + '">' + (n === t ? '<span class="role__done">Complete</span>' : '') +
        '<h2>' + esc(c.title) + '</h2><p>' + esc(c.who) + '</p>' +
        '<div class="bar" aria-hidden="true"><span style="width:' + Math.round(100 * n / t) + '%"></span></div>' +
        '<div class="role__meta"><span>' + t + ' modules, about ' + Math.round(mins(c) / 5) * 5 + ' minutes</span><span>' + n + ' of ' + t + ' done</span></div></a>';
    }).join('');
    app.innerHTML = '<h1>Learn PHAEMA for your job</h1><p class="lede">Choose your role. Each course walks you through the real screens, then you try it on the demonstration data and check what you have learnt with a short quiz.</p>' +
      '<div class="roles">' + cards + '</div>' +
      '<h2 style="margin-top:40px">Before you start</h2><ol><li>Get a sign-in to a copy of PHAEMA with the demonstration data: your council&#8217;s training copy, from your administrator, or the public test site at <a href="https://demo.phaema.co.uk">demo.phaema.co.uk</a> (select Request a test account there). The test site is reset every 48 hours.</li><li>Open it in another window beside this one, so you can follow along.</li><li>Every course starts with Getting around PHAEMA. If you have done it in another course, it is already ticked.</li></ol>';
  }

  function courseView(c) {
    crumbs.innerHTML = '<a href="#home">All courses</a> / ' + esc(c.title);
    var list = c.modules.map(function (m, i) {
      var s = state[m.id] || {};
      return '<li class="mod' + (s.done ? ' done' : '') + '"><span class="mod__n" aria-hidden="true">' + (s.done ? '✓' : i + 1) + '</span>' +
        '<div><h3>' + esc(m.title) + '</h3><p>' + esc(m.intro) + '</p></div>' +
        '<div class="mod__state"><span>' + m.minutes + ' minutes' + (s.done ? ' · quiz ' + s.score + '/' + m.quiz.length : '') + '</span>' +
        '<a class="btn ' + (s.done ? 'btn--plain' : 'btn--go') + '" href="#' + c.id + '--' + m.id + '">' + (s.done ? 'Go over it again' : 'Start') + '<span class="visually-hidden"> ' + esc(m.title) + '</span></a></div></li>';
    }).join('');
    var n = doneCount(c);
    app.innerHTML = '<h1>' + esc(c.title) + '</h1><p class="lede">' + esc(c.who) + '</p>' +
      '<div class="bar" role="img" aria-label="' + n + ' of ' + c.modules.length + ' modules done"><span style="width:' + Math.round(100 * n / c.modules.length) + '%"></span></div>' +
      '<ol class="modules">' + list + '</ol>' +
      (n === c.modules.length ? '<div class="result"><p class="score">Course complete</p><p>You have finished every module of the ' + esc(c.title) + ' course. Keep the manual to hand: select Help with this page in PHAEMA at any time.</p></div>' : '');
  }

  function player(c, m) {
    crumbs.innerHTML = '<a href="#home">All courses</a> / <a href="#' + c.id + '">' + esc(c.title) + '</a> / ' + esc(m.title);
    var total = m.steps.length, i = 0, seen = {};
    function step() {
      seen[i] = true;
      var s = m.steps[i];
      var box = s.box ? 'left:' + (s.box[0] * 100) + '%;top:' + (s.box[1] * 100) + '%;width:' + (s.box[2] * 100) + '%;height:' + (s.box[3] * 100) + '%' : 'display:none';
      var dots = m.steps.map(function (_, k) {
        return '<button type="button" data-k="' + k + '" class="' + (seen[k] ? 'seen' : '') + '"' + (k === i ? ' aria-current="step"' : '') + ' aria-label="Step ' + (k + 1) + '"></button>';
      }).join('');
      app.innerHTML = '<h1>' + esc(m.title) + '</h1>' +
        '<div class="player"><figure class="shot" style="margin:0"><img src="' + s.img + '" width="1280" height="800" alt="PHAEMA screen: ' + esc(s.title) + '. The highlighted area is described in the step text."><span class="hl pulse" style="' + box + '"></span></figure>' +
        '<section class="panel" aria-live="polite"><p class="phase">Step ' + (i + 1) + ' of ' + total + '</p><h2>' + esc(s.title) + '</h2><p>' + esc(s.text) + '</p>' +
        '<div class="dots" aria-label="Steps">' + dots + '</div>' +
        '<div class="nav"><button class="btn btn--plain" id="prev"' + (i === 0 ? ' disabled' : '') + '>Back</button>' +
        '<button class="btn btn--go" id="next">' + (i === total - 1 ? 'Try it yourself' : 'Next') + '</button></div></section></div>';
      document.getElementById('prev').onclick = function () { if (i > 0) { i--; step(); } };
      document.getElementById('next').onclick = function () { if (i < total - 1) { i++; step(); } else exercise(); };
      Array.prototype.forEach.call(app.querySelectorAll('.dots button'), function (b) { b.onclick = function () { i = +b.dataset.k; step(); }; });
      document.getElementById('next').focus();
    }
    function mcq(name, q, onAnswer) {
      return '<fieldset class="choices"><legend>' + esc(q.q) + '</legend>' + order(q).map(function (k) {
        return '<label class="choice"><input type="radio" name="' + name + '" value="' + k + '"><span>' + esc(q.options[k]) + '</span></label>';
      }).join('') + '</fieldset>';
    }
    function order(q) {  // stable shuffle so the answer is not always first
      var idx = q.options.map(function (_, k) { return k; });
      var seed = q.q.length;
      for (var k = idx.length - 1; k > 0; k--) { seed = (seed * 9301 + 49297) % 233280; var j = seed % (k + 1); var t = idx[k]; idx[k] = idx[j]; idx[j] = t; }
      return idx;
    }
    function mark(name, q, extra) {
      var picked = app.querySelector('input[name="' + name + '"]:checked');
      if (!picked) return null;
      var right = +picked.value === q.answer;
      Array.prototype.forEach.call(app.querySelectorAll('input[name="' + name + '"]'), function (inp) {
        inp.disabled = true;
        var lab = inp.parentNode;
        if (+inp.value === q.answer) lab.classList.add('right'); else if (inp === picked) lab.classList.add('wrong');
      });
      return right;
    }
    function exercise() {
      var e = m.exercise;
      app.innerHTML = '<h1>' + esc(m.title) + '</h1><div class="trythis"><h3>Try it yourself</h3><p>Open your training copy of PHAEMA, or the test site at <a href="https://demo.phaema.co.uk">demo.phaema.co.uk</a>, and find the answer in the demonstration data.</p></div>' +
        '<div class="panel" style="position:static">' + mcq('ex', e) +
        '<p class="hint" id="hintp"><button class="linkbtn" id="hint">Show a hint</button></p><div id="fb" aria-live="polite"></div>' +
        '<div class="nav"><button class="btn btn--plain" id="back">Back to the steps</button><button class="btn btn--go" id="check">Check my answer</button></div></div>';
      document.getElementById('hint').onclick = function () { document.getElementById('hintp').textContent = 'Hint: ' + e.hint; };
      document.getElementById('back').onclick = function () { i = 0; step(); };
      document.getElementById('check').onclick = function () {
        var r = mark('ex', e);
        var fb = document.getElementById('fb');
        if (r === null) { fb.innerHTML = '<p class="feedback no">Choose an answer first.</p>'; return; }
        fb.innerHTML = '<p class="feedback' + (r ? '' : ' no') + '">' + (r ? 'Right. ' : 'Not quite. ') + 'The answer is ' + esc(e.options[e.answer]) + '.</p>';
        var btn = document.getElementById('check'); btn.textContent = 'Go to the quiz'; btn.onclick = quiz; btn.focus();
      };
    }
    function quiz() {
      var qs = m.quiz;
      app.innerHTML = '<h1>Quiz: ' + esc(m.title) + '</h1><p class="lede">' + qs.length + ' questions. You see the answer after each one.</p>' +
        qs.map(function (q, k) { return '<div class="panel" style="position:static;margin-bottom:14px">' + mcq('q' + k, q) + '<div id="fb' + k + '" aria-live="polite"></div><button class="btn btn--plain" data-q="' + k + '">Check</button></div>'; }).join('') +
        '<p id="sum" aria-live="polite"></p><button class="btn btn--go" id="finish" disabled>Finish the module</button>';
      var marks = {};
      Array.prototype.forEach.call(app.querySelectorAll('[data-q]'), function (b) {
        b.onclick = function () {
          var k = +b.dataset.q, q = qs[k], r = mark('q' + k, q);
          var fb = document.getElementById('fb' + k);
          if (r === null) { fb.innerHTML = '<p class="feedback no">Choose an answer first.</p>'; return; }
          marks[k] = r; b.disabled = true;
          fb.innerHTML = '<p class="feedback' + (r ? '' : ' no') + '">' + (r ? 'Right. ' : 'Not quite. ') + esc(q.why) + '</p>';
          var n = Object.keys(marks).length;
          if (n === qs.length) { var f = document.getElementById('finish'); f.disabled = false; document.getElementById('sum').textContent = 'All answered.'; f.focus(); }
        };
      });
      document.getElementById('finish').onclick = function () {
        var score = Object.keys(marks).filter(function (k) { return marks[k]; }).length;
        state[m.id] = { done: true, score: Math.max(score, (state[m.id] && state[m.id].score) || 0) }; save();
        var idx = c.modules.indexOf(m), next = c.modules[idx + 1];
        app.innerHTML = '<div class="result"><p class="phase">' + esc(c.title) + '</p><h1>' + esc(m.title) + ': done</h1><p class="score">' + score + ' / ' + qs.length + '</p>' +
          '<p>' + (score === qs.length ? 'Full marks.' : 'Go over the steps again any time from the course page.') + '</p>' +
          '<div class="nav" style="justify-content:flex-start">' + (next ? '<a class="btn btn--go" href="#' + c.id + '--' + next.id + '">Next: ' + esc(next.title) + '</a>' : '') +
          '<a class="btn btn--plain" href="#' + c.id + '">Back to the course</a></div></div>';
        app.focus();
      };
    }
    step();
  }

  function route() {
    var h = (location.hash || '#home').slice(1), parts = h.split('--'), c = course(parts[0]);
    if (!c) home();
    else if (parts[1]) { var m = c.modules.filter(function (x) { return x.id === parts[1]; })[0]; if (m) player(c, m); else courseView(c); }
    else courseView(c);
    window.scrollTo(0, 0);
  }
  window.addEventListener('hashchange', route);
  route();
})();
</script>
'''

EXTRA = '<style>.visually-hidden{position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0 0 0 0);white-space:nowrap}</style>\n'


def build(artifact):
    body = BODY.replace("__DATA__", json.dumps(data()))
    if artifact:
        return HEAD + EXTRA + body
    return ('<!doctype html>\n<html lang="en-GB">\n<head>\n<meta charset="utf-8">\n'
            '<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">\n'
            + HEAD + EXTRA + '</head>\n<body>\n' + body + '\n</body>\n</html>\n')


if __name__ == "__main__":
    art = "--artifact" in sys.argv
    out = HERE / "artifact.html" if art else HERE.parent / "static" / "training" / "index.html"
    out.write_text(build(art), encoding="utf-8")
    print("Wrote", out)
