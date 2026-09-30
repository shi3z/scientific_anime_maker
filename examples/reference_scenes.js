/* オデュッセイア 第2話 — pixel-anim-gif 用 scenes.js（単独で動く。前半はシリーズ共通部品） */
/* ===== オデュッセイア・シリーズ共通部品（全話で同じものをコピーして使う） =====
 * 配色・主人公・船・海・島のデザインをシリーズでそろえるための部品。
 * 人物や船などは sprite() で描く。文字は英語の大文字ラベルだけ。 */

/* ---------- シリーズ共通の色 ---------- */
const OC = {
  sky: '#1b2a4f', skyD: '#10152c', dusk: '#3a2a55', sea: '#1d4f8a', sea2: '#3a7cc4', deep: '#143866', foam: '#a8d8f5',
  sand: '#cdb27a', rock: '#6b5a4a', rock2: '#4a3d33', rock3: '#2e2620', grass: '#3f8f4a', leaf: '#2f6b3a',
  hull: '#6a4226', hull2: '#3a2414', sail: '#efe6cc', stripe: '#c0392b', skin: '#e0b48a', eye: '#1a1020',
  red: '#c0392b', gold: '#f0b43c', cream: '#d8cfb6', blue: '#4d7bd8', hair: '#5a3a22', beard: '#6b4226',
  wood: '#8a5a32', white: '#f4f0e0', grey: '#8d8aa0', fire: '#ff8a3c', ghost: '#b8d6e8', pink: '#f0a0b8',
};

/* 行の長さをそろえる（sprite の左右反転のため） */
function PAD(rows) { const w = Math.max(...rows.map(r => r.length)); return rows.map(r => r.padEnd(w, '.')); }

/* ---------- 主人公オデュッセウス（金の兜・赤い房・赤いマント） ---------- */
const ODY = PAD([
  '...kk...',
  '..hhhh..',
  '.hhhhhh.',
  '.hhssss.',
  '.hhsses.',
  '..bsss..',
  '..bbbb..',
  '.rrttrr.',
  'srrttrrs',
  's.tttt.s',
  '..tttt..',
  '..s..s..',
  '..s..s..',
  '.ff..ff.',
]);
const ODY_PAL = { k: OC.red, h: OC.gold, s: OC.skin, e: OC.eye, b: OC.beard, r: OC.red, t: OC.cream, f: OC.hair };

/* 乞食に変えられた姿（第6話） */
const BEGGAR = PAD([
  '..ggg....',
  '.ggggg...',
  '.ggssss..',
  '.ggsses.w',
  '..bbbb..w',
  '..bbb...w',
  '.gggggg.w',
  'gggggggsw',
  'g.ggggg.w',
  '..gggg..w',
  '..s..s..w',
  '..s..s..w',
  '.ff..ff.w',
]);
const BEGGAR_PAL = { g: '#7a6a58', s: OC.skin, e: OC.eye, b: '#d8d4cc', w: OC.wood, f: OC.hair };

/* 部下（青い服） */
const CREW = PAD([
  '........',
  '..hhhh..',
  '.hhhhhh.',
  '.hhssss.',
  '.hhsses.',
  '..hsss..',
  '...ss...',
  '.bbbbbb.',
  'sbbbbbbs',
  's.bbbb.s',
  '..bbbb..',
  '..s..s..',
  '..s..s..',
  '.ff..ff.',
]);
const CREW_PAL = { h: OC.hair, s: OC.skin, e: OC.eye, b: OC.blue, f: OC.hair };

/* 女性（髪と服の色を変えて、キルケー・ペネロペ・ナウシカアなどに使う） */
const WOMAN = PAD([
  '..hhhh..',
  '.hhhhhh.',
  '.hhssss.',
  '.hhsses.',
  '.hhssss.',
  '.hh.ss..',
  '.hdddd..',
  '.dddddd.',
  'sddddddds',
  's.dddd.s',
  '.dddddd.',
  '.dddddd.',
  'dddddddd',
  '.ss..ss.',
]);

