/* pixel.js — 320x180 のピクセルアート教材アニメーション用の描画エンジン
 * 使い方: この後に scenes.js を読み込み、グローバル SCENES を定義する（SKILL.md 参照）。
 * すべての関数はグローバル ctx（320x180 の canvas）に描く。座標は整数に丸められる。 */
'use strict';
const W = 320, H = 180;
/* 高解像度モード: window.PIXEL_SCALE = 4 なら、座標は 320x180 のまま 1280x720 で描く。
 * 文字はなめらかな等幅フォント、線・円はなめらかな線になる（1 文字の幅は 4 のままなのでレイアウトは変わらない） */
const HI = (typeof window !== 'undefined' && window.PIXEL_SCALE > 1) ? window.PIXEL_SCALE : 1;
const cv = document.getElementById('screen');
cv.width = W * HI; cv.height = H * HI;
const ctx = cv.getContext('2d');
ctx.imageSmoothingEnabled = false;
function resetCtx() { ctx.setTransform(HI, 0, 0, HI, 0, 0); ctx.globalAlpha = 1; }
resetCtx();

/* ---------- 色（暗い背景用。これ以外の色も使ってよい） ---------- */
const C = {
  bg:'#0f0e1a', panel:'#1c1a2e', line:'#3a3657', dim:'#5c5880', ink:'#e9e6f7', ink2:'#a9a4c6',
  gold:'#f0b43c', gold2:'#9c6a1c', blue:'#4d7bd8', red:'#e2483d', teal:'#39c3a4', purp:'#9b6bdf',
  pink:'#e36fa6', green:'#4fb35a', yellow:'#ffd66b', moon:'#cfe0f5', empty:'#262338', dark:'#0b0a13',
  paper:'#d8cfb6', paperInk:'#7d6f55'
};

/* ---------- 数値ユーティリティ ---------- */
const clamp = (v, a = 0, b = 1) => Math.max(a, Math.min(b, v));
const ease = x => 1 - Math.pow(1 - clamp(x), 3);          // 0→1 を減速しながら
const lerp = (a, b, f) => a + (b - a) * f;
const blink = (t, hz = 3) => ((t * hz) | 0) % 2 === 0;     // 点滅（決定的）
function rng(seed) { return () => { seed |= 0; seed = seed + 0x6D2B79F5 | 0; let t = Math.imul(seed ^ seed >>> 15, 1 | seed); t = t + Math.imul(t ^ t >>> 7, 61 | t) ^ t; return ((t ^ t >>> 14) >>> 0) / 4294967296; }; }
function hexRGB(c) { return [parseInt(c.slice(1, 3), 16), parseInt(c.slice(3, 5), 16), parseInt(c.slice(5, 7), 16)]; }
function mix(a, b, f) { const A = hexRGB(a), B = hexRGB(b); f = clamp(f); return '#' + A.map((v, i) => Math.round(v + (B[i] - v) * f).toString(16).padStart(2, '0')).join(''); }

