/* Claudio Symphony — session-centric control + living constellation */
'use strict';
const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];
const api = {
  get: (u) => fetch(u).then(r => r.json()),
  post: (u, b) => fetch(u, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(b || {}) }).then(r => r.json()),
};
const PALETTE = ['#e8b25c', '#ffd98a', '#8fc0a6', '#8ab6d6', '#e58c66', '#c98c34', '#d9b07a', '#9ec9b0'];
let STATE = null, DETAIL = null;
let FOCUS = { kind: 'global' };        // {kind:'global'} | {kind:'session', id, s}
let lastVoiceTs = {}, lastEventTs = {};
let EVT_COUNTS = {}, SORT_BY_FREQ = false;   // event fire-frequency + opt-in "most fired" sort
let TIMELINES = {}, REPLAY = { active: false };   // per-session mini-tracks + live replay state
// Mic-jam: listen to the room and re-key Claudio to the loudest steady note.
const MIC = { on: false, ctx: null, stream: null, analyser: null, buf: null, raf: 0,
  lastFire: 0,        // perf.now() of Claudio's most recent note (gap-aware gating)
  hist: [], lockedPc: null, lastSent: 0, lastShownPc: null, prevOffset: 0,
  src: null, mon: null };   // mic source node + live monitor FX chain (headphone mode)
const cssEsc = (s) => (window.CSS && CSS.escape) ? CSS.escape(s) : s;

const toast = (() => { const el = $('#toast'); let t;
  return (h) => { el.innerHTML = h; el.classList.add('show'); clearTimeout(t); t = setTimeout(() => el.classList.remove('show'), 2200); }; })();
const fmt = (n, d = 2) => (n == null ? '—' : (+n).toFixed(d));
const setFill = (el) => { const p = (el.value - el.min) / (el.max - el.min) * 100; el.style.setProperty('--p', p + '%'); };
function ageLabel(a) { if (a == null) return ''; if (a < 60) return Math.round(a) + 's'; if (a < 3600) return Math.round(a / 60) + 'm'; return Math.round(a / 3600) + 'h'; }

/* which preset the stage is currently editing (depends on focus) */
function editPreset() {
  if (FOCUS.kind === 'session' && FOCUS.s && FOCUS.s.preset) return FOCUS.s.preset;
  return STATE ? STATE.active : null;
}

/* ---------------- boot ---------------- */
async function boot() {
  applyTheme();           // restore per-browser accent before anything paints
  await loadState();
  wireGlobal();
  setFocus({ kind: 'global' });
  startActivityLoop(); startSky();
  setInterval(syncExternal, 4000);
}
async function loadState() {
  STATE = await api.get('/api/state');
  const m = $('#master'); m.value = STATE.master_gain; setFill(m); $('#masterVal').textContent = fmt(STATE.master_gain, 2);
  setPower(!STATE.muted); document.body.classList.toggle('is-muted', STATE.muted);
  $('#npName').textContent = STATE.active;
  paintDroneTop();
  renderRail();
}
function setPower(on) { const p = $('#power'); p.classList.toggle('on', on); p.classList.toggle('off', !on); p.querySelector('.lbl').textContent = on ? 'ON' : 'OFF'; }

/* ---------------- left rail: sessions ---------------- */
function renderRail() {
  const wrap = $('#sessList'); wrap.innerHTML = '';
  const sess = (STATE.sessions || []).filter(s => !s.ended || s.age < 300);
  $('#sessCount').textContent = sess.length ? sess.length + ' open' : '';

  // Global default pseudo-session
  const g = document.createElement('div');
  g.className = 'srail-item global' + (FOCUS.kind === 'global' ? ' focused' : '');
  g.innerHTML = `<div class="si-top"><span class="si-dot" style="background:var(--gold);box-shadow:0 0 7px var(--gold)"></span>
    <span class="si-name">Global default</span></div>
    <div class="si-preset">${STATE.active} <span class="via">· when no session matches</span></div>`;
  g.onclick = () => setFocus({ kind: 'global' });
  wrap.appendChild(g);

  if (!sess.length) {
    const e = document.createElement('div'); e.className = 'rempty'; e.style.padding = '14px 4px';
    e.textContent = 'no open Claude sessions yet — start one in any project and it appears here.';
    wrap.appendChild(e); return;
  }
  sess.forEach(s => {
    const recent = s.age < 90 && !s.ended;
    const focused = FOCUS.kind === 'session' && FOCUS.id === s.id;
    const badges = [s.pinned && `<span class="ov pin">📌</span>`, s.scale && `<span class="ov">♪</span>`, s.song && `<span class="ov">🎹</span>`].filter(Boolean).join('');
    const el = document.createElement('div');
    el.className = 'srail-item' + (recent ? ' recent' : '') + (focused ? ' focused' : '');
    el.dataset.session = s.id;
    el.innerHTML = `<div class="si-top"><span class="si-dot"></span><span class="si-name" title="${s.cwd || s.id}">${s.base}</span><span class="si-age">${ageLabel(s.age)}</span></div>
      <div class="si-preset">${s.preset || '—'} <span class="via">via ${s.source}</span></div>
      ${badges ? `<div class="si-badges">${badges}</div>` : ''}
      ${railTrackHTML(s)}`;
    el.onclick = () => setFocus({ kind: 'session', id: s.id, s });
    const rb = el.querySelector('.si-replay');
    if (rb) rb.onclick = (e) => { e.stopPropagation(); toggleReplay(s); };
    wrap.appendChild(el);
  });
  paintReplay();
}

/* per-session "mini-track": heavy-traffic sparkline + replay button */
function railTrackHTML(s) {
  const t = TIMELINES[s.id];
  if (!t || !t.count) return '';
  const peak = t.peak || 1;
  const bars = t.density.map(v => `<i style="height:${Math.max(8, Math.round(v / peak * 100))}%;opacity:${(0.3 + 0.7 * v / peak).toFixed(2)}"></i>`).join('');
  return `<div class="si-track" title="${t.count} events over ${Math.round(t.duration)}s — click ▶ to replay this session">
      <button class="si-replay" data-id="${s.id}" title="Replay this session through ${s.preset || 'the preset'}">▶</button>
      <div class="si-spark">${bars}<span class="si-head" hidden></span></div>
      <span class="si-evts">${t.count}</span>
    </div>`;
}
function toggleReplay(s) {
  if (REPLAY.active && REPLAY.session === s.id) { api.post('/api/score/stop', {}); toast('replay stopped'); }
  else { api.post('/api/score/replay', { id: s.id, preset: s.preset || STATE.active }); toast(`▶ replaying <span class="g">${s.base}</span> through ${s.preset || STATE.active}`); }
}
/* live: reflect replay state on the rail (button + playhead) without re-rendering */
function paintReplay() {
  const active = REPLAY.active, sid = REPLAY.session;
  $$('.srail-item').forEach(el => {
    const id = el.dataset.session;
    const btn = el.querySelector('.si-replay'); if (!btn) return;
    const me = active && id === sid;
    btn.textContent = me ? '■' : '▶';
    btn.classList.toggle('on', me);
    el.classList.toggle('replaying', me);
    if (!me) {            // playhead + lit bars belong to animReplay; clear strays
      const head = el.querySelector('.si-head'); if (head) head.hidden = true;
      const sp = el.querySelector('.si-spark');
      if (sp && sp._pl) { sp.querySelectorAll('i.played').forEach(b => b.classList.remove('played')); sp._pl = 0; }
    }
  });
  // keep the focused-session strip button in sync too
  const mb = $('#mtReplay');
  if (mb && FOCUS.kind === 'session') {
    const me = active && FOCUS.id === sid;
    mb.textContent = me ? '■ stop' : '▶ replay';
    mb.classList.toggle('on', me);
  }
}

/* the playhead sweeps continuously: between polls we dead-reckon from the last
   known elapsed time at the true playback rate, and ease in each correction —
   no more 280ms staircase. Bars light up (sage) as the head passes them. */
let REPLAY_RAF = 0;
function animReplayStart() { if (!REPLAY_RAF && REPLAY.active) REPLAY_RAF = requestAnimationFrame(animReplay); }
function animReplay() {
  REPLAY_RAF = 0;
  const el = REPLAY.session ? $(`.srail-item[data-session="${cssEsc(REPLAY.session)}"]`) : null;
  const spark = el && el.querySelector('.si-spark');
  if (!REPLAY.active) {
    if (spark) { spark.querySelectorAll('i.played').forEach(b => b.classList.remove('played')); spark._pl = 0;
      const h = spark.querySelector('.si-head'); if (h) h.hidden = true; }
    REPLAY.shown = 0; return;
  }
  if (spark) {
    // truth: time-based when the backend gave us duration, idx-based otherwise
    const est = REPLAY.duration > 0
      ? Math.min(1, (REPLAY.elapsed + (performance.now() - REPLAY.at) / 1000) / REPLAY.duration)
      : REPLAY.target;
    REPLAY.shown = (REPLAY.shown || 0) + (est - (REPLAY.shown || 0)) * 0.15;
    if (est >= 0.999 && REPLAY.shown > 0.99) REPLAY.shown = 1;
    const head = spark.querySelector('.si-head');
    if (head) { head.hidden = false; head.style.left = (REPLAY.shown * 100).toFixed(2) + '%'; }
    const bars = spark.querySelectorAll('i');
    const k = Math.floor(REPLAY.shown * bars.length);
    if (spark._pl !== k) { bars.forEach((b, i) => b.classList.toggle('played', i < k)); spark._pl = k; }
  }
  REPLAY_RAF = requestAnimationFrame(animReplay);
}

function setFocus(focus) {
  // refresh the session object from latest state if it's a session
  if (focus.kind === 'session') {
    const fresh = (STATE.sessions || []).find(x => x.id === focus.id);
    if (fresh) focus.s = fresh;
  }
  FOCUS = focus;
  renderRail();
  loadFocus();
}
async function loadFocus() {
  const name = editPreset();
  if (!name) return;
  DETAIL = await api.get('/api/preset?name=' + encodeURIComponent(name));
  lastVoiceTs = {}; lastEventTs = {};
  renderStage(); buildNodes();
}

/* ---------------- stage ---------------- */
function renderStage() {
  const isGlobal = FOCUS.kind === 'global';
  const s = FOCUS.s;
  $('#stageTitle').textContent = isGlobal ? 'Global default' : (s ? s.base : '—');
  const ct = $('#ctxTag');
  ct.className = 'ctx-tag ' + (isGlobal ? 'global' : 'session');
  ct.textContent = isGlobal ? 'default' : 'session';
  $('#stageSub').textContent = isGlobal
    ? `tuning ${DETAIL.name} — plays whenever no session rule/pin matches`
    : `tuning ${DETAIL.name}${s && s.source ? ` · resolved via ${s.source}` : ''} — ${DETAIL.description || ''}`.slice(0, 150);
  renderSessionStrip();
  const rs = $('#reverbScale'); rs.value = DETAIL.reverb_scale ?? 1; setFill(rs); $('#reverbScaleVal').textContent = fmt(rs.value, 2) + '×';
  $('#voiceHint').textContent = `the ${DETAIL.voices.length} instruments in this room — drag to shape each`;
  $('#musicScaleHint').textContent = isGlobal ? 'global default key' : 'global default (override per-session at right)';
  renderVoices(); renderEvents(); renderMusic(); renderActions(); renderSettings(); renderRules();
}

function renderSessionStrip() {
  const strip = $('#sessionStrip'); strip.innerHTML = '';
  const m = STATE.music || { scales: [], songs: [] };
  // preset chip → opens browser
  const chip = document.createElement('div'); chip.className = 'ss-field';
  chip.innerHTML = `<label>${FOCUS.kind === 'global' ? 'default preset' : 'session preset'}</label>
    <div class="preset-chip" id="presetChip"><span class="pc-name">${DETAIL.name}</span><span class="pc-ico">⊞ change</span></div>`;
  chip.querySelector('#presetChip').onclick = openBrowser;
  strip.appendChild(chip);

  if (FOCUS.kind === 'session' && FOCUS.s) {
    const s = FOCUS.s;
    const scaleOpts = `<option value="__none__"${!s.scale ? ' selected' : ''}>default</option>` +
      (m.scales || []).map(x => `<option ${x === s.scale ? 'selected' : ''}>${x}</option>`).join('');
    const songOpts = `<option value="__none__"${!s.song ? ' selected' : ''}>off</option>` +
      (m.songs || []).map(x => `<option ${x === s.song ? 'selected' : ''}>${x}</option>`).join('');
    const sc = document.createElement('div'); sc.className = 'ss-field';
    sc.innerHTML = `<label>scale</label><select class="vsel ${s.scale ? '' : 'silent'}" id="ssScale">${scaleOpts}</select>`;
    sc.querySelector('#ssScale').onchange = e => { api.post('/api/session/scale', { id: s.id, scale: e.target.value === '__none__' ? null : e.target.value }); s.scale = e.target.value === '__none__' ? null : e.target.value; e.target.classList.toggle('silent', !s.scale); toast(`${s.base} scale → ${s.scale || 'default'}`); renderRail(); };
    strip.appendChild(sc);
    const sg = document.createElement('div'); sg.className = 'ss-field';
    sg.innerHTML = `<label>song</label><select class="vsel ${s.song ? '' : 'silent'}" id="ssSong">${songOpts}</select>`;
    sg.querySelector('#ssSong').onchange = e => { api.post('/api/session/song', { id: s.id, song: e.target.value === '__none__' ? null : e.target.value }); s.song = e.target.value === '__none__' ? null : e.target.value; e.target.classList.toggle('silent', !s.song); toast(`${s.base} song → ${s.song || 'off'}`); renderRail(); };
    strip.appendChild(sg);
    if (s.pinned) {
      const un = document.createElement('div'); un.className = 'ss-field';
      un.innerHTML = `<label>&nbsp;</label><button class="btn ghost sm" id="ssUnpin">📌 unpin</button>`;
      un.querySelector('#ssUnpin').onclick = async () => { await api.post('/api/session/pin', { id: s.id, preset: '__none__' }); s.pinned = null; toast(`${s.base} follows rules`); renderRail(); renderSessionStrip(); };
      strip.appendChild(un);
    }
    // mini-track: replay / render-to-WAV / export this session's timeline
    const t = TIMELINES[s.id];
    if (t && t.count) {
      const mt = document.createElement('div'); mt.className = 'ss-field';
      const playing = REPLAY.active && REPLAY.session === s.id;
      mt.innerHTML = `<label>mini-track <span style="color:var(--faint)">${t.count} ev</span></label>
        <div class="ss-track">
          <button class="ss-trk-btn${playing ? ' on' : ''}" id="mtReplay">${playing ? '■ stop' : '▶ replay'}</button>
          <button class="ss-trk-btn" id="mtRender" title="Replay into a recording → a shareable WAV">● render WAV</button>
          <button class="ss-trk-btn" id="mtExport" title="Save a tiny .score.json you can share + replay anywhere">⤓ score</button>
        </div>`;
      mt.querySelector('#mtReplay').onclick = () => toggleReplay(s);
      mt.querySelector('#mtRender').onclick = () => { api.post('/api/score/replay', { id: s.id, preset: s.preset || STATE.active, render: true }); toast(`● rendering <span class="g">${s.base}</span> → recordings/`); };
      mt.querySelector('#mtExport').onclick = async () => { const r = await api.post('/api/score/export', { id: s.id, label: s.base }); toast(r && r.ok ? `⤓ saved <span class="g">${r.name}.score.json</span>` : 'export failed'); };
      strip.appendChild(mt);
    }
  }
}

/* ---------------- preset browser overlay ---------------- */
function openBrowser() {
  const isGlobal = FOCUS.kind === 'global';
  $('#browserTitle').textContent = isGlobal ? 'Set the global default' : `Choose a preset for ${FOCUS.s.base}`;
  $('#browserSub').textContent = isGlobal
    ? 'plays whenever no session pin or directory rule matches'
    : 'pins this session to the preset — overrides rules + default';
  $('#browserSearch').value = '';
  renderBrowser('');
  $('#browser').hidden = false;
  setTimeout(() => $('#browserSearch').focus(), 50);
}
function closeBrowser() { $('#browser').hidden = true; }

/* ---------------- manage custom presets ---------------- */
async function refreshPresetsState() {
  const s = await api.get('/api/state');
  STATE.presets = s.presets; STATE.active = s.active; $('#npName').textContent = s.active;
}
async function deletePreset(name) {
  if (!confirm(`Delete the custom preset “${name}”? This removes its sounds for good.`)) return;
  const r = await api.post('/api/preset/delete', { name });
  if (!r.ok) { toast(r.msg || 'could not delete'); return; }
  const wasEditing = editPreset() === name;
  await refreshPresetsState();
  if (wasEditing) setFocus({ kind: 'global' });
  renderBrowser($('#browserSearch').value);
  toast(`deleted <span class="g">${name}</span>`);
}
async function renamePreset(name) {
  const to = prompt(`Rename “${name}” to:`, name);
  if (to == null) return;
  const wasEditing = editPreset() === name;
  const r = await api.post('/api/preset/rename', { name, to });
  if (!r.ok) { toast(r.msg || 'could not rename'); return; }
  await refreshPresetsState();
  if (wasEditing) setFocus({ kind: 'global' });
  renderBrowser($('#browserSearch').value);
  toast(`renamed → <span class="g">${r.name}</span>`);
}

