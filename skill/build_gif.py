#!/usr/bin/env python3
"""scenes.js（SCENES を定義したファイル）から、字幕つきのピクセルアート GIF を作る。

  python3 build_gif.py scenes.js -o out.gif --title "ロドリゲスの回転公式"

やること:
  1. pixel.js + scenes.js をヘッドレス Chrome で動かし、全コマを書き出す
     （同じものをブラウザで動かせるプレビュー <out>_preview.html も書き出す）
  2. 自動チェック（例外・フォントにない文字・画面外の文字・文字同士の重なり）を表示する
  3. 各場面の途中のコマを並べた確認用画像 <out>_sheet.png を作る
  4. 下に日本語字幕の帯を付け、ffmpeg で GIF にする
必要なもの: Google Chrome / Chromium、ffmpeg、Python の Pillow、日本語フォント
"""
import argparse, base64, html, io, json, os, re, shutil, subprocess, sys, tempfile
from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
FPS = 10

LOOP_JS = r"""
(() => {
  const out = [], lint = { errors: [], missing: [], outside: {}, overlaps: {} };
  const seen = {};
  if (typeof SCENES === 'undefined' || !Array.isArray(SCENES)) lint.errors.push('SCENES が定義されていません');
  else SCENES.forEach((s, si) => {
    const n = Math.round(s.dur * FPS_);
    for (let f = 0; f < n; f++) {
      const t = f / FPS_;
      resetCtx();
      clear(); LINT.boxes = []; LINT.out = [];
      const c0 = typeof CHECKS !== 'undefined' ? CHECKS.length : 0;
      try { s.draw(t); } catch (e) { if (!seen['e' + si]) { seen['e' + si] = 1; lint.errors.push('場面 ' + si + ' t=' + t.toFixed(1) + ': ' + e.message); } }
      if (typeof CHECKS !== 'undefined' && CHECKS.length > c0) {   // draw の中の検算は場面ごとに記録して捨てる
        CHECKS.splice(c0).forEach(([lab, ok]) => { lint.drawChecks = lint.drawChecks || 0; lint.drawChecks++; if (!ok) { const k = si + '|chk|' + lab; if (!seen[k]) { seen[k] = 1; (lint.sceneChecks = lint.sceneChecks || {})[si] = ((lint.sceneChecks || {})[si] || []).concat(['t=' + t.toFixed(1) + ' ' + lab]); } } });
      }
      const B = LINT.boxes;
      for (let i = 0; i < B.length; i++) for (let j = i + 1; j < B.length; j++) {
        const a = B[i], b = B[j];
        if (a[0] < b[2] && b[0] < a[2] && a[1] < b[3] && b[1] < a[3] && a[4] !== b[4]) {
          const k = si + '|' + a[4] + '|' + b[4];
          if (!seen[k]) { seen[k] = 1; (lint.overlaps[si] = lint.overlaps[si] || []).push('t=' + t.toFixed(1) + ' 「' + a[4] + '」と「' + b[4] + '」'); }
        }
      }
      B.forEach(bx => { if (/undefined|NaN|\[object|null/.test(bx[4])) { const k = si + '|bad|' + bx[4]; if (!seen[k]) { seen[k] = 1; (lint.badText = lint.badText || {})[si] = ((lint.badText || {})[si] || []).concat(['t=' + t.toFixed(1) + ' 「' + bx[4] + '」']); } } });
      LINT.out.forEach(o => { const k = si + '|out|' + o; if (!seen[k]) { seen[k] = 1; (lint.outside[si] = lint.outside[si] || []).push('t=' + t.toFixed(1) + ' 「' + o + '」'); } });
      let cap = '';
      try { cap = String(s.cap ? s.cap(t) : ''); } catch (e) { cap = ''; }
      out.push(si + '\t' + f + '\t' + (s.name || '') + '\t' + cap.replace(/[\t\n]/g, ' ') + '\t' + cv.toDataURL('image/png'));
    }
  });
  lint.missing = [...LINT.missing];
  lint.colorText = [...new Set(LINT.colorText || [])].slice(0, 5);
  lint.checks = (typeof CHECKS !== 'undefined' ? CHECKS : []).filter(c => !c[1]).map(c => c[0]);
  lint.nchecks = typeof CHECKS !== 'undefined' ? CHECKS.length : 0;
  lint.exprErr = [...new Set(LINT.exprErr || [])].slice(0, 8);
  document.getElementById('lint').textContent = JSON.stringify(lint);
  document.getElementById('out').textContent = out.join('\n');
})();
"""


