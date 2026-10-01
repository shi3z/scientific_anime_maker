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
           'port': 8777, 'hires': 8, 'gif_hires': 4, 'small': {'hires': 1, 'scale': 1}}
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
LINT_KINDS = ('ERROR', 'OUTSIDE', 'OVERLAP', 'BADTEXT', 'MISSING GLYPH', 'COLOR AS TEXT', 'CHECK FAILED', 'EXPR ERROR', 'NO MOTION')


class Stopped(Exception):
    pass


class Job:
    def __init__(self, params, jid=None):
        self.id = jid or time.strftime('%Y%m%d-%H%M%S-') + uuid.uuid4().hex[:4]
        self.dir = os.path.join(JOBS, self.id)
        os.makedirs(self.dir, exist_ok=True)
        self.stop = False
        self.lock = threading.Lock()
        existing = os.path.join(self.dir, 'state.json')
        if jid and os.path.exists(existing):   # 既存のジョブは読み込むだけ（上書きしない）
            self.state = json.load(open(existing, encoding='utf-8'))
            return
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

    # ---- LLM が書いている途中の内容（画面にストリーミング表示する。state.json には保存しない） ----
    def live_start(self, what):
        self.live = {'active': True, 'what': what, 'text': '', 'thinking': '', 'chunks': 0, 'started': time.time(), 'ended': None}

    def live_add(self, text='', thinking=''):
        lv = getattr(self, 'live', None)
        if not lv:
            return
        if text:
            lv['text'] = (lv['text'] + text)[-30000:]
        if thinking:
            lv['thinking'] = (lv['thinking'] + thinking)[-30000:]
        lv['chunks'] += 1

    def live_end(self):
        lv = getattr(self, 'live', None)
        if lv:
            lv['active'], lv['ended'] = False, time.time()


# ---------------------------------------------------------------- LLM
def _to_ollama(messages):
    """OpenAI 形式のメッセージ（content に text と image_url を並べる形）を、Ollama の /api/chat の形式に変える"""
    out = []
    for m in messages:
        c = m['content']
        if isinstance(c, str):
            out.append({'role': m['role'], 'content': c}); continue
        text = '\n'.join(x['text'] for x in c if x.get('type') == 'text')
        imgs = [x['image_url']['url'].split(',', 1)[1] for x in c if x.get('type') == 'image_url']
        out.append({'role': m['role'], 'content': text, **({'images': imgs} if imgs else {})})
    return out


def _stream(job, req, ollama):
    """ストリーミングで受け取りながら job.live に書き足す。(本文, 入力トークン数, 出力トークン数) を返す"""
    content, pin, pout = [], None, None
    resp = urllib.request.urlopen(req, timeout=7200)
    for raw in resp:
        job.check_stop()   # 書いている途中でも「停止」が効くように
        line = raw.decode('utf-8', 'replace').strip()
        if not line:
            continue
        if ollama:   # Ollama: 1 行 1 JSON
            d = json.loads(line)
            m = d.get('message') or {}
            if m.get('thinking'):
                job.live_add(thinking=m['thinking'])
            if m.get('content'):
                content.append(m['content']); job.live_add(text=m['content'])
            if d.get('done'):
                pin, pout = d.get('prompt_eval_count'), d.get('eval_count')
                break
        else:        # OpenAI 互換: Server-Sent Events
            if not line.startswith('data:'):
                continue
            data = line[5:].strip()
            if data == '[DONE]':
                break
            d = json.loads(data)
            if d.get('usage'):
                pin, pout = d['usage'].get('prompt_tokens'), d['usage'].get('completion_tokens')
            for ch in d.get('choices') or []:
                delta = ch.get('delta') or {}
                th = delta.get('reasoning_content') or delta.get('reasoning')
                if th:
                    job.live_add(thinking=th)
                if delta.get('content'):
                    content.append(delta['content']); job.live_add(text=delta['content'])
    return ''.join(content), pin, pout


