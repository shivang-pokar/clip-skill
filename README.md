# Clip: long video → vertical shorts, with Claude Code

Give Claude Code a link (or a video file) and the moments you want. It downloads only those parts, turns each one into a 1080×1920 short, burns in word-by-word captions and evens out the loudness.

## Setup (once)
1. Install [ffmpeg](https://ffmpeg.org/download.html) and Python 3.10+.
2. Clone this repo, then:
   ```bash
   python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
   ```
3. For captions, create a `.env` file with `OPENAI_API_KEY=...` (OpenAI's transcription API, paid per minute of audio). Skip it and use `--captions off` if you don't want captions.

## Use it
Open the folder in Claude Code and say:
> Clip https://www.youtube.com/watch?v=… at 1:02:10, 1:30:00 and 2:05:00, 20 seconds each. I have the creator's permission: <link>.

Claude Code uses the `clip` skill in `.claude/skills/clip/`. Or run it yourself:
```bash
.venv/bin/python clip.py "<link or file>" --at "1:02:10+20, 1:30:00+20, 2:05-2:40" --rights permission --proof "<link>"
```
| option | what it does | default |
|---|---|---|
| `--at` | moments: `1:02:10` · `1:02:10+20` · `1:02:10-1:02:45` | required |
| `--len` | seconds per clip when only a start is given | 30 |
| `--layout` | `blur` (full frame on a blurred fill) · `crop` (centre crop) | blur |
| `--captions` | `on` · `off` | on |
| `--lang` | spoken language for captions (`hi`, `en`, …) | auto |
| `--rights` + `--proof` | why you may clip it + a link or note | required |

You get `clips/<id>-c01.mp4`, `-c02.mp4`, … and `clips/<id>-credit.txt`.

## Only clip what you're allowed to
The script won't run without `--rights` and `--proof`.
- Allowed: your own videos, creators who said yes in writing, official clipping campaigns, Creative Commons videos that allow reuse, public domain.
- Credit is not permission. Clipping a creator who hasn't allowed it can get you a copyright strike.
- Games have their own fan-content rules: check the publisher's policy before posting gameplay.
- Add your own edit and context; platforms down-rank raw reposts.
- Take a clip down when the creator asks.

## Licence
MIT. Made by @techonomics.in.