def find_chrome(arg):
    cands = [arg, os.environ.get('CHROME'),
             '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
             '/Applications/Chromium.app/Contents/MacOS/Chromium',
             shutil.which('google-chrome'), shutil.which('google-chrome-stable'),
             shutil.which('chromium'), shutil.which('chromium-browser')]
    for c in cands:
        if c and os.path.exists(c):
            return c
    sys.exit('Chrome / Chromium が見つかりません。--chrome で場所を指定してください。')


def find_font(arg, bold=False):
    cands = [arg,
             f"/System/Library/Fonts/ヒラギノ角ゴシック {'W6' if bold else 'W5'}.ttc",
             '/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc' if bold else '/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc',
             '/usr/share/fonts/noto-cjk/NotoSansCJK-Regular.ttc',
             '/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc',
             'C:/Windows/Fonts/meiryo.ttc', 'C:/Windows/Fonts/msgothic.ttc']
    for c in cands:
        if c and os.path.exists(c):
            return c
    sys.exit('日本語フォントが見つかりません。--font で .ttf/.ttc を指定してください。')


PREVIEW_JS = r"""
(() => {
  const cap = document.getElementById('cap'), tabs = document.getElementById('tabs'), bar = document.getElementById('bar');
  let cur = 0, t = 0, playing = true, last = performance.now();
  SCENES.forEach((s, i) => {
    const b = document.createElement('button'); b.textContent = i + ' ' + (s.name || '');
    b.onclick = () => { cur = i; t = 0; }; tabs.appendChild(b);
  });
  document.getElementById('play').onclick = e => { playing = !playing; e.target.textContent = playing ? '一時停止' : '再生'; };
  document.addEventListener('keydown', e => {
    if (e.key === 'ArrowRight') { cur = (cur + 1) % SCENES.length; t = 0; }
    if (e.key === 'ArrowLeft') { cur = (cur - 1 + SCENES.length) % SCENES.length; t = 0; }
    if (e.key === ' ') { e.preventDefault(); document.getElementById('play').click(); }
  });
  function frame(now) {
    const dt = Math.min(.1, (now - last) / 1000); last = now;
    const s = SCENES[cur];
    if (playing) { t += dt; if (t > s.dur + 1.2) { cur = (cur + 1) % SCENES.length; t = 0; } }
    const tt = Math.min(t, s.dur);
    resetCtx(); clear();
    try { s.draw(tt); cap.textContent = s.cap ? s.cap(tt) : ''; } catch (e) { cap.textContent = 'エラー: ' + e.message; }
    [...tabs.children].forEach((b, i) => b.className = i === cur ? 'on' : '');
    bar.style.width = (Math.min(1, t / s.dur) * 100) + '%';
    requestAnimationFrame(frame);
  }
  requestAnimationFrame(frame);
})();
"""


def write_preview(path, scenes_path, title, hires=1):
    pixel = open(os.path.join(HERE, 'pixel.js'), encoding='utf-8').read()
    scenes = open(scenes_path, encoding='utf-8').read()
    page = f"""<!doctype html><html lang="ja"><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(title or 'pixel anim')}</title>
<style>
  body {{ margin: 0; padding: 16px; background: #0b0a13; color: #e9e6f7; font-family: "Hiragino Sans", "Noto Sans CJK JP", sans-serif; }}
  .wrap {{ max-width: 960px; margin: 0 auto; display: grid; gap: 10px; }}
  h1 {{ font-size: 18px; margin: 0; color: #f0b43c; }}
  canvas {{ width: 100%; aspect-ratio: 16 / 9; image-rendering: pixelated; background: #0f0e1a; display: block; }}
  #cap {{ min-height: 3em; font-size: 16px; line-height: 1.6; }}
  #tabs {{ display: flex; flex-wrap: wrap; gap: 6px; }}
  button {{ background: #1c1a2e; color: #a9a4c6; border: 1px solid #3a3657; padding: 4px 10px; cursor: pointer; font: inherit; font-size: 13px; }}
  button.on {{ background: #f0b43c; color: #1a1206; border-color: #f0b43c; }}
  .track {{ height: 4px; background: #262338; }} #bar {{ height: 4px; background: #f0b43c; width: 0; }}
</style>
<div class="wrap">
  <h1>{html.escape(title or '')}</h1>
  <canvas id="screen" width="320" height="180"></canvas>
  <div class="track"><div id="bar"></div></div>
  <div id="cap"></div>
  <div id="tabs"></div>
  <div><button id="play">一時停止</button> ← → で場面を移動、スペースで一時停止</div>
</div>
<script>window.PIXEL_SCALE = {hires};</script><script>{pixel}</script><script>{scenes}</script><script>{PREVIEW_JS}</script>
</html>"""
    open(path, 'w', encoding='utf-8').write(page)