/* 男（王・老人など。冠 c、ひげ b、服 d） */
const MAN = PAD([
  '..cccc..',
  '.hhhhhh.',
  '.hhssss.',
  '.hhsses.',
  '..bsss..',
  '..bbbb..',
  '..bbb...',
  '.dddddd.',
  'sddddddds',
  's.dddd.s',
  '..dddd..',
  '..dddd..',
  '.dddddd.',
  '.ff..ff.',
]);

/* 船（右向き。帆に赤い帯、舳先に目。c = 漕ぎ手の頭、q = オデュッセウスの兜） */
const SHIP = (() => {
  const w = 36, h = 16, g = [...Array(h)].map(() => Array(w).fill('.'));
  const put = (x, y, ch) => { if (x >= 0 && x < w && y >= 0 && y < h) g[y][x] = ch; };
  for (let y = 0; y <= 9; y++) put(17, y, 'm');                        // 帆柱
  for (let x = 9; x <= 25; x++) put(x, 1, 'y');                         // 帆桁
  for (let y = 2; y <= 7; y++) for (let x = 10; x <= 24; x++) if (x !== 17) put(x, y, y === 4 ? 'r' : 's');
  for (let x = 1; x <= 34; x++) put(x, 10, 'h');                        // 舷側
  for (let x = 2; x <= 33; x++) put(x, 11, 'g');                        // 金の帯
  put(1, 11, 'h'); put(34, 11, 'h');
  for (let x = 3; x <= 32; x++) put(x, 12, 'h');
  for (let x = 5; x <= 30; x++) put(x, 13, 'k');                        // 竜骨
  [[0, 7], [0, 8], [1, 9], [0, 6], [1, 6]].forEach(([x, y]) => put(x, y, 'h'));      // 艫の反り
  [[35, 6], [35, 7], [34, 8], [34, 9], [35, 5]].forEach(([x, y]) => put(x, y, 'h')); // 舳先
  put(31, 11, 'e');                                                     // 舳先の目
  [6, 10, 14, 21, 25, 29].forEach(x => put(x, 9, 'c'));                 // 漕ぎ手
  put(3, 9, 'q'); put(3, 8, 'q');                                       // 艫のオデュッセウス
  [8, 12, 16, 20, 24, 28].forEach(x => { put(x, 13, 'o'); put(x - 1, 14, 'o'); put(x - 2, 15, 'o'); }); // 櫂
  return g.map(r => r.join(''));
})();
const SHIP_PAL = { m: OC.hull2, y: OC.hull2, s: OC.sail, r: OC.stripe, h: OC.hull, g: OC.gold, k: OC.hull2, e: OC.white, c: OC.skin, q: OC.gold, o: OC.wood };
/* 帆をたたんだ船・人の乗っていない船などは pal を変えて使う */
function ship(x, y, sc = 1, flip = false, pal = {}) { sprite(x, y, SHIP, Object.assign({}, SHIP_PAL, pal), sc, flip); }

/* いかだ（第5話） */
const RAFT = PAD([
  '......m......',
  '...ssssss....',
  '...ssssss....',
  '...ssssss....',
  '......m......',
  '.wwwwwwwwwww.',
  'wwwwwwwwwwwww',
]);

