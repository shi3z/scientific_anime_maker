#!/usr/bin/env python3
"""Anim Studio — LLM（既定は DeepSeek）に教材アニメーション GIF を作らせ、自己判定で合格するまで直させる Web ツール。

  python3 studio/server.py          # http://localhost:8777 を開く（ポートは config.json の port）

LLM の接続先は、リポジトリ直下の config.json（config.example.json をコピーして作る）で設定する。
環境変数 SAM_LLM_URL / SAM_LLM_KEY / SAM_LLM_MODEL / PORT でも上書きでき、画面の「接続設定」でジョブごとにも変えられる。
"""
import json, mimetypes, os, queue, re, threading
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, unquote
import pipeline

PORT = int(pipeline.CONFIG.get('port', 8777))
JOBS = {}
Q = queue.Queue()


def load_jobs():
    for jid in sorted(os.listdir(pipeline.JOBS)):
        f = os.path.join(pipeline.JOBS, jid, 'state.json')
        if not os.path.exists(f):
            continue
        st = json.load(open(f, encoding='utf-8'))
        j = pipeline.Job(st['params'], jid)
        j.state = st
        if st['status'] in ('queued', 'running'):
            j.state['status'], j.state['phase'] = 'stopped', 'サーバー再起動で中断'
        j.save()
        JOBS[jid] = j


def worker():
    while True:
        job = Q.get()
        if job.stop:
            job.set(status='stopped', phase='停止')
            continue
        pipeline.run(job)


def summary(j):
    s = j.state
    last = s['iterations'][-1] if s['iterations'] else None
    return {'id': s['id'], 'title': s['params'].get('title') or s['params']['topic'][:40], 'status': s['status'], 'phase': s['phase'],
            'iterations': len(s['iterations']), 'created': s['created'],
            'passed': sum(1 for r in (last or {}).get('scenes', []) if r['verdict'] == 'PASS'),
            'total': len((last or {}).get('scenes', []))}


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def send(self, code, body, ctype='application/json; charset=utf-8'):
        data = body if isinstance(body, bytes) else json.dumps(body, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header('Content-Type', ctype)
        self.send_header('Content-Length', str(len(data)))
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        self.wfile.write(data)

    def body(self):
        n = int(self.headers.get('Content-Length') or 0)
        return json.loads(self.rfile.read(n) or b'{}')

    def do_GET(self):
        path = unquote(urlparse(self.path).path)
        if path in ('/', '/index.html'):
            return self.send(200, open(os.path.join(pipeline.ROOT, 'index.html'), 'rb').read(), 'text/html; charset=utf-8')
        if path == '/api/config':
            return self.send(200, {k: v for k, v in pipeline.DEFAULT_CFG.items() if k != 'key'})
        if path == '/api/jobs':
            return self.send(200, [summary(j) for j in sorted(JOBS.values(), key=lambda j: -j.state['created'])])
        m = re.fullmatch(r'/api/jobs/([\w-]+)/live', path)
        if m and m.group(1) in JOBS:   # LLM が書いている途中の内容（ストリーミング表示用）
            return self.send(200, getattr(JOBS[m.group(1)], 'live', None) or {'active': False})
        m = re.fullmatch(r'/api/jobs/([\w-]+)', path)
        if m and m.group(1) in JOBS:
            st = json.loads(json.dumps(JOBS[m.group(1)].state))
            (st['params'].get('llm') or {}).pop('key', None)   # API キーは画面に返さない
            return self.send(200, st)
        m = re.fullmatch(r'/files/([\w-]+)/([\w.-]+)', path)
        if m and m.group(1) in JOBS:
            f = JOBS[m.group(1)].path(m.group(2))
            if os.path.isfile(f):
                return self.send(200, open(f, 'rb').read(), mimetypes.guess_type(f)[0] or 'application/octet-stream')
        self.send(404, {'error': 'not found'})

    def do_POST(self):
        path = urlparse(self.path).path
        if path == '/api/jobs':
            b = self.body()
            if not (b.get('topic') or '').strip():
                return self.send(400, {'error': 'テーマを入力してください'})
            params = {'topic': b['topic'].strip(), 'details': (b.get('details') or '').strip(), 'title': (b.get('title') or '').strip(),
                      'scenes': max(2, min(12, int(b.get('scenes') or 6))), 'seconds': max(10, min(180, int(b.get('seconds') or 45))),
                      'max_iter': max(1, min(30, int(b.get('max_iter') or 8))),
                      'accept': max(0, min(10, int(b.get('accept') or 7))), 'patience': max(1, min(10, int(b.get('patience') or 2)))}
            llm = {k: b[k] for k in ('url', 'key', 'model') if b.get(k)}
            if llm:
                params['llm'] = llm
            j = pipeline.Job(params)
            JOBS[j.id] = j
            Q.put(j)
            return self.send(200, {'id': j.id})
        m = re.fullmatch(r'/api/jobs/([\w-]+)/stop', path)
        if m and m.group(1) in JOBS:
            JOBS[m.group(1)].stop = True
            return self.send(200, {'ok': True})
        self.send(404, {'error': 'not found'})


if __name__ == '__main__':
    load_jobs()
    threading.Thread(target=worker, daemon=True).start()
    print(f'Anim Studio: http://localhost:{PORT}', flush=True)
    print(f"LLM: {pipeline.DEFAULT_CFG['model']} @ {pipeline.DEFAULT_CFG['url']}（設定: {pipeline.CONFIG['config_path'] or '既定値。config.json がありません'}）", flush=True)
    ThreadingHTTPServer(('127.0.0.1', PORT), H).serve_forever()
