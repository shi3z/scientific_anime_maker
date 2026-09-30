"""DeepSeek にピクセルアート GIF アニメを作らせ、DeepSeek 自身に出来を判定させて、合格するまで直させる。

流れ（1 ジョブ）:
  1. 生成   … pixel-anim-gif スキルを渡して scenes.js を書かせる
  2. 検査   … build_gif.py --lint-only（例外・はみ出し・重なり・検算など）と確認画像
  3. 判定   … 場面ごとに確認画像を見せ、問題候補を洗い出させてから点数と合否を JSON で出させる
  4. 修正   … 不合格の場面だけ、判定の指摘と検査結果を渡して書き直させる
               （1 コマも描けないほど壊れていたら全体を作り直させる）
  5. 全場面が合格するか、上限回数に達するまで 2〜4 を繰り返し、最後に GIF を作る
"""
import base64, io, json, os, re, subprocess, threading, time, traceback, urllib.request, uuid
from PIL import Image

ROOT = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.normpath(os.path.join(ROOT, '..'))
SKILL = os.path.join(REPO, 'skill')
REFERENCE = os.path.join(REPO, 'examples', 'reference_scenes.js')   # 見本（あれば使う）
JOBS = os.path.join(ROOT, 'jobs')
os.makedirs(JOBS, exist_ok=True)


def load_config():
    """設定の読み込み。優先順位: 環境変数 > config.json > 既定値。
    config.json の場所は環境変数 SAM_CONFIG で変えられる（既定はリポジトリ直下）。"""
    cfg = {'llm': {'url': 'http://localhost:8000/v1/chat/completions', 'key': '', 'model': 'deepseek-v4.1-flash'},
           'port': 8777, 'hires': 4}
    path = os.environ.get('SAM_CONFIG', os.path.join(REPO, 'config.json'))
    if os.path.exists(path):
        user = json.load(open(path, encoding='utf-8'))
        cfg['llm'].update(user.get('llm') or {})
        cfg.update({k: v for k, v in user.items() if k != 'llm'})
    for env, key in (('SAM_LLM_URL', 'url'), ('SAM_LLM_KEY', 'key'), ('SAM_LLM_MODEL', 'model')):
        if os.environ.get(env):
            cfg['llm'][key] = os.environ[env]
    if os.environ.get('PORT'):
        cfg['port'] = int(os.environ['PORT'])
    cfg['config_path'] = path if os.path.exists(path) else None
    return cfg


CONFIG = load_config()
DEFAULT_CFG = CONFIG['llm']
LINT_KINDS = ('ERROR', 'OUTSIDE', 'OVERLAP', 'BADTEXT', 'MISSING GLYPH', 'COLOR AS TEXT', 'CHECK FAILED', 'EXPR ERROR')


class Stopped(Exception):
    pass


class Job:
    def __init__(self, params, jid=None):
        self.id = jid or time.strftime('%Y%m%d-%H%M%S-') + uuid.uuid4().hex[:4]
        self.dir = os.path.join(JOBS, self.id)
        os.makedirs(self.dir, exist_ok=True)
        self.stop = False
        self.lock = threading.Lock()
        self.state = {'id': self.id, 'params': params, 'status': 'queued', 'phase': '', 'created': time.time(),
                      'log': [], 'iterations': [], 'files': {}, 'llm_calls': 0, 'llm_seconds': 0}
        self.save()

    # ---- 状態 ----
    def log(self, msg):
        line = time.strftime('%H:%M:%S ') + msg
        with self.lock:
            self.state['log'].append(line)
            self.state['log'] = self.state['log'][-400:]
        print(f'[{self.id}] {line}', flush=True)
        self.save()

    def set(self, **kw):
        with self.lock:
            self.state.update(kw)
        self.save()

    def save(self):
        with open(os.path.join(self.dir, 'state.json'), 'w', encoding='utf-8') as f:
            json.dump(self.state, f, ensure_ascii=False, indent=1)

    def path(self, name):
        return os.path.join(self.dir, name)

    def check_stop(self):
        if self.stop:
            raise Stopped()