/* ---------------- sound picker (swap modal, generalized) ---------------- */
// One palette overlay, two users: "swap this voice's sound" (console) and
// "pick any sound for this track" (jukebox). PICKCB receives (preset, voice).
let SWAP = null, PICKCB = null;
async function openSoundPicker(title, sub, cb) {
  PICKCB = cb;
  $('#swapTitle').textContent = title;
  const subEl = $('#swap .builder-sub'); if (subEl) subEl.textContent = sub;
  $('#swap').hidden = false;
  if (!BANK) { try { BANK = (await api.get('/api/palette')).palette; } catch (e) { BANK = []; } }
  $('#swapSearch').value = ''; renderSwapPalette('');
  setTimeout(() => $('#swapSearch').focus(), 50);
}
function openSwap(voice) {
  SWAP = { preset: editPreset(), voice };
  openSoundPicker(`Replace the sound of “${voice}”`,
    "Pick a new sound — keeps this voice's level, echo and event mappings.",
    (sp, sv) => doSwap(sp, sv));
}
function closeSwap() { $('#swap').hidden = true; SWAP = null; PICKCB = null; }
function renderSwapPalette(filter) {
  const f = (filter || '').trim().toLowerCase();
  const wrap = $('#swapPalette'); wrap.innerHTML = '';
  (BANK || []).forEach(grp => {
    const voices = grp.voices.filter(v => !f || v.voice.toLowerCase().includes(f) || grp.preset.includes(f));
    if (!voices.length) return;
    const sec = document.createElement('div'); sec.className = 'b-grp';
    sec.innerHTML = `<div class="b-grp-h">${grp.preset}</div>`;
    const row = document.createElement('div'); row.className = 'b-chips';
    voices.forEach(v => {
      const chip = document.createElement('div'); chip.className = 'b-chip';
      chip.innerHTML = `<button class="b-play" title="hear it">▶</button><span class="b-vn">${v.voice}</span><button class="b-use" title="use this sound">use</button>`;
      chip.querySelector('.b-play').onclick = () => api.post('/api/voice/play', { preset: grp.preset, voice: v.voice });
      chip.querySelector('.b-use').onclick = () => { if (PICKCB) PICKCB(grp.preset, v.voice); };
      row.appendChild(chip);
    });
    sec.appendChild(row); wrap.appendChild(sec);
  });
}
async function doSwap(sp, sv) {
  if (!SWAP) return;
  const target = SWAP;
  const r = await api.post('/api/voice/swap', { preset: target.preset, voice: target.voice, src_preset: sp, src_voice: sv });
  if (!r.ok) { toast(r.msg || 'swap failed'); return; }
  closeSwap();
  await loadFocus();
  api.post('/api/voice/play', { preset: target.preset, voice: target.voice });
  toast(`<span class="g">${target.voice}</span> now sounds like ${sp}/${sv}`);
}

/* ---------------- preset builder ---------------- */
let BANK = null, bPicks = [], bMode = 'blank';
const pkKey = (sp, sv) => sp + '/' + sv;
async function openBuilder() {
  closeBrowser();
  $('#builder').hidden = false;
  bPicks = []; bMode = 'blank'; $('#bName').value = '';
  $$('.b-seg').forEach(s => s.classList.toggle('on', s.dataset.mode === 'blank'));
  const dup = $('#bDupSel'); dup.hidden = true;
  dup.innerHTML = (STATE.presets || []).map(p => `<option>${p.name}</option>`).join('');
  if (!BANK) { try { BANK = (await api.get('/api/palette')).palette; } catch (e) { BANK = []; } }
  $('#bSearch').value = '';
  renderPalette(''); renderBuilderSel();
  setTimeout(() => $('#bName').focus(), 50);
}
function closeBuilder() { $('#builder').hidden = true; }
function renderPalette(filter) {
  const f = (filter || '').trim().toLowerCase();
  const wrap = $('#bPalette'); wrap.innerHTML = '';
  (BANK || []).forEach(grp => {
    const voices = grp.voices.filter(v => !f || v.voice.toLowerCase().includes(f) || grp.preset.includes(f));
    if (!voices.length) return;
    const sec = document.createElement('div'); sec.className = 'b-grp';
    sec.innerHTML = `<div class="b-grp-h">${grp.preset}</div>`;
    const row = document.createElement('div'); row.className = 'b-chips';
    voices.forEach(v => {
      const key = pkKey(grp.preset, v.voice);
      const picked = bPicks.some(p => p.key === key);
      const chip = document.createElement('div'); chip.className = 'b-chip' + (picked ? ' picked' : ''); chip.dataset.pk = key;
      chip.innerHTML = `<button class="b-play" title="hear it">▶</button><span class="b-vn">${v.voice}</span><button class="b-add">${picked ? '✓' : '+'}</button>`;
      chip.querySelector('.b-play').onclick = () => { api.post('/api/voice/play', { preset: grp.preset, voice: v.voice }); toast(`<span class="g">${grp.preset}</span> · ${v.voice}`); };
      chip.querySelector('.b-add').onclick = () => { togglePick(grp.preset, v.voice); };
      row.appendChild(chip);
    });
    sec.appendChild(row); wrap.appendChild(sec);
  });
}
function togglePick(sp, sv) {
  const key = pkKey(sp, sv); const i = bPicks.findIndex(p => p.key === key);
  const nowPicked = i < 0;
  if (i >= 0) bPicks.splice(i, 1); else bPicks.push({ src_preset: sp, src_voice: sv, key });
  // update the matching palette chip in place (don't re-render — keeps scroll)
  const chip = $(`#bPalette .b-chip[data-pk="${cssEsc(key)}"]`);
  if (chip) { chip.classList.toggle('picked', nowPicked); chip.querySelector('.b-add').textContent = nowPicked ? '✓' : '+'; }
  renderBuilderSel();
}
function renderBuilderSel() {
  const el = $('#bSel');
  const dupNote = bMode === 'dup' ? `<span class="b-sel-note">+ all of <b>${$('#bDupSel').value}</b>'s voices</span>` : '';
  if (!bPicks.length && bMode !== 'dup') { el.innerHTML = `<span class="b-sel-empty">no sounds yet — tap <b>+</b> on any sound below to add it</span>`; return; }
  el.innerHTML = `<span class="b-sel-lbl">your sounds (${bPicks.length})</span>` +
    bPicks.map(p => `<span class="b-sel-chip" data-key="${p.key}">${p.src_voice}<small>${p.src_preset}</small><button class="b-x">✕</button></span>`).join('') + dupNote;
  el.querySelectorAll('.b-sel-chip').forEach(c => c.querySelector('.b-x').onclick = () => {
    const p = bPicks.find(x => x.key === c.dataset.key); if (p) togglePick(p.src_preset, p.src_voice);
  });
}
async function builderCreate() {
  const name = $('#bName').value.trim();
  if (!name) { toast('give your preset a name'); $('#bName').focus(); return; }
  const body = { name, set_active: true,
    voices: bPicks.map(p => ({ src_preset: p.src_preset, src_voice: p.src_voice })) };
  if (bMode === 'dup') body.base = $('#bDupSel').value;
  const btn = $('#bCreate'); btn.disabled = true; btn.textContent = 'building…';
  const r = await api.post('/api/preset/create', body);
  btn.disabled = false; btn.textContent = 'Create →';
  if (!r.ok) { toast(r.msg || 'could not create'); return; }
  closeBuilder();
  const s = await api.get('/api/state'); STATE.presets = s.presets; STATE.active = s.active;
  $('#npName').textContent = s.active;
  setFocus({ kind: 'global' });
  toast(`built <span class="g">${r.name}</span> · ${r.voices.length} voices — now playing`);
}

/* ---------------- tip / buy-me-a-coffee ---------------- */
let DONATE = null;
async function openTip() {
  $('#tipModal').hidden = false;
  if (!DONATE) { try { DONATE = await api.get('/api/donate'); } catch (e) { DONATE = { methods: [] }; } }
  $('#tipTitle').textContent = DONATE.title || '☕ Buy me a coffee';
  $('#tipBlurb').textContent = DONATE.blurb || '';
  renderTip();
}
function closeTip() { $('#tipModal').hidden = true; }

/* ---------------- record & share ---------------- */
const REC_DURATIONS = [[15, '15s'], [30, '30s'], [60, '1m'], [120, '2m'], [300, '5m']];
let recPick = 30, recDrone = false, recPoll = null;
function openRec() { $('#recModal').hidden = false; refreshRec(); recPoll = setInterval(refreshRec, 1000); }
function closeRec() { $('#recModal').hidden = true; if (recPoll) { clearInterval(recPoll); recPoll = null; } }
async function refreshRec() {
  let s; try { s = await api.get('/api/record/status'); } catch (e) { return; }
  renderRecBody(s); renderRecList(s);
  const btn = $('#recBtn'), lbl = $('#recBtnLbl');
  btn.classList.toggle('on', !!s.active);
  lbl.textContent = s.active ? `${Math.ceil(s.remaining)}s` : 'Rec';
}
function renderRecBody(s) {
  const body = $('#recBody');
  if (s.active) {
    const pct = s.duration ? Math.max(0, Math.min(100, 100 * (1 - s.remaining / s.duration))) : 0;
    body.innerHTML = `
      <div class="rec-live">
        <div class="rec-live-top"><span class="rec-pulse"></span>
          <span class="rec-rem">${Math.ceil(s.remaining)}s left</span>
          <span class="rec-cap">${s.events || 0} sound${s.events === 1 ? '' : 's'} captured</span></div>
        <div class="rec-bar"><span style="width:${pct}%"></span></div>
        <button class="rec-stop" id="recStop">■ Stop &amp; save now</button>
      </div>`;
    body.querySelector('#recStop').onclick = async () => { await api.post('/api/record/stop', {}); toast('saving your clip…'); setTimeout(refreshRec, 600); };
  } else {
    body.innerHTML = `
      <div class="rec-idle">
        <div class="rec-pick">${REC_DURATIONS.map(([v, l]) => `<button class="rec-chip${v === recPick ? ' on' : ''}" data-v="${v}">${l}</button>`).join('')}</div>
        <button class="rec-drone${recDrone ? ' on' : ''}" id="recDrone">
          <span class="rec-drone-sw"></span>
          <span class="rec-drone-txt">🌫️ Add a drone bed <em>· fades in &amp; out, for a more song-like clip</em></span>
        </button>
        <button class="rec-go" id="recGo">● Start recording</button>
        <div class="rec-hint">Then go work in your Claude sessions — sounds are captured as Claude plays them.</div>
      </div>`;
    body.querySelectorAll('.rec-chip').forEach(c => c.onclick = () => { recPick = +c.dataset.v; renderRecBody(s); });
    body.querySelector('#recDrone').onclick = () => { recDrone = !recDrone; renderRecBody(s); };
    body.querySelector('#recGo').onclick = async () => {
      const r = await api.post('/api/record/start', { seconds: recPick, drone: recDrone });
      if (r && r.ok === false) { toast(r.msg || 'already recording'); }
      else { toast(`<span class="g">recording</span> ${recPick}s — go make some sounds`); }
      setTimeout(refreshRec, 500);
    };
  }
}
let recSeen = -1;
function renderRecList(s) {
  const list = $('#recList'); const recs = s.recordings || [];
  // toast when a new clip lands
  if (recSeen >= 0 && recs.length > recSeen && !s.active) toast('✅ clip saved — scroll down to play or download');
  recSeen = recs.length;
  if (!recs.length) { list.innerHTML = '<div class="rec-empty">No clips yet. Your recordings will show here.</div>'; return; }
  const scores = recs.filter(r => r.kind === 'score');
  // audio clips: one row per take, pair .m4a/.wav by basename
  const byBase = {};
  recs.filter(r => r.kind !== 'score').forEach(r => { const base = r.name.replace(/\.(wav|m4a)$/, ''); (byBase[base] ||= []).push(r); });
  let html = Object.keys(byBase).length ? '<div class="rec-list-h">Your clips</div>' + Object.entries(byBase).map(([base, items]) => {
    const m4a = items.find(i => i.name.endsWith('.m4a')); const wav = items.find(i => i.name.endsWith('.wav'));
    const play = m4a || wav;
    const dls = items.map(i => `<a class="rec-dl" href="${i.url}" download>${i.name.endsWith('.m4a') ? 'm4a' : 'wav'} ↓</a>`).join('');
    return `<div class="rec-row"><div class="rec-name">${base}</div>
      ${play ? `<audio class="rec-audio" controls preload="none" src="${play.url}"></audio>` : ''}
      <div class="rec-dls">${dls}</div></div>`;
  }).join('') : '';
  // session-score exports: tiny, replay-anywhere — download only (not audio)
  if (scores.length) {
    html += '<div class="rec-list-h">Session scores <span class="rec-list-note">tiny · replay anywhere</span></div>' +
      scores.map(r => `<div class="rec-row"><div class="rec-name">🎬 ${r.name.replace(/\.score\.json$/, '')}</div>
        <div class="rec-dls"><a class="rec-dl" href="${r.url}" download>score.json ↓ (${Math.max(1, Math.round(r.size / 1024))} KB)</a></div></div>`).join('');
  }
  list.innerHTML = html;
}
/* ---------------- help: what can I do here? ---------------- */
const HELP_ICONS = ['🎛️', '🧭', '🎵', '🎬', '🎹', '🎙️', '🎧'];
const WEB_HELP = [
  { heading: 'Presets & sound', items: [
    'Browse 36+ presets, audition any, and set one as the global default.',
    'Constellation view: each orbiting orb is a voice — click it to hear it and jump to its controls.',
    'Sounds tab: what plays when (events up top), then every voice\'s gain, reverb, rate and echo below — ✎ on any event jumps to its voice.',
    "Swap any voice's samples for a sound from any other preset.",
    'Build your own preset from sounds across all presets (Browse → Build).'] },
  { heading: 'Routing — who plays where', items: [
    'Left rail lists live Claude sessions; click one to focus and edit it.',
    'Pin a preset, scale, or MIDI song to just one session; Unpin to release.',
    'Setup tab: path-glob rules auto-select a preset when the cwd matches.',
    'Global-default pseudo-session plays when no pin or rule matches.'] },
  { heading: 'Events & music', items: [
    'Sounds tab: map each of the 9 hook events to a voice, with by-tool and on-failure overrides.',
    'Sort events by fire frequency and reset counters.',
    'Music tab: pick a global scale and a MIDI song to drive melodies (off = Markov).',
    'Chord progression: cycle the room through the four-chord song (or your own changes) — the live chord glows and sweeps toward the next.',
    'Quantize: toggle beat-snap, set BPM and grid (16th/8th/quarter/half).',
    '🎤 Listen (top bar): jam with the room — Claudio tunes its key to the loudest steady note your mic hears. Tap to keep it on, or press-and-hold to listen only while held; turning it off restores the previous key.'] },
  { heading: 'Session replay & mini-tracks', items: [
    'Each session shows a sparkline of its event-fire history (heavy-traffic spots).',
    "Play the mini-track to replay that session's timeline through any preset.",
    'Render the replay to a shareable .wav.',
    'Export the timeline as a tiny .score.json to replay elsewhere.'] },
  { heading: 'Jukebox (secret instrument)', items: [
    'Click the gold dot in the logo, or the Music-tab Jukebox button, to open it.',
    'Every track shows its register, note range, count and a density bar; map it to an event (fire counts shown — see what your sessions use most), pick any voice directly, or ⊞ browse every preset\'s sounds.',
    '▶ on a row previews that sound; ✨ smart arrange matches drums to percussive voices and melodies to voices in the right register. The `studio` preset is a drums/bass/synth kit made for this.',
    '💾 save as preset copies every mapped sound into a new preset you can use anywhere.',
    'Pitch comes from the MIDI: pitched voices land exactly on each note; percussive ones bend toward it.',
    'Adjust tempo (0.5×–2×) and loop; rows pulse as they fire. Tip: start Rec first to capture the whole performance.'] },
  { heading: 'Record & tune', items: [
    'Rec: capture a 15s–5m clip (optional drone bed); clips download as .m4a + .wav.',
    'Setup tab: master/drone gain, preset actions (test, regenerate, reset), directory rules.',
    'Top bar: master volume slider and a global power toggle (mute/unmute).',
    '⋯ menu → Options: pick your accent color, headphone mode, mic monitor, visual energy.',
    'Display modes: hover the constellation for the ✦ ◍ ≈ switcher — orbs, still pond, or flowing tides.'] },
  { heading: 'Headphones & jamming', items: [
    '🎤 Listen detects what you\'re humming — or the music you\'re playing — and re-keys Claudio to match, live.',
    'Options → Headphone mode: with Claudio in your ears the mic never hears it, so Listen tracks you continuously.',
    'Options → Mic monitor: mic passthrough with Claudio\'s reverb + delay on your voice or instrument — actually jam with your Claudio. Headphones only, so it can\'t feed back.',
    'Add a chord progression (Music tab) and the room cycles changes underneath you while you play.',
    'Turn the drone on (Setup) and the bed bends to your voice in ~½s as Listen re-keys — set it to follow the chords and it walks the changes too.',
    'Monitor space slider: dry ↔ drenched. Everything stays in this browser — no audio leaves your machine.'] },
];
function openHelp() {
  $('#helpGrid').innerHTML = WEB_HELP.map((s, i) => `
    <div class="help-card">
      <div class="help-card-h"><span class="help-ico">${HELP_ICONS[i] || '•'}</span>${s.heading}</div>
      <ul>${s.items.map(it => `<li>${it}</li>`).join('')}</ul>
    </div>`).join('');
  $('#helpModal').hidden = false;
}
function closeHelp() { $('#helpModal').hidden = true; }

/* ---------------- jukebox: perform a MIDI through the preset (easter egg) ---------------- */
// Plain-language for Claude Code's hook events — newcomers shouldn't have to
// know the API names. title = what shows; tech = the raw hook name (small);
// desc = a one-liner so nobody has to guess what triggers it.
const EVENT_INFO = {
  SessionStart:     { title: 'Session starts',        tech: 'SessionStart',     desc: 'Claude Code opens in a project' },
  UserPromptSubmit: { title: 'You send a message',    tech: 'UserPromptSubmit', desc: 'every time you hit enter' },
  PreToolUse:       { title: 'Before a tool runs',    tech: 'PreToolUse',       desc: 'Claude is about to read, edit, or run something' },
  PostToolUse:      { title: 'After a tool runs',     tech: 'PostToolUse',      desc: 'a read / edit / command just finished' },
  SubagentStop:     { title: 'A sub-agent finishes',  tech: 'SubagentStop',     desc: 'a helper task Claude spawned returns' },
  Stop:             { title: 'Claude finishes',       tech: 'Stop',             desc: 'the reply is done — your move' },
  SessionEnd:       { title: 'Session ends',          tech: 'SessionEnd',       desc: 'the Claude Code session closes' },
  Notification:     { title: 'Claude needs you',      tech: 'Notification',     desc: 'waiting on input or permission' },
  PreCompact:       { title: 'Before summarizing',    tech: 'PreCompact',       desc: 'the conversation is being compacted' },
};
const evTitle = (e) => (EVENT_INFO[e] && EVENT_INFO[e].title) || e;
const evDesc  = (e) => (EVENT_INFO[e] && EVENT_INFO[e].desc) || '';
// kept for the jukebox's compact channel labels
const EVENT_LABELS = {
  PostToolUse: 'after a tool', Stop: 'turn ends', PreToolUse: 'before a tool',
  UserPromptSubmit: 'you prompt', Notification: 'notification', SubagentStop: 'subagent ends',
  SessionStart: 'session start', SessionEnd: 'session end', PreCompact: 'compaction',
};
const JCOLS = ['#e8b25c', '#8ab6d6', '#8fc0a6', '#e58c66', '#ffd98a', '#c98c34', '#9ec9b0', '#d9b07a', '#b39ddb'];
// JUKE.preset = the "sound kit": the preset the performance plays through,
// independent of the room's active preset (so you can demo a MIDI on the
// studio drums/bass/synth kit while meadow keeps playing your hooks).
let JUKE = { song: null, preset: null, plan: null, map: {}, tempo: 1, loop: false, evVoice: {}, poll: null, playing: false };