def render(scenes_path, chrome, hires=1):
    pixel = open(os.path.join(HERE, 'pixel.js'), encoding='utf-8').read()
    scenes = open(scenes_path, encoding='utf-8').read()
    page = ('<!doctype html><meta charset="utf-8"><canvas id="screen" width="320" height="180"></canvas>'
            '<pre id="lint"></pre><pre id="out"></pre>'
            '<script>window.__err=[];window.onerror=(m,s,l)=>{window.__err.push(m+" (line "+l+")");document.getElementById("lint").textContent=JSON.stringify({errors:window.__err});};</script>'
            f'<script>window.PIXEL_SCALE = {hires};</script><script>{pixel}</script><script>{scenes}</script>'
            f'<script>const FPS_ = {FPS};{LOOP_JS}</script>')
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, 'render.html')
        open(p, 'w', encoding='utf-8').write(page)
        r = subprocess.run([chrome, '--headless=new', '--disable-gpu', '--virtual-time-budget=180000', '--dump-dom', 'file://' + p],
                           capture_output=True, text=True, timeout=900)
    dom = r.stdout
    lint = json.loads(html.unescape(re.search(r'<pre id="lint">(.*?)</pre>', dom, re.S).group(1)) or '{}')
    body = html.unescape(re.search(r'<pre id="out">(.*?)</pre>', dom, re.S).group(1)).strip()
    rows = [l.split('\t') for l in body.split('\n')] if body else []
    return rows, lint