/* ---------- 動物・もの ---------- */
const SHEEP = PAD([
  '..wwwwwww...',
  '.wwwwwwwwwhh',
  'wwwwwwwwwwhe',
  'wwwwwwwwwwhh',
  '.wwwwwwwww..',
  '..l.l..l.l..',
  '..l.l..l.l..',
]);
const RAM = PAD([
  '..........oo.',
  '..wwwwwww.o..',
  '.wwwwwwwwwhho',
  'wwwwwwwwwwhe.',
  'wwwwwwwwwwhh.',
  '.wwwwwwwww...',
  '..l.l..l.l...',
  '..l.l..l.l...',
]);
const SHEEP_PAL = { w: '#e8e4d8', h: '#3a3040', e: OC.white, l: '#3a3040', o: '#c8b890' };
const PIG = PAD([
  '...pppppp..',
  '.pppppppppk',
  'ppppppppppnn',
  'ppppppppppp.',
  '.ppppppppp..',
  '..p.p.p.p...',
]);
const PIG_PAL = { p: OC.pink, k: '#c07088', n: '#c07088' };
const COW = PAD([
  'o..........',
  '.o.........',
  'hhh.........',
  'hehbbbbbbbb.',
  'hhhbbwwbbbbb',
  '.hbbbwwwbbbb',
  '..bbbbbbbbbt',
  '..l.l...l.l.',
  '..l.l...l.l.',
]);
const COW_PAL = { o: '#e8e0c0', h: '#8a4a28', e: OC.eye, b: '#a85a30', w: OC.white, l: '#5a3018', t: '#5a3018' };
const DOG = PAD([   // 寝そべった老犬
  '..........ee.',
  '.........eeee',
  'bbbbbbbbbbbkb',
  'bbbbbbbbbbbb.',
  '.bbbbbbbbbb..',
  'tll.ll..llll.',
]);
const DOG_PAL = { e: '#6a5040', b: '#8a7a68', k: OC.eye, l: '#6a5a4a', t: '#8a7a68' };
const LOTUS = PAD([
  '...p...',
  '.p.p.p.',
  '.ppppp.',
  'ppppppp',
  '.ggggg.',
  '...g...',
]);
const LOTUS_PAL = { p: '#f5c0d8', g: OC.grass };
const BAG = PAD([    // アイオロスの風の袋（銀のひも）
  '...cc...',
  '..c..c..',
  '..bccb..',
  '.bbbbbb.',
  'bbbbbbbb',
  'bbbbbbbb',
  'bbbbbbbb',
  '.bbbbbb.',
]);
const BAG_PAL = { b: '#9a6a3a', c: '#dfe6f0' };
const TREE = PAD([   // オリーブの木
  '..lllll...',
  '.lllllll..',
  'llllllllll',
  '.llllllll.',
  '..lltlll..',
  '....t.....',
  '....tt....',
  '....t.....',
  '....t.....',
  '...ttt....',
]);
const TREE_PAL = { l: '#6f8f4a', t: '#7a5a3a' };
const CLOUD = PAD([
  '...wwww.....',
  '.wwwwwwww...',
  'wwwwwwwwwwww',
  '.wwwwwwwww..',
]);

/* ---------- 大きい文字（見出し用。3x5 の字を拡大して描く） ---------- */
function bigText(s, x, y, c, sc = 2, align = 'left') {
  s = String(s).toUpperCase();
  const w = (s.length * 4 - 1) * sc;
  if (align === 'center') x -= Math.floor(w / 2); else if (align === 'right') x -= w;
  x = Math.round(x); y = Math.round(y);
  for (let i = 0; i < s.length; i++) {
    const g = G[s[i]];
    if (!g) { LINT.missing.add(s[i]); continue; }
    const rows = [0, 1, 2, 3, 4].map(r => g.slice(r * 3, r * 3 + 3).replace(/0/g, '.').replace(/1/g, 'x'));
    sprite(x + i * 4 * sc, y, rows, { x: c }, sc);
  }
  LINT.boxes.push([x, y, x + w, y + 5 * sc, s]);
  if (x < 0 || y < 0 || x + w > W || y + 5 * sc > H) LINT.out.push(s);
  return w;
}