let VIEW = 'console';
function setView(view) {
  VIEW = view;
  const juke = view === 'jukebox';
  $('#jukePage').hidden = !juke;
  document.body.classList.toggle('jukebox-view', juke);
  $$('.vsw').forEach(b => b.classList.toggle('on', b.dataset.view === view));
  if (juke) enterJuke(); else exitJuke();
}
const openJuke = () => setView('jukebox');     // brand-dot easter egg + Music-tab button
const closeJuke = () => setView('console');

async function enterJuke() {
  // sound-kit picker: any preset, defaults to the room's active one
  if (!JUKE.preset || !(STATE.presets || []).some(p => p.name === JUKE.preset)) JUKE.preset = STATE.active;
  const kit = $('#jukeKit');
  kit.innerHTML = (STATE.presets || []).map(p =>
    `<option value="${p.name}" ${p.name === JUKE.preset ? 'selected' : ''}>${p.name}${p.name === 'studio' ? ' · 🥁 drums/bass/synth' : ''}</option>`).join('');
  kit.onchange = async () => { JUKE.preset = kit.value; await jukeKitChanged(); toast(`kit → <span class="g">${JUKE.preset}</span>`); };
  await jukeKitChanged();
  refreshJukeStatus();
  if (!JUKE.poll) JUKE.poll = setInterval(refreshJukeStatus, 300);
}

/* (re)load everything that depends on the chosen kit preset */
async function jukeKitChanged() {
  try {
    const d = await api.get('/api/preset?name=' + encodeURIComponent(JUKE.preset));
    JUKE.evVoice = {}; (d.events || []).forEach(e => { JUKE.evVoice[e.event] = e.default; });
  } catch { JUKE.evVoice = {}; }
  const songs = (STATE.music && STATE.music.songs) || [];
  const sel = $('#jukeSong');
  if (!songs.length) {
    sel.innerHTML = `<option>— no MIDI yet —</option>`;
    $('#jukeMap').innerHTML = `<div class="juke-empty">No songs yet. Drop a <code>.mid</code> with <b>＋ import</b> above, or run <code>claudio song import &lt;file.mid&gt;</code>.</div>`;
  } else {
    sel.innerHTML = songs.map(s => `<option ${s === JUKE.song ? 'selected' : ''}>${s}</option>`).join('');
    JUKE.song = JUKE.song && songs.includes(JUKE.song) ? JUKE.song : songs[0];
    sel.value = JUKE.song;
    await loadJukePlan();
  }
}
function exitJuke() { if (JUKE.poll) { clearInterval(JUKE.poll); JUKE.poll = null; } }

async function loadJukePlan() {
  if (!JUKE.song) return;
  let p; try { p = await api.get(`/api/midiplay/plan?song=${encodeURIComponent(JUKE.song)}&preset=${encodeURIComponent(JUKE.preset)}`); } catch { return; }
  if (!p || p.error) { $('#jukeMap').innerHTML = `<div class="juke-empty">Couldn't read that song.</div>`; return; }
  JUKE.plan = p; JUKE.map = {}; JUKE.auto = {};
  p.channels.forEach(c => { JUKE.map[c.channel] = c.token; JUKE.auto[c.channel] = c.token; });
  // fire counts: badge the event options so you can see what your sessions use most
  try { const a = await api.get('/api/activity?name=' + encodeURIComponent(JUKE.preset)); JUKE.counts = a.counts || {}; }
  catch { JUKE.counts = {}; }
  renderJukeMap();
}

const NOTE_N = ['C','C#','D','D#','E','F','F#','G','G#','A','A#','B'];
const noteName = (m) => m == null ? '' : NOTE_N[m % 12] + (Math.floor(m / 12) - 1);

/* what does this token sound like? → {preset, voice} it resolves to.
   Tokens: event name | 'voice:<name>' | 'voice:<preset>/<voice>' (any sound). */
function tokenParts(token) {
  if (!token || token === '__none__') return null;
  if (token.startsWith('voice:')) {
    const v = token.slice(6);
    if (v.includes('/')) { const [p, name] = v.split('/'); return { preset: p, voice: name }; }
    return { preset: JUKE.preset, voice: v };
  }
  const v = JUKE.evVoice[token];
  return v ? { preset: JUKE.preset, voice: v } : null;
}

function renderJukeMap() {
  const p = JUKE.plan; if (!p) return;
  const vmeta = {}; (p.voices || []).forEach(v => vmeta[v.name] = v);
  const vTag = (v) => { const f = vmeta[v]; if (!f) return '';
    return f.pitched ? `${f.register} · melodic` : `${f.register || '—'} · percussive`; };
  const cnt = (e) => JUKE.counts && JUKE.counts[e] ? ` ×${JUKE.counts[e]}` : '';
  const opts = (token) => {
    const cross = token && token.startsWith('voice:') && token.includes('/');
    return `${cross ? `<option value="${token}" selected>⊞ ${token.slice(6)}</option>` : ''}
    <optgroup label="events — the room blooms with the song">
      ${p.events.map(e => `<option value="${e}" ${e === token ? 'selected' : ''}>${e} → ${JUKE.evVoice[e] || '?'}${cnt(e)}</option>`).join('')}
    </optgroup>
    <optgroup label="voices — pick the sound directly">
      ${(p.voices || []).map(v => `<option value="voice:${v.name}" ${('voice:' + v.name) === token ? 'selected' : ''}>${v.name} · ${vTag(v.name)}</option>`).join('')}
    </optgroup>
    <option value="__pick__">⊞ any sound — browse all presets…</option>
    <option value="__none__" ${!token ? 'selected' : ''}>— silent —</option>`;
  };
  const maxN = Math.max(1, ...p.channels.map(c => c.notes));
  $('#jukeMap').innerHTML =
    `<div class="juke-map-h">${p.total_notes} notes · ${Math.round(p.duration)}s · bpm ${Math.round(p.bpm * JUKE.tempo)}
       <span class="juke-arr-btns"><button class="btn sm" id="jukeSmart" title="match percussive tracks to percussive sounds, melodies to melodic voices by register">✨ smart arrange</button>
       <button class="btn sm ghost" id="jukeAuto" title="back to the default event order">↺ auto</button>
       <button class="btn sm ghost" id="jukeSave" title="copy every mapped sound into a new preset you can use anywhere">💾 save as preset</button></span></div>` +
    p.channels.map((c, i) => {
      const token = JUKE.map[c.channel];
      const parts = tokenParts(token);
      const voice = parts ? parts.voice : null;
      const col = JCOLS[i % JCOLS.length];
      const range = c.lo != null ? `${noteName(c.lo)}–${noteName(c.hi)}` : '';
      const tags = `${c.is_lead ? '<em>◆lead</em>' : ''}${c.is_drum ? '<em class="drum">🥁drums</em>' : ''}`;
      return `<div class="juke-row" data-ch="${c.channel}" data-voice="${voice || ''}">
        <span class="juke-ch-dot" style="--jc:${col}"></span>
        <div class="juke-trk">
          <span class="juke-ch">ch${c.channel} ${tags}</span>
          <span class="juke-reg">${c.register} ${range} · ${c.notes}n · ${c.density}/s</span>
          <span class="juke-dens"><i style="width:${Math.round(100 * c.notes / maxN)}%;background:${col}"></i></span>
        </div>
        <span class="juke-arrow">→</span>
        <select class="vsel juke-ev" data-ch="${c.channel}">${opts(token)}</select>
        <button class="juke-prev" data-ch="${c.channel}" title="hear this sound">▶</button>
      </div>`;
    }).join('');
  $$('.juke-ev', $('#jukeMap')).forEach(s => s.onchange = e => {
    const ch = +e.target.dataset.ch, val = e.target.value;
    if (val === '__pick__') {     // browse every preset's sounds for this track
      openSoundPicker(`Pick a sound for ch${ch}`, 'Any sound from any preset — ▶ to hear, use to take it.',
        (sp, sv) => { JUKE.map[ch] = `voice:${sp}/${sv}`; closeSwap(); renderJukeMap(); toast(`ch${ch} → <span class="g">${sp}/${sv}</span>`); });
      renderJukeMap();            // snap the select back until they pick
      return;
    }
    JUKE.map[ch] = val === '__none__' ? null : val;
    renderJukeMap();
  });
  $$('.juke-prev', $('#jukeMap')).forEach(b => b.onclick = () => {
    const parts = tokenParts(JUKE.map[+b.dataset.ch]);
    if (!parts) { toast('this track is silent'); return; }
    api.post('/api/voice/play', { preset: parts.preset, voice: parts.voice });
    toast(`♪ <span class="g">${parts.voice}</span>${parts.preset !== JUKE.preset ? ' · ' + parts.preset : ''}`);
  });
  $('#jukeSmart').onclick = () => {
    Object.entries(p.smart || {}).forEach(([ch, tok]) => { JUKE.map[+ch] = tok; });
    renderJukeMap();
    toast('✨ arranged — drums → percussive, melodies → matching registers');
  };
  $('#jukeAuto').onclick = () => { JUKE.map = { ...JUKE.auto }; renderJukeMap(); toast('back to auto order'); };
  $('#jukeSave').onclick = jukeSaveKit;
}

/* save the current jukebox mix as a real preset: every mapped sound (from any
   preset) gets copied into a new self-contained preset via the same endpoint
   the builder uses. Use it later like any preset — or jukebox it again. */
async function jukeSaveKit() {
  const picks = [], seen = new Set();
  Object.values(JUKE.map).forEach(tok => {
    const p = tokenParts(tok); if (!p) return;
    const key = p.preset + '/' + p.voice;
    if (!seen.has(key)) { seen.add(key); picks.push({ src_preset: p.preset, src_voice: p.voice }); }
  });
  if (!picks.length) { toast('map some sounds first'); return; }
  const name = prompt(`Save these ${picks.length} sounds as a preset — name it:`);
  if (!name || !name.trim()) return;
  const r = await api.post('/api/preset/create', { name: name.trim(), set_active: false, voices: picks });
  if (!r || !r.ok) { toast((r && r.msg) || 'could not create'); return; }
  try { const s = await api.get('/api/state'); STATE.presets = s.presets; } catch { }
  toast(`💾 saved <span class="g">${r.name}</span> · ${(r.voices || picks).length} sounds — in Browse presets`);
}
function jukeMapPayload() {
  // send EVERY channel — silent ones as "__none__" so they override the auto-map
  const out = {}; Object.entries(JUKE.map).forEach(([ch, ev]) => { out[ch] = ev || '__none__'; });
  return out;
}
async function jukePlay() {
  if (!JUKE.song) { toast('import a MIDI first'); return; }
  const r = await api.post('/api/midiplay/start', { song: JUKE.song, preset: JUKE.preset, tempo: JUKE.tempo, loop: JUKE.loop, mapping: jukeMapPayload() });
  if (r && r.ok) { toast(`🎹 performing <span class="g">${JUKE.song}</span>`); setTimeout(refreshJukeStatus, 250); }
  else toast((r && r.msg) || 'could not start');
}
async function jukeStop() { await api.post('/api/midiplay/stop', {}); setTimeout(refreshJukeStatus, 200); }