# ---------------------------------------------------------------- LLM
def chat(job, messages, max_tokens=32000, what=''):
    cfg = {**DEFAULT_CFG, **(job.state['params'].get('llm') or {})}
    body = {'model': cfg['model'], 'messages': messages, 'max_tokens': max_tokens, 'temperature': 0.6}
    last = None
    for attempt in range(4):
        job.check_stop()
        try:
            req = urllib.request.Request(cfg['url'], data=json.dumps(body).encode(),
                                         headers={'Content-Type': 'application/json', 'Authorization': 'Bearer ' + cfg['key']})
            t0 = time.time()
            r = json.load(urllib.request.urlopen(req, timeout=3000))
            dt = time.time() - t0
            with job.lock:
                job.state['llm_calls'] += 1
                job.state['llm_seconds'] += dt
            job.log(f'  DeepSeek {what}: {dt:.0f}秒 / 出力 {r.get("usage", {}).get("completion_tokens", "?")} トークン')
            return r['choices'][0]['message']['content'] or ''
        except urllib.error.HTTPError as e:
            last = f'HTTP {e.code} {e.read()[:200].decode("utf-8", "replace")}'
        except Exception as e:
            last = str(e)
        job.log(f'  DeepSeek エラー（{attempt + 1}回目）: {last}')
        time.sleep(15 * (attempt + 1))
    raise RuntimeError('DeepSeek に接続できません: ' + (last or ''))


def code_block(text, lang='javascript|js'):
    m = re.findall(r'```(?:' + lang + r')?\s*\n(.*?)```', text, re.S)
    return max(m, key=len) if m else None


def system_prompt():
    rd = lambda p: open(p, encoding='utf-8').read()
    s = (f"あなたは教材アニメーションを作るエンジニアです。次のスキルに従って作業します。\n\n"
         f"<skill name=\"pixel-anim-gif\">\n{rd(os.path.join(SKILL, 'SKILL.md'))}\n</skill>\n\n"
         f"<file name=\"pixel.js\">\n{rd(os.path.join(SKILL, 'pixel.js'))}\n</file>\n\n"
         f"<file name=\"example_scenes.js\">\n{rd(os.path.join(SKILL, 'example_scenes.js'))}\n</file>")
    if os.path.exists(REFERENCE):
        s += (f"\n\n<file name=\"reference_scenes.js\" note=\"同じスキルで作った別作品の見本。ドット絵・演出の水準の参考。流用しないこと\">\n"
              f"{rd(REFERENCE)}\n</file>")
    return s


# ---------------------------------------------------------------- 検査
def build(job, lint_only):
    title = job.state['params'].get('title') or ''
    cmd = ['python3', os.path.join(SKILL, 'build_gif.py'), job.path('scenes.js'), '-o', job.path('anim.gif'), '--title', title,
           '--hires', str(CONFIG.get('hires', 4)), '--frames-dir', job.path('frames')]
    if lint_only:
        cmd.append('--lint-only')
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=1800)
    out = r.stdout + r.stderr
    per, common = {}, []
    for l in out.splitlines():
        if not l.startswith(LINT_KINDS):
            continue
        m = re.search(r'場面 (\d+)', l)
        (per.setdefault(int(m.group(1)), []) if m else common).append(l.strip())
    ok = 'LINT OK' in out
    frames = 'コマが1枚も' not in out and os.path.exists(job.path('anim_sheet.png'))
    return {'text': out, 'per': per, 'common': common, 'ok': ok, 'frames': frames}


def split_scenes(src):
    """SCENES 配列の場面オブジェクトを字下げ（行頭 2 字の "  {" 〜 "  },"）で切り出す"""
    lines = src.split('\n')
    si = next((k for k, l in enumerate(lines) if re.match(r'\s*(const|let|var)\s+SCENES\s*=', l)), None)
    if si is None:
        return [], None
    offs = [0]
    for l in lines:
        offs.append(offs[-1] + len(l) + 1)
    objs, st = [], None
    for k in range(si + 1, len(lines)):
        if re.fullmatch(r'  \{\s*', lines[k]):
            st = k
        elif re.fullmatch(r'  \},?\s*', lines[k]) and st is not None:
            objs.append((offs[st], offs[k] + len(lines[k])))
            st = None
    return objs, offs[si]


def scene_images(job, idx):
    """判定・修正用: その場面の 35% と 80% のコマを原寸（1280x720）で 1 枚ずつ"""
    out = []
    for tag in ('a', 'b'):
        f = job.path(f'frames/s{idx}_{tag}.png')
        if os.path.exists(f):
            out.append({'type': 'image_url', 'image_url': {'url': 'data:image/png;base64,' + base64.b64encode(open(f, 'rb').read()).decode()}})
    return out