def report(lint):
    ok = True
    for e in lint.get('errors', []):
        print('ERROR    ', e); ok = False
    for x in lint.get('colorText', []):
        print('COLOR AS TEXT 色コードが文字として描かれている（matrix/segs の渡し方を確認）:', x); ok = False
    for si, v in (lint.get('sceneChecks') or {}).items():
        for x in v[:4]:
            print(f'CHECK FAILED 場面 {si} {x} の検算が合わない'); ok = False
    for x in lint.get('checks', []):
        print('CHECK FAILED 検算が合わない:', x); ok = False
    for x in lint.get('exprErr', []):
        print('EXPR ERROR 式が読めない:', x); ok = False
    if lint.get('nchecks') == 0 and not lint.get('drawChecks'):
        print('NO CHECKS 検算が1件もない（式を画面に出すなら checkExpr を使う）')
    if lint.get('nchecks') is not None:
        print(f"検算 {lint.get('nchecks')} 件のうち失敗 {len(lint.get('checks', []))} 件（draw 内の検算 {lint.get('drawChecks', 0)} 回、失敗 {sum(len(v) for v in (lint.get('sceneChecks') or {}).values())} 種類）")
    if lint.get('missing'):
        print('MISSING GLYPH（フォントにない文字。別の書き方に）:', ' '.join(lint['missing'])); ok = False
    for si, v in (lint.get('badText') or {}).items():
        for x in v[:3]:
            print(f'BADTEXT   場面 {si} {x} にプログラムの値（undefined / NaN など）が出ている'); ok = False
    for si, v in (lint.get('outside') or {}).items():
        for x in v[:5]:
            print(f'OUTSIDE   場面 {si} {x} が画面からはみ出し'); ok = False
    for si, v in (lint.get('overlaps') or {}).items():
        for x in v[:6]:
            print(f'OVERLAP   場面 {si} {x} が重なっている'); ok = False
    print('LINT OK' if ok else 'LINT: 上の問題を直してから再ビルドすること')
    return ok


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('scenes')
    ap.add_argument('-o', '--out', default='out.gif')
    ap.add_argument('--title', default='')
    ap.add_argument('--colors', type=int, default=64)
    ap.add_argument('--scale', type=int, default=2, help='ドットの拡大率（2 → 640x360）')
    ap.add_argument('--step', type=int, default=2, help='何コマおきに使うか（2 → 毎秒5コマ）')
    ap.add_argument('--hold', type=float, default=1.5, help='各場面の最後で止める秒数')
    ap.add_argument('--per-scene', action='store_true', help='場面ごとの GIF も作る')
    ap.add_argument('--lint-only', action='store_true', help='チェックと確認画像だけ作る')
    ap.add_argument('--hires', type=int, default=1, help='高解像度モード（4 なら 1280x720 で描き、文字をなめらかなフォントにする）')
    ap.add_argument('--frames-dir', help='各場面の 35%% と 80%% のコマを原寸 PNG で保存するフォルダ（判定用）')
    ap.add_argument('--chrome'); ap.add_argument('--font')
    a = ap.parse_args()

    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    rows, lint = render(a.scenes, find_chrome(a.chrome), a.hires)
    report(lint)
    write_preview(os.path.splitext(a.out)[0] + '_preview.html', a.scenes, a.title, a.hires)
    print('プレビュー:', os.path.splitext(a.out)[0] + '_preview.html', '（ブラウザで開くと動く）')
    if not rows:
        sys.exit('コマが1枚も書き出せませんでした。')

    scenes = {}
    for si, f, name, cap, url in rows:
        scenes.setdefault(int(si), []).append((int(f), name, cap, url.split(',', 1)[1]))
    n = len(scenes)

    # 確認用の一覧画像（各場面 35% と 80% の時点）
    base = os.path.splitext(a.out)[0]
    shots = []
    for si in sorted(scenes):
        fr = scenes[si]
        for q in (.35, .8):
            shots.append(Image.open(io.BytesIO(base64.b64decode(fr[min(len(fr) - 1, int(len(fr) * q))][3]))).convert('RGB').resize((640, 360), Image.NEAREST if a.hires == 1 else Image.LANCZOS))
    sheet = Image.new('RGB', (1280, 360 * len(scenes)), (0, 0, 0))
    for k, im in enumerate(shots):
        sheet.paste(im, ((k % 2) * 640, (k // 2) * 360))
    sheet.save(base + '_sheet.png')
    if a.frames_dir:
        os.makedirs(a.frames_dir, exist_ok=True)
        for si in sorted(scenes):
            fr = scenes[si]
            for tag, q in (('a', .35), ('b', .8)):
                Image.open(io.BytesIO(base64.b64decode(fr[min(len(fr) - 1, int(len(fr) * q))][3]))).convert('RGB').save(os.path.join(a.frames_dir, f's{si}_{tag}.png'))
    print('確認画像:', base + '_sheet.png', '（各場面の 35% と 80% の時点）')
    if a.lint_only:
        return

    S = a.scale
    Wd, Hd, BAND = 320 * S, 180 * S, 32 * S
    font = ImageFont.truetype(find_font(a.font), 8 * S)
    small = ImageFont.truetype(find_font(a.font, bold=True), 6 * S)

    def wrap(s, width):
        lines, cur = [], ''
        for ch in s:
            if font.getlength(cur + ch) > width and ch not in '、。）」':
                lines.append(cur); cur = ch
            else:
                cur += ch
        return lines + [cur] if cur else lines

    def compose(si, name, cap, b64):
        img = Image.open(io.BytesIO(base64.b64decode(b64))).convert('RGB')
        img = img.resize((Wd, Hd), Image.NEAREST if img.size[0] <= Wd else Image.LANCZOS)
        o = Image.new('RGB', (Wd, Hd + BAND), (15, 14, 26)); o.paste(img, (0, 0))
        d = ImageDraw.Draw(o)
        d.rectangle([0, Hd, Wd, Hd + 1], fill=(46, 43, 69))
        head = ' '.join(x for x in [a.title, f'{si}/{n - 1}', name] if x)
        d.text((7 * S, Hd + 3 * S), head, font=small, fill=(240, 180, 60))
        for i, l in enumerate(wrap(cap, Wd - 14 * S)[:2]):
            d.text((7 * S, Hd + 12 * S + i * 10 * S), l, font=font, fill=(233, 230, 247))
        return o

    def encode(frames, path):
        with tempfile.TemporaryDirectory() as d:
            for k, im in enumerate(frames):
                im.save(f'{d}/f{k:05d}.png')
            subprocess.run(['ffmpeg', '-y', '-loglevel', 'error', '-framerate', str(FPS / a.step), '-i', f'{d}/f%05d.png',
                            '-lavfi', f'palettegen=max_colors={a.colors}:stats_mode=full[p];[0:v][p]paletteuse=dither=none:diff_mode=rectangle',
                            '-loop', '0', path], check=True)

    allf = []
    hold = max(1, round(a.hold * FPS / a.step))
    for si in sorted(scenes):
        fr = [compose(si, name, cap, b64) for f, name, cap, b64 in scenes[si] if f % a.step == 0]
        fr += [fr[-1]] * hold
        if a.per_scene:
            encode(fr, f'{base}_{si}.gif')
        allf += fr
    encode(allf, a.out)
    secs = len(allf) * a.step / FPS
    print(f'GIF: {a.out}  {os.path.getsize(a.out) // 1024} KB  約{secs:.0f}秒  {Wd}x{Hd + BAND}')


if __name__ == '__main__':
    main()