async function refreshJukeStatus() {
  let s; try { s = await api.get('/api/midiplay/status'); } catch { return; }
  const playing = !!s.active;
  JUKE.playing = playing;
  const btn = $('#jukePlay');
  btn.classList.toggle('on', playing);
  btn.textContent = playing ? '■ Stop' : '▶ Play';
  btn.onclick = playing ? jukeStop : jukePlay;
  // playhead
  const prog = s.progress || {};
  const total = s.total_notes || (JUKE.plan && JUKE.plan.total_notes) || 1;
  const pct = playing && prog.total ? Math.max(0, Math.min(100, 100 * (prog.idx || 0) / prog.total)) : 0;
  $('#jukeBarFill').style.width = pct + '%';
  $('#jukeBarHead').style.left = pct + '%';
  $('#jukeBarHead').style.opacity = playing ? 1 : 0;
  const dur = s.duration || (JUKE.plan && JUKE.plan.duration) || 0;
  const el = playing ? (prog.elapsed || 0) : 0;
  $('#jukeTime').textContent = `${mmss(el)} / ${mmss(dur)}`;
  // pulse the row whose event most recently fired (read the same markers the sky uses)
  if (playing && JUKE.plan) {
    try {
      const a = await api.get('/api/activity?name=' + encodeURIComponent(JUKE.preset));
      $$('.juke-row').forEach(row => {
        const v = row.dataset.voice; const ts = v && a.voices ? a.voices[v] : 0;
        const age = ts ? a.now - ts : 1e9;
        row.classList.toggle('lit', age < 0.5);
        row.style.setProperty('--lit', age < 1.2 ? (1 - age / 1.2).toFixed(2) : 0);
      });
    } catch { }
  } else {
    $$('.juke-row').forEach(row => { row.classList.remove('lit'); row.style.setProperty('--lit', 0); });
  }
}
function mmss(s) { s = Math.max(0, Math.round(s || 0)); return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`; }

function jukeImportFile(file) {
  if (!file) return;
  const rd = new FileReader();
  rd.onload = async () => {
    const name = file.name.replace(/\.(mid|midi)$/i, '');
    const r = await api.post('/api/song/import', { name, b64: rd.result });
    if (r && r.ok) {
      toast(`imported <span class="g">${r.name}</span> · ${r.notes} notes`);
      const s = await api.get('/api/state'); STATE.music = s.music;     // refresh song list
      JUKE.song = r.name;
      const sel = $('#jukeSong');
      sel.innerHTML = (STATE.music.songs || []).map(x => `<option ${x === r.name ? 'selected' : ''}>${x}</option>`).join('');
      await loadJukePlan();
    } else toast((r && r.msg) || 'import failed');
  };
  rd.readAsDataURL(file);
}

function renderTip() {
  const grid = $('#tipGrid'); grid.innerHTML = '';
  (DONATE.methods || []).forEach(m => {
    const card = document.createElement('div'); card.className = 'tip-card';
    const accepts = (m.accepts || []).map(a => `<span class="tip-chip">${a}</span>`).join('');
    card.innerHTML = `
      <div class="tip-card-head"><span class="tip-coin">${m.label}</span><span class="tip-sym">${m.symbol || ''}</span></div>
      <img class="tip-qr" src="/static/qr/${m.id}.svg" alt="${m.symbol} address QR">
      <div class="tip-accepts">${accepts}</div>
      <div class="tip-addr-row">
        <code class="tip-addr" title="${m.address}">${m.address}</code>
        <button class="tip-copy" data-addr="${m.address}" data-sym="${m.symbol}">copy</button>
      </div>`;
    card.querySelector('.tip-copy').onclick = async (e) => {
      const b = e.currentTarget;
      try { await navigator.clipboard.writeText(b.dataset.addr); }
      catch (_) { const t = document.createElement('textarea'); t.value = b.dataset.addr; document.body.appendChild(t); t.select(); document.execCommand('copy'); t.remove(); }
      b.textContent = 'copied ✓'; b.classList.add('done');
      toast(`${b.dataset.sym} address copied — thank you 🙏`);
      setTimeout(() => { b.textContent = 'copy'; b.classList.remove('done'); }, 1600);
    };
    grid.appendChild(card);
  });
}
function renderBrowser(filter) {
  const grid = $('#browserGrid'); grid.innerHTML = '';
  const f = (filter || '').trim().toLowerCase();
  const cur = editPreset();
  STATE.presets.filter(p => !f || p.name.includes(f) || (p.description || '').toLowerCase().includes(f)).forEach(p => {
    const c = document.createElement('div');
    c.className = 'card' + (p.name === cur ? ' active' : '') + (p.custom ? ' custom' : '');
    const customBtns = p.custom ? `<button class="cardx rename" title="rename">✎</button><button class="cardx del" title="delete">🗑</button>` : '';
    c.innerHTML = `<div class="nm">${p.name}${p.custom ? '<span class="cust-tag">custom</span>' : ''}</div><div class="desc">${p.description || ''}</div>
      <div class="meta"><span class="chip">${p.voice_count} voices</span>${p.has_drone ? '<span class="chip">drone</span>' : ''}${customBtns}<button class="play" title="audition">▶</button></div>`;
    c.onclick = (e) => { if (e.target.closest('.play,.cardx')) return; assignPreset(p.name); };
    c.querySelector('.play').onclick = (e) => { e.stopPropagation(); api.post('/api/audition', { name: p.name }); toast(`auditioning <span class="g">${p.name}</span>`); };
    if (p.custom) {
      c.querySelector('.del').onclick = (e) => { e.stopPropagation(); deletePreset(p.name); };
      c.querySelector('.rename').onclick = (e) => { e.stopPropagation(); renamePreset(p.name); };
    }
    grid.appendChild(c);
  });
}
async function assignPreset(name) {
  if (FOCUS.kind === 'global') {
    await api.post('/api/preset/use', { name });
    STATE.active = name; $('#npName').textContent = name; toast(`default → <span class="g">${name}</span>`);
  } else {
    const s = FOCUS.s;
    await api.post('/api/session/pin', { id: s.id, preset: name });
    s.preset = name; s.pinned = name; s.source = 'pin'; toast(`<span class="g">${s.base}</span> → ${name}`);
  }
  closeBrowser(); renderRail(); loadFocus();
}

/* ---------------- voices (Mix) ---------------- */
const DELAYS = [
  { v: null, label: 'dry' }, { v: { ms: 220, feedback: 0.20, count: 2 }, label: 'subtle' },
  { v: { ms: 320, feedback: 0.30, count: 3 }, label: 'med' }, { v: { ms: 500, feedback: 0.40, count: 4 }, label: 'long' },
  { v: { ms: 700, feedback: 0.50, count: 5 }, label: 'echo' },
];
function delayIdx(d) { if (!d) return 0; let b = 0; DELAYS.forEach((o, i) => { if (o.v && o.v.ms === d.ms && o.v.count === d.count) b = i; }); return b; }

function renderVoices() {
  const wrap = $('#voices'); wrap.innerHTML = '';
  const P = editPreset();
  DETAIL.voices.forEach((v, i) => {
    const row = document.createElement('div'); row.className = 'vrow'; row.dataset.voice = v.name;
    const col = PALETTE[i % PALETTE.length]; const di = delayIdx(v.delay);
    row.innerHTML = `
      <span class="orb" style="--c:${col}"></span>
      <span class="vname" title="click to hear ${v.name}">${v.name}</span>
      <div class="controls">
        <div class="ctl"><span class="k" title="how loud this sound is">volume</span><input type="range" class="r gain" min="0" max="1" step="0.01" value="${v.gain}" title="how loud this sound is"><span class="val gv">${fmt(v.gain,2)}</span></div>
        <div class="ctl"><span class="k" title="echoey space / wash around the sound">reverb</span><input type="range" class="r rev wet" min="0" max="1" step="0.01" value="${v.reverb.wet||0}" title="echoey space / wash around the sound"><span class="val wv">${fmt(v.reverb.wet||0,2)}</span></div>
        <div class="ctl"><span class="k" title="shortest gap between repeats — higher = sparser">min gap</span><input class="numbox mioi" type="number" min="0.02" max="60" step="0.05" value="${v.mioi}" title="shortest gap between repeats, in seconds"><span class="k">s</span></div>
        <div class="ctl"><span class="k" title="trailing repeats, like a delay pedal">echo</span><div class="chips">${DELAYS.map((o,j)=>`<button class="dchip${j===di?' on':''}" data-j="${j}" title="${o.label} echo">${o.label}</button>`).join('')}</div></div>
        <div class="ctl"><span class="k" title="tiny random pitch wobble so repeats feel alive, not robotic">wobble</span><div class="toggle mini${v.rate_jitter?' on':''}" title="tiny random pitch wobble so repeats feel alive"><span class="tk"></span></div></div>
      </div>
      <button class="vswap" title="swap in a different sound for this voice">↺ swap</button>
      <button class="vplay" title="hear this voice">▶</button>`;
    const g = row.querySelector('.gain'); setFill(g);
    g.oninput = () => { row.querySelector('.gv').textContent = fmt(g.value,2); setFill(g); };
    g.onchange = () => api.post('/api/voice', { preset: P, voice: v.name, field: 'gain', value: +g.value });
    const w = row.querySelector('.wet'); setFill(w);
    w.oninput = () => { row.querySelector('.wv').textContent = fmt(w.value,2); setFill(w); };
    w.onchange = () => { if (!v.regenable) { toast('reverb fixed (no renderer)'); return; } api.post('/api/voice/reverb', { preset: P, voice: v.name, wet: +w.value }); toast(`re-rendering <span class="g">${v.name}</span>…`); };
    row.querySelectorAll('.dchip').forEach(ch => ch.onclick = () => { const o = DELAYS[+ch.dataset.j];
      row.querySelectorAll('.dchip').forEach(x => x.classList.remove('on')); ch.classList.add('on');
      if (!o.v) api.post('/api/voice/delay', { preset: P, voice: v.name, off: true });
      else api.post('/api/voice/delay', { preset: P, voice: v.name, ms: o.v.ms, feedback: o.v.feedback, count: o.v.count }); });
    const mi = row.querySelector('.mioi'); mi.onchange = () => api.post('/api/voice', { preset: P, voice: v.name, field: 'mioi', value: +mi.value });
    const jt = row.querySelector('.toggle'); jt.onclick = () => { const on = !jt.classList.contains('on'); jt.classList.toggle('on', on); api.post('/api/voice', { preset: P, voice: v.name, field: 'rate_jitter', value: on }); };
    const play = () => { api.post('/api/voice/play', { preset: P, voice: v.name }); flare(v.name); };
    row.querySelector('.vplay').onclick = play; row.querySelector('.vname').onclick = play;
    row.querySelector('.vswap').onclick = () => openSwap(v.name);
    wrap.appendChild(row);
  });
}

/* event ↔ voice cross-link: jump from an event row (or a constellation orb)
   to that voice's controls in the rack below — scroll there and flash it */
function scrollFlashVoice(name) {
  if (!name || name === '__none__') return;
  const sp = $('.tabpanel[data-panel="sounds"]'); if (!sp || sp.hidden) return;
  const row = $(`.vrow[data-voice="${cssEsc(name)}"]`); if (!row) return;
  row.scrollIntoView({ behavior: 'smooth', block: 'center' });
  row.classList.remove('flash'); void row.offsetWidth;    // restart the animation
  row.classList.add('flash');
  setTimeout(() => row.classList.remove('flash'), 1700);
}

function playMapped(row, label) {
  const sel = row.querySelector('select.vsel');
  const voice = sel ? sel.value : null;
  if (!voice || voice === '__none__') { toast(`<span class="g">${label}</span> is silent`); return; }
  api.post('/api/voice/play', { preset: editPreset(), voice });
  flare(voice);
  toast(`<span class="g">${label}</span> → ${voice}`);
}
function renderEvents() {
  const wrap = $('#events'); wrap.innerHTML = ''; const P = editPreset();
  const opts = (sel) => ['<option value="__none__"' + (sel == null ? ' selected' : '') + '>— silent —</option>']
    .concat(DETAIL.voice_names.map(n => `<option ${n === sel ? 'selected' : ''}>${n}</option>`)).join('');

  const tools = document.createElement('div'); tools.className = 'etools';
  tools.innerHTML = `<span class="etools-note">each row is a moment in Claude's work → the sound it plays. A dot glows when it just fired; the bar shows how often.</span>
    <button class="esort${SORT_BY_FREQ ? ' on' : ''}" id="esort" title="reorder with the most-used events on top">↕ most used</button>
    <button class="ereset" id="ereset" title="reset the usage bars to zero">reset</button>`;
  tools.querySelector('#esort').onclick = () => { SORT_BY_FREQ = !SORT_BY_FREQ; renderEvents(); };
  tools.querySelector('#ereset').onclick = async () => { await api.post('/api/counts/reset', { name: P }); EVT_COUNTS = {}; toast('fire counts reset'); paintFreq(); };
  wrap.appendChild(tools);

  let evs = DETAIL.events.slice();
  if (SORT_BY_FREQ) evs.sort((a, b) => (EVT_COUNTS[b.event] || 0) - (EVT_COUNTS[a.event] || 0));

  evs.forEach(ev => {
    const g = document.createElement('div'); g.className = 'egroup'; g.dataset.event = ev.event;
    const row = document.createElement('div'); row.className = 'erow'; row.dataset.event = ev.event;
    row.innerHTML = `<span class="edot"></span><span class="elabel" title="click to preview this sound"><span class="ename">${evTitle(ev.event)}</span><span class="edesc">${evDesc(ev.event)}</span><span class="etech">${ev.event}</span><span class="ecount" data-event="${ev.event}"></span></span><select class="vsel ${ev.default==null?'silent':''}" title="the sound this moment plays">${opts(ev.default)}</select><button class="ejump" title="open this sound's controls below">✎</button><i class="efreq" data-event="${ev.event}"></i>`;
    row.querySelector('select').onchange = e => { api.post('/api/map', { preset: P, event: ev.event, key: 'default', voice: e.target.value }); e.target.classList.toggle('silent', e.target.value === '__none__'); };
    row.querySelector('.elabel').onclick = () => playMapped(row, ev.event);
    row.querySelector('.ejump').onclick = () => scrollFlashVoice(row.querySelector('select').value);
    g.appendChild(row);
    Object.entries(ev.by_tool).forEach(([tool, voice]) => {
      const sr = document.createElement('div'); sr.className = 'erow sub';
      sr.innerHTML = `<span></span><span class="elabel" title="click to preview this sound"><span class="ename">only the ${tool} tool</span><span class="ekey">override</span></span><select class="vsel ${voice==null?'silent':''}" title="a special sound just for the ${tool} tool">${opts(voice)}</select><button class="ejump" title="open this sound's controls below">✎</button>`;
      sr.querySelector('select').onchange = e => api.post('/api/map', { preset: P, event: ev.event, key: tool, voice: e.target.value });
      sr.querySelector('.elabel').onclick = () => playMapped(sr, tool);
      sr.querySelector('.ejump').onclick = () => scrollFlashVoice(sr.querySelector('select').value);
      g.appendChild(sr);
    });
    if (ev.on_failure !== null && ev.on_failure !== undefined) {
      const ofv = ev.on_failure === '__none__' ? null : ev.on_failure;
      const sr = document.createElement('div'); sr.className = 'erow sub';
      sr.innerHTML = `<span></span><span class="elabel" title="click to preview this sound"><span class="ename">…but if it failed</span><span class="ekey">on error</span></span><select class="vsel ${ofv==null?'silent':''}" title="plays instead when the tool errored">${opts(ofv)}</select><button class="ejump" title="open this sound's controls below">✎</button>`;
      sr.querySelector('select').onchange = e => api.post('/api/map', { preset: P, event: ev.event, key: 'on_failure', voice: e.target.value });
      sr.querySelector('.elabel').onclick = () => playMapped(sr, 'on failure');
      sr.querySelector('.ejump').onclick = () => scrollFlashVoice(sr.querySelector('select').value);
      g.appendChild(sr);
    }
    wrap.appendChild(g);
  });
  paintFreq();
}
function paintFreq() {
  if (!DETAIL || !DETAIL.events) return;
  const maxc = Math.max(1, ...DETAIL.events.map(e => EVT_COUNTS[e.event] || 0));
  DETAIL.events.forEach(e => {
    const c = EVT_COUNTS[e.event] || 0;
    const cn = $(`.ecount[data-event="${cssEsc(e.event)}"]`); if (cn) cn.textContent = c ? `×${c}` : '';
    const bar = $(`.efreq[data-event="${cssEsc(e.event)}"]`); if (bar) bar.style.width = (100 * c / maxc).toFixed(1) + '%';
  });
}
function maybeSortEvents() {
  if (!SORT_BY_FREQ) return;
  const wrap = $('#events'); if (!wrap) return;
  const focused = document.activeElement && document.activeElement.closest && document.activeElement.closest('#events select');
  if (focused) return;                     // don't yank rows out from under an open dropdown
  const groups = [...wrap.querySelectorAll('.egroup')];
  const sorted = groups.slice().sort((a, b) => (EVT_COUNTS[b.dataset.event] || 0) - (EVT_COUNTS[a.dataset.event] || 0));
  if (sorted.some((g, i) => g !== groups[i])) sorted.forEach(g => wrap.appendChild(g));
}

function renderSettings() {
  const wrap = $('#settings'); wrap.innerHTML = '';
  const rows = [
    { lab: 'Master gain', small: 'overall volume', val: STATE.master_gain, change: v => { api.post('/api/master', { gain: v }); STATE.master_gain = v; $('#master').value = v; setFill($('#master')); $('#masterVal').textContent = fmt(v,2); } },
  ];
  rows.forEach(r => {
    const el = document.createElement('div'); el.className = 'setrow';
    el.innerHTML = `<div class="lab">${r.lab}<small>${r.small}</small></div><div style="display:flex;align-items:center;gap:10px">
      <input type="range" class="r" min="0" max="1" step="0.01" value="${r.val}" style="width:130px"><span class="val" style="font:11px/1 var(--mono);color:var(--muted);min-width:34px">${fmt(r.val,2)}</span></div>`;
    const inp = el.querySelector('input'); setFill(inp);
    inp.oninput = () => { el.querySelector('.val').textContent = fmt(inp.value,2); setFill(inp); };
    inp.onchange = () => r.change(+inp.value); wrap.appendChild(el);
  });
  renderDrone(wrap);
  // Reverb space lives in the always-visible stage header (the "reverb space"
  // knob), so it isn't duplicated here — just point people at it.
  const note = document.createElement('div'); note.className = 'setrow setrow-note';
  note.innerHTML = `<div class="lab">Reverb space<small>hall size · the “reverb space” knob up in the stage header</small></div>`;
  wrap.appendChild(note);
}

/* always-visible drone toggle in the stage header (the easy switch — full
   controls live in Setup). Shown whenever the ACTIVE preset has a drone. */
function paintDroneTop() {
  const w = $('#droneWrap'); if (!w) return;
  const d = STATE.drone || {};
  w.hidden = !d.available;
  if (d.available) {
    $('#droneTop').classList.toggle('on', !!d.running);
    $('#droneTopVal').textContent = d.running ? 'humming' : 'off';
  }
}
async function toggleDroneTop() {
  const d = STATE.drone || {};
  const on = !d.running;
  const r = await api.post(on ? '/api/drone/start' : '/api/drone/stop', {});
  if (r.drone) STATE.drone = r.drone;
  if (on && r.ok === false) { toast(r.msg || 'no drone'); return; }
  paintDroneTop();
  const sp = $('.tabpanel[data-panel="setup"]'); if (sp && !sp.hidden) renderSettings();
  toast(on ? 'drone <span class="g">on</span> — it follows your root' : 'drone off');
}

/* drone bed: on/off + gain + follow-the-chords. The drone always follows the
   live root note (mic-jam included) — retuning within ~½s, so you can hear
   the bed bend as you hum. Off by default; only presets with a drone qualify. */
function renderDrone(wrap) {
  const d = STATE.drone || { available: false, running: false, follow_chords: false, gain: 0.45 };
  const el = document.createElement('div'); el.className = 'setrow dronerow';
  if (!d.available) {
    el.innerHTML = `<div class="lab">Drone bed<small>this preset has no drone — try <b>cathedral</b></small></div>
      <div class="toggle" style="opacity:.35;pointer-events:none"><span class="tk"></span></div>`;
    wrap.appendChild(el); return;
  }
  el.innerHTML = `<div class="lab">Drone bed<small>${d.running ? 'humming — it follows the root note live (🎤 too)' : 'off · sustained bed that follows the root note live'}</small></div>
    <div style="display:flex;align-items:center;gap:12px">
      <input type="range" class="r" id="droneGain" min="0" max="1" step="0.01" value="${d.gain}" style="width:96px" title="drone gain">
      <span class="val" id="droneGainVal" style="font:11px/1 var(--mono);color:var(--muted);min-width:30px">${fmt(d.gain,2)}</span>
      <div class="toggle${d.running ? ' on' : ''}" id="droneOn" title="start/stop the drone"><span class="tk"></span></div>
    </div>`;
  const fl = document.createElement('div'); fl.className = 'setrow';
  fl.innerHTML = `<div class="lab">Drone follows chords<small>walk the progression's roots instead of holding A · needs a progression on</small></div>
    <div class="toggle${d.follow_chords ? ' on' : ''}" id="droneFollow"><span class="tk"></span></div>`;
  const g = el.querySelector('#droneGain'); setFill(g);
  g.oninput = () => { el.querySelector('#droneGainVal').textContent = fmt(g.value,2); setFill(g); };
  g.onchange = () => { api.post('/api/drone', { gain: +g.value }); STATE.drone_gain = +g.value; };
  el.querySelector('#droneOn').onclick = async (e) => {
    const on = !e.currentTarget.classList.contains('on');
    const r = await api.post(on ? '/api/drone/start' : '/api/drone/stop', {});
    if (r.drone) STATE.drone = r.drone;
    if (on && r.ok === false) { toast(r.msg || 'no drone'); return; }
    renderSettings(); paintDroneTop();
    toast(on ? 'drone <span class="g">on</span> — it follows your root' : 'drone off');
  };
  fl.querySelector('#droneFollow').onclick = async (e) => {
    const on = !e.currentTarget.classList.contains('on');
    e.currentTarget.classList.toggle('on', on);
    await api.post('/api/drone/follow', { on });
    if (STATE.drone) STATE.drone.follow_chords = on;
    toast(on ? 'drone walks the <span class="g">chords</span>' : 'drone holds the root');
  };
  wrap.appendChild(el); wrap.appendChild(fl);
}

/* ---------------- music (global defaults) ---------------- */
function renderMusic() {
  const m = STATE.music || {}; const sw = $('#musicScale'); sw.innerHTML = '';
  const f = document.createElement('div'); f.className = 'field';
  f.innerHTML = `<div class="flab">Scale<small>the set of notes everything is allowed to play — the room's mood</small></div>
    <div class="fctl"><select class="vsel" id="scaleSel"><option value="__none__"${!m.scale_global?' selected':''}>preset default</option>
      ${(m.scales||[]).map(s => `<option ${s===m.scale_global?'selected':''}>${s}</option>`).join('')}</select></div>`;
  f.querySelector('#scaleSel').onchange = e => { api.post('/api/scale', { name: e.target.value === '__none__' ? null : e.target.value }); toast(`global scale → ${e.target.value === '__none__' ? 'preset default' : e.target.value}`); };
  sw.appendChild(f);

  // Root note — pick any of the 12; the whole room transposes live (samples
  // stay rendered at A=432, the shift happens at playback). 🎤 Listen drives
  // this too, so the select always shows where the room currently sits.
  const rf = document.createElement('div'); rf.className = 'field';
  const note = m.root_note || 'A', off = m.root_offset || 0;
  rf.innerHTML = `<div class="flab">Root note<small>${off ? `re-keyed ${off>0?'+':''}${off} from A · everything transposed live` : 'pick a key — everything transposes live, no re-render'}</small></div>
    <div class="fctl rootctl">
      <select class="vsel" id="rootSel" style="min-width:72px">${NOTE_N.map((n, pc) => `<option value="${pc}"${n === note ? ' selected' : ''}>${n}</option>`).join('')}</select>
      <button class="btn ghost" id="rootReset"${off ? '' : ' disabled'}>↺ A</button></div>`;
  const setRoot = async (body, label) => {
    const r = await api.post('/api/root', body);
    if (STATE.music) { STATE.music.root_offset = r.root_offset; STATE.music.root_note = r.root_note; }
    renderMusic(); toast(`root → <span class="g">${label || r.root_note}</span>`);
  };
  rf.querySelector('#rootSel').onchange = e => setRoot({ pc: +e.target.value });
  rf.querySelector('#rootReset').onclick = () => setRoot({ clear: true }, 'A');
  sw.appendChild(rf);
  renderChords(sw);

  const rw = $('#musicRhythm'); rw.innerHTML = '';
  const q = m.quant || { enabled: false, bpm: 120, grid: 0.5 };
  const qf = document.createElement('div'); qf.className = 'field';
  qf.innerHTML = `<div class="flab">Snap to a beat<small>line sounds up to a tempo instead of free-time (a.k.a. quantize)</small></div><div class="fctl">
    <input class="numbox" id="qbpm" type="number" min="30" max="300" step="1" value="${q.bpm}" title="bpm">
    <select class="vsel" id="qgrid" style="min-width:90px">${[[0.25,'16th'],[0.5,'8th'],[1,'quarter'],[2,'half']].map(([v,l])=>`<option value="${v}" ${+q.grid===v?'selected':''}>${l}</option>`).join('')}</select>
    <div class="toggle${q.enabled?' on':''}" id="qtoggle"><span class="tk"></span></div></div>`;
  qf.querySelector('#qtoggle').onclick = (e) => { const on = !e.currentTarget.classList.contains('on'); e.currentTarget.classList.toggle('on', on); api.post('/api/quant', { enabled: on }); toast(`quantize ${on?'on':'off'}`); };
  qf.querySelector('#qbpm').onchange = e => api.post('/api/quant', { bpm: +e.target.value });
  qf.querySelector('#qgrid').onchange = e => api.post('/api/quant', { grid: +e.target.value });
  rw.appendChild(qf);
  const sf = document.createElement('div'); sf.className = 'field';
  if ((m.songs || []).length) {
    sf.innerHTML = `<div class="flab">Global MIDI song<small>drive melodies from a MIDI file</small></div><div class="fctl">
      <select class="vsel" id="songSel" style="min-width:150px"><option value="__none__"${!m.song_global?' selected':''}>— off (markov) —</option>
      ${m.songs.map(s => `<option ${s===m.song_global?'selected':''}>${s}</option>`).join('')}</select></div>`;
    sf.querySelector('#songSel').onchange = e => api.post('/api/song', { name: e.target.value === '__none__' ? null : e.target.value });
  } else sf.innerHTML = `<div class="flab">MIDI song<small>no songs imported — <code>claudio song import</code></small></div>`;
  rw.appendChild(sf);

  // Jukebox launcher — perform a whole MIDI through the preset (the fun one)
  const jf = document.createElement('div'); jf.className = 'field';
  jf.innerHTML = `<div class="flab">🎹 Jukebox<small>perform a MIDI live — each track plays an event's voice</small></div>
    <div class="fctl"><button class="btn juke-open" id="jukeOpen">Open Jukebox →</button></div>`;
  jf.querySelector('#jukeOpen').onclick = openJuke;
  rw.appendChild(jf);
}

/* ---------------- chord progressions ---------------- */
// A wall-clock cycle of chords the whole room moves through. The chips below
// glow live (same time math the backend uses, so they're always in sync) and
// the current chip sweeps a progress underline toward the next change.
const PROG_PRETTY = { pop: 'Pop (I–V–vi–IV)', doo_wop: 'Doo-wop (I–vi–IV–V)',
  andalusian: 'Andalusian (i–♭VII–♭VI–V)', canon: 'Canon (Pachelbel)', lofi: 'Lo-fi (ii–V–I–vi)' };
function normProg(p) { p = p || {}; return { enabled: !!p.enabled, preset: p.preset, steps: p.steps || [], step_s: +(p.step_s || 8) }; }

function renderChords(sw) {
  const ch = (STATE.music || {}).chords || {}; const prog = normProg(ch.prog);
  const f = document.createElement('div'); f.className = 'field';
  const sel = prog.enabled ? (prog.preset || 'custom') : '__off__';
  f.innerHTML = `<div class="flab">Chord progression<small>${prog.enabled ? 'the whole room moves through these chords, live' : 'cycle the room through chords — the four-chord song, ambient'}</small></div>
    <div class="fctl"><select class="vsel" id="chordSel">
      <option value="__off__"${sel === '__off__' ? ' selected' : ''}>— off —</option>
      ${Object.keys(ch.presets || {}).map(p => `<option value="${p}"${sel === p ? ' selected' : ''}>${PROG_PRETTY[p] || p}</option>`).join('')}
      <option value="custom"${sel === 'custom' ? ' selected' : ''}>custom…</option></select></div>`;
  f.querySelector('#chordSel').onchange = async e => {
    const v = e.target.value; let r;
    if (v === '__off__') r = await api.post('/api/chords', { off: true });
    else if (v === 'custom') r = await api.post('/api/chords', { steps: prog.steps.length >= 2 ? prog.steps : ['A', 'D'], enabled: true });
    else r = await api.post('/api/chords', { preset: v });
    STATE.music.chords.prog = r.progression; renderMusic();
    toast(v === '__off__' ? 'chords off' : `chords → <span class="g">${(r.progression.steps || []).join(' · ')}</span>`);
  };
  sw.appendChild(f);
  if (!prog.enabled || !prog.steps.length) return;

  const sendSteps = async (steps) => {
    const r = await api.post('/api/chords', { steps });
    STATE.music.chords.prog = r.progression; renderMusic();
  };
  const row = document.createElement('div'); row.className = 'chordrow'; row.id = 'chordRow';
  const custom = prog.preset === 'custom';
  prog.steps.forEach((label, i) => {
    const chip = document.createElement('span'); chip.className = 'chord-chip';
    if (custom) {
      chip.innerHTML = `<select class="chip-sel" title="change this chord">${(ch.library || []).map(c => `<option${c === label ? ' selected' : ''}>${c}</option>`).join('')}</select>${prog.steps.length > 2 ? '<button class="chip-x" title="remove">×</button>' : ''}`;
      chip.querySelector('.chip-sel').onchange = e => sendSteps(prog.steps.map((s, j) => j === i ? e.target.value : s));
      const x = chip.querySelector('.chip-x'); if (x) x.onclick = () => sendSteps(prog.steps.filter((_, j) => j !== i));
    } else chip.textContent = label;
    row.appendChild(chip);
  });
  if (custom && prog.steps.length < 8) {
    const add = document.createElement('button'); add.className = 'chip-add'; add.textContent = '+'; add.title = 'add a chord';
    add.onclick = () => sendSteps([...prog.steps, 'A']);
    row.appendChild(add);
  }
  sw.appendChild(row);

  const sf = document.createElement('div'); sf.className = 'field';
  sf.innerHTML = `<div class="flab">Chord length<small>seconds per chord · 8s ≈ 4 bars at 120 BPM</small></div>
    <div class="fctl"><input type="range" class="r" id="chordLen" min="3" max="30" step="1" value="${prog.step_s}">
    <span class="val" style="font:11px/1 var(--mono);color:var(--muted);min-width:26px" id="chordLenVal">${Math.round(prog.step_s)}s</span></div>`;
  const cl = sf.querySelector('#chordLen'); setFill(cl);
  cl.oninput = () => { sf.querySelector('#chordLenVal').textContent = cl.value + 's'; setFill(cl); };
  cl.onchange = async () => { const r = await api.post('/api/chords', { step_s: +cl.value }); STATE.music.chords.prog = r.progression; };
  sw.appendChild(sf);
}

// live chord clock — pure time math, identical to event.py's chord_step()
setInterval(() => {
  const row = $('#chordRow'); if (!row) return;
  const prog = normProg(((STATE.music || {}).chords || {}).prog);
  if (!prog.enabled || !prog.steps.length) return;
  const step_s = Math.max(2, prog.step_s);
  const tsec = Date.now() / 1000;
  const i = Math.floor(tsec / step_s) % prog.steps.length;
  const frac = (tsec % step_s) / step_s;
  [...row.querySelectorAll('.chord-chip')].forEach((c, j) => {
    c.classList.toggle('on', j === i);
    if (j === i) c.style.setProperty('--p', (frac * 100).toFixed(1) + '%'); else c.style.removeProperty('--p');
  });
}, 250);

/* ---------------- preset actions ---------------- */
function renderActions() {
  const w = $('#presetActions'); w.innerHTML = ''; const P = editPreset();
  const acts = [
    { lab: 'Audition', small: 'play a taste of this preset', btn: '▶ play', cls: '', fn: () => { api.post('/api/audition', { name: P }); toast(`auditioning <span class="g">${P}</span>`); } },
    { lab: 'Test events', small: 'fire one of each hook event', btn: 'run test', cls: 'ghost', fn: () => { api.post('/api/test', { name: P }); toast('walking through events…'); } },
    { lab: 'Regenerate samples', small: 'rebuild all WAVs from render.py', btn: 'regenerate', cls: 'ghost', fn: () => { api.post('/api/regen', { name: P }); toast(`re-rendering <span class="g">${P}</span>…`); } },
    { lab: 'Reset preset', small: 'restore preset.json from shipped default', btn: 'reset', cls: 'danger', fn: async () => { const r = await api.post('/api/preset/reset', { name: P }); toast(r.ok ? 'reset to default' : (r.msg || 'no default')); if (r.ok) loadFocus(); } },
  ];
  acts.forEach(a => { const el = document.createElement('div'); el.className = 'actrow';
    el.innerHTML = `<div class="alab">${a.lab}<small>${a.small}</small></div><button class="btn ${a.cls}">${a.btn}</button>`;
    el.querySelector('button').onclick = a.fn; w.appendChild(el); });
}

/* ---------------- rules ---------------- */
function presetOptions(sel, includeNone, noneLabel) {
  const o = includeNone ? [`<option value="__none__"${sel==null?' selected':''}>${noneLabel||'— none —'}</option>`] : [];
  return o.concat(STATE.presets.map(p => `<option ${p.name===sel?'selected':''}>${p.name}</option>`)).join('');
}
function renderRules() {
  const rl = $('#rulesList'); rl.innerHTML = '';
  const rules = STATE.rules || [];
  $('#routeBadge').textContent = rules.length ? String(rules.length) : '';
  if (!rules.length) rl.innerHTML = '<div class="rempty">no directory rules — add one below</div>';
  rules.forEach(r => {
    const el = document.createElement('div'); el.className = 'rule';
    const cond = [r.time && `⏰ ${r.time}`, r.idle_after_s && `idle ${r.idle_after_s}s`].filter(Boolean).map(c => `<span class="rcond">${c}</span>`).join('');
    el.innerHTML = `<span class="rpat">${r.pattern}</span><span class="rarrow">→</span><span class="rpre">${r.preset}</span>${cond}<button class="rx" title="remove">✕</button>`;
    el.querySelector('.rx').onclick = async () => { await api.post('/api/rule/rm', { pattern: r.pattern }); await refreshState(); renderRules(); toast('rule removed'); };
    rl.appendChild(el);
  });
  const rp = $('#rulePreset'); if (rp) rp.innerHTML = presetOptions(editPreset(), false);
  const addBtn = $('#ruleAdd');
  if (addBtn && !addBtn.dataset.wired) { addBtn.dataset.wired = '1';
    addBtn.onclick = async () => { const pattern = $('#rulePattern').value.trim(); const preset = $('#rulePreset').value;
      if (!pattern) { toast('enter a path pattern'); return; }
      const r = await api.post('/api/rule/add', { pattern, preset });
      if (r.ok) { $('#rulePattern').value = ''; await refreshState(); renderRules(); toast(`rule added → <span class="g">${preset}</span>`); } else toast('could not add rule'); };
  }
}
async function refreshState() { const s = await api.get('/api/state'); STATE.rules = s.rules; STATE.sessions = s.sessions; STATE.music = s.music; }

/* ---------------- global controls ---------------- */
function setTab(name) { $$('.tab').forEach(t => t.classList.toggle('on', t.dataset.tab === name)); $$('.tabpanel').forEach(p => p.hidden = (p.dataset.panel !== name)); }
function wireGlobal() {
  $$('.tab').forEach(t => t.onclick = () => setTab(t.dataset.tab));
  $('#browseBtn').onclick = openBrowser;
  $('#browserClose').onclick = closeBrowser;
  $('#browser').onclick = (e) => { if (e.target.id === 'browser') closeBrowser(); };
  $('#browserSearch').oninput = e => renderBrowser(e.target.value);
  $('#tipBtn').onclick = openTip;
  $('#tipClose').onclick = closeTip;
  $('#tipModal').onclick = (e) => { if (e.target.id === 'tipModal') closeTip(); };
  $('#recBtn').onclick = openRec;
  $('#recClose').onclick = closeRec;
  $('#recModal').onclick = (e) => { if (e.target.id === 'recModal') closeRec(); };
  $('#buildBtn').onclick = openBuilder;
  $('#builderClose').onclick = closeBuilder;
  $('#builder').onclick = (e) => { if (e.target.id === 'builder') closeBuilder(); };
  $('#bSearch').oninput = e => renderPalette(e.target.value);
  $('#bCreate').onclick = builderCreate;
  $('#bDupSel').onchange = renderBuilderSel;
  $$('.b-seg').forEach(s => s.onclick = () => {
    bMode = s.dataset.mode; $$('.b-seg').forEach(x => x.classList.toggle('on', x === s));
    $('#bDupSel').hidden = bMode !== 'dup'; renderBuilderSel();
  });
  $('#swapClose').onclick = closeSwap;
  $('#swap').onclick = (e) => { if (e.target.id === 'swap') closeSwap(); };
  $('#swapSearch').oninput = e => renderSwapPalette(e.target.value);
  $('#helpBtn').onclick = openHelp;
  $('#helpClose').onclick = closeHelp;
  $('#helpModal').onclick = (e) => { if (e.target.id === 'helpModal') closeHelp(); };
  $('#optsBtn').onclick = openOpts;
  $('#optsClose').onclick = closeOpts;
  $('#optsModal').onclick = (e) => { if (e.target.id === 'optsModal') closeOpts(); };
  // first-run welcome — show once, reopenable from the ⋯ menu
  $('#welBtn').onclick = openWelcome;
  $('#welGo').onclick = closeWelcome;
  $('#welcome').onclick = (e) => { if (e.target.id === 'welcome') closeWelcome(); };
  if (!localStorage.getItem('claudio_welcomed')) setTimeout(openWelcome, 500);
  $$('#vizSwitch button').forEach(b => b.onclick = () => setViz(b.dataset.viz));
  // 🎤 Listen — quick tap latches on/off; press-and-hold = listen only while held
  $('#droneTop').onclick = toggleDroneTop;
  const lb = $('#listenBtn'); let pressT = 0, wasOn = false;
  lb.addEventListener('pointerdown', (e) => {
    e.preventDefault();
    pressT = performance.now(); wasOn = MIC.on;
    if (!MIC.on) startListen();
    window.addEventListener('pointerup', () => {
      const held = performance.now() - pressT;
      if (held >= MIC_CFG.holdMs) stopListen();   // momentary hold released → off
      else if (wasOn) stopListen();               // quick tap while on → toggle off
      // quick tap while off → leave it latched on
    }, { once: true });
  });
  window.addEventListener('beforeunload', () => {
    // best-effort revert so closing the tab mid-jam doesn't strand the key
    if (MIC.on && navigator.sendBeacon) {
      const prev = MIC.prevOffset || 0;
      navigator.sendBeacon('/api/root', new Blob(
        [JSON.stringify(prev ? { offset: prev } : { clear: true })], { type: 'application/json' }));
    }
  });
  // overflow "⋯" menu (Help / Tip live in here to keep the bar calm)
  const ofMenu = $('#ofMenu'), ofBtn = $('#ofBtn');
  const closeOf = () => { ofMenu.hidden = true; };
  ofBtn.onclick = (e) => { e.stopPropagation(); ofMenu.hidden = !ofMenu.hidden; };
  $$('#ofMenu button').forEach(b => b.addEventListener('click', closeOf));
  document.addEventListener('click', (e) => { if (!$('#overflow').contains(e.target)) closeOf(); });
  // view switch: Console ⇄ Jukebox (top bar). The brand dot is a fun shortcut to Jukebox.
  $$('.vsw').forEach(b => b.onclick = () => setView(b.dataset.view));
  $('.brand .dot').onclick = openJuke;
  $('#jukeClose').onclick = closeJuke;
  $('#jukeSong').onchange = e => { JUKE.song = e.target.value; loadJukePlan(); };
  $('#jukeTempo').oninput = e => { JUKE.tempo = +e.target.value; $('#jukeTempoVal').textContent = (+e.target.value).toFixed(2) + '×'; if (JUKE.plan) renderJukeMap(); };
  $('#jukeLoop').onclick = e => { JUKE.loop = !JUKE.loop; e.currentTarget.classList.toggle('on', JUKE.loop); };
  $('#jukeImport').onchange = e => { jukeImportFile(e.target.files[0]); e.target.value = ''; };
  document.addEventListener('keydown', e => {
    if (e.key !== 'Escape') return;
    if (!$('#ofMenu').hidden) $('#ofMenu').hidden = true;
    else if (!$('#welcome').hidden) closeWelcome();
    else if (!$('#optsModal').hidden) closeOpts();
    else if (!$('#swap').hidden) closeSwap();
    else if (!$('#builder').hidden) closeBuilder();
    else if (!$('#browser').hidden) closeBrowser();
    else if (!$('#tipModal').hidden) closeTip();
    else if (!$('#recModal').hidden) closeRec();
    else if (!$('#helpModal').hidden) closeHelp();
    else if (VIEW === 'jukebox') closeJuke();
  });
  const m = $('#master');
  m.oninput = () => { $('#masterVal').textContent = fmt(m.value,2); setFill(m); };
  m.onchange = () => { api.post('/api/master', { gain: +m.value }); STATE.master_gain = +m.value; };
  $('#power').onclick = async () => { const willMute = $('#power').classList.contains('on'); setPower(!willMute); document.body.classList.toggle('is-muted', willMute);
    await api.post('/api/mute', { muted: willMute }); STATE.muted = willMute; toast(willMute ? 'claudio <span class="g">muted</span>' : 'claudio <span class="g">live</span>'); };
  const rs = $('#reverbScale');
  rs.oninput = () => { $('#reverbScaleVal').textContent = fmt(rs.value,2)+'×'; setFill(rs); };
  rs.onchange = () => { api.post('/api/reverb_scale', { preset: editPreset(), value: +rs.value }); toast('re-rendering reverb space…'); };
}
async function syncExternal() {
  const s = await api.get('/api/state');
  STATE.presets = s.presets; STATE.rules = s.rules; STATE.music = s.music; STATE.drone = s.drone;
  paintDroneTop();
  if (s.active !== STATE.active) { STATE.active = s.active; $('#npName').textContent = s.active; }
  if (s.muted !== STATE.muted) { STATE.muted = s.muted; setPower(!s.muted); document.body.classList.toggle('is-muted', s.muted); }
  STATE.sessions = s.sessions;
  // refresh per-session mini-track sparklines (slow cadence is fine)
  try {
    const t = await api.get('/api/timelines');
    const sig = JSON.stringify(Object.entries(t).map(([k, v]) => [k, v.count]));
    TIMELINES = t;
    if (sig !== STATE._tlSig) { STATE._tlSig = sig; updateSparks(); }
  } catch { }
}

/* morph sparklines in place — bars ease to new heights (CSS transition) and a
   session's first mini-track slides in, instead of the whole rail re-rendering
   with a hard cut. */
function updateSparks() {
  $$('.srail-item[data-session]').forEach(el => {
    const id = el.dataset.session, t = TIMELINES[id];
    if (!t || !t.count) return;
    let track = el.querySelector('.si-track');
    if (!track) {                       // first events for this session
      const s = (STATE.sessions || []).find(x => x.id === id); if (!s) return;
      el.insertAdjacentHTML('beforeend', railTrackHTML(s));
      const rb = el.querySelector('.si-replay');
      if (rb) rb.onclick = (e) => { e.stopPropagation(); toggleReplay(s); };
      return;
    }
    const spark = track.querySelector('.si-spark'), head = spark.querySelector('.si-head');
    const bars = [...spark.querySelectorAll('i')];
    for (let i = bars.length; i < t.density.length; i++) {   // new buckets grow in
      const b = document.createElement('i'); b.className = 'new';
      spark.insertBefore(b, head); bars.push(b);
    }
    if (bars.length > t.density.length) bars.splice(t.density.length).forEach(b => b.remove());
    const peak = t.peak || 1;
    t.density.forEach((v, i) => { const b = bars[i]; if (!b) return;
      b.style.height = Math.max(8, Math.round(v / peak * 100)) + '%';
      b.style.opacity = (0.3 + 0.7 * v / peak).toFixed(2);
    });
    const ev = track.querySelector('.si-evts'); if (ev) ev.textContent = t.count;
    track.title = `${t.count} events over ${Math.round(t.duration)}s — click ▶ to replay this session`;
  });
}

/* ---------------- live activity ---------------- */
function startActivityLoop() { poll(); setInterval(poll, 280); }
async function poll() {
  const P = editPreset(); if (!P) return;
  let a; try { a = await api.get('/api/activity?name=' + encodeURIComponent(P)); } catch { return; }
  const live = a.heartbeat && (a.now - a.heartbeat < 12) && !a.muted;
  $('#pulse').classList.toggle('live', !!live);
  $('#pulseTxt').textContent = a.muted ? 'muted' : (live ? 'listening' : 'idle');
  Object.entries(a.voices).forEach(([vn, ts]) => { if (ts && ts !== lastVoiceTs[vn]) { if (lastVoiceTs[vn] !== undefined) { flare(vn); MIC.lastFire = performance.now(); } lastVoiceTs[vn] = ts; } paintDot($(`.vrow[data-voice="${cssEsc(vn)}"] .orb`), a.now - ts, true); });
  Object.entries(a.events).forEach(([en, ts]) => { if (ts && ts !== lastEventTs[en]) { if (lastEventTs[en] !== undefined) eventFX(en); lastEventTs[en] = ts; } paintDot($(`.erow[data-event="${cssEsc(en)}"] .edot`), a.now - ts, false); });
  if (a.counts) { EVT_COUNTS = a.counts; paintFreq(); maybeSortEvents(); }
  // live replay state (button + playhead on the rail sparklines). The playhead
  // itself is animated client-side in animReplay — here we just feed it fresh
  // truth (elapsed/duration when available, event idx/total as fallback).
  if (a.midiplay) {
    const mp = a.midiplay;
    const active = !!mp.active && mp.kind === 'replay';
    const pr = mp.progress || {};
    if (active && !REPLAY.active) REPLAY.shown = 0;
    REPLAY.active = active; REPLAY.session = mp.session;
    REPLAY.elapsed = +pr.elapsed || 0; REPLAY.duration = +mp.duration || 0;
    REPLAY.target = pr.total ? Math.min(1, (pr.idx || 0) / pr.total) : 0;
    REPLAY.at = performance.now();
    paintReplay(); animReplayStart();
  }
  // refresh rail when sessions change (not whole stage)
  if (a.sessions) {
    STATE.sessions = a.sessions;
    if (a.active && a.active !== STATE.active) { STATE.active = a.active; $('#npName').textContent = a.active; }
    const sig = JSON.stringify(a.sessions.map(s => [s.id, s.preset, s.pinned, s.scale, s.song, s.ended, Math.floor(s.age / 30)])) + '|' + STATE.active + '|' + FOCUS.kind + (FOCUS.id || '');
    const editing = document.activeElement && document.activeElement.closest && document.activeElement.closest('.session-strip,.browser');
    if (sig !== STATE._sig && !editing) { STATE._sig = sig; renderRail(); }
  }
}
const RECENCY_WINDOW = 45;   // seconds a fired dot lingers as a dim ember before going faint
function paintDot(el, age, isVoice) {
  if (!el) return;
  if (age == null || age > 1e8 || !isFinite(age)) { el.style.background = 'var(--faint)'; el.style.boxShadow = 'none'; el.style.opacity = .5; return; }
  const c = isVoice ? (el.style.getPropertyValue('--c') || 'var(--sage)') : 'var(--sage)';
  // bright flash on fire, then fade almost all the way out and HOLD a faint
  // ember for ~RECENCY_WINDOW so a glance shows what fired recently.
  let op, glow;
  if (age < 0.5) { op = 1; glow = 12; }
  else if (age < 2) { op = 0.8; glow = 5; }
  else if (age < 2 + RECENCY_WINDOW) {
    const k = (age - 2) / RECENCY_WINDOW;        // 0 → 1 across the window
    op = 0.55 - 0.42 * k;                        // ~0.55 down to ~0.13
    glow = 2 * (1 - k);
  } else { el.style.background = 'var(--faint)'; el.style.opacity = .5; el.style.boxShadow = 'none'; return; }
  el.style.background = c; el.style.opacity = op.toFixed(2);
  el.style.boxShadow = glow > 0.3 ? `0 0 ${glow.toFixed(1)}px ${c}` : 'none';
}

/* ---------------- constellation canvas ---------------- */
const sky = $('#sky'); const ctx = sky.getContext('2d');
let nodes = [], rings = [], DPR = Math.min(2, window.devicePixelRatio || 1);
function resizeSky() { const r = sky.parentElement.getBoundingClientRect(); sky.width = r.width * DPR; sky.height = r.height * DPR; sky.style.width = r.width + 'px'; sky.style.height = r.height + 'px'; layoutNodes(); }
window.addEventListener('resize', resizeSky);
function buildNodes() { nodes = (DETAIL ? DETAIL.voices : []).map((v, i) => ({ name: v.name, gain: v.gain, col: PALETTE[i % PALETTE.length], fire: 0, x: 0, y: 0, rad: 0, ang: 0, phase: i * 1.7, base: 5 + Math.min(11, (v.gain || .4) * 13),
  ox: 0, oy: 0, ovx: 0, ovy: 0, pulses: [] })); resizeSky(); }   // ox/oy: spring displacement (burst push) · pulses: tides swells
let SKY = { cx: 0, cy: 0, sx: 1, sy: 1 };
function layoutNodes() { const W = sky.width, H = sky.height; SKY.cx = W / 2; SKY.cy = H * 0.5; const GA = Math.PI * (3 - Math.sqrt(5)); const maxR = Math.sqrt(Math.max(1, nodes.length - 1) + 0.6); SKY.sx = (W * 0.40) / maxR; SKY.sy = (H * 0.34) / maxR; nodes.forEach((n, i) => { n.rad = Math.sqrt(i + 0.6); n.ang = i * GA - Math.PI / 2; }); }
/* activity energy: every fire feeds it, it decays slowly — the aurora, web
   brightness and node swell all breathe with how busy the session actually is */
let MOTES = [], PARTS = [], ENERGY = 0, nextGlint = 0;
function vizLevel() { return Math.min(1, OPTS.energy); }
function flare(name) { const n = nodes.find(x => x.name === name); if (!n) return;
  n.fire = 1;
  ENERGY = Math.min(1, ENERGY + 0.16);
  const now = performance.now();
  if (OPTS.viz === 'tides') {                       // a swell sets off along this voice's ribbon
    if (n.pulses.length < 6) n.pulses.push({ t0: now });
    return;
  }
  if (OPTS.viz === 'pond') {                        // one big slow ripple on the water
    rings.push({ x: n.x, y: n.y, t: now, col: n.col, r0: 2 * DPR, life: 3600, grow: 120 });
    return;
  }
  if (OPTS.viz === 'flow') {                        // inject bright particles into the current
    for (let i = 0; i < 10 && PARTS.length < 240; i++) {
      const a = Math.random() * 6.283, s = (0.5 + Math.random()) * DPR;
      PARTS.push({ kind: 'jet', x: n.x, y: n.y, vx: Math.cos(a) * s, vy: Math.sin(a) * s,
        t0: now, life: 2200 + Math.random() * 1800, col: n.col, tr: [] });
    }
    return;
  }
  if (OPTS.viz === 'gravity') {                     // fling orbiters that the wells catch
    for (let i = 0; i < 16 && PARTS.length < 260; i++) {
      const a = (i / 16) * 6.283 + Math.random() * 0.4, s = (2.2 + Math.random() * 2.2) * DPR;
      PARTS.push({ x: n.x, y: n.y, vx: Math.cos(a) * s, vy: Math.sin(a) * s,
        t0: now, life: 5200 + Math.random() * 3000, col: n.col, tr: [] });
    }
    return;
  }
  rings.push({ x: n.x, y: n.y, t: performance.now(), col: n.col, r0: n.base * DPR });
  spawnMotes(n, Math.round((2 + Math.random() * 2) * OPTS.energy));
  // burst push: shove nearby orbs away from the one that just sang; the spring
  // in positionNodes eases them home, so the constellation moves as one fabric
  const R = 150 * DPR;
  nodes.forEach(o => { if (o === n) return; const dx = o.x - n.x, dy = o.y - n.y, d = Math.hypot(dx, dy);
    if (d < R && d > 1) { const f = (1 - d / R) * 2.4 * DPR; o.ovx += dx / d * f; o.ovy += dy / d * f; } });
}
/* motes: tiny embers that drift up off a voice when it sings, then fade */
function spawnMotes(n, count) {
  for (let i = 0; i < count && MOTES.length < 90; i++) {
    const a = Math.random() * Math.PI * 2, sp = (0.10 + Math.random() * 0.28) * DPR;
    MOTES.push({ x: n.x, y: n.y, vx: Math.cos(a) * sp, vy: Math.sin(a) * sp - 0.16 * DPR,
      t0: performance.now(), life: 2400 + Math.random() * 2400, col: n.col,
      r: (0.8 + Math.random() * 1.5) * DPR, ph: Math.random() * 7 });
  }
}
/* ---- event-aware FX: the visuals narrate WHAT Claude did, not just that a
   voice fired. A finished turn (Stop) breaks like a wave of light; a sub-agent
   return is a smaller echo; "needs you" pulses the edges; session start/end
   sweep and fade. Drawn as a full-canvas overlay so it works in every mode. */
let FX = [];
const EVENT_FX = {
  Stop:         { type: 'shock',   big: true, veil: 0.14, life: 2300, col: () => ACCENT.hi },
  SubagentStop: { type: 'shock',              life: 1500, col: () => '#8fc0a6' },
  Notification: { type: 'edge',               life: 1500, col: () => '#e58c66' },
  SessionStart: { type: 'sweep',              life: 1700, col: () => ACCENT.gold },
  SessionEnd:   { type: 'veil',               life: 1700, col: () => '#8ab6d6' },
  PreCompact:   { type: 'implode',            life: 1300, col: () => '#b39ddb' },
};
function eventFX(name) {
  const d = EVENT_FX[name]; if (!d) return;            // tool calls stay calm so big moments pop
  ENERGY = Math.min(1, ENERGY + (d.big ? 0.45 : 0.2));
  FX.push({ type: d.type, big: !!d.big, veil: d.veil || 0, life: d.life, col: d.col(), t0: performance.now() });
  if (FX.length > 24) FX.shift();
}
function drawFX(now) {
  if (!FX.length) return;
  const W = sky.width, H = sky.height, diag = Math.hypot(W, H);
  FX = FX.filter(f => now - f.t0 < f.life);
  FX.forEach(f => {
    const p = (now - f.t0) / f.life, e = 1 - (1 - p) * (1 - p);   // ease-out
    if (f.type === 'shock') {
      const maxR = diag * (f.big ? 0.6 : 0.34), rad = e * maxR;
      if (f.veil) { ctx.fillStyle = hexA(f.col, f.veil * (1 - p) * (1 - p)); ctx.fillRect(0, 0, W, H); }
      ctx.strokeStyle = hexA(f.col, (1 - p) * (f.big ? 0.55 : 0.4)); ctx.lineWidth = (1 - p) * (f.big ? 6 : 3) * DPR + 0.5;
      ctx.beginPath(); ctx.arc(SKY.cx, SKY.cy, rad, 0, 7); ctx.stroke();
      ctx.strokeStyle = hexA(f.col, (1 - p) * 0.22); ctx.lineWidth = (1 - p) * 2 * DPR + 0.4;
      ctx.beginPath(); ctx.arc(SKY.cx, SKY.cy, rad * 0.62, 0, 7); ctx.stroke();
    } else if (f.type === 'edge') {
      const a = Math.sin(p * Math.PI) * 0.55;
      const g = ctx.createRadialGradient(SKY.cx, SKY.cy, W * 0.18, SKY.cx, SKY.cy, W * 0.62);
      g.addColorStop(0, 'rgba(0,0,0,0)'); g.addColorStop(1, hexA(f.col, a));
      ctx.fillStyle = g; ctx.fillRect(0, 0, W, H);
    } else if (f.type === 'sweep') {
      const x = e * W, w = W * 0.16;
      const g = ctx.createLinearGradient(x - w, 0, x + w, 0);
      g.addColorStop(0, 'rgba(0,0,0,0)'); g.addColorStop(0.5, hexA(f.col, (1 - p) * 0.22)); g.addColorStop(1, 'rgba(0,0,0,0)');
      ctx.fillStyle = g; ctx.fillRect(0, 0, W, H);
    } else if (f.type === 'veil') {
      ctx.fillStyle = hexA(f.col, Math.sin(p * Math.PI) * 0.13); ctx.fillRect(0, 0, W, H);
    } else if (f.type === 'implode') {
      const rad = (1 - e) * diag * 0.5;
      ctx.strokeStyle = hexA(f.col, (1 - p) * 0.45); ctx.lineWidth = 2 * DPR;
      ctx.beginPath(); ctx.arc(SKY.cx, SKY.cy, rad, 0, 7); ctx.stroke();
    }
  });
}

function skyHit(e) {
  const r = sky.getBoundingClientRect(); const mx = (e.clientX - r.left) * DPR, my = (e.clientY - r.top) * DPR;
  let hit = null, hd = 1e9;
  if (OPTS.viz === 'tides') {       // ribbons: hit anywhere along a voice's row
    nodes.forEach(n => { const d = Math.abs((n._ty ?? -1e9) - my); if (d < hd) { hd = d; hit = n; } });
    const band = Math.max(16 * DPR, sky.height / Math.max(2, nodes.length + 1) * 0.45);
    return (hit && hd < band) ? hit : null;
  }
  nodes.forEach(n => { const d = Math.hypot(n.x - mx, n.y - my); if (d < hd) { hd = d; hit = n; } });
  return (hit && hd < 26 * DPR) ? hit : null;
}
// canvas click = hear it + bloom it, nothing else (never scrolls the page)
sky.addEventListener('click', (e) => { const hit = skyHit(e); if (hit) { api.post('/api/voice/play', { preset: editPreset(), voice: hit.name }); flare(hit.name); toast(`<span class="g">${hit.name}</span> · tune it in the Sounds tab`); } });
let hover = null;
sky.addEventListener('mousemove', (e) => { hover = skyHit(e); sky.style.cursor = hover ? 'pointer' : 'default'; });
const VIZ_HINTS = {
  orbs:    'each orb is a voice · it blooms (and nudges its neighbours) when Claude plays it · click to hear it',
  pond:    'still water · every sound rings out as a ripple · click a seed to hear it',
  tides:   'each ribbon is a voice · a swell rolls down it when it sounds · click one to hear it',
  flow:    'a flowing current · each sound sprays particles that ride the stream · click a source to hear it',
  gravity: 'each voice is a star with real pull · sounds fling orbiters that slingshot around them · click a star to hear it',
};
function setViz(v) {
  if (!VIZ_HINTS[v]) v = 'orbs';
  OPTS.viz = v; saveOpts();
  $$('#vizSwitch button').forEach(b => b.classList.toggle('on', b.dataset.viz === v));
  $('#constHint').textContent = VIZ_HINTS[v];
  MOTES = []; rings = []; PARTS = [];                  // clean slate between worlds
  nodes.forEach(n => { n.ox = n.oy = n.ovx = n.ovy = 0; n.pulses = []; });
}
function startSky() { resizeSky(); setViz(OPTS.viz); requestAnimationFrame(drawSky); }
function drawSky(t) {
  ctx.clearRect(0, 0, sky.width, sky.height);
  const breath = 0.5 + 0.5 * Math.sin(t / 2600);
  ENERGY *= 0.994;                                     // slow exhale (~2s half-life)
  const lv = vizLevel(), now = performance.now();
  if (OPTS.viz === 'tides') { drawTides(t, now, lv, breath); }
  else {
    positionNodes(t);
    if (OPTS.viz === 'pond') drawPond(t, now, lv, breath);
    else if (OPTS.viz === 'flow') drawFlow(t, now, lv, breath);
    else if (OPTS.viz === 'gravity') drawGravity(t, now, lv, breath);
    else drawOrbs(t, now, lv, breath);
  }
  drawFX(now);                                         // event-aware overlay, every mode
  requestAnimationFrame(drawSky);
}

/* trail polyline helper — fading line through a particle's recent points */
function drawTrail(tr, col, a, w) {
  if (tr.length < 4) return;
  ctx.strokeStyle = hexA(col, a); ctx.lineWidth = w; ctx.lineCap = 'round';
  ctx.beginPath(); ctx.moveTo(tr[0], tr[1]);
  for (let i = 2; i < tr.length; i += 2) ctx.lineTo(tr[i], tr[i + 1]);
  ctx.stroke();
}
function nodeSourcesAndHover(now) {
  nodes.forEach(n => { n.fire *= 0.93; const isH = hover === n;
    ctx.fillStyle = hexA(n.col, 0.25 + n.fire * 0.7 + (isH ? .4 : 0));
    ctx.beginPath(); ctx.arc(n.x, n.y, (3 + n.fire * 5) * DPR, 0, 7); ctx.fill();
    if (isH || n.fire > 0.3) { ctx.font = `${10 * DPR}px 'Space Mono', monospace`; ctx.textAlign = 'center';
      ctx.fillStyle = hexA('#f5ecdd', isH ? .95 : n.fire); ctx.fillText(n.name, n.x, n.y - 11 * DPR); } });
}

/* flow: a curl-noise current fills the field; voices live as faint sources and
   each sound injects a bright spray of particles that ride the stream and fade.
   The field itself slowly turns, so it's never the same picture twice. */
function drawFlow(t, now, lv, breath) {
  const W = sky.width, H = sky.height, sc = 0.0017 / DPR, ts = t * 0.00015;
  const field = (x, y) => (Math.sin(x * sc + ts) + Math.cos(y * sc * 1.1 - ts * 0.8)
    + 0.5 * Math.sin((x + y) * sc * 0.6 + ts * 1.4)) * Math.PI;
  const target = Math.round(70 * lv);
  let amb = 0; PARTS.forEach(p => { if (p.kind === 'amb') amb++; });
  while (amb < target) { PARTS.push({ kind: 'amb', x: Math.random() * W, y: Math.random() * H, vx: 0, vy: 0, col: ACCENT.gold, tr: [] }); amb++; }
  PARTS = PARTS.filter(p => p.kind === 'amb' || now - p.t0 < p.life);
  PARTS.forEach(p => {
    const ang = field(p.x, p.y), sp = (p.kind === 'amb' ? 0.85 : 1.3) * DPR;
    p.vx += (Math.cos(ang) * sp - p.vx) * 0.14; p.vy += (Math.sin(ang) * sp - p.vy) * 0.14;
    p.x += p.vx; p.y += p.vy;
    p.tr.push(p.x, p.y); if (p.tr.length > 16) p.tr.splice(0, 2);
    if (p.x < -12 || p.x > W + 12 || p.y < -12 || p.y > H + 12) {
      if (p.kind === 'amb') { p.x = Math.random() * W; p.y = Math.random() * H; p.tr.length = 0; }
      else p.t0 = 0;       // burst that left the field → retire next filter
    }
    const age = p.kind === 'amb' ? 0 : (now - p.t0) / p.life;
    const a = (p.kind === 'amb' ? 0.16 + 0.12 * ENERGY : 0.85 * (1 - age)) * lv;
    drawTrail(p.tr, p.col, a, (p.kind === 'amb' ? 1 : 1.8) * DPR);
    if (p.kind !== 'amb') { ctx.fillStyle = hexA(p.col, a); ctx.beginPath(); ctx.arc(p.x, p.y, 1.6 * DPR, 0, 7); ctx.fill(); }
  });
  nodeSourcesAndHover(now);
}

/* gravity: each voice is a star with real pull; a sound flings orbiters that
   curve, slingshot and settle into arcs around the wells (softened 1/r²). */
function drawGravity(t, now, lv, breath) {
  const W = sky.width, H = sky.height, G = 90 * DPR * DPR, soft = (46 * DPR) ** 2, maxv = 6 * DPR;
  PARTS = PARTS.filter(p => now - p.t0 < p.life && p.x > -60 && p.x < W + 60 && p.y > -60 && p.y < H + 60);
  PARTS.forEach(p => {
    let ax = 0, ay = 0;
    for (const nd of nodes) { const dx = nd.x - p.x, dy = nd.y - p.y, r2 = dx * dx + dy * dy + soft, inv = 1 / Math.sqrt(r2), f = G / r2; ax += dx * inv * f; ay += dy * inv * f; }
    p.vx = (p.vx + ax) * 0.9992; p.vy = (p.vy + ay) * 0.9992;
    const sp = Math.hypot(p.vx, p.vy); if (sp > maxv) { p.vx *= maxv / sp; p.vy *= maxv / sp; }
    p.x += p.vx; p.y += p.vy;
    p.tr.push(p.x, p.y); if (p.tr.length > 20) p.tr.splice(0, 2);
    const age = (now - p.t0) / p.life, a = (age < 0.85 ? 1 : (1 - age) / 0.15) * 0.8 * lv;
    drawTrail(p.tr, p.col, a * 0.7, 1.5 * DPR);
    ctx.fillStyle = hexA(p.col, a); ctx.beginPath(); ctx.arc(p.x, p.y, 1.7 * DPR, 0, 7); ctx.fill();
  });
  // wells: a soft glow + bright core, brighter on fire
  nodes.forEach(n => { n.fire *= 0.95; const isH = hover === n; const rr = (n.base * 0.7 + n.fire * 5) * DPR;
    const g = ctx.createRadialGradient(n.x, n.y, 0, n.x, n.y, rr * 5); g.addColorStop(0, hexA(n.col, 0.45 + n.fire * 0.4)); g.addColorStop(1, hexA(n.col, 0));
    ctx.fillStyle = g; ctx.beginPath(); ctx.arc(n.x, n.y, rr * 5, 0, 7); ctx.fill();
    ctx.fillStyle = hexA('#fff7e6', 0.7 + n.fire * 0.3); ctx.beginPath(); ctx.arc(n.x, n.y, rr * 0.5, 0, 7); ctx.fill();
    if (isH || n.fire > 0.3) { ctx.font = `${10 * DPR}px 'Space Mono', monospace`; ctx.textAlign = 'center';
      ctx.fillStyle = hexA('#f5ecdd', isH ? .95 : n.fire); ctx.fillText(n.name, n.x, n.y - rr - 6 * DPR); } });
  if (t > nextGlint) { nextGlint = t + 5000 + Math.random() * 7000;   // keep the system alive when idle
    if (lv > 0 && nodes.length && PARTS.length < 30) { const n = nodes[(Math.random() * nodes.length) | 0]; n.fire = Math.max(n.fire, 0.4);
      for (let i = 0; i < 10; i++) { const a = Math.random() * 6.283, s = (2.4 + Math.random() * 2) * DPR; PARTS.push({ x: n.x, y: n.y, vx: Math.cos(a) * s, vy: Math.sin(a) * s, t0: now, life: 6000, col: n.col, tr: [] }); } } }
}

/* shared drift + spring physics: home position + slow wander, plus the burst-
   push displacement (ox/oy) that a soft spring always eases back to zero */
function positionNodes(t) {
  const s = t * 0.001, amp = 13 * DPR;
  nodes.forEach(n => { const hx = SKY.cx + SKY.sx * n.rad * Math.cos(n.ang); const hy = SKY.cy + SKY.sy * n.rad * Math.sin(n.ang); const a = n.phase;
    const dx = Math.sin(s * 0.43 + a) + 0.55 * Math.sin(s * 0.91 + a * 1.7) + 0.3 * Math.sin(s * 1.7 + a * 2.6);
    const dy = Math.cos(s * 0.39 + a * 1.3) + 0.55 * Math.cos(s * 0.83 + a * 2.1) + 0.3 * Math.cos(s * 1.5 + a * 1.4);
    n.ovx += -0.022 * n.ox; n.ovy += -0.022 * n.oy;    // spring home
    n.ovx *= 0.93; n.ovy *= 0.93;                       // damping: settle in ~1.5s
    n.ox += n.ovx; n.oy += n.ovy;
    n.x = hx + dx * amp * 0.55 + n.ox; n.y = hy + dy * amp * 0.55 + n.oy; });
}

function drawOrbs(t, now, lv, breath) {
  // aurora: an accent-colored wash that swells with real session activity
  if (lv > 0) {
    const aA = (0.025 + 0.14 * ENERGY) * lv * (0.85 + 0.15 * breath);
    const ag = ctx.createRadialGradient(SKY.cx, SKY.cy * 0.8, 0, SKY.cx, SKY.cy * 0.8, sky.width * 0.46);
    ag.addColorStop(0, `rgba(${ACCENT.rgb.join(',')},${aA.toFixed(3)})`); ag.addColorStop(1, 'rgba(0,0,0,0)');
    ctx.fillStyle = ag; ctx.fillRect(0, 0, sky.width, sky.height);
  }
  // web: brighter when the room is busy; edges flash where a voice just sang
  const WEB = 96 * DPR; ctx.lineWidth = DPR;
  const webBase = 0.05 + 0.10 * ENERGY * lv;
  for (let i = 0; i < nodes.length; i++) for (let j = i + 1; j < nodes.length; j++) { const a = nodes[i], b = nodes[j], d = Math.hypot(a.x - b.x, a.y - b.y); if (d < WEB) {
    const al = Math.min(0.5, webBase * (1 - d / WEB) * (1 + (a.fire + b.fire) * 2.2));
    ctx.strokeStyle = `rgba(244,225,193,${al.toFixed(3)})`; ctx.beginPath(); ctx.moveTo(a.x, a.y); ctx.lineTo(b.x, b.y); ctx.stroke(); } }
  rings = rings.filter(r => now - r.t < (r.life || 1300));
  rings.forEach(r => { const L = r.life || 1300, p = (now - r.t) / L, rad = r.r0 + p * (r.grow || 60) * DPR; ctx.strokeStyle = hexA(r.col, (1 - p) * 0.55); ctx.lineWidth = (1 - p) * 2.4 * DPR + 0.3; ctx.beginPath(); ctx.arc(r.x, r.y, rad, 0, 7); ctx.stroke(); });
  // motes: drifting embers with a slight curl, fading as they rise
  MOTES = MOTES.filter(m => now - m.t0 < m.life);
  MOTES.forEach(m => { const p = (now - m.t0) / m.life;
    m.vx += Math.sin(now * 0.001 + m.ph) * 0.004 * DPR;
    m.x += m.vx; m.y += m.vy;
    const al = (1 - p) * 0.7 * lv;
    ctx.fillStyle = hexA(m.col, al * 0.35); ctx.beginPath(); ctx.arc(m.x, m.y, m.r * 2.6, 0, 7); ctx.fill();
    ctx.fillStyle = hexA(m.col, al); ctx.beginPath(); ctx.arc(m.x, m.y, m.r, 0, 7); ctx.fill(); });
  // idle glints: a rare spontaneous shimmer so the sky never reads as frozen
  if (t > nextGlint) { nextGlint = t + 6000 + Math.random() * 9000;
    if (lv > 0 && nodes.length && ENERGY < 0.12) { const n = nodes[(Math.random() * nodes.length) | 0]; n.fire = Math.max(n.fire, 0.3); spawnMotes(n, 1); } }
  nodes.forEach(n => { n.fire *= 0.92; const twinkle = 0.78 + 0.22 * Math.sin(t * 0.0011 + n.phase * 2.3); const glowPulse = (0.5 + 0.4 * breath) * twinkle; const rr = (n.base * (1 + 0.16 * ENERGY * lv) + n.fire * 6) * DPR; const isH = hover === n;
    const g = ctx.createRadialGradient(n.x, n.y, 0, n.x, n.y, rr * 4.2); g.addColorStop(0, hexA(n.col, (0.5 + n.fire * 0.5) * (isH ? 1 : glowPulse))); g.addColorStop(1, hexA(n.col, 0));
    ctx.fillStyle = g; ctx.beginPath(); ctx.arc(n.x, n.y, rr * 4.2, 0, 7); ctx.fill();
    ctx.fillStyle = hexA(n.col, 0.55 + n.fire * 0.45 + (isH ? .2 : 0)); ctx.beginPath(); ctx.arc(n.x, n.y, rr, 0, 7); ctx.fill();
    ctx.fillStyle = hexA('#fff7e6', 0.5 + n.fire * 0.5); ctx.beginPath(); ctx.arc(n.x, n.y, rr * 0.42, 0, 7); ctx.fill();
    if (isH || n.fire > 0.25) { ctx.font = `${10 * DPR}px 'Space Mono', monospace`; ctx.fillStyle = hexA('#f5ecdd', isH ? 0.95 : n.fire); ctx.textAlign = 'center'; ctx.fillText(n.name, n.x, n.y + rr + 14 * DPR); } });
}

/* pond: every sound is a ripple on still water. Voices are dim seeds in the
   same constellation layout; a fire rings out as one big slow circle with a
   faint inner echo. Silence is the canvas — the rainfall idea, made visible. */
function drawPond(t, now, lv, breath) {
  if (lv > 0) {
    const aA = (0.018 + 0.09 * ENERGY) * lv * (0.85 + 0.15 * breath);
    const ag = ctx.createRadialGradient(SKY.cx, SKY.cy, 0, SKY.cx, SKY.cy, sky.width * 0.5);
    ag.addColorStop(0, `rgba(${ACCENT.rgb.join(',')},${aA.toFixed(3)})`); ag.addColorStop(1, 'rgba(0,0,0,0)');
    ctx.fillStyle = ag; ctx.fillRect(0, 0, sky.width, sky.height);
  }
  rings = rings.filter(r => now - r.t < (r.life || 1300));
  rings.forEach(r => { const L = r.life || 1300, p = (now - r.t) / L, rad = r.r0 + p * (r.grow || 60) * DPR;
    const al = (1 - p) * (1 - p) * 0.5;               // ease-out fade, like water settling
    ctx.lineWidth = (1 - p) * 2 * DPR + 0.4;
    ctx.strokeStyle = hexA(r.col, al); ctx.beginPath(); ctx.arc(r.x, r.y, rad, 0, 7); ctx.stroke();
    ctx.strokeStyle = hexA(r.col, al * 0.45); ctx.beginPath(); ctx.arc(r.x, r.y, rad * 0.78, 0, 7); ctx.stroke(); });
  if (t > nextGlint) { nextGlint = t + 4500 + Math.random() * 8000;   // a drop falls somewhere
    if (lv > 0 && nodes.length) { const n = nodes[(Math.random() * nodes.length) | 0];
      rings.push({ x: n.x, y: n.y, t: now, col: n.col, r0: 2 * DPR, life: 4200, grow: 60 }); } }
  nodes.forEach(n => { n.fire *= 0.94; const isH = hover === n;
    ctx.fillStyle = hexA(n.col, 0.22 + n.fire * 0.7 + (isH ? 0.45 : 0));
    ctx.beginPath(); ctx.arc(n.x, n.y, (2.6 + n.fire * 5) * DPR, 0, 7); ctx.fill();
    if (isH || n.fire > 0.3) { ctx.font = `${10 * DPR}px 'Space Mono', monospace`; ctx.fillStyle = hexA('#f5ecdd', isH ? 0.95 : n.fire * 0.8); ctx.textAlign = 'center'; ctx.fillText(n.name, n.x, n.y + 16 * DPR); } });
}

/* tides: each voice is a flowing ribbon stacked down the canvas; when it sings,
   a luminous swell travels left→right along its line and the ribbon brightens.
   Sampled every ~5px — silky at a fraction of the orb-web cost. */
function drawTides(t, now, lv, breath) {
  const W = sky.width, H = sky.height, N = Math.max(1, nodes.length);
  const gap = H / (N + 1);
  const baseA = Math.min(14 * DPR, gap * 0.33) * (0.65 + 0.5 * ENERGY * lv + 0.1 * breath);
  const step = 5 * DPR;
  nodes.forEach((n, i) => {
    n.fire *= 0.94;
    const yC = gap * (i + 1); n._ty = yC;
    n.x = W - 30 * DPR; n.y = yC;                      // nominal anchor
    n.pulses = n.pulses.filter(p => now - p.t0 < 2800);
    const isH = hover === n;
    const glow = Math.max(n.fire, n.pulses.length ? 0.5 : 0);
    for (let pass = glow > 0.12 || isH ? 0 : 1; pass < 2; pass++) {   // halo pass only when alive
      ctx.beginPath();
      for (let x = 0; x <= W; x += step) {
        let y = yC + Math.sin(x * 0.006 / DPR * (1 + i * 0.07) + t * 0.00042 + n.phase) * baseA
              + Math.sin(x * 0.0023 / DPR + t * 0.00027 + n.phase * 2.1) * baseA * 0.55;
        n.pulses.forEach(p => { const age = (now - p.t0) / 2800, cx = W * age;
          const g = Math.exp(-((x - cx) * (x - cx)) / (2 * Math.pow(W * 0.045, 2)));
          y -= g * baseA * 1.9 * (1 - age); });
        x === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y);
      }
      if (pass === 0) { ctx.strokeStyle = hexA(n.col, 0.10 + glow * 0.16); ctx.lineWidth = 5 * DPR; }
      else { ctx.strokeStyle = hexA(n.col, 0.30 + glow * 0.55 + (isH ? 0.25 : 0)); ctx.lineWidth = 1.5 * DPR; }
      ctx.stroke();
    }
    ctx.font = `${10 * DPR}px 'Space Mono', monospace`; ctx.textAlign = 'right';
    ctx.fillStyle = hexA(n.col, isH ? 0.95 : 0.34 + glow * 0.5);
    ctx.fillText(n.name, W - 10 * DPR, yC - 8 * DPR);
  });
  ctx.textAlign = 'center';                            // restore for other modes
}
function hexA(hex, a) { if (hex[0] !== '#') return hex; const n = parseInt(hex.slice(1), 16); return `rgba(${(n >> 16) & 255},${(n >> 8) & 255},${n & 255},${Math.max(0, Math.min(1, a))})`; }

/* ---------------- options: appearance · headphone mode · visuals ---------------- */
// Per-browser preferences (localStorage) — nothing here touches server config.
// hue: accent hue (null = shipped gold). headphones: output is on headphones, so
// the mic can't hear Claudio → Listen skips its self-filter gap and reacts faster.
// monitor: jam-through — your mic, with Claudio-style reverb+delay, in your ears.
// monMix: monitor wet amount. energy: constellation liveliness (0 calm → 2 lively).
const OPTS = Object.assign({ hue: null, headphones: false, monitor: false, monMix: 0.5, energy: 1, viz: 'tides' },
  JSON.parse(localStorage.getItem('claudio_opts') || '{}'));
let ACCENT = { gold: '#e8b25c', hi: '#ffd98a', rgb: [232, 178, 92] };
const THEME_SWATCHES = [
  { name: 'Gold', hue: null }, { name: 'Ember', hue: 16 }, { name: 'Rose', hue: 345 },
  { name: 'Violet', hue: 268 }, { name: 'Ocean', hue: 205 }, { name: 'Sage', hue: 150 },
];

function saveOpts() { localStorage.setItem('claudio_opts', JSON.stringify(OPTS)); }

function hsl2rgb(h, s, l) {
  const a = s * Math.min(l, 1 - l);
  const f = n => { const k = (n + h / 30) % 12; return Math.round(255 * (l - a * Math.max(-1, Math.min(k - 3, 9 - k, 1)))); };
  return [f(0), f(8), f(4)];
}
const rgbHex = (r) => '#' + r.map(v => v.toString(16).padStart(2, '0')).join('');

function applyTheme() {
  const rt = document.documentElement.style;
  if (OPTS.hue == null) {
    ['--gold', '--gold-hi', '--gold-deep', '--accent-rgb', '--accent-deep-rgb'].forEach(p => rt.removeProperty(p));
    ACCENT = { gold: '#e8b25c', hi: '#ffd98a', rgb: [232, 178, 92] };
  } else {
    // saturation/lightness chosen so every hue lands with the same warmth as the shipped gold
    const base = hsl2rgb(OPTS.hue, 0.70, 0.64), hi = hsl2rgb(OPTS.hue, 0.82, 0.77), deep = hsl2rgb(OPTS.hue, 0.62, 0.49);
    rt.setProperty('--gold', rgbHex(base)); rt.setProperty('--gold-hi', rgbHex(hi)); rt.setProperty('--gold-deep', rgbHex(deep));
    rt.setProperty('--accent-rgb', base.join(',')); rt.setProperty('--accent-deep-rgb', deep.join(','));
    ACCENT = { gold: rgbHex(base), hi: rgbHex(hi), rgb: base };
  }
  // constellation + favicon follow the accent
  PALETTE[0] = ACCENT.gold; PALETTE[1] = ACCENT.hi;
  const fav = document.querySelector('link[rel="icon"]');
  if (fav) fav.href = `data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'%3E%3Ccircle cx='16' cy='16' r='9' fill='%23${ACCENT.gold.slice(1)}'/%3E%3C/svg%3E`;
  if (typeof DETAIL !== 'undefined' && DETAIL) buildNodes();
}