/* ---------- 図形 ---------- */
function R(x, y, w, h, c) { ctx.fillStyle = c; ctx.fillRect(Math.round(x), Math.round(y), Math.round(w), Math.round(h)); }
function clear(c = C.bg) { R(0, 0, W, H, c); }
function box(x, y, w, h, fill = C.panel, edge = C.line) { R(x, y, w, h, edge); R(x + 1, y + 1, w - 2, h - 2, fill); }
function frameBox(x, y, w, h, edge) { R(x, y, w, 1, edge); R(x, y + h - 1, w, 1, edge); R(x, y, 1, h, edge); R(x + w - 1, y, 1, h, edge); }
function dotted(x, y, w, h, c) { for (let i = 0; i < w; i += 2) { R(x + i, y, 1, 1, c); R(x + i, y + h - 1, 1, 1, c); } for (let j = 0; j < h; j += 2) { R(x, y + j, 1, 1, c); R(x + w - 1, y + j, 1, 1, c); } }
function line(x0, y0, x1, y1, c) {
  if (HI > 1) { ctx.strokeStyle = c; ctx.lineWidth = 1; ctx.lineCap = 'square'; ctx.beginPath(); ctx.moveTo(x0 + .5, y0 + .5); ctx.lineTo(x1 + .5, y1 + .5); ctx.stroke(); return; }
  x0 = Math.round(x0); y0 = Math.round(y0); x1 = Math.round(x1); y1 = Math.round(y1);
  const dx = Math.abs(x1 - x0), dy = -Math.abs(y1 - y0), sx = x0 < x1 ? 1 : -1, sy = y0 < y1 ? 1 : -1;
  let e = dx + dy;
  for (let n = 0; n < 2000; n++) { R(x0, y0, 1, 1, c); if (x0 === x1 && y0 === y1) break; const e2 = 2 * e; if (e2 >= dy) { e += dy; x0 += sx; } if (e2 <= dx) { e += dx; y0 += sy; } }
}
function circ(cx, cy, r, c) { if (HI > 1) { ctx.strokeStyle = c; ctx.lineWidth = 1; ctx.beginPath(); ctx.arc(cx + .5, cy + .5, r, 0, Math.PI * 2); ctx.stroke(); return; } const n = Math.max(24, Math.round(r * 7)); for (let a = 0; a < n; a++) { const th = a / n * Math.PI * 2; R(cx + Math.round(Math.cos(th) * r), cy + Math.round(Math.sin(th) * r), 1, 1, c); } }
function disc(cx, cy, r, c) { if (HI > 1) { ctx.fillStyle = c; ctx.beginPath(); ctx.arc(cx + .5, cy + .5, r + .5, 0, Math.PI * 2); ctx.fill(); return; } for (let dy = -r; dy <= r; dy++) { const w = Math.round(Math.sqrt(r * r - dy * dy)); R(cx - w, cy + dy, w * 2 + 1, 1, c); } }
function ellipse(cx, cy, rx, ry, edge, fill) {
  if (HI > 1) { ctx.beginPath(); ctx.ellipse(cx + .5, cy + .5, rx, ry, 0, 0, Math.PI * 2); if (fill) { ctx.fillStyle = fill; ctx.fill(); } ctx.strokeStyle = edge; ctx.lineWidth = 1; ctx.stroke(); return; }
  for (let dy = -ry; dy <= ry; dy++) {
    const w = Math.round(rx * Math.sqrt(Math.max(0, 1 - (dy * dy) / (ry * ry))));
    if (fill) R(cx - w, cy + dy, w * 2 + 1, 1, fill);
    R(cx - w, cy + dy, 1, 1, edge); R(cx + w, cy + dy, 1, 1, edge);
  }
}
/* 矢印（画面座標）。lab を付けると先端の右上にラベル */
function arrow(x0, y0, x1, y1, c, lab) {
  line(x0, y0, x1, y1, c);
  const a = Math.atan2(y1 - y0, x1 - x0);
  for (const s of [-1, 1]) line(x1, y1, x1 - Math.cos(a + s * .45) * 5, y1 - Math.sin(a + s * .45) * 5, c);
  if (lab) text(lab, x1 + 3, y1 - 6, c);
}
function arrowR(x, y, c) { R(x, y - 2, 1, 5, c); R(x + 1, y - 1, 1, 3, c); R(x + 2, y, 1, 1, c); }   // 小さな ▶
function arrowD(x, y, c) { R(x - 2, y, 5, 1, c); R(x - 1, y + 1, 3, 1, c); R(x, y + 2, 1, 1, c); }   // 小さな ▼

/* ---------- 配線と流れる粒（直角に曲がる折れ線） ---------- */
function pathLen(p) { let L = 0; for (let i = 1; i < p.length; i++) L += Math.hypot(p[i][0] - p[i - 1][0], p[i][1] - p[i - 1][1]); return L; }
function pointAt(p, d) {
  for (let i = 1; i < p.length; i++) {
    const L = Math.hypot(p[i][0] - p[i - 1][0], p[i][1] - p[i - 1][1]);
    if (d <= L) { const f = L ? d / L : 0; return [lerp(p[i - 1][0], p[i][0], f), lerp(p[i - 1][1], p[i][1], f)]; }
    d -= L;
  }
  return p[p.length - 1];
}
function wire(p, c, alpha = .45) { ctx.globalAlpha = alpha; for (let i = 1; i < p.length; i++) line(p[i - 1][0], p[i - 1][1], p[i][0], p[i][1], c); ctx.globalAlpha = 1; }
function packets(p, c, t, speed = 22, gap = 26) {
  const L = pathLen(p), n = Math.max(1, Math.floor(L / gap));
  for (let i = 0; i < n; i++) { const [x, y] = pointAt(p, (t * speed + i * (L / n)) % L); R(x - 1, y - 1, 3, 3, c); }
}