def expects_of(scene_code):
    """場面オブジェクトの expect: ['...', ...] を取り出す"""
    m = re.search(r'expect\s*:\s*\[(.*?)\]\s*,?\s*\n', scene_code, re.S)
    return re.findall(r"'((?:[^'\\]|\\.)*)'|\"((?:[^\"\\]|\\.)*)\"", m.group(1)) if m else []


def defined_names(head):
    return ', '.join(sorted(set(re.findall(r'(?:const|let|var|function)\s+([A-Za-z_$][\w$]*)', head))))


# ---------------------------------------------------------------- 生成・判定・修正
def generate(job):
    p = job.state['params']
    task = f"""次のテーマで、ピクセルアートの教材アニメーションの scenes.js を書いてください。
出力は ```javascript のコードブロック 1 つ（scenes.js 全体）だけ。

## テーマ
{p['topic']}

## 内容・要望
{p.get('details') or '（おまかせ。テーマの要点が順を追ってわかる構成にする）'}

## 条件
- 場面数 {p.get('scenes', 6)}、合計 {p.get('seconds', 45)} 秒前後。
- canvas 内は短い英語ラベル・数式・記号だけ。説明は日本語字幕 cap(t)。
- 動き（登場、点滅、移動、変化）を必ず入れる。式や数値を画面に出すなら checkExpr で検算する。
- 場面オブジェクトは SCENES 配列の中で、行頭 2 字下げの `  {{` で始めて `  }},` で終える（あとで場面ごとに直すため）。
- 各場面オブジェクトに `expect: ['...', ...]` を書く。80% の時点の絵が「こうなっているはず」という、目で確かめられる具体的な項目を 4〜8 個
  （例: '赤い箱は黄色い板の上に接して乗っている'、'L2 の線は支点の真下から箱の真下まで水平'、'W= のラベルは箱と重ならない'）。
  出来の判定はこの項目を 1 つずつ画像で確かめて行う。
- 図の座標は直書きせず、場面ごとに少数の変数（支点の x、板の y、腕の長さ、倍率など）から計算する。ラベルや寸法線もその変数から置く。
  そのうえで、図の部品どうしの関係（「箱の下端 = 板の上面」「L2 の右端 = 箱の中心 x」「ラベルは矢印と重ならない」など）を
  `check('説明', 条件)` で数値として検算する。draw の中で計算する位置は、同じ計算を場面の外の関数にしておき、検算にも使う。"""
    c = chat(job, [{'role': 'system', 'content': system_prompt()}, {'role': 'user', 'content': task}], what='生成')
    code = code_block(c)
    if not code:
        raise RuntimeError('生成結果にコードが含まれていません')
    open(job.path('scenes.js'), 'w', encoding='utf-8').write(code)


JUDGE_RULES = """あなたは厳しい品質レビュアーです。甘い判定をすると、壊れた教材がそのまま公開されます。
教材アニメーションの 1 場面を判定してください。画像は 2 枚で、1 枚目がその場面の 35%、2 枚目が 80% の時点のコマです。

判定の手順:
1. 画像を左上から右下まで順に見て、**問題の候補を必ず 3 つ以上**書き出す（どこの何が、なぜ問題かを具体的に）。
   見る観点: 文字同士の重なり / 文字と図形・線の重なり / 画面や枠からのはみ出し / 文字が小さすぎる・潰れて読めない /
   詰め込みすぎ / 何を描いたのかわからない絵 / 場面の意図（コードの name・cap）と絵が合っていない /
   動きがなく止まって見える / 不自然な空白や未描画の部分 / 事実や式の誤り
2. 各候補が本当に問題かを判断する。気のせい・好みの問題は除く。
3. 最後に次の JSON を ```json のコードブロックで出力する。
{"candidates": ["候補1", "候補2", "候補3", ...], "issues": ["確定した問題（直し方がわかる具体的な書き方）", ...], "score": 0から10の整数, "verdict": "PASS" または "FAIL"}

この画面の前提（これを理由に不合格にしない）:
- 文字の大きさと書体は固定。**文字を大きくしたり、太くしたり、縁取りしたりはできない。**
  「文字が小さい」「フォントを大きく」は指摘しない。ただし、文字同士や図と重なって読めない、背景と同じ色で見えない、は問題。
- canvas 内の文字は英語の大文字・記号だけ。日本語の説明は画面の外（字幕）に出るので、説明文が画面にないことは問題にしない。

判定の基準:
- PASS は、issues が空で、score が 9 以上のときだけ。少しでも直すべき点があれば FAIL。
- 自動検査の問題が 1 つでもあれば、必ず FAIL にし、その内容を issues に含める。"""