function openOpts() { renderOpts(); $('#optsModal').hidden = false; }
function closeOpts() { $('#optsModal').hidden = true; }

function openWelcome() { $('#ofMenu').hidden = true; $('#welcome').hidden = false; }
function closeWelcome() { $('#welcome').hidden = true; localStorage.setItem('claudio_welcomed', '1'); }

function renderOpts() {
  const w = $('#optsBody'); w.innerHTML = '';
  // — appearance —
  const ap = document.createElement('div'); ap.className = 'opts-sect';
  ap.innerHTML = `<h4>Appearance</h4>
    <div class="opts-row"><div class="lab">Accent<small>recolors the whole console — orbs, glows, sparklines</small></div>
      <div class="swatches">${THEME_SWATCHES.map(t => {
        const rgb = t.hue == null ? [232, 178, 92] : hsl2rgb(t.hue, 0.70, 0.64);
        const on = (t.hue == null && OPTS.hue == null) || t.hue === OPTS.hue;
        return `<button class="sw${on ? ' on' : ''}" data-hue="${t.hue == null ? '' : t.hue}" title="${t.name}" style="background:${rgbHex(rgb)}"></button>`;
      }).join('')}</div></div>
    <div class="opts-row"><div class="lab">Custom hue<small>find your own color</small></div>
      <div class="huectl"><input type="range" class="r hue" id="optHue" min="0" max="359" step="1" value="${OPTS.hue ?? 37}"></div></div>`;
  ap.querySelectorAll('.sw').forEach(b => b.onclick = () => {
    OPTS.hue = b.dataset.hue === '' ? null : +b.dataset.hue;
    saveOpts(); applyTheme(); renderOpts();
  });
  const hu = ap.querySelector('#optHue');
  hu.oninput = () => { OPTS.hue = +hu.value; applyTheme(); };
  hu.onchange = () => { saveOpts(); renderOpts(); };
  w.appendChild(ap);

  // — listening / headphones —
  const hp = document.createElement('div'); hp.className = 'opts-sect';
  hp.innerHTML = `<h4>Headphones &amp; jamming</h4>
    <div class="opts-row"><div class="lab">Headphone mode<small>output is in your ears, so the mic never hears Claudio — 🎤 Listen reacts faster (no self-filter gaps)</small></div>
      <div class="toggle${OPTS.headphones ? ' on' : ''}" id="optHp"><span class="tk"></span></div></div>
    <div class="opts-row${OPTS.headphones ? '' : ' dim'}"><div class="lab">Mic monitor<small>jam-through: hear your own mic with Claudio-style reverb + delay while Listen is on · headphones only (feedback-safe)</small></div>
      <div class="toggle${OPTS.monitor && OPTS.headphones ? ' on' : ''}" id="optMon"><span class="tk"></span></div></div>
    <div class="opts-row${OPTS.headphones && OPTS.monitor ? '' : ' dim'}"><div class="lab">Monitor space<small>dry ↔ drenched</small></div>
      <div class="huectl"><input type="range" class="r" id="optMix" min="0" max="1" step="0.05" value="${OPTS.monMix}"></div></div>`;
  hp.querySelector('#optHp').onclick = () => {
    OPTS.headphones = !OPTS.headphones;
    if (!OPTS.headphones) killMonitor();
    else if (OPTS.monitor && MIC.on) buildMonitor();
    saveOpts(); renderOpts();
    toast(OPTS.headphones ? '🎧 headphone mode <span class="g">on</span>' : '🎧 headphone mode off');
  };
  hp.querySelector('#optMon').onclick = () => {
    if (!OPTS.headphones) { toast('🎧 turn on headphone mode first — monitoring through speakers would feed back'); return; }
    OPTS.monitor = !OPTS.monitor;
    if (OPTS.monitor && MIC.on) buildMonitor(); else killMonitor();
    saveOpts(); renderOpts();
    toast(OPTS.monitor ? '🎙 monitor <span class="g">on</span> — jam away' : '🎙 monitor off');
  };
  const mx = hp.querySelector('#optMix');
  mx.oninput = () => { OPTS.monMix = +mx.value; if (MIC.mon) setMonitorMix(); };
  mx.onchange = saveOpts;
  w.appendChild(hp);

  // — visuals —
  const vz = document.createElement('div'); vz.className = 'opts-sect';
  vz.innerHTML = `<h4>Constellation</h4>
    <div class="opts-row"><div class="lab">Visual energy<small>calm ↔ lively — motes, aurora, web glow</small></div>
      <div class="huectl"><input type="range" class="r" id="optNrg" min="0" max="2" step="0.1" value="${OPTS.energy}"></div></div>`;
  const nrg = vz.querySelector('#optNrg');
  nrg.oninput = () => { OPTS.energy = +nrg.value; };
  nrg.onchange = saveOpts;
  w.appendChild(vz);
  w.querySelectorAll('input.r').forEach(setFill);
}