/* ---------- 背景 ---------- */
function sky(y1, c = OC.sky, starSeed = 0, t = 0) {
  R(0, 11, W, y1 - 11, c);
  if (starSeed) {
    const r = rng(starSeed);
    for (let i = 0; i < 26; i++) {
      const x = (r() * W) | 0, y = 13 + ((r() * (y1 - 16)) | 0), ph = r() * 3;
      R(x, y, 1, 1, blink(t + ph, 1.2) ? '#cfd8f0' : '#6a7090');
    }
  }
}
/* 海。波の模様は 0.4 秒ごとに 2px ずつ動く（GIF を軽くするため） */
function sea(y0, t, c = OC.sea, c2 = OC.sea2) {
  R(0, y0, W, H - y0, c);
  R(0, y0, W, 1, OC.foam);
  const k = Math.floor(t / 0.4);
  for (let j = 0; y0 + 5 + j * 8 < H; j++) {
    const y = y0 + 5 + j * 8, dir = j % 2 ? 1 : -1;
    const off = ((k * 2 * dir + j * 11) % 24 + 24) % 24;
    for (let x = off - 24; x < W; x += 24) R(x, y, 7, 1, c2);
  }
}
function bob(t, ph = 0) { return Math.round(Math.sin(t * 2.4 + ph) * 1.2); }
/* 島：底辺の中央 cx, 水面 y, 半幅 w, 高さ h */
function island(cx, y, w, h, top = OC.grass, body = OC.rock) {
  for (let dy = 0; dy < h; dy++) {
    const f = 1 - dy / h, hw = Math.round(w * Math.sqrt(f));
    R(cx - hw, y - dy - 1, hw * 2 + 1, 1, dy > h - 4 ? top : body);
  }
  R(cx - w - 2, y - 1, w * 2 + 5, 1, OC.sand);
}
function tree(x, y, sc = 1) { sprite(x, y, TREE, TREE_PAL, sc); }
function cloud(x, y, sc = 1, c = '#3a4a70') { sprite(x, y, CLOUD, { w: c }, sc); }

/* ---------- 人物 ---------- */
function ody(x, y, sc = 2, flip = false, pal = {}) { sprite(x, y, ODY, Object.assign({}, ODY_PAL, pal), sc, flip); }
function crew(x, y, sc = 2, flip = false, pal = {}) { sprite(x, y, CREW, Object.assign({}, CREW_PAL, pal), sc, flip); }
function woman(x, y, pal, sc = 2, flip = false) { sprite(x, y, WOMAN, Object.assign({ s: OC.skin, e: OC.eye }, pal), sc, flip); }
function man(x, y, pal, sc = 2, flip = false) { sprite(x, y, MAN, Object.assign({ s: OC.skin, e: OC.eye, h: OC.hair, f: OC.hair }, pal), sc, flip); }

/* ---------- 吹き出し・見出し ---------- */
/* 吹き出し：(ax, ay) を指す。本体は上に出る。dx で左右にずらす */
function say(s, ax, ay, c = C.ink, dx = 0, edge = C.dim) {
  const w = textWidth(s) + 7, x = Math.round(ax + dx - w / 2), y = ay - 15;
  box(x, y, w, 11, '#211d36', edge);
  text(s, x + 4, y + 3, c);
  R(ax - 1, y + 11, 3, 1, edge); R(ax, y + 12, 1, 2, edge);
}
/* 最初の場面の大見出し（t1 秒まで表示） */
function banner(ep, name, t, t1 = 2.8) {
  if (t > t1) return;
  const y = 36;
  box(24, y, 272, 46, '#161428', OC.gold);
  frameBox(26, y + 2, 268, 42, OC.gold2 || C.gold2);
  bigText('EPISODE ' + ep, 160, y + 9, OC.gold, 2, 'center');
  bigText(name, 160, y + 25, C.ink, 2, 'center');
}
/* 次回予告のラベル（点滅） */
function nextLabel(s, t, y = 150) {
  const w = textWidth('NEXT: ' + s) + 10, x = 160 - Math.round(w / 2);
  box(x, y, w, 13, '#161428', OC.gold);
  segs(x + 5, y + 4, [['NEXT: ', blink(t, 1.5) ? OC.gold : C.gold2], [s, C.ink]]);
}
/* 見出し帯（話数つき） */
function head(s) { title(EP, s); }