/* ---------- 3x5 ピクセルフォント ----------
 * 1 文字 = 幅 3px + 間隔 1px = 4px、高さ 5px。行送りは 8〜10px が目安。
 * 小文字は自動で大文字になる。フォントにない文字は描かれず、ビルド時に「MISSING GLYPH」として報告される。 */
const G = {
  A:'010101111101101',B:'110101110101110',C:'011100100100011',D:'110101101101110',E:'111100110100111',
  F:'111100110100100',G:'011100101101011',H:'101101111101101',I:'111010010010111',J:'001001001101010',
  K:'101101110101101',L:'100100100100111',M:'101111111101101',N:'110101101101101',O:'010101101101010',
  P:'110101110100100',Q:'010101101110011',R:'110101110101101',S:'011100010001110',T:'111010010010010',
  U:'101101101101111',V:'101101101101010',W:'101101111111101',X:'101101010101101',Y:'101101010010010',
  Z:'111001010100111',
  '0':'111101101101111','1':'010110010010111','2':'110001010100111','3':'110001010001110','4':'101101111001001',
  '5':'111100110001110','6':'011100111101111','7':'111001010010010','8':'111101111101111','9':'111101111001110',
  ' ':'000000000000000','.':'000000000000010',':':'000010000010000','-':'000000111000000','+':'000010111010000',
  '=':'000111000111000','/':'001001010100100','%':'101001010100101','(':'001010010010001',')':'100010010010100',
  '<':'001010100010001','>':'100010001010100','_':'000000000000111','!':'010010010000010','?':'110001010000010',
  ',':'000000000010100',"'":'010010000000000','"':'101101000000000',';':'000010000010100','|':'010010010010010',
  '[':'011010010010011',']':'110010010010110','{':'011010110010011','}':'110010011010110','#':'101111101111101',
  '*':'000101010101000','@':'010101111100011','&':'010101010101011','^':'010101000000000','~':'000000011110000',
  // 記号
  '×':'000101010101000','·':'000000010000000','−':'000000111000000','±':'010111010000111','≈':'000011110011110',
  '≤':'001010100000111','≥':'100010001000111','→':'000001111001000','←':'000100111100000','°':'010101010000000',
  '√':'001001001101010','∝':'000011100011000','∥':'101101101101101','⊥':'010010010010111','′':'010010000000000',
  '²':'110010100110000','³':'110010110010110','ᵀ':'111010010000000','∞':'000000111111000',
  // ギリシャ文字（大文字にせずそのまま使う）
  'α':'000011101101011','β':'110101110101100','γ':'101101010010010','δ':'011100010101010','ε':'011100110100011',
  'θ':'010101111101010','κ':'000101110101000','λ':'100010010101101','μ':'000101101110100','µ':'000101101110100',
  'π':'000111101101101','ρ':'000110101110100','σ':'000011110101010','τ':'000111010010001','φ':'010111101111010',
  'ψ':'101101111010010','ω':'000000101111111','ħ':'100111100101101','Δ':'000010101101111','Σ':'111100010100111',
  'Φ':'010111101111010','Ω':'010101101010101'
};
const LINT = { missing: new Set(), boxes: [], out: [] };
function textWidth(s) { return String(s).length * 4 - 1; }
/* 文字を描く。align は 'left' | 'center' | 'right'。戻り値は描いた幅 */
function text(s, x, y, c = C.ink, align = 'left') {
  const o = String(s), w = textWidth(o);
  if (align === 'center') x -= Math.floor(w / 2); else if (align === 'right') x -= w;
  x = Math.round(x); y = Math.round(y);
  ctx.fillStyle = c;
  if (HI > 1) { ctx.font = '600 6.4px Menlo, "DejaVu Sans Mono", Consolas, monospace'; ctx.textAlign = 'center'; ctx.textBaseline = 'alphabetic'; }
  for (let i = 0; i < o.length; i++) {
    const ch = o[i];
    const g = G[ch] || G[ch.toUpperCase()];
    if (!g) { LINT.missing.add(ch); continue; }
    if (HI > 1) { if (ch !== ' ') ctx.fillText(ch === ch.toLowerCase() && /[a-z]/.test(ch) ? ch.toUpperCase() : ch, x + i * 4 + 1.5, y + 5); continue; }
    for (let b = 0; b < 15; b++) if (g[b] === '1') ctx.fillRect(x + i * 4 + (b % 3), y + ((b / 3) | 0), 1, 1);
  }
  if (/#[0-9a-fA-F]{6}/.test(o)) LINT.colorText = (LINT.colorText || []).concat([o]);
  if (o.trim()) {
    LINT.boxes.push([x, y, x + w, y + 5, o]);
    if (x < 0 || y < 0 || x + w > W || y + 5 > H) LINT.out.push(o);
  }
  return w;
}
/* 色の違う文字列を横に並べる: segs(x, y, [['V COS', C.gold], ['θ', C.red]]) → 右端の x を返す */
function segs(x, y, parts) { let cx = x; for (const [s, c] of toParts(parts)) { text(s, cx, y, c); cx += String(s).length * 4; } return cx; }
/* 画面上部の見出し帯（0〜11px を使う） */
function title(n, s) { R(0, 0, W, 11, '#161428'); text(String(n), 4, 3, C.gold); text(s, 4 + String(n).length * 4 + 6, 3, C.ink); }

/* ---------- 行列・数式 ---------- */
function brackets(x, y, w, h, c = C.ink2) { R(x, y, 1, h, c); R(x, y, 3, 1, c); R(x, y + h - 1, 3, 1, c); R(x + w - 1, y, 1, h, c); R(x + w - 3, y, 3, 1, c); R(x + w - 3, y + h - 1, 3, 1, c); }
/* 色つきの文字列の並びに正規化する。受け付ける形:
 *   '文字'  /  ['文字', '#色']  /  [['文字', '#色'], ['文字', '#色'], ...]  /  それをさらに配列で包んだもの */
function toParts(cell, color = C.ink) {
  if (typeof cell === 'string' || typeof cell === 'number') return [[String(cell), color]];
  if (Array.isArray(cell) && cell.length === 2 && typeof cell[0] === 'string' && typeof cell[1] === 'string' && cell[1][0] === '#') return [cell];
  if (Array.isArray(cell)) return cell.flatMap(x => toParts(x, color));
  return [[String(cell), color]];
}
/* 行列: cells[r][c] は toParts が受け付ける形。colW は列幅(px)。成分の最大文字数 × 4 + 6 以上にすること。戻り値は全体の幅 */
function matrix(x, y, cells, colW, rowH = 12, color = C.ink) {
  const cols = cells[0].length, w = cols * colW + 6, h = cells.length * rowH + 2;
  brackets(x, y - 3, w, h);
  cells.forEach((row, r) => row.forEach((cell, c) => {
    const parts = toParts(cell, color);
    const len = parts.reduce((a, [s]) => a + String(s).length, 0) * 4 - 1;
    segs(x + 3 + c * colW + Math.floor((colW - len) / 2), y + r * rowH, parts);
  }));
  return w;
}
/* ベクトルを色の帯で表す（値は -1〜1）。横向き / 縦向き */
function vcolor(v, pos = C.gold, neg = C.blue) { v = clamp(v, -1, 1); return v >= 0 ? mix(C.empty, pos, v) : mix(C.empty, neg, -v); }
function hvec(x, y, vals, cw = 5, ch = 6, pos, neg) { vals.forEach((v, i) => R(x + i * cw, y, cw - 1, ch, vcolor(v, pos, neg))); }
function vcol(x, y, vals, cw = 6, ch = 5, pos, neg) { vals.forEach((v, i) => R(x, y + i * ch, cw, ch - 1, vcolor(v, pos, neg))); }
/* 棒グラフの 1 本、進捗バー */
function bar(x, y, w, h, f, c, edge = C.line) { frameBox(x, y, w, h, edge); R(x + 1, y + 1, (w - 2) * clamp(f), h - 2, c); }
/* 折れ線グラフ: pts は [[x値, y値], ...]、範囲 xr=[min,max] yr=[min,max] を枠 (x,y,w,h) に描く */
function plot(x, y, w, h, pts, xr, yr, c, edge = C.line) {
  if (edge) frameBox(x - 1, y - 1, w + 2, h + 2, edge);
  let prev = null;
  for (const [px, py] of pts) {
    const sx = x + (px - xr[0]) / (xr[1] - xr[0]) * (w - 1), sy = y + h - 1 - (py - yr[0]) / (yr[1] - yr[0]) * (h - 1);
    if (prev) line(prev[0], prev[1], sx, sy, c); else R(sx, sy, 1, 1, c);
    prev = [sx, sy];
  }
}

/* ---------- 3D（簡単な斜め投影） ---------- */
const CAM = { ox: 90, oy: 100, scale: 40, yaw: -0.5, pitch: 0.42 };   // 原点の画面位置・倍率・向き。場面ごとに書き換えてよい
function P3(p) {
  const x1 = p[0] * Math.cos(CAM.yaw) - p[1] * Math.sin(CAM.yaw), y1 = p[0] * Math.sin(CAM.yaw) + p[1] * Math.cos(CAM.yaw);
  return [CAM.ox + x1 * CAM.scale, CAM.oy - (p[2] * Math.cos(CAM.pitch) + y1 * Math.sin(CAM.pitch)) * CAM.scale];
}
function line3(a, b, c) { const [x0, y0] = P3(a), [x1, y1] = P3(b); line(x0, y0, x1, y1, c); }
function arrow3(a, b, c, lab) { const [x0, y0] = P3(a), [x1, y1] = P3(b); arrow(x0, y0, x1, y1, c, lab); }
function axes3(len = .6, c = C.dim) { ctx.globalAlpha = .5; [[1, 0, 0], [0, 1, 0], [0, 0, 1]].forEach(e => line3([0, 0, 0], e.map(v => v * len), c)); ctx.globalAlpha = 1; }
const V3 = {
  dot: (a, b) => a[0] * b[0] + a[1] * b[1] + a[2] * b[2],
  cross: (a, b) => [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]],
  add: (...v) => v.reduce((s, x) => [s[0] + x[0], s[1] + x[1], s[2] + x[2]], [0, 0, 0]),
  mul: (a, s) => [a[0] * s, a[1] * s, a[2] * s],
  norm: a => { const n = Math.hypot(a[0], a[1], a[2]); return [a[0] / n, a[1] / n, a[2] / n]; },
};