/* ---------------- mic-jam: sing with the room ---------------- */
// Listen to the mic, find the loudest *steady* note in the room, and re-key
// Claudio's whole palette to it — live, no re-render. Dependency-free: a
// normalized autocorrelation pitch detector (no FFT lib). Gated three ways so
// Claudio sings *with* the room instead of chasing its own tail:
//   1. noise gate — ignore quiet input (RMS below a floor)
//   2. gap-aware  — ignore the ~400ms after Claudio plays a note, so its own
//                   output (and decaying reverb tail) isn't detected back
//   3. stability  — a pitch must hold across several frames before it commits
// (Even if it does hear itself it just re-affirms the current root, so it's
// self-stable; the debounce stops it chasing harmonics.) A=432 is Claudio's
// rendered root, so pitch class is measured against 432 Hz.
const A432 = 432.0;
const NOTE_NAMES = ['C','C#','D','D#','E','F','F#','G','G#','A','A#','B'];
// of/need: rolling-window stability for *committing* a re-key. show: a (looser)
// threshold for the on-button readout — but it only relabels when one note
// clearly dominates AND differs from what's shown, so the text stays calm
// instead of flickering with every raw frame. holdMs: press longer than this =
// momentary "listen while held"; a quick tap latches on/off.
const MIC_CFG = { rms: 0.012, gapMs: 420, need: 9, of: 18, minSendMs: 1500, show: 8, holdMs: 350 };