def judge_scene(job, idx, scene_code, lint_lines):
    exp = [x[0] or x[1] for x in expects_of(scene_code)]
    checklist = ('\n## こうなっているはずの項目（2 枚目の画像で 1 つずつ確かめる）\n'
                 '各項目について、画像で実際にどうなっているかを位置関係で具体的に書いてから（例:「箱の下端は板より約 15 ドット上で、接していない」）、'
                 'はい / いいえで答える。推測で「はい」にしない。「いいえ」の項目は必ず issues に入れる。JSON に "checks": [{"item": 項目, "observed": 実際の様子, "ok": true/false}, ...] も入れる。\n'
                 + '\n'.join(f'{k + 1}. {e}' for k, e in enumerate(exp))) if exp else ''
    text = f"""{JUDGE_RULES}
{checklist}

## この場面のコード（意図の確認用）
```javascript
{scene_code}
```

## この場面の自動検査結果
```
{chr(10).join(lint_lines) or '問題なし'}
```"""
    c = chat(job, [{'role': 'user', 'content': [{'type': 'text', 'text': text}] + scene_images(job, idx)}], 6000, what=f'判定 場面{idx}')
    raw = code_block(c, 'json') or (re.search(r'\{.*\}', c, re.S).group(0) if re.search(r'\{.*\}', c, re.S) else '')
    try:
        j = json.loads(raw)
    except Exception:
        return {'score': 0, 'verdict': 'FAIL', 'issues': ['判定結果を読み取れなかった'], 'candidates': []}
    j['score'] = int(j.get('score') or 0)
    issues = [str(x) for x in (j.get('issues') or [])]
    for c in (j.get('checks') or []):
        if isinstance(c, dict) and c.get('ok') is False:
            msg = f"「{c.get('item', '')}」になっていない: {c.get('observed', '')}"
            if msg not in issues:
                issues.append(msg)
    verdict = 'PASS' if str(j.get('verdict', '')).upper() == 'PASS' and not issues and j['score'] >= 9 and not lint_lines else 'FAIL'
    if lint_lines and not issues:
        issues = lint_lines
    return {'score': j['score'], 'verdict': verdict, 'issues': issues, 'candidates': [str(x) for x in (j.get('candidates') or [])],
            'checks': [c for c in (j.get('checks') or []) if isinstance(c, dict)]}


def fix_scene(job, src, idx, issues, lint_lines):
    objs, sstart = split_scenes(src)
    a, b = objs[idx]
    scene, head = src[a:b], src[:sstart]
    text = f"""scenes.js の場面 {idx} だけを書き直してください。画像はこの場面の 35% と 80% の時点のコマです。

## レビューで指摘された問題（すべて直す）
{chr(10).join('- ' + x for x in issues) or '- なし'}

## 自動検査の結果
```
{chr(10).join(lint_lines) or '問題なし'}
```

## 場面の外で定義されている名前
**使ってよいのはこれと pixel.js の関数だけ**。ここにない名前を使うと ReferenceError になる。必要な人物や物がなければ、この場面の draw の中で sprite() を使って描く:
{defined_names(head)}

## 場面の外のコード（参照のみ。変更不可）
```javascript
{head}
```

## いまの場面 {idx}
```javascript
{scene}
```

問題をどう直すかを 3 行以内で書き、SKILL.md の「レイアウトの注意」に従って直した場面オブジェクト 1 つだけ
（`{{ name, dur, expect: [...], draw(t) {{...}}, cap: t => ... }}` の形、末尾のカンマなし）を ```javascript のコードブロック 1 つで出力する。
expect の項目は残し、図の部品どうしの関係は場面の外で check() による数値検算を加える（検算は場面オブジェクトの外に置けないので、draw の先頭で `check(...)` を呼んでもよい）。"""
    c = chat(job, [{'role': 'system', 'content': system_prompt()},
                   {'role': 'user', 'content': [{'type': 'text', 'text': text}] + scene_images(job, idx)}], 16000, what=f'修正 場面{idx}')
    new = (code_block(c) or '').strip().rstrip(';').rstrip(',')
    if not new.startswith('{'):
        job.log(f'  場面{idx}: 書き直しの結果を読み取れなかったので、そのまま残す')
        return src
    comma = ',' if src[a:b].rstrip().endswith(',') else ''
    return src[:a] + '  ' + new.lstrip() + comma + src[b:]