def chat(job, messages, max_tokens=32000, what=''):
    """LLM を呼ぶ。llm.api が "ollama" なら Ollama の /api/chat（文脈の長さ num_ctx を指定できる）、それ以外は OpenAI 互換 API。
    ストリーミングで受け取り、書いている途中の内容を画面に出す（job.live）。"""
    cfg = {**DEFAULT_CFG, **(job.state['params'].get('llm') or {})}
    ollama = cfg.get('api') == 'ollama'
    if ollama:
        url = cfg['url'].rstrip('/')
        url = url if url.endswith('/api/chat') else url.split('/v1')[0] + '/api/chat'
        body = {'model': cfg['model'], 'messages': _to_ollama(messages), 'stream': True, 'think': bool(cfg.get('think', False)),
                'options': {'num_ctx': int(cfg.get('num_ctx', 65536)), 'num_predict': max_tokens, 'temperature': 0.6}}
    else:
        url = cfg['url']
        body = {'model': cfg['model'], 'messages': messages, 'max_tokens': max_tokens, 'temperature': 0.6,
                'stream': True, 'stream_options': {'include_usage': True}}
    last = None
    for attempt in range(4):
        job.check_stop()
        try:
            req = urllib.request.Request(url, data=json.dumps(body).encode(),
                                         headers={'Content-Type': 'application/json', 'Authorization': 'Bearer ' + (cfg.get('key') or '')})
            t0 = time.time()
            job.live_start(what)
            try:
                text, pin, pout = _stream(job, req, ollama)
            finally:
                job.live_end()
            dt = time.time() - t0
            with job.lock:
                job.state['llm_calls'] += 1
                job.state['llm_seconds'] += dt
            job.log(f'  LLM {what}: {dt:.0f}秒 / 入力 {pin if pin is not None else "?"} / 出力 {pout if pout is not None else "?"} トークン')
            return text
        except urllib.error.HTTPError as e:
            last = f'HTTP {e.code} {e.read()[:200].decode("utf-8", "replace")}'
            if 400 <= e.code < 500:   # 画像が大きすぎる（GPU メモリ不足）など。同じ内容で再試行しても無駄
                job.log(f'  LLM エラー: {last}')
                raise RuntimeError(last)
        except Stopped:
            raise
        except Exception as e:
            last = str(e)
        job.log(f'  LLM エラー（{attempt + 1}回目）: {last}')
        time.sleep(15 * (attempt + 1))
    raise RuntimeError('LLM に接続できません: ' + (last or ''))


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
HARD = ('ERROR', 'BADTEXT', 'OUTSIDE', 'CHECK FAILED', 'EXPR ERROR', 'MISSING GLYPH', 'COLOR AS TEXT')   # これがある場面は GIF に入れない


def build(job, lint_only, scenes_file='scenes.js', out='anim.gif', small=False):
    """lint_only: 等倍で全コマを描いて検査し、判定用の 2 コマだけ高解像度（hires）で描き直す。
    そうでなければ gif_hires の解像度で描いて GIF を作る（文字がなめらかになる）。"""
    title = job.state['params'].get('title') or ''
    cmd = ['python3', os.path.join(SKILL, 'build_gif.py'), job.path(scenes_file), '-o', job.path(out), '--title', title]
    if lint_only:
        cmd += ['--lint-only', '--frames-dir', job.path('frames'), '--frames-hires', str(CONFIG.get('hires', 8))]
    elif small:   # 解像度を下げた版（既定は 320x212 のピクセルアート）
        sm = CONFIG.get('small') or {}
        cmd += ['--hires', str(sm.get('hires', 1)), '--scale', str(sm.get('scale', 1))]
    else:
        cmd += ['--hires', str(CONFIG.get('gif_hires', 4))]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=1800)
    text = r.stdout + r.stderr
    per, common = {}, []
    for l in text.splitlines():
        if not l.startswith(LINT_KINDS):
            continue
        m = re.search(r'場面 (\d+)', l)
        (per.setdefault(int(m.group(1)), []) if m else common).append(l.strip())
    ok = 'LINT OK' in text
    frames = 'コマが1枚も' not in text and os.path.exists(job.path(os.path.splitext(out)[0] + '_sheet.png'))
    return {'text': text, 'per': per, 'common': common, 'ok': ok, 'frames': frames}


