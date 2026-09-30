# scientific_anime_maker

科学や数学の仕組みを説明する教材アニメーション GIF を、LLM に作らせるための道具一式です。

- **skill/** … 描画エンジンと書き出しツール。LLM（や人）は `scenes.js` を 1 つ書くだけで、字幕つきの GIF、ブラウザで動くプレビュー、自動検査の結果が得られます。
- **studio/** … Web ツール「Anim Studio」。テーマを入れると、LLM（既定は DeepSeek）が GIF を作り、**自分で出来を判定して、全場面が合格するまで作り直します**。

<p>
<img src="examples/odyssey_ep2.gif" width="48%" alt="オデュッセイア 第2話 キュクロプス">
<img src="examples/rodrigues.gif" width="48%" alt="任意軸まわりの回転（ロドリゲスの公式）">
</p>

## 必要なもの

- Python 3.9 以上と Pillow（`pip install pillow`）
- ffmpeg（GIF の書き出しに使う）
- Google Chrome または Chromium（ヘッドレスで描画する）
- 日本語フォント（字幕に使う。mac は標準で入っている。Linux は Noto Sans CJK など）
- OpenAI 互換の Chat Completions API で使える LLM。**画像を読めるモデル**が必要（出来の判定で画面の画像を見せるため）

## 設定（LLM の接続先）

LLM の接続先・API キー・モデル名はコードに書かず、リポジトリ直下の `config.json` で設定します。
`config.json` は `.gitignore` に入っているので、手元の固有アドレスやキーがリポジトリに入ることはありません。

```sh
cp config.example.json config.json
```

```json
{
  "llm": {
    "url": "http://YOUR-LLM-HOST:8101/v1/chat/completions",
    "key": "YOUR-API-KEY",
    "model": "deepseek-v4.1-flash"
  },
  "port": 8777,
  "hires": 4
}
```

| 項目 | 意味 |
|---|---|
| `llm.url` | Chat Completions のエンドポイント（`…/v1/chat/completions` まで書く）。自分の LLM サーバー（例: LiteLLM や vLLM を置いたマシン）のアドレスに変える |
| `llm.key` | API キー（`Authorization: Bearer …` で送る）。不要なサーバーなら空文字 |
| `llm.model` | モデル名 |
| `port` | Anim Studio を開くポート |
| `hires` | 判定用に描く解像度の倍率。4 なら 1280x720 で描く（下の「わかったこと」参照） |

設定の優先順位は **環境変数 > config.json > 既定値** です。

- 環境変数 `SAM_LLM_URL` / `SAM_LLM_KEY` / `SAM_LLM_MODEL` / `PORT` で一時的に上書きできます。
- `SAM_CONFIG=/path/to/other.json` で、別の設定ファイルを使えます（接続先を複数使い分けるとき）。
- Anim Studio の画面の「接続設定」に入れると、そのジョブだけ接続先を変えられます。

## Anim Studio（Web ツール）

```sh
python3 studio/server.py
# → http://localhost:8777 を開く
```

左の欄にテーマと場面の流れ（空欄ならおまかせ）、場面数・秒数・最大回数を入れて「作り始める」を押します。
右側に、回ごと・場面ごとの点数、判定の理由（確認項目ごとの「はい／いいえ」と LLM が見た実際の様子）、
確認画像、動くプレビュー、完成した GIF、ログが出ます。ジョブは `studio/jobs/` に保存され、サーバーを再起動しても残ります。

処理の流れ:

1. **生成** — `skill/` の手順書・描画エンジン・見本を LLM に渡し、`scenes.js` を書かせる。
   各場面には「80% の時点でこうなっているはず」という確認項目（`expect`）も書かせる。
2. **検査** — `build_gif.py` で全コマを描き、例外・フォントにない文字・はみ出し・文字の重なり・数値の検算を自動で調べる。
3. **判定** — 場面ごとに、原寸（1280x720）のコマを LLM に見せる。まず問題の候補を 3 つ以上挙げさせ、
   確認項目を 1 つずつ「実際の様子」を書いてから「はい／いいえ」で答えさせ、最後に点数と合否を JSON で出させる。
   自動検査で問題が出ている場面は、LLM が何と言っても不合格。
4. **修正** — 不合格の場面だけを、指摘と画像を渡して書き直させる（全体を書き直させると、直したはずの場面が元に戻りやすいため）。
   コードが壊れて 1 コマも描けないときは、全体を作り直させる。
5. 全場面が合格するか、最大回数に達するまで 2〜4 を繰り返し、GIF を書き出す。

## skill/ だけを使う

`skill/SKILL.md` が手順書です。Claude Code などのエージェントのスキルとしてそのまま使えます（`~/.claude/skills/pixel-anim-gif/` に置く）。
別の LLM に使わせるときは、`SKILL.md`・`pixel.js`・`example_scenes.js` をシステムプロンプトに入れて `scenes.js` を書かせます。

```sh
python3 skill/build_gif.py scenes.js -o out.gif --title "題名" --lint-only   # 検査と確認画像だけ
python3 skill/build_gif.py scenes.js -o out.gif --title "題名"               # GIF まで
python3 skill/build_gif.py scenes.js -o out.gif --hires 4 --frames-dir frames # 高解像度で描く
```

出力: `out.gif`（字幕つき GIF）、`out_preview.html`（ブラウザで動くプレビュー）、`out_sheet.png`（各場面の途中 2 コマを並べた確認画像）。

## わかったこと（DeepSeek v4.1 Flash で試した結果）

- **スキルなしでは文字が読めない。** 自作のビットマップフォントが壊れる。検証済みのフォントと部品を渡すと、ほぼ全場面が動くコードになる。
- **画面の式は、表示する文字列そのものを検算させる。** 別に書いた計算用の関数どうしを比べるだけの「形だけの検算」では、画面の符号の誤りを見逃す。`checkExpr()` は表示用の文字列を解釈して計算する。
- **全体を書き直させると、直したはずの場面が元に戻る。** 問題のある場面だけを切り出して書き直させると確実に直る。
- **存在しない部品を推測で使う。** 場面の外で定義されている名前の一覧を明示して渡すと直る。
- **縮めた画像はほぼ読めない。** 1280x360 の画像 1 枚が約 365 トークンに縮められ、画面にない文字を読んだりする。1 コマを 1280x720 にすると文字は正しく読めるが、3x5 ドットの文字は W と M などを読み違える。
  そのため判定用には、座標はそのままで 4 倍の解像度・なめらかなフォントで描く（`hires`）。
- **画像を見るだけでは数ドットのずれに気づけない。** 「こうなっているはず」の確認項目を 1 つずつ聞くと大きなずれ（箱が板から浮いている）は見つけるが、線の傾きや数ドットの重なりは見逃す。
  図の座標を少数の変数から計算させ、部品どうしの関係（「箱の下端 = 板の上面」など）を `check()` で数値として検算させるのが確実。
- **画像を大きくしすぎると、サーバーによっては GPU メモリが足りなくなる**（1280x1440 の 1 枚で CUDA out of memory）。1 コマ 1 枚（1280x720）に分けて渡すと通った。

## 構成

```
config.example.json   接続先の雛形（config.json にコピーして使う）
skill/
  SKILL.md            手順書（場面の分け方、規約、部品、検算、レイアウトの注意）
  pixel.js            描画エンジン（3x5 フォント、図形、配線、行列、3D、グラフ、スプライト、検算、高解像度モード）
  build_gif.py        検査・確認画像・プレビュー・GIF の書き出し
  example_scenes.js   2 場面の見本
studio/
  server.py           Web サーバー（標準ライブラリだけで動く）
  pipeline.py         生成・検査・判定・修正の流れ
  index.html          画面
examples/
  reference_scenes.js LLM に渡す作例（オデュッセイア第 2 話）
  *.gif               作例
```