async function startListen() {
  if (MIC.on) return true;
  if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
    toast('🎤 <span class="g">no mic API</span> — open the console on localhost'); return false; }
  try {
    // headphone mode: nothing to echo-cancel (Claudio is in your ears), and EC
    // mangles music — turn it off for cleaner detection and monitoring.
    MIC.stream = await navigator.mediaDevices.getUserMedia({
      audio: { echoCancellation: !OPTS.headphones, noiseSuppression: false, autoGainControl: false } });
  } catch { toast('🎤 <span class="g">mic blocked</span> — allow microphone access'); return false; }
  const Ctx = window.AudioContext || window.webkitAudioContext;
  MIC.ctx = new Ctx();
  MIC.src = MIC.ctx.createMediaStreamSource(MIC.stream);
  MIC.analyser = MIC.ctx.createAnalyser();
  MIC.analyser.fftSize = 2048;
  MIC.src.connect(MIC.analyser);
  MIC.buf = new Float32Array(MIC.analyser.fftSize);
  if (OPTS.headphones && OPTS.monitor) buildMonitor();
  // remember the key we were in, so turning Listen off restores it
  MIC.prevOffset = (STATE.music && STATE.music.root_offset) || 0;
  MIC.on = true; MIC.hist = []; MIC.lockedPc = null; MIC.lastShownPc = null;
  setListenUI(); micLoop();
  toast('🎤 <span class="g">listening</span> — hum, play, or put on a song');
  return true;
}