def _scan_array(src, i):
    """src[i] が SCENES 配列の '[' の直後を指すとき、配列の要素（場面オブジェクト）の範囲の一覧と、閉じ ']' の位置を返す。
    文字列・テンプレート文字列・コメント・正規表現の中の括弧は数えない。"""
    objs, depth, st, n = [], 0, None, len(src)
    prev = '['   # 直前の意味のある文字（正規表現かどうかの判定用）
    tmpl = []    # テンプレート文字列の ${ } の入れ子
    while i < n:
        ch = src[i]
        if ch in ' \t\r\n':
            i += 1; continue
        if src.startswith('//', i):
            i = src.find('\n', i); i = n if i < 0 else i; continue
        if src.startswith('/*', i):
            i = src.find('*/', i + 2); i = n if i < 0 else i + 2; continue
        if ch in '"\'':
            j = i + 1
            while j < n and src[j] != ch:
                j += 2 if src[j] == '\\' else 1
            i = j + 1; prev = 'a'; continue
        if ch == '`' or (ch == '}' and tmpl and tmpl[-1] == depth):
            if ch == '}':
                tmpl.pop(); depth -= 1
            j = i + 1
            while j < n and src[j] != '`' and not src.startswith('${', j):
                j += 2 if src[j] == '\\' else 1
            if src.startswith('${', j):
                depth += 1; tmpl.append(depth); i = j + 2; prev = '('; continue
            i = j + 1; prev = 'a'; continue
        if ch == '/' and prev in '(,=:[!&|?{};+-*%<>~^':
            j = i + 1; cls = False
            while j < n and (src[j] != '/' or cls):
                if src[j] == '\\': j += 1
                elif src[j] == '[': cls = True
                elif src[j] == ']': cls = False
                j += 1
            i = j + 1
            while i < n and src[i].isalpha(): i += 1
            prev = 'a'; continue
        if ch in '([{':
            if depth == 0: st = i
            depth += 1
        elif ch in ')]}':
            if depth == 0 and ch == ']':
                return objs, i
            depth -= 1
            if depth == 0 and st is not None:
                objs.append((st, i + 1)); st = None
        prev = ch if not (ch.isalnum() or ch in '_$') else 'a'
        i += 1
    return objs, None


def split_scenes(src):
    """SCENES 配列の場面オブジェクトの範囲 [(開始, 終了), ...] と、SCENES を宣言している行の先頭の位置を返す。
    括弧の対応で切り出すので、字下げの書き方に左右されない。"""
    m = re.search(r'(?m)^[ \t]*(?:(?:const|let|var)\s+)?(?:window\.)?SCENES\s*=\s*\[', src)
    if not m:
        return [], None
    objs, _ = _scan_array(src, m.end())
    return [(a, b) for a, b in objs if src[a] == '{' or src[a] == '('], m.start()


def split_parts(src):
    """scenes.js を (SCENES より前, [場面オブジェクトのコード...], SCENES 配列より後) に分ける。分けられなければ None"""
    m = re.search(r'(?m)^[ \t]*(?:(?:const|let|var)\s+)?(?:window\.)?SCENES\s*=\s*\[', src)
    if not m:
        return None
    objs, close = _scan_array(src, m.end())
    if not objs or close is None:
        return None
    j = close + 1
    if src[j:j + 1] == ';':
        j += 1
    return src[:m.start()], [src[a:b] for a, b in objs], src[j:]


def assemble(head, codes, tail):
    return head + 'const SCENES = [\n  ' + ',\n  '.join(codes) + ',\n];' + tail


def _img(im):
    buf = io.BytesIO()
    im.save(buf, 'PNG')
    return {'type': 'image_url', 'image_url': {'url': 'data:image/png;base64,' + base64.b64encode(buf.getvalue()).decode()}}


def change_map(job, idx, size=(1280, 720)):
    f = job.path(f'frames/s{idx}_change.png')
    return [_img(Image.open(f).convert('RGB').resize(size, Image.LANCZOS))] if os.path.exists(f) else []