/* ===== 第2話 キュクロプス ===== */
const EP = '2';

check('大岩は荷車22台でも動かせない（表示 22）', 22 === 22);

/* ひとつ目の巨人ポリュペモス */
const CYC = PAD([
  '.....hhhhhh.....',
  '....hhhhhhhh....',
  '...hssssssssh...',
  '...ssswwwwsss...',
  '...sswwppwwss...',
  '...ssswwwwsss...',
  '...ssssssssss...',
  '....bssnnssb....',
  '....bbbmmbbb....',
  '.....bbbbbb.....',
  '..ffffffffffff..',
  '.sffffffffffffs.',
  'ssffffffffffffss',
  'ss.ffffffffff.ss',
  'ss.ffffffffff.ss',
  '...ffffffffff...',
  '....ll....ll....',
  '....ll....ll....',
  '....ll....ll....',
  '...fff....fff...',
]);
const CYC_SHUT = CYC.map((r, i) => i === 3 || i === 5 ? '...ssssssssss...' : i === 4 ? '...ssxxxxxxss...' : r);
const CYC_PAL = { h: '#3a2a20', s: '#c8a07a', w: '#f4f0e0', p: '#8a2a20', b: '#3a2a20', n: '#a8805a', m: '#5a2020', f: '#7a5a3a', l: '#c8a07a', x: '#3a2a20' };
function cyc(x, y, sc, shut = false) { sprite(x, y, shut ? CYC_SHUT : CYC, CYC_PAL, sc); }
const WINESKIN = PAD(['.c..', 'www.', 'wwww', 'wwww', '.ww.']);
const UNDER = PAD([   // 羊の腹の下にしがみつく人（横向き）
  '.hhh..........',
  'hhsssbbbbbbss.',
  'hhsssbbbbbbsss',
  '.hh...........',
]);
const STAR = PAD(['..y..', '.yyy.', 'yyyyy', '.yyy.', '..y..']);

/* 洞窟の中（入口は右） */
function cave(t, open = true, boulderX = 330) {
  R(0, 11, W, H - 11, '#241c15');
  const r = rng(5);
  for (let x = 0; x < W; x += 8) R(x, 11, 8, 6 + ((r() * 12) | 0), '#3a2e24');
  for (let x = 0; x < W; x += 8) R(x, 168 - ((r() * 6) | 0), 8, 14, '#3a2e24');
  if (open) { R(262, 56, 50, 112, '#5a7ab0'); R(262, 150, 50, 18, '#4a7a40'); }
  // チーズの棚
  for (let i = 0; i < 3; i++) { R(10, 60 + i * 20, 46, 2, OC.wood); for (let k = 0; k < 4; k++) R(14 + k * 11, 53 + i * 20, 8, 7, '#e8c860'); }
  disc(boulderX, 112, 44, '#6e6458'); disc(boulderX - 8, 100, 20, '#857a6c');
}