def rewrite_all(job, src, reason):
    task = f"""前回の scenes.js には次の問題があり、場面ごとの修正ができません。scenes.js 全体を書き直してください。
出力は ```javascript のコードブロック 1 つだけ。場面オブジェクトは SCENES 配列の中で、行頭 2 字下げの `  {{` で始めて `  }},` で終える。

## 問題
{reason}

## テーマ
{job.state['params']['topic']}

## 前回の scenes.js
```javascript
{src}
```"""
    c = chat(job, [{'role': 'system', 'content': system_prompt()}, {'role': 'user', 'content': task}], what='全体の作り直し')
    code = code_block(c)
    if code:
        open(job.path('scenes.js'), 'w', encoding='utf-8').write(code)
        return code
    return src


# ---------------------------------------------------------------- 全体の流れ
def run(job):
    p = job.state['params']
    max_iter = int(p.get('max_iter', 8))
    try:
        job.set(status='running', phase='生成')
        job.log('生成を開始')
        generate(job)
        src = open(job.path('scenes.js'), encoding='utf-8').read()
        for it in range(1, max_iter + 1):
            job.check_stop()
            job.set(phase=f'{it}回目: 検査')
            lint = build(job, True)
            objs, _ = split_scenes(src)
            if not lint['frames'] or not objs:
                reason = lint['text'][-1500:] if not lint['frames'] else 'SCENES 配列の場面を字下げの規則で切り出せない'
                job.log(f'{it}回目: 描画できないか場面を切り出せないため、全体を作り直す')
                job.state['iterations'].append({'n': it, 'scenes': [], 'note': '全体の作り直し', 'lint_ok': False})
                job.set(phase=f'{it}回目: 全体の作り直し')
                src = rewrite_all(job, src, reason)
                continue
            sheet_name = f'sheet_{it}.png'
            Image.open(job.path('anim_sheet.png')).save(job.path(sheet_name))
            with job.lock:
                job.state['files'].update({'sheet': sheet_name, 'preview': 'anim_preview.html', 'scenes': 'scenes.js'})
            job.log(f'{it}回目: 場面 {len(objs)} / 自動検査 ' + ('OK' if lint['ok'] else 'NG'))

            # 判定
            results = []
            rec = {'n': it, 'lint_ok': lint['ok'], 'common': lint['common'], 'sheet': sheet_name, 'scenes': results}
            job.state['iterations'].append(rec)
            for idx, (a, b) in enumerate(objs):
                job.set(phase=f'{it}回目: 判定 場面{idx}')
                lines = lint['per'].get(idx, []) + lint['common']
                r = judge_scene(job, idx, src[a:b], lines)
                r['lint'] = lines
                results.append(r)
                job.save()
                job.log(f'  場面{idx}: {r["verdict"]} {r["score"]}点' + (' / ' + ' / '.join(r['issues'][:2]) if r['issues'] else ''))

            if all(r['verdict'] == 'PASS' for r in results) and lint['ok']:
                job.log(f'{it}回目: 全場面が合格')
                break
            if it == max_iter:
                job.log('上限回数に達した')
                break

            # 修正（後ろの場面から直すと、前の場面の位置がずれない）
            for idx in reversed(range(len(results))):
                if results[idx]['verdict'] == 'PASS':
                    continue
                job.set(phase=f'{it}回目: 修正 場面{idx}')
                src = fix_scene(job, src, idx, results[idx]['issues'], results[idx]['lint'])
                open(job.path('scenes.js'), 'w', encoding='utf-8').write(src)

        job.set(phase='GIF の書き出し')
        final = build(job, False)
        m = re.search(r'GIF: .*?(\d+) KB\s+約(\d+)秒', final['text'])
        with job.lock:
            job.state['files'].update({'gif': 'anim.gif', 'preview': 'anim_preview.html', 'sheet': 'anim_sheet.png', 'scenes': 'scenes.js'})
            job.state['gif_info'] = f'{m.group(1)} KB / 約{m.group(2)}秒' if m else ''
        passed = job.state['iterations'] and all(r['verdict'] == 'PASS' for r in job.state['iterations'][-1]['scenes']) and final['ok']
        job.set(status='done' if passed else 'done_with_issues', phase='完了' if passed else '上限に達して終了（未合格の場面あり）')
        job.log('完了' if passed else '終了（未合格の場面あり）')
    except Stopped:
        job.set(status='stopped', phase='停止')
        job.log('停止しました')
    except Exception as e:
        job.set(status='error', phase='エラー')
        job.log('エラー: ' + str(e))
        job.log(traceback.format_exc()[-800:])