/* ---------- 飾り ---------- */
function noiseTile(x, y, w, h, seed, pal = [C.purp, C.pink, '#5a3f8a', '#8a3f6a', '#3b2f5c']) { const r = rng(seed); for (let j = 0; j < h; j += 2) for (let i = 0; i < w; i += 2) R(x + i, y + j, 2, 2, pal[(r() * pal.length) | 0]); }
function waveform(x, y, w, amp, t, c, seed = 1) { for (let i = 0; i < w; i++) { const ph = (i + t * 40) * .18; const v = Math.sin(ph) * .5 + Math.sin(ph * 2.7 + seed) * .3 + Math.sin(ph * .31) * .4; const hh = Math.max(1, Math.round(Math.abs(v) * amp)); R(x + i, y - hh, 1, hh * 2, c); } }

/* ---------- 内容の検算 ----------
 * 画面に出す式や数値が正しいかを、scenes.js の中で数値計算して確かめる。失敗はビルド時に CHECK FAILED として報告される。
 *   check('R の (0,1) 成分', near(式で書いた値, 実際に計算した値));  */
const CHECKS = [];
function near(a, b, eps = 1e-6) { return Math.abs(a - b) <= eps * Math.max(1, Math.abs(a), Math.abs(b)); }
function check(label, ok) { CHECKS.push([String(label), !!ok]); return !!ok; }
/* 画面に表示する式の文字列そのものを計算する。表示と検算を切り離さないために使う。
 *   evalExpr('k1k2C−k3S', { k1: .6, k2: .8, k3: 0, C: 1 - Math.cos(th), S: Math.sin(th) })
 * 'F2 = F1×L1/L2' のような等式は、最後の = の右側を計算する。
 * 使える書き方: 数字、変数（vars のキー。長い名前を優先して切り出す）、+ - − × · * / ^ ² ³、( )、
 *   関数 COS SIN TAN SQRT（例 COSθ, SIN(2θ)）、並べて書くと掛け算（2k1k2 → 2×k1×k2）。
 * 読めない式は NaN を返し、ビルド時に報告される。 */
