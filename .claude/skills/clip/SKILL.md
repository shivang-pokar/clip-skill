---
name: clip
description: Turn a long video or stream (YouTube, Twitch, any yt-dlp link, or a local file) into vertical 1080x1920 shorts with word captions, from a list of timestamps. Use when the user says "clip this", "make shorts from this stream", "cut these moments", or pastes a link with timestamps.
---

# Clip: long video → vertical shorts

Run everything from the repo root with the repo's Python env.

## 1 · First time on this machine
- Check `ffmpeg -version` works. If not, tell the user how to install it (macOS `brew install ffmpeg`, Windows `winget install ffmpeg`), don't install it yourself without asking.
- `python3 -m venv .venv && .venv/bin/pip install -r requirements.txt` (Windows: `.venv\Scripts\pip`).
- Captions need an OpenAI key: ask the user to put `OPENAI_API_KEY=...` in `.env` **themselves**. Never print, log or commit it. No key → run with `--captions off`.

## 2 · Rights check (always, before downloading anything)
Ask the user why they're allowed to clip this video and get a link or note as proof:
`own` (their video) · `permission` (the creator said yes in writing) · `campaign` (an official clipping program for that creator) · `cc` (a Creative Commons licence that allows reuse) · `public-domain`.
If the answer is "I'll give credit" or nothing: stop. Credit is not permission. Also flag game footage: publishers have their own fan-content rules; tell the user to check them.

## 3 · Moments
Take timestamps from the user (pasted list, screenshot of a list, or the comments under the video). Formats per moment: `1:02:10` (uses `--len`), `1:02:10+20` (20 s), `1:02:10-1:02:45`. Show the list back and get an OK.

## 4 · Run
```bash
.venv/bin/python clip.py "<link or file>" --at "<moments>" --rights <basis> --proof "<link/note>" [--len 30] [--layout blur|crop] [--lang hi|en] [--captions on|off] [--out clips]
```
- `--layout blur` (default): the whole frame in the middle on a blurred fill. Good for talking, menus, wide gameplay.
- `--layout crop`: centre crop to 9:16. Good when the action is in the middle of the screen.
- It downloads **only** those sections, transcribes each clip, burns in 2–3-word captions and normalises loudness (-14 LUFS).

## 5 · Check, then hand over
- Make a frame sheet per clip (`ffmpeg -i clip.mp4 -vf "fps=1/3,scale=270:480,tile=6x1" -frames:v 1 sheet.png`), look at it: captions readable, not covering faces, nothing cut off.
- Give the user the clips and `*-credit.txt`. The credit line goes in every post.
- Never post for the user.