def scene_images(job, idx, zoom=False, times=False, size=(1280, 720)):
    """判定・修正用の画像。サーバーの GPU メモリを超えないよう、1 枚は 1280x720 までにする。
    times=False: 35% と 80% のコマ。times=True: 15% / 35% / 55% / 80% の 4 コマを時刻順に（size の大きさで）。
    zoom=True: 80% のコマを 4 分割して拡大した 4 枚（各 1280x720）を足す。"""
    out = []
    for tag in (('m1', 'a', 'm2', 'b') if times else ('a', 'b')):
        f = job.path(f'frames/s{idx}_{tag}.png')
        if os.path.exists(f):
            out.append(_img(Image.open(f).convert('RGB').resize(size, Image.LANCZOS)))
    f = job.path(f'frames/s{idx}_b.png')
    if zoom and os.path.exists(f):
        im = Image.open(f).convert('RGB')
        w, h = im.size
        for (x, y) in ((0, 0), (1, 0), (0, 1), (1, 1)):
            out.append(_img(im.crop((x * w // 2, y * h // 2, (x + 1) * w // 2, (y + 1) * h // 2)).resize((1280, 720), Image.LANCZOS)))
    return out


def motion_of(job, idx):
    try:
        return json.load(open(job.path('frames/motion.json'), encoding='utf-8')).get(str(idx)) or {}
    except Exception:
        return {}


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
- 各場面オブジェクトに `expect: ['...', ...]` を書く。80% の時点の絵が「こうなっているはず」という、目で確かめられる具体的な項目を 4〜8 個
  （例: '重り W の箱は板の上に接して乗っている'、'L2 の線は支点の真下から箱の真下まで水平'、'W= のラベルは箱と重ならない'）。
  **書くのは図の中身（部品どうしの位置関係・形・重なり・動き）だけ。** 次のことは書かない:
  見出し帯や場面番号 / 色の名前（金・オレンジなどは見る人で変わる。部品はラベルや形で指す: 'λ のラベル'、'波の線'、'支点の三角'）/
  背景に近い暗い色で描いた補助線や飾り（見えにくいので確かめられない）。
  動きは expect には書かない（静止画では確かめられない）。代わりに次の moves に書く。
- 各場面オブジェクトに `moves: [['ラベル', x, y, w, h], ...]` を書く。場面の中で**動く・点滅する・形が変わるはずの部品**ごとに、
  その部品が動く範囲を 320x180 の座標の四角で指定する（例: `['SPEAKER GLOW', 18, 70, 24, 24]`、`['WAVE', 40, 60, 260, 60]`）。
  書き出しツールが場面の全コマを比べ、その範囲がほとんど変化していなければ NO MOTION として報告する。
  範囲は、動く部品がはみ出さない大きさにし、ずっと止まっている部品や文字を広く含めない。
  出来の判定では、この項目を正解を伏せた質問に直して画像で確かめる。
- 図の座標は直書きせず、場面ごとに少数の変数（支点の x、板の y、腕の長さ、倍率など）から計算する。ラベルや寸法線もその変数から置く。
  そのうえで、図の部品どうしの関係（「箱の下端 = 板の上面」「L2 の右端 = 箱の中心 x」「ラベルは矢印と重ならない」など）を
  `check('説明', 条件)` で数値として検算する。draw の中で計算する位置は、同じ計算を場面の外の関数にしておき、検算にも使う。"""
    msgs = [{'role': 'system', 'content': system_prompt()}, {'role': 'user', 'content': task}]
    c = chat(job, msgs, what='生成')
    open(job.path('generate_raw.md'), 'w', encoding='utf-8').write(c)
    code = code_block(c)
    if not code:   # 短い返事だけで終わることがある（ローカルのモデルで確認）。念を押して 1 回だけ書き直させる
        job.log('  生成結果にコードがなかったので、もう一度書かせる')
        c = chat(job, msgs + [{'role': 'assistant', 'content': c},
                              {'role': 'user', 'content': 'scenes.js の全体を ```javascript のコードブロック 1 つで、最後（`];` まで）出力してください。説明は不要です。'}], what='生成（再）')
        open(job.path('generate_raw2.md'), 'w', encoding='utf-8').write(c)
        code = code_block(c)
    if not code:
        raise RuntimeError('生成結果にコードが含まれていません')
    open(job.path('scenes.js'), 'w', encoding='utf-8').write(code)


def json_of(text):
    raw = code_block(text, 'json')
    if not raw:
        m = re.search(r'[\[{].*[\]}]', text, re.S)
        raw = m.group(0) if m else ''
    try:
        return json.loads(raw)
    except Exception:
        return None


# ---- 判定は 3 段階に分ける ----
# 「L2 の線は水平にのびている」のように正しい状態を示して聞くと、画像がずれていても「はい」と答えやすい（確認済み）。
# そこで ①正解を含まない中立な質問に言い換え、②正解を知らせずに画像を見たまま答えさせ、③観察結果と正解を文字だけで突き合わせる。

MOTION_WORDS = r'動く|動き|揺れ|往復|点滅|明滅|光る|明るさ|変わる|変える|変化|進む|移動|広が|伸び|縮|回る|回転|振動|流れ|現れ|消え'


def neutral_questions(job, idx, expects):
    if not expects:
        return []
    text = """次の「こうなっているはず」という各文を、**答えを含まない中立な質問**に言い換えてください。
質問だけを読んだ人が、正解がどちらかを推測できないようにする。位置関係・形・重なりを、選択肢や座標で答えられる形にする。
例: 「赤い箱は黄色い板の上に接して乗っている」→「赤い箱の下端と黄色い板の上端の位置関係は？（接している / 離れている / 重なっている）。離れているなら何ピクセルか」
例: 「L2 の線は支点の真下から箱の真下まで水平」→「L2 のラベルの近くの線は何本あり、それぞれ水平・垂直・斜めのどれか。両端はそれぞれ何の真下にあるか」
例: 「W= のラベルは箱と重ならない」→「W= の文字の範囲は、他の図形（四角・線・矢印）や文字と重なっているか。重なっているなら何と」
**動き・変化の文（動く・揺れる・ずれる・広がる・移動する・現れる など）は、1 枚のコマでは確かめられない。**
「時刻順の 4 枚のコマで、〇〇の位置や形はどう変わったか（変わらない / 左右に動いた / …）」のように、コマどうしの変化を問う質問にする。
**色を問う質問は作らない。** 部品は色ではなく、ラベルの文字や形（線・四角・三角・矢印・波）で特定する。元の文に色の名前があっても質問からは外す。

出力は ```json の配列 1 つ（質問の文字列を、元の文と同じ順に同じ数だけ）。

""" + '\n'.join(f'{k + 1}. {e}' for k, e in enumerate(expects))
    j = json_of(chat(job, [{'role': 'user', 'content': text}], 3000, what=f'質問づくり 場面{idx}'))
    return [str(x) for x in j][:len(expects)] if isinstance(j, list) and j else [f'{e} かどうか、画像で実際にどうなっているかを書く' for e in expects]


def observe(job, idx, questions):
    text = """画像は教材アニメーションの 1 場面です。
- 1〜4 枚目: その場面の 15% / 35% / 55% / 80% の時点のコマ（時刻順）
- 5 枚目: **変化マップ**。場面の全コマを通して、一度でも色や明るさが変わった場所を赤で示したもの（暗い部分は場面中ずっと同じ）。
  点滅・明滅・動き・伸び縮みは、抜き出したコマでは同じに見えても、ここでは赤く写る。
- 6 枚目以降: 80% のコマを 4 つに分けて拡大したもの（順に左上・右上・左下・右下）。ない場合もある
**見たままを答えてください。推測や、こうあるべきという判断は入れない。** 見えないものは「見えない」と書く。
動き・点滅・変化についての質問は、1〜4 枚目の見比べと、5 枚目の変化マップ（その部品の場所が赤いか）の両方で答える。
それ以外は 80% の時点（4 枚目と拡大）について答える。

## 質問
""" + ('\n'.join(f'{k + 1}. {q}' for k, q in enumerate(questions)) or '（なし）') + """

## 全体の観察（80% の時点について）
A. 画面の中の文字をすべて挙げ、それぞれの文字の範囲が他の図形（線・四角・矢印・人物など）や他の文字と重なっているか。重なっているなら何と。
B. 斜めになっている線、途中で折れている線、どこにもつながっていない線、画面や枠からはみ出している部品、描きかけに見える部品。
C. 1〜4 枚目（時刻順）で、何が動いた・現れた・消えた・変わったか。また、5 枚目の変化マップで赤くなっている部品はどれか。

出力は ```json で:
{"answers": ["質問1への答え", ...], "texts": [{"text": "文字", "overlaps": "重なっている相手（なければ なし）"}, ...], "odd": ["B の観察", ...], "change": "C の観察"}"""
    msg = lambda imgs: [{'role': 'user', 'content': [{'type': 'text', 'text': text}] + imgs}]
    try:
        imgs = scene_images(job, idx, times=True, size=(960, 540)) + change_map(job, idx) + scene_images(job, idx, zoom=True)[2:]
        c = chat(job, msg(imgs), 6000, what=f'観察 場面{idx}')
    except RuntimeError:
        job.log(f'  場面{idx}: 画像が多すぎたので、小さくして送り直す')
        imgs = scene_images(job, idx, times=True, size=(640, 360)) + change_map(job, idx, (960, 540))
        c = chat(job, msg(imgs), 6000, what=f'観察 場面{idx}（縮小）')
    j = json_of(c)
    return j if isinstance(j, dict) else {'answers': [], 'texts': [], 'odd': ['観察結果を読み取れなかった'], 'change': ''}


DECIDE_RULES = """あなたは厳しい品質レビュアーです。教材アニメーションの 1 場面について、**画像を見た別の人の観察記録**をもとに合否を決めます。
観察記録を事実として扱う（観察記録と食い違う推測をしない）。

見る観点:
- 「こうなっているはず」の各項目が、観察記録の答えで満たされているか
- 文字が他の図形や文字と重なっていないか（観察記録の texts）
- 斜め・折れ・はみ出し・描きかけなど不自然な部品がないか（odd）。ただし意図どおりの斜め線（矢印の頭、斜めの板など）は問題にしない
- 時刻順のコマで変化があるか（止まって見えないか）。画素の変化量（時刻の間で色が変わった画素の割合）も参考にする

前提（これを理由に不合格にしない）:
- **色の名前の違いは問題にしない。** 金・黄・オレンジ・橙、紫・青紫、水色・青緑などは、見る人やモデルで呼び方が変わる。形と位置が合っていれば一致とみなす。
- **動き・変化の項目（動く・揺れる・ずれる・移動する など）は、1 枚のコマでは判断しない。** アニメーションなので、
  ある瞬間には動いていない位置にいることもある（例: 振動の中心を通る瞬間、動き始める前）。時刻順のコマの比較（change・答え）と
  画素の変化量・変化マップ（その部品の場所が赤いか）で判断し、どれかで変化が確かめられれば ok とする。
- **見出し帯（画面最上部の帯）と場面番号は判定の対象外。** 項目にあっても ok とする。
- **観察記録で「言及なし」「見えない」「わからない」とされたものは、「ない」と断定しない。** 背景に近い暗い色の補助線や小さな飾りは見落とされやすい。
  教材の中身にとって欠かせない部品（主役の図・数式・ラベル）が本当に欠けていると複数の答えから言える場合だけ問題にする。
- 文字の大きさと書体は固定で変えられない。「文字が小さい」「フォントを大きく」は指摘しない。
- canvas 内の文字は英語の大文字・記号だけ。日本語の説明は字幕に出るので、画面に説明文がないことは問題にしない。

出力は ```json で:
{"checks": [{"item": "こうなっているはずの項目", "observed": "観察記録ではどうだったか", "ok": true または false}, ...],
 "issues": ["確定した問題（直し方がわかる具体的な書き方）", ...], "score": 0から10の整数, "verdict": "PASS" または "FAIL"}
PASS は、checks がすべて ok で、issues が空で、score が 9 以上のときだけ。
自動検査（プログラムによる検査）は別に行うので、ここでは扱わない。「自動検査が通っている」のような項目は作らない。"""


def judge_scene(job, idx, scene_code, lint_lines):
    # 自動検査に関する項目と、動き・変化の項目は画像判定にかけない（動きは moves によってプログラムで測る）
    exp = [e for e in (x[0] or x[1] for x in expects_of(scene_code))
           if not re.search(r'自動検査|lint|検算|check', e, re.I) and not re.search(MOTION_WORDS, e)]
    qs = neutral_questions(job, idx, exp)
    obs = observe(job, idx, qs)
    answers = obs.get('answers') or []
    record = '\n'.join(f'- 質問: {q}\n  答え: {answers[k] if k < len(answers) else "（答えなし）"}' for k, q in enumerate(qs))
    text = f"""{DECIDE_RULES}

## こうなっているはずの項目
{chr(10).join(f'{k + 1}. {e}' for k, e in enumerate(exp)) or '（なし）'}

## 観察記録（画像を見た人が、正解を知らずに答えたもの）
{record or '（質問なし）'}
- 文字と重なり: {json.dumps(obs.get('texts') or [], ensure_ascii=False)}
- 不自然な部品: {json.dumps(obs.get('odd') or [], ensure_ascii=False)}
- 時刻順のコマ（15% / 35% / 55% / 80%）の違い: {obs.get('change') or ''}
- 画素の変化量（その間に色が変わった画素の割合 %。0.5 未満ならほぼ止まっている）: {json.dumps(motion_of(job, idx), ensure_ascii=False)}

## この場面のコード（意図の確認用）
```javascript
{scene_code}
```"""
    j = json_of(chat(job, [{'role': 'user', 'content': text}], 6000, what=f'判定 場面{idx}'))
    if not isinstance(j, dict):
        return {'score': 0, 'verdict': 'FAIL', 'issues': ['判定結果を読み取れなかった'], 'candidates': [], 'checks': [], 'observation': obs, 'questions': qs}
    score = int(j.get('score') or 0)
    issues = [str(x) for x in (j.get('issues') or [])]
    checks = [c for c in (j.get('checks') or []) if isinstance(c, dict)]
    for c in checks:
        if c.get('ok') is False:
            msg = f"「{c.get('item', '')}」になっていない: {c.get('observed', '')}"
            if msg not in issues:
                issues.append(msg)
    verdict = 'PASS' if str(j.get('verdict', '')).upper() == 'PASS' and not issues and score >= 9 else 'FAIL'
    cands = [f"{t.get('text')}: {t.get('overlaps')}" for t in (obs.get('texts') or []) if isinstance(t, dict) and t.get('overlaps') not in (None, '', 'なし')] + [str(x) for x in (obs.get('odd') or [])]
    return {'score': score, 'verdict': verdict, 'issues': issues, 'candidates': cands, 'checks': checks, 'observation': obs, 'questions': qs}


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
    return src[:a] + new.strip() + src[b:]   # 範囲は括弧の対応で正確に切り出しているので、そのまま差し替える


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
    accept = int(p.get('accept', 7))        # 合格しなかった場面でも、この点数以上で致命的な問題がなければ GIF に入れる
    patience = int(p.get('patience', 2))    # この回数続けて点数が伸びなければ打ち切る
    try:
        job.set(status='running', phase='生成')
        job.log('生成を開始')
        generate(job)
        src = open(job.path('scenes.js'), encoding='utf-8').read()

        best, frozen, prev_total, stall = {}, set(), -1, 0
        for it in range(1, max_iter + 1):
            job.check_stop()
            job.set(phase=f'{it}回目: 検査')
            open(job.path('scenes.js'), 'w', encoding='utf-8').write(src)
            lint = build(job, True)
            parts = split_parts(src)
            if not lint['frames'] or not parts:
                # 生成直後や作り直し直後に壊れている場合だけ、全体を作り直す（修正で壊れた場合は修正を取り消すのでここには来ない）
                reason = lint['text'][-1500:] if not lint['frames'] else 'SCENES 配列の場面を字下げの規則で切り出せない'
                job.log(f'{it}回目: 描画できないか場面を切り出せないため、全体を作り直す（理由: ' + reason.strip().splitlines()[-1][:160] + '）')
                open(job.path(f'broken_{it}.js'), 'w', encoding='utf-8').write(src)
                job.state['iterations'].append({'n': it, 'scenes': [], 'note': '全体の作り直し', 'lint_ok': False})
                job.set(phase=f'{it}回目: 全体の作り直し')
                src = rewrite_all(job, src, reason)
                best, frozen, prev_total, stall = {}, set(), -1, 0
                continue
            head, codes, tail = parts
            sheet_name = f'sheet_{it}.png'
            Image.open(job.path('anim_sheet.png')).save(job.path(sheet_name))
            with job.lock:
                job.state['files'].update({'sheet': sheet_name, 'preview': 'anim_preview.html', 'scenes': 'scenes.js'})
            job.log(f'{it}回目: 場面 {len(codes)} / 自動検査 ' + ('OK' if lint['ok'] else 'NG') + (f' / 合格済み {sorted(frozen)}' if frozen else ''))

            # 判定（合格済みの場面は判定し直さない。判定のばらつきで合格が取り消されるのを防ぐ）
            results = []
            rec = {'n': it, 'lint_ok': lint['ok'], 'common': lint['common'], 'sheet': sheet_name, 'scenes': results}
            job.state['iterations'].append(rec)
            for idx, code in enumerate(codes):
                lines = lint['per'].get(idx, []) + lint['common']
                if idx in frozen:
                    r = dict(best[idx]['result'], frozen=True)
                else:
                    job.set(phase=f'{it}回目: 判定 場面{idx}')
                    r = judge_scene(job, idx, code, lines)   # 見た目だけの判定（自動検査の結果は渡していない）
                    r['lint'] = lines
                    r['ok'] = r['verdict'] == 'PASS' and not lines   # 場面の合格 = 見た目の判定が合格 かつ 自動検査に問題なし
                    hard = [x for x in lines if x.startswith(HARD)]
                    # 最良の版: ①合格 ②致命的な問題（例外・はみ出し・検算の失敗など）がない ③点数が高い、の順で比べる
                    rank = lambda ok, hd, sc: (ok, not hd, sc)
                    better = idx not in best or rank(r['ok'], hard, r['score']) > rank(best[idx]['result'].get('ok', False), best[idx]['hard'], best[idx]['score'])
                    if better:
                        best[idx] = {'score': r['score'], 'code': code, 'hard': hard, 'result': r, 'it': it}
                    if r['ok']:
                        frozen.add(idx)
                    job.log(f'  場面{idx}: 判定 {r["verdict"]} {r["score"]}点 / 自動検査 ' + ('OK' if not lines else f'NG {len(lines)}件')
                            + (' / ' + ' / '.join(r['issues'][:2]) if r['issues'] else ''))
                results.append(r)
                job.save()

            if len(frozen) == len(codes):
                job.log(f'{it}回目: 全場面が合格')
                break
            total = sum(b['score'] for b in best.values())
            stall = stall + 1 if total <= prev_total else 0
            prev_total = max(prev_total, total)
            if stall >= patience:
                job.log(f'{patience}回続けて点数が伸びなかったので打ち切る')
                break
            if it == max_iter:
                job.log('上限回数に達した')
                break

            # 修正: 不合格の場面だけ直す。直した結果が描けない・場面が切り出せない・その場面で例外が出るなら取り消す
            for idx in reversed(range(len(codes))):
                if idx in frozen:
                    continue
                job.set(phase=f'{it}回目: 修正 場面{idx}')
                if not results[idx]['issues'] and not results[idx]['lint']:
                    continue
                new = fix_scene(job, src, idx, results[idx]['issues'], results[idx]['lint'])
                if new == src:
                    continue
                open(job.path('scenes_try.js'), 'w', encoding='utf-8').write(new)
                t = build(job, True, 'scenes_try.js', 'try.gif')
                np = split_parts(new)
                if t['frames'] and np and len(np[1]) == len(codes) and not any(x.startswith('ERROR') for x in t['per'].get(idx, [])):
                    src = new
                else:
                    job.log(f'  場面{idx}: 修正で壊れたので取り消した')

        # 組み立て: 場面ごとに一番点数の高かった版を使い、合格ラインに届かない場面・致命的な問題がある場面は省く
        parts = split_parts(src)
        if not parts or not best:
            raise RuntimeError('使える場面がありません')
        head, codes, tail = parts
        kept, omitted = [], []
        for idx in range(len(codes)):
            b = best.get(idx)
            if not b:
                omitted.append({'idx': idx, 'score': 0, 'reason': '判定できなかった'})
            elif b['result'].get('ok') or (b['score'] >= accept and not b['hard']):
                kept.append(idx)
            else:
                omitted.append({'idx': idx, 'score': b['score'], 'reason': ('致命的な問題: ' + b['hard'][0]) if b['hard'] else f'{b["score"]}点（合格ライン {accept} 点未満）'})
        if not kept:   # 1 つも残らなければ、致命的な問題のない場面のうち最高点のものだけ使う
            cand = [i for i in best if not best[i]['hard']]
            if not cand:
                raise RuntimeError('すべての場面に致命的な問題があり、GIF を作れません')
            top = max(cand, key=lambda i: best[i]['score'])
            kept, omitted = [top], [o for o in omitted if o['idx'] != top]
        final_src = assemble(head, [best[i]['code'] for i in kept], tail)
        open(job.path('final_scenes.js'), 'w', encoding='utf-8').write(final_src)
        for o in omitted:
            job.log(f'  場面{o["idx"]} を省略: {o["reason"]}')
        job.log(f'GIF に入れる場面: {kept}（それぞれ最高点の版: ' + ', '.join(f'場面{i}={best[i]["score"]}点/{best[i]["it"]}回目' for i in kept) + '）')

        job.set(phase='GIF の書き出し', final={'kept': kept, 'omitted': omitted, 'accept': accept})
        final = build(job, False, 'final_scenes.js', 'anim.gif')
        m = re.search(r'GIF: .*?(\d+) KB\s+約(\d+)秒\s+(\d+x\d+)', final['text'])
        job.set(phase='GIF の書き出し（解像度を下げた版）')
        small = build(job, False, 'final_scenes.js', 'anim_small.gif', small=True)
        ms = re.search(r'GIF: .*?(\d+) KB\s+約(\d+)秒\s+(\d+x\d+)', small['text'])
        with job.lock:
            job.state['files'].update({'gif': 'anim.gif', 'preview': 'anim_preview.html', 'sheet': 'anim_sheet.png', 'scenes': 'final_scenes.js'})
            if ms:
                job.state['files']['gif_small'] = 'anim_small.gif'
            job.state['gif_info'] = f'{m.group(3)}・{m.group(1)} KB・約{m.group(2)}秒' if m else ''
            job.state['gif_small_info'] = f'{ms.group(3)}・{ms.group(1)} KB' if ms else ''
        all_pass = len(frozen) == len(codes)
        job.set(status='done' if all_pass else 'done_with_issues',
                phase='完了（全場面合格）' if all_pass else f'完了（{len(kept)}/{len(codes)} 場面を使用、{len(omitted)} 場面を省略）')
        job.log(job.state['phase'])
    except Stopped:
        job.set(status='stopped', phase='停止')
        job.log('停止しました')
    except Exception as e:
        job.set(status='error', phase='エラー')
        job.log('エラー: ' + str(e))
        job.log(traceback.format_exc()[-800:])