function evalExpr(str, vars) {
  const FN = { COS: Math.cos, SIN: Math.sin, TAN: Math.tan, SQRT: Math.sqrt };
  // 等式（例 'F2 = F1×L1/L2'）は右辺を計算する
  const s = String(str).split('=').pop().replace(/\s+/g, '').replace(/[−–]/g, '-').replace(/[×·]/g, '*').replace(/²/g, '^2').replace(/³/g, '^3');
  const names = Object.keys(vars).concat(Object.keys(FN)).sort((a, b) => b.length - a.length);
  const tok = [];
  for (let i = 0; i < s.length;) {
    const m = /^\d+(\.\d+)?/.exec(s.slice(i));
    if (m) { tok.push({ n: parseFloat(m[0]) }); i += m[0].length; continue; }
    if ('+-*/^()'.includes(s[i])) { tok.push({ o: s[i] }); i++; continue; }
    const nm = names.find(n => s.startsWith(n, i) || s.slice(i, i + n.length).toUpperCase() === n);
    if (!nm) { LINT.exprErr = (LINT.exprErr || []).concat([str + '（「' + s.slice(i) + '」が読めない）']); return NaN; }
    tok.push(FN[nm] ? { f: FN[nm] } : { v: vars[nm] }); i += nm.length;
  }
  let p = 0;
  const peek = () => tok[p], starts = t => t && (t.n !== undefined || t.v !== undefined || t.f || t.o === '(');
  function expr() { let v = term(); while (peek() && (peek().o === '+' || peek().o === '-')) { const o = tok[p++].o; const r = term(); v = o === '+' ? v + r : v - r; } return v; }
  function term() { let v = unary(); for (;;) { const t = peek(); if (t && (t.o === '*' || t.o === '/')) { p++; const r = unary(); v = t.o === '*' ? v * r : v / r; } else if (starts(t)) v *= power(); else return v; } }
  function unary() { const t = peek(); if (t && (t.o === '-' || t.o === '+')) { p++; const v = unary(); return t.o === '-' ? -v : v; } return power(); }
  function power() { const b = atom(); if (peek() && peek().o === '^') { p++; return Math.pow(b, unary()); } return b; }
  function atom() {
    const t = tok[p++];
    if (!t) throw 0;
    if (t.n !== undefined) return t.n;
    if (t.v !== undefined) return t.v;
    if (t.f) return t.f(power());
    if (t.o === '(') { const v = expr(); if (!tok[p] || tok[p].o !== ')') throw 0; p++; return v; }
    throw 0;
  }
  try { const v = expr(); if (p !== tok.length) throw 0; return v; }
  catch (e) { LINT.exprErr = (LINT.exprErr || []).concat([String(str) + '（式として読めない）']); return NaN; }
}
/* 表示する式の文字列を、正しい値と比べて検算する */
function checkExpr(expr, vars, expected, label) { return check((label ? label + ': ' : '') + expr, near(evalExpr(expr, vars), expected, 1e-6)); }

/* ---------- ドット絵スプライト ----------
 * rows は同じ長さの文字列の配列、pal は { 文字: 色 }。'.' と ' ' は透明。scale で拡大、flip で左右反転。
 *   sprite(40, 60, ['..hh..', '.hssh.', '..bb..'], { h: '#3a2a1f', s: '#e0b48a', b: C.blue }, 2)  */
function sprite(x, y, rows, pal, scale = 1, flip = false) {
  const w = rows[0].length;
  rows.forEach((row, j) => { for (let i = 0; i < row.length; i++) { const ch = row[i]; if (ch === '.' || ch === ' ' || !pal[ch]) continue; R(x + (flip ? w - 1 - i : i) * scale, y + j * scale, scale, scale, pal[ch]); } });
}