function stopListen() {
  if (!MIC.on) return;
  MIC.on = false;
  killMonitor();
  if (MIC.raf) { cancelAnimationFrame(MIC.raf); MIC.raf = 0; }
  if (MIC.stream) MIC.stream.getTracks().forEach(t => t.stop());
  if (MIC.ctx) MIC.ctx.close().catch(() => {});
  MIC.ctx = MIC.stream = MIC.analyser = MIC.src = null; MIC.hist = []; MIC.lastShownPc = null;
  setListenUI();
  // revert to whatever the root was before we started jamming
  const prev = MIC.prevOffset || 0;
  api.post('/api/root', prev ? { offset: prev } : { clear: true }).then(r => {
    if (STATE.music) { STATE.music.root_offset = r.root_offset; STATE.music.root_note = r.root_note; }
    const mp = $('.tabpanel[data-panel="music"]'); if (mp && !mp.hidden) renderMusic();
    toast(`🎤 off · key → <span class="g">${r.root_note}</span>`);
  });
}

function setListenUI(pc) {
  const b = $('#listenBtn'), lbl = $('#listenLbl'); if (!b || !lbl) return;
  b.classList.toggle('on', MIC.on);
  lbl.textContent = !MIC.on ? 'Listen' : (pc == null ? 'listening…' : NOTE_NAMES[pc]);
}

function micLoop() {
  if (!MIC.on) return;
  MIC.raf = requestAnimationFrame(micLoop);
  const an = MIC.analyser; if (!an) return;
  an.getFloatTimeDomainData(MIC.buf);
  let sum = 0; for (let i = 0; i < MIC.buf.length; i++) sum += MIC.buf[i] * MIC.buf[i];
  const rms = Math.sqrt(sum / MIC.buf.length);
  // headphone mode: Claudio is in your ears, the mic can't hear it — no gap needed
  const inGap = OPTS.headphones || (performance.now() - MIC.lastFire) > MIC_CFG.gapMs;
  let pc = null;
  if (rms >= MIC_CFG.rms && inGap) {
    const f = detectPitch(MIC.buf, MIC.ctx.sampleRate);
    if (f > 0) { const midi = 69 + 12 * Math.log2(f / A432); pc = ((Math.round(midi) % 12) + 12) % 12; }
  }
  MIC.hist.push(pc); if (MIC.hist.length > MIC_CFG.of) MIC.hist.shift();
  const counts = {}; MIC.hist.forEach(p => { if (p != null) counts[p] = (counts[p] || 0) + 1; });
  let best = null, bestN = 0; for (const k in counts) if (counts[k] > bestN) { bestN = counts[k]; best = +k; }
  if (best != null && bestN >= MIC_CFG.need) commitRoot(best);
  // calm readout: only relabel when one note clearly dominates and it changed
  if (best != null && bestN >= MIC_CFG.show && best !== MIC.lastShownPc) { MIC.lastShownPc = best; setListenUI(best); }
}

async function commitRoot(pc) {
  const now = performance.now();
  if (pc === MIC.lockedPc || now - MIC.lastSent < MIC_CFG.minSendMs) return;
  MIC.lockedPc = pc; MIC.lastSent = now;
  const r = await api.post('/api/root', { pc });
  if (STATE.music) { STATE.music.root_offset = r.root_offset; STATE.music.root_note = r.root_note; }
  MIC.lastShownPc = pc; setListenUI(pc);
  const mp = $('.tabpanel[data-panel="music"]');
  if (mp && !mp.hidden) renderMusic();          // keep the Root-note readout live
  toast(`🎤 room → <span class="g">${r.root_note}</span>`);
}

/* live mic monitor (headphone mode only): dry + reverb + feedback delay, all
   stock Web Audio nodes. The reverb impulse is a synthesized decaying noise
   burst — the classic trick, no samples to load. Feedback-safe by policy:
   buildMonitor refuses to run unless headphone mode is on. */
function buildMonitor() {
  if (!MIC.ctx || !MIC.src || MIC.mon || !OPTS.headphones) return;
  const c = MIC.ctx, m = {};
  m.in = c.createGain();   m.in.gain.value = 0.9;
  m.dry = c.createGain();  m.dry.gain.value = 0.75;
  m.wetR = c.createGain(); m.wetD = c.createGain();
  m.out = c.createGain();  m.out.gain.value = 1.0;
  m.conv = c.createConvolver(); m.conv.buffer = makeIR(c, 2.6, 2.4);
  m.delay = c.createDelay(1.5); m.delay.delayTime.value = 0.34;
  m.fb = c.createGain();   m.fb.gain.value = 0.32;
  MIC.src.connect(m.in);
  m.in.connect(m.dry).connect(m.out);
  m.in.connect(m.conv).connect(m.wetR).connect(m.out);
  m.in.connect(m.delay); m.delay.connect(m.fb).connect(m.delay);   // feedback loop
  m.delay.connect(m.wetD).connect(m.out);
  m.out.connect(c.destination);
  MIC.mon = m; setMonitorMix();
}
function setMonitorMix() {
  if (!MIC.mon) return;
  const mix = OPTS.monMix;
  MIC.mon.wetR.gain.value = 0.85 * mix;
  MIC.mon.wetD.gain.value = 0.55 * mix;
}
function killMonitor() {
  if (!MIC.mon) return;
  try { MIC.src && MIC.src.disconnect(MIC.mon.in); } catch {}
  try { MIC.mon.out.disconnect(); } catch {}
  MIC.mon = null;
}
function makeIR(c, seconds, decay) {
  const rate = c.sampleRate, len = Math.floor(rate * seconds);
  const buf = c.createBuffer(2, len, rate);
  for (let ch = 0; ch < 2; ch++) {
    const d = buf.getChannelData(ch);
    for (let i = 0; i < len; i++) d[i] = (Math.random() * 2 - 1) * Math.pow(1 - i / len, decay);
  }
  return buf;
}

// Normalized autocorrelation (ACF2+ style). Returns the fundamental in Hz, or -1.
function detectPitch(buf, sr) {
  const N = buf.length;
  let r1 = 0, r2 = N - 1; const thres = 0.2;
  for (let i = 0; i < N / 2; i++) if (Math.abs(buf[i]) < thres) { r1 = i; break; }
  for (let i = 1; i < N / 2; i++) if (Math.abs(buf[N - i]) < thres) { r2 = N - i; break; }
  const b = buf.slice(r1, r2), M = b.length; if (M < 32) return -1;
  const c = new Float32Array(M);
  for (let lag = 0; lag < M; lag++) { let s = 0; for (let i = 0; i < M - lag; i++) s += b[i] * b[i + lag]; c[lag] = s; }
  let d = 0; while (d < M - 1 && c[d] > c[d + 1]) d++;          // walk down past lag-0 peak
  let maxv = -1, maxp = -1; for (let i = d; i < M; i++) if (c[i] > maxv) { maxv = c[i]; maxp = i; }
  if (maxp <= 0) return -1;
  const x1 = c[maxp - 1] || 0, x2 = c[maxp], x3 = c[maxp + 1] || 0;   // parabolic interp
  const a = (x1 + x3 - 2 * x2) / 2, bb = (x3 - x1) / 2;
  const T = a ? maxp - bb / (2 * a) : maxp;
  const f = sr / T;
  return (f >= 50 && f <= 2000) ? f : -1;        // drop sub-bass rumble & hiss
}

boot();
