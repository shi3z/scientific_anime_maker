# scientific_anime_maker

English | [日本語](README.ja.md)

A toolkit for having an LLM make educational animated GIFs that explain how things work in science and math.

- **skill/** — a drawing engine and a build tool. An LLM (or a person) writes a single `scenes.js` and gets a captioned GIF, a browser preview, and automatic checks.
- **studio/** — a web tool, "Anim Studio". Enter a topic and an LLM (DeepSeek by default) makes the GIF, **judges its own output, and keeps fixing it until every scene passes**.

<p>
<img src="examples/odyssey_ep2.gif" width="48%" alt="The Odyssey, episode 2: the Cyclops">
<img src="examples/rodrigues.gif" width="48%" alt="Rotation about an arbitrary axis (Rodrigues' formula)">
</p>

> The web UI, the prompts, and the subtitles are currently in Japanese. Text drawn inside the animation is short English labels and math.

## Requirements

- Python 3.9+ and Pillow (`pip install pillow`)
- ffmpeg (for writing GIFs)
- Google Chrome or Chromium (used headless for rendering)
- A Japanese font for the subtitles (built into macOS; on Linux, e.g. Noto Sans CJK)
- An LLM behind an OpenAI-compatible Chat Completions API. **It must accept images**, because judging works by showing it rendered frames.

## Configuration (LLM endpoint)

The LLM endpoint, API key, and model name are not in the code. Set them in `config.json` at the repository root.
`config.json` is listed in `.gitignore`, so your own host address and key never end up in the repository.

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
  "hires": 8,
  "gif_hires": 4,
  "small": { "hires": 1, "scale": 1 }
}
```

| Key | Meaning |
|---|---|
| `llm.url` | Chat Completions endpoint (include the full `…/v1/chat/completions`). Point it at your own LLM server, e.g. a machine running LiteLLM or vLLM |
| `llm.key` | API key, sent as `Authorization: Bearer …`. Use an empty string if your server needs none |
| `llm.model` | Model name |
| `port` | Port Anim Studio listens on |
| `hires` | Scale factor for the frames used in judging. 8 renders at 2560x1440; the frames are then downscaled or cropped before being shown to the LLM |
| `gif_hires` | Scale factor for rendering the finished GIF. 4 gives smooth text; 1 keeps the 3x5-dot pixel-art font |
| `small` | Settings for the low-resolution copy (`anim_small.gif`). `hires` is the render scale, `scale` the output scale. The default 1 and 1 gives 320x212 pixel art (about 330 KB for the sound-wave example, versus about 1.5 MB for the regular 640x424 GIF) |

Precedence is **environment variables > config.json > defaults**.

- `SAM_LLM_URL` / `SAM_LLM_KEY` / `SAM_LLM_MODEL` / `PORT` override values temporarily.
- `SAM_CONFIG=/path/to/other.json` uses a different config file (handy when switching between servers).
- Values typed into "接続設定" (connection settings) in the Anim Studio UI apply to that job only.

## Anim Studio (web tool)

```sh
python3 studio/server.py
# then open http://localhost:8777
```

On the left, enter a topic, an optional outline of the scenes, the number of scenes, the length in seconds, and the maximum number of rounds, then press "作り始める" (start).
The right side shows the score of each scene in each round, the reasons behind each verdict (a yes/no for each check item, with what the LLM actually saw),
the review sheet, a live preview, the finished GIFs, and the log. Jobs are saved under `studio/jobs/` and survive a server restart.

How a job runs:

1. **Generate** — give the LLM the skill's instructions, drawing engine, and examples, and have it write `scenes.js`. Each scene must also declare:
   - `expect`: things that should be true in a still frame (positions of parts relative to each other, shapes, overlaps)
   - `moves`: parts that should move or blink, with the region they occupy
2. **Automatic checks** — `build_gif.py` renders every frame and checks, in code: exceptions, characters missing from the font, text off screen, overlapping text,
   numeric self-checks, and whether each `moves` region actually changes (measured from the per-pixel max and min over all frames).
3. **Visual judging** (the automatic check results are *not* given to the judge) — three stages:
   1. Rewrite each `expect` item as a **neutral question that does not contain the answer** (text only).
   2. Without revealing the expected answer, have the LLM describe what it sees. It gets frames at 15% / 35% / 55% / 80% (in time order),
      a change map that marks in red everything that changed during the scene, and the 80% frame split into four enlarged quarters. Only these frames are re-rendered at 8x.
   3. Compare the observations with `expect` and produce a pass/fail verdict and a score (text only).
4. **A scene passes** when the visual verdict passes *and* the scene has no automatic-check problems. Passed scenes are frozen and never judged or edited again.
5. **Fix** — rewrite only the failing scenes, giving the LLM the judge's findings, the automatic-check results, and the frames. If a fix breaks the file (nothing renders, scenes can't be split out, or an exception), it is rolled back.
6. Stop when every scene passes, the maximum number of rounds is reached, or the total score stops improving for a set number of rounds.
7. **Assemble** — build the GIF from the best version of each scene (preferring, in order: passed, no fatal problem, highest score).
   A scene that never passed is still used if it scored at least the pass line and has no fatal problem; otherwise it is left out. The UI shows which scenes were used and which were dropped.
   Two GIFs are written: the regular `anim.gif` and a lighter low-resolution `anim_small.gif`.

## Using skill/ on its own

`skill/SKILL.md` is the instruction file. It works as-is as a skill for agents such as Claude Code (put it in `~/.claude/skills/pixel-anim-gif/`).
To use it with another LLM, put `SKILL.md`, `pixel.js`, and `example_scenes.js` in the system prompt and ask it to write `scenes.js`.

```sh
python3 skill/build_gif.py scenes.js -o out.gif --title "Title" --lint-only   # checks and review sheet only
python3 skill/build_gif.py scenes.js -o out.gif --title "Title"               # through to the GIF
python3 skill/build_gif.py scenes.js -o out.gif --hires 4 --frames-dir frames # render at high resolution
```

Outputs: `out.gif` (captioned GIF), `out_preview.html` (runs in a browser), `out_sheet.png` (review sheet with two frames from each scene).

## What we learned (tested with DeepSeek v4.1 Flash)

- **Without the skill, the text is unreadable.** The model's own bitmap font comes out broken. Given a tested font and drawing parts, almost every scene becomes working code.
- **Check the displayed formula string itself.** Comparing two separately written helper functions misses sign errors on screen; `checkExpr()` parses and evaluates the exact string that is displayed.
- **Rewriting the whole file undoes earlier fixes.** Rewriting only the failing scene works reliably. Split scenes out by matching brackets, not by indentation (indentation gets misread).
- **The model guesses at names that don't exist.** Passing the list of names defined outside the scene fixes it.
- **Downscaled images are nearly unreadable.** Render judging frames at high resolution with a smooth font. But **higher resolution alone is not enough.**
- **Tell it the expected answer and it says "yes".** Asked "is the L2 line horizontal?", it answers yes even when the line is slanted. Rephrase checks as neutral questions, have it describe what it sees, and compare in a separate step.
- **Don't fail on color names, the title bar, or faint guide lines.** Gold versus orange, or a line close to the background color, can't be judged reliably from images. Keep them out of the check items and don't count them in judging.
- **Motion can't be read from images.** Even with sampled frames and a change map, it may say a blinking part "doesn't change". Declare the region in `moves` and measure the change over all frames in code.
- **Catch few-pixel misalignments with numbers.** Have the model compute coordinates from a few variables and write `check()` for relationships between parts ("bottom of the box = top of the board", etc.).
- **Keep automatic checks separate from visual judging.** When the judge sees the check results, it mixes roles — for example, it invents an item "automatic checks pass" and fails it.
- **Judging is noisy.** A scene that passed can fail when re-judged. Freeze passed scenes and keep the best version of each scene.
- **Very large images can exhaust GPU memory on some servers.** Keep each image at or below 1280x720, and resend smaller ones if a request fails.

## Layout

```
config.example.json   template for config.json
skill/
  SKILL.md            instructions (splitting into scenes, conventions, parts, self-checks, layout tips)
  pixel.js            drawing engine (3x5 font, shapes, wires, matrices, 3D, plots, sprites, self-checks, high-resolution mode)
  build_gif.py        checks, review sheet, preview, and GIF output
  example_scenes.js   two-scene example
studio/
  server.py           web server (standard library only)
  pipeline.py         generate / check / judge / fix loop
  index.html          UI
examples/
  reference_scenes.js example given to the LLM (The Odyssey, episode 2)
  *.gif               sample output
```

## License

[Apache License 2.0](LICENSE)