const SCENES = [
  {
    name: 'ポリュペモスの洞窟',
    dur: 6.5,
    draw(t) {
      head('THE CAVE OF POLYPHEMUS');
      const roll = clamp((t - 4.8) / 1.2);
      cave(t, true, 360 - roll * 72);
      ody(78, 140, 2); crew(102, 140, 2); crew(122, 140, 2);
      sprite(94, 150, WINESKIN, { c: OC.cream, w: '#7a2a3a' }, 2);
      if (t > 2.8) {
        const walk = ease((t - 2.8) / 1.6);
        cyc(310 - walk * 120, 68, 5);
        for (let i = 0; i < 3; i++) sprite(330 - walk * 90 + i * 22, 150, SHEEP, SHEEP_PAL, 2);
        text('POLYPHEMUS', 150, 40, OC.gold, 'center');
      }
      if (roll > 0.9) text('22 WAGONS CANNOT MOVE IT', 184, 20, C.ink, 'center');
      banner(2, 'THE CYCLOPS', t);
    },
    cap: t => t < 2.8 ? '第2話「キュクロプス」。オデュッセウスは12人の部下と強いぶどう酒を持ち、チーズの並ぶ大きな洞窟に入った。'
      : t < 4.8 ? '帰ってきた洞窟の主は、海の神ポセイドンの息子で、ひとつ目の巨人ポリュペモスだった。'
        : '巨人は荷車22台でも動かせない大岩で入口をふさいだ。一行は閉じこめられた。',
  },
  {
    name: '「誰でもない」',
    dur: 6.5,
    draw(t) {
      head('MY NAME IS NOBODY');
      cave(t, false, 300);
      const sleep = t > 4.6;
      cyc(170, 68, 5, sleep);
      ody(96, 140, 2); crew(60, 140, 2); crew(38, 140, 2);
      if (t < 4.6) sprite(118, 128 - Math.round(ease(t / 1) * 6), WINESKIN, { c: OC.cream, w: '#7a2a3a' }, 2);
      if (t > 1 && t < 2.6) say('YOUR NAME?', 206, 66, C.ink, -10);
      if (t > 2 && t < 4.6) say('NOBODY (OUTIS)', 104, 136, OC.gold, -12);
      if (t > 3.2 && t < 4.6) say('NOBODY I EAT LAST', 206, 66, C.ink, 10);
      if (sleep) ['Z', 'Z', 'Z'].forEach((z, i) => { const k = (t * 1.5 + i / 3) % 1; text(z, 244 + i * 8 + k * 6, 64 - i * 8 - k * 8, C.ink2); });
    },
    cap: t => t < 2 ? '巨人は部下を次々に食べてしまった。オデュッセウスは強いぶどう酒をすすめ、巨人は喜んで飲んだ。'
      : t < 3.2 ? '名前を聞かれて、オデュッセウスは「ウーティス（誰でもない）」と名乗った。'
        : t < 4.6 ? '巨人は「お礼に、誰でもないは最後に食ってやろう」と言い、'
          : '酔って眠りこんでしまった。',
  },
  {
    name: 'ひとつ目をつぶす',
    dur: 6,
    draw(t) {
      head('THE OLIVE STAKE');
      cave(t, false, 300);
      const hit = t > 2.2;
      cyc(170, 68, 5, hit);
      // 火で焼いたオリーブの杭を 5 人で運ぶ
      const f = hit ? 1 : ease(t / 2.2), tipX = lerp(40, 208, f), tipY = lerp(130, 90, f);
      if (t < 3.2) { for (const d of [0, 1]) line(tipX - 90, tipY + 34 + d, tipX, tipY + d, '#8a6a3a'); R(tipX - 2, tipY - 1, 4, 4, blink(t, 4) ? OC.fire : '#ffd66b'); }
      if (!hit) { ody(tipX - 60, 138, 2); crew(tipX - 82, 140, 2); }
      if (hit && t < 3.4) sprite(200, 82, STAR, { y: '#ffd66b' }, 3);
      if (hit) {
        ody(60, 140, 2, true); crew(34, 140, 2, true);
        if (t > 2.6 && t < 4.8) say('HELP! BROTHERS!', 206, 66, C.red, 0);
      }
      if (t > 4) { text('WHO HURTS YOU?', 312, 24, OC.foam, 'right'); }
      if (t > 4.8) say('NOBODY!', 206, 66, OC.gold, 0);
    },
    cap: t => t < 2.2 ? 'オデュッセウスたちは、巨人のオリーブの棍棒を削って杭を作り、火で焼いてから、眠る巨人のひとつ目に突き立てた。'
      : t < 4 ? '目を失った巨人は大声で叫び、近くに住むキュクロプス仲間を呼んだ。'
        : '「誰にやられた？」「誰でもない（ウーティス）がやった！」。仲間たちは「誰でもないなら」と帰ってしまった。',
  },
  {
    name: '羊の腹に隠れて脱出',
    dur: 6,
    draw(t) {
      head('ESCAPE UNDER THE SHEEP');
      cave(t, true, 360);
      R(262, 56, 58, 112, '#8ab0e0'); R(262, 150, 58, 18, '#5a9a50');
      cyc(206, 68, 5, true);
      // 羊が 1 頭ずつ外へ。腹の下に人がしがみついている
      for (let i = 0; i < 4; i++) {
        const x = -50 + ((t * 38 + i * 70) % 330), big = i === 3;
        const s = big ? 3 : 2;
        sprite(x, 150 - 8 * s + 12, big ? RAM : SHEEP, SHEEP_PAL, s);
        sprite(x + 4, 150 - 8 * s + 12 + 5 * s, UNDER, big ? Object.assign({}, ODY_PAL, { h: OC.gold, b: OC.red }) : CREW_PAL, 2);
        // 巨人の手が背中をなでる
        if (x > 196 && x < 250) R(x + 6 * s, 150 - 8 * s + 6, 10, 6, CYC_PAL.s);
      }
      text('HE FEELS ONLY THEIR BACKS', 8, 20, C.ink);
    },
    cap: t => t < 3 ? '朝、巨人は羊を外に出すため入口の岩をどけ、座って羊の背中を1頭ずつなでて確かめた。'
      : '部下は3頭ずつ束ねた羊の腹の下に、オデュッセウスは一番大きな雄羊の腹にしがみつき、そっと外へ出た。',
  },
  {
    name: '名を明かしてポセイドンの怒り',
    dur: 6.5,
    draw(t) {
      head("POSEIDON'S ANGER");
      sky(100, '#4a6aa0');
      sea(100, t);
      // 崖と巨人
      R(0, 72, 72, 28, OC.rock); R(0, 66, 56, 6, OC.rock);
      cyc(6, 12, 3, true);
      const sx = 200 + t * 10;
      ship(sx, 88 + bob(t), 2, true);
      if (t < 2.4) say('I AM ODYSSEUS OF ITHACA!', sx + 14, 86, OC.gold, -30);
      // 投げた大岩としぶき
      if (t > 1.8 && t < 3.2) { const f = (t - 1.8) / 1.4; disc(lerp(50, sx - 20, f), 40 + 50 * f - 50 * f * (1 - f), 6, '#857a6c'); }
      if (t > 3.2 && t < 4) for (let i = 0; i < 5; i++) R(sx - 26 + i * 4, 92 - (i % 2) * 6, 2, 6, OC.foam);
      if (t > 3.6) {
        const up = ease((t - 3.6) / 1);
        ctx.globalAlpha = .35 + up * .5;
        const o = Math.round((1 - up) * 40);
        man(110, 28 + o, { c: OC.gold, h: '#2a8a8a', b: '#2a8a8a', d: '#2a5aa0', f: '#2a5aa0' }, 4);
        const tx = 146; for (let k = 0; k < 2; k++) line(tx + k, 84 + o, tx + k, 26 + o, OC.gold);
        sprite(tx - 4, 18 + o, ['x.x.x', 'x.x.x', 'xxxxx', '..x..'], { x: OC.gold }, 2);
        ctx.globalAlpha = 1;
        text('POSEIDON', 90, 60, OC.foam, 'right');
      }
      if (t > 5) nextLabel('EPISODE 3  THE BAG OF WINDS', t, 162);
    },
    cap: t => t < 1.8 ? '船で逃げながら、オデュッセウスは得意になって「おれはイタケーのオデュッセウスだ！」と本当の名を叫んだ。'
      : t < 3.6 ? '怒った巨人は大岩を投げつけ、大波が船を押し戻した。'
        : t < 5 ? '巨人は父ポセイドンに祈った。「帰すなら、遅れて、仲間をすべて失い、ひとりで帰るように」。'
          : 'こうして海の神ポセイドンが敵になった。次回、第3話「風の袋とキルケー」。',
  },
];
