#!/usr/bin/env python3
"""clip: long video + timestamps -> vertical 1080x1920 shorts with word captions.

  python clip.py "<youtube/twitch link or file.mp4>" --at "1:02:10, 1:30:00+20, 2:05-2:40" \
      --rights permission --proof "https://x.com/creator/status/..."

Needs: ffmpeg on PATH, `pip install -r requirements.txt` (yt-dlp, pillow).
Captions use OpenAI's transcription API (OPENAI_API_KEY in the environment or a .env file);
pass --captions off to skip them.
"""
import argparse, json, os, re, shutil, subprocess, sys, tempfile, uuid, urllib.request
from pathlib import Path

RIGHTS = ["own", "permission", "campaign", "cc", "public-domain"]
W, H = 1080, 1920
FONTS = [  # first one found wins; nothing is bundled
    "/System/Library/Fonts/Supplemental/Impact.ttf",
    "/System/Library/Fonts/Supplemental/Arial Black.ttf",
    "C:/Windows/Fonts/impact.ttf",
    "C:/Windows/Fonts/ariblk.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
]


def die(msg):
    sys.exit(f"clip: {msg}")


def secs(t):
    t = t.strip()
    if not re.fullmatch(r"\d+(:\d{1,2}){0,2}(\.\d+)?", t):
        die(f"can't read time '{t}' (use 1:02:10, 62:10 or 3730)")
    s = 0.0
    for part in t.split(":"):
        s = s * 60 + float(part)
    return s


def moments(spec, default_len):
    """'1:00:00' | '1:00:00+15' | '1:00:00-1:00:40', comma separated."""
    out = []
    for item in [x for x in spec.split(",") if x.strip()]:
        item = item.strip()
        if "+" in item:
            a, n = item.split("+", 1)
            start, end = secs(a), secs(a) + float(n)
        elif re.search(r"\d-\d", item):
            a, b = item.split("-", 1)
            start, end = secs(a), secs(b)
        else:
            start, end = secs(item), secs(item) + default_len
        if end <= start:
            die(f"'{item}' ends before it starts")
        if end - start > 180:
            die(f"'{item}' is {end - start:.0f} s; shorts stay under 3 min")
        out.append((start, end))
    if not out:
        die("no moments given (--at)")
    return out


def run(cmd):
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode:
        die(f"{cmd[0]} failed:\n{r.stderr[-1500:]}")
    return r


def fetch(src, start, end, work):
    """Download (or cut) only [start, end] of the source -> mp4 path."""
    out = work / f"src-{int(start)}.mp4"
    if Path(src).exists():
        run(["ffmpeg", "-y", "-v", "error", "-ss", str(start), "-i", src, "-t", str(end - start),
             "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-c:a", "aac", str(out)])
        return out
    import yt_dlp
    from yt_dlp.utils import download_range_func
    opts = {
        "format": "bv*[height<=1080][ext=mp4]+ba[ext=m4a]/bv*[height<=1080]+ba/b",
        "merge_output_format": "mp4",
        "outtmpl": str(work / f"dl-{int(start)}.%(ext)s"),
        "download_ranges": download_range_func(None, [(start, end)]),
        "force_keyframes_at_cuts": True,
        "quiet": True, "no_warnings": True, "noprogress": True,
    }
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(src, download=True)
    files = sorted(work.glob(f"dl-{int(start)}.*"))
    if not files:
        die("download produced no file")
    files[0].rename(out)
    return out, info


def api_key():
    if os.environ.get("OPENAI_API_KEY"):
        return os.environ["OPENAI_API_KEY"]
    for env in [Path.cwd() / ".env", Path(__file__).parent / ".env"]:
        if env.exists():
            for line in env.read_text().splitlines():
                if line.strip().startswith("OPENAI_API_KEY="):
                    return line.split("=", 1)[1].strip().strip('"\'')
    return None


def transcribe(clip, work, lang):
    """Word timings from OpenAI transcription -> [(word, start, end)]."""
    key = api_key()
    if not key:
        die("captions need OPENAI_API_KEY (env or .env); or pass --captions off")
    audio = work / f"{clip.stem}.mp3"
    run(["ffmpeg", "-y", "-v", "error", "-i", str(clip), "-vn", "-ac", "1", "-ar", "16000", "-b:a", "48k", str(audio)])
    fields = {"model": "whisper-1", "response_format": "verbose_json", "timestamp_granularities[]": "word"}
    if lang:
        fields["language"] = lang
    b = uuid.uuid4().hex
    body = b"".join(f'--{b}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode() for k, v in fields.items())
    body += f'--{b}\r\nContent-Disposition: form-data; name="file"; filename="a.mp3"\r\nContent-Type: audio/mpeg\r\n\r\n'.encode()
    body += audio.read_bytes() + f"\r\n--{b}--\r\n".encode()
    req = urllib.request.Request("https://api.openai.com/v1/audio/transcriptions", data=body, headers={
        "Authorization": f"Bearer {key}", "Content-Type": f"multipart/form-data; boundary={b}"})
    try:
        with urllib.request.urlopen(req, timeout=300) as r:
            data = json.load(r)
    except urllib.error.HTTPError as e:
        die(f"transcription failed ({e.code}): {e.read()[:300]!r}")
    return [(w["word"].strip(), w["start"], w["end"]) for w in data.get("words", []) if w["word"].strip()]


def chunks(words, max_words=3, max_chars=16):
    """Group words into short caption lines that break on pauses."""
    out, cur = [], []
    for w in words:
        if cur and (len(cur) >= max_words or len(" ".join(x[0] for x in cur + [w])) > max_chars or w[1] - cur[-1][2] > 0.6):
            out.append(cur)
            cur = []
        cur.append(w)
    if cur:
        out.append(cur)
    lines = []
    for i, c in enumerate(out):
        end = out[i + 1][0][1] if i + 1 < len(out) else c[-1][2] + 0.3
        lines.append((" ".join(x[0] for x in c), c[0][1], min(end, c[-1][2] + 0.8)))
    return lines


def font(size):
    from PIL import ImageFont
    for f in FONTS:
        if Path(f).exists():
            return ImageFont.truetype(f, size)
    return ImageFont.load_default(size)


def caption_png(text, path):
    from PIL import Image, ImageDraw
    text = text.upper()
    size = 96
    while size > 48 and font(size).getlength(text) > W - 120:
        size -= 4
    img = Image.new("RGBA", (W, 220), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.text((W / 2, 110), text, font=font(size), fill="white", anchor="mm", stroke_width=10, stroke_fill="black")
    img.save(path)


def compose(clip, lines, layout, out, work):
    dur = float(run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(clip)]).stdout.strip())
    if layout == "crop":
        graph = f"[0:v]scale=-2:{H},crop={W}:{H},setsar=1[v0]"
        cap_y = 1380
    else:  # blur: whole frame in the middle, blurred copy behind it
        graph = (f"[0:v]split[a][b];[a]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},boxblur=24:2[bg];"
                 f"[b]scale={W}:-2[fg];[bg][fg]overlay=(W-w)/2:(H-h)/2,setsar=1[v0]")
        cap_y = 1330
    inputs = ["-i", str(clip)]
    last = "v0"
    for i, (text, a, b) in enumerate(lines, 1):
        png = work / f"{out.stem}-cap{i:03d}.png"
        caption_png(text, png)
        inputs += ["-i", str(png)]
        graph += f";[{last}][{i}:v]overlay=0:{cap_y}:enable='between(t,{a:.2f},{b:.2f})'[v{i}]"
        last = f"v{i}"
    run(["ffmpeg", "-y", "-v", "error", *inputs, "-filter_complex", graph, "-map", f"[{last}]", "-map", "0:a?",
         "-t", f"{dur:.3f}", "-r", "30", "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-pix_fmt", "yuv420p",
         "-c:a", "aac", "-b:a", "160k", "-af", "loudnorm=I=-14:TP=-1.5:LRA=11", "-movflags", "+faststart", str(out)])


def main():
    p = argparse.ArgumentParser(description="Long video + timestamps -> vertical shorts with captions.")
    p.add_argument("source", help="YouTube/Twitch/other yt-dlp link, or a local video file")
    p.add_argument("--at", required=True, help="moments: '1:00:00, 1:20:00+15, 2:05-2:40'")
    p.add_argument("--len", type=float, default=30, help="seconds per clip when only a start is given (30)")
    p.add_argument("--layout", choices=["blur", "crop"], default="blur", help="blur: full frame on a blurred fill; crop: centre crop")
    p.add_argument("--captions", choices=["on", "off"], default="on")
    p.add_argument("--lang", default=None, help="spoken language code for captions, e.g. hi or en (auto if empty)")
    p.add_argument("--out", default="clips", help="output folder (clips/)")
    p.add_argument("--rights", choices=RIGHTS, help="why you may clip this: " + ", ".join(RIGHTS))
    p.add_argument("--proof", help="link or note that backs it (the creator's yes, the campaign page, the licence)")
    a = p.parse_args()

    if not a.rights or not a.proof:
        die("say why you're allowed to clip this: --rights {" + ",".join(RIGHTS) + "} --proof \"<link or note>\". "
            "Credit alone is not permission.")
    if not shutil.which("ffmpeg"):
        die("ffmpeg not found on PATH")

    outdir = Path(a.out)
    outdir.mkdir(parents=True, exist_ok=True)
    slug = re.sub(r"[^a-z0-9]+", "-", Path(a.source).stem.lower() if Path(a.source).exists() else "clip").strip("-") or "clip"
    made, title, page = [], None, a.source
    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp)
        for n, (start, end) in enumerate(moments(a.at, a.len), 1):
            print(f"[{n}] {start:.0f}s -> {end:.0f}s  fetching", flush=True)
            got = fetch(a.source, start, end, work)
            clip, info = got if isinstance(got, tuple) else (got, None)
            if info:
                title, page = info.get("title"), info.get("webpage_url", a.source)
                slug = re.sub(r"[^a-z0-9]+", "-", (info.get("id") or "clip").lower()).strip("-")
            lines = []
            if a.captions == "on":
                print(f"[{n}] captions", flush=True)
                lines = chunks(transcribe(clip, work, a.lang))
                print(f"[{n}] {len(lines)} caption lines" + ("  (no speech found)" if not lines else ""), flush=True)
            out = outdir / f"{slug}-c{n:02d}.mp4"
            print(f"[{n}] rendering {out}", flush=True)
            compose(clip, lines, a.layout, out, work)
            made.append(out)
    credit = outdir / f"{slug}-credit.txt"
    credit.write_text(f"Source: {title or a.source}\nLink: {page}\nRights: {a.rights} ({a.proof})\n"
                      f"Clips: {', '.join(m.name for m in made)}\n")
    print("\ndone:\n" + "\n".join(f"  {m}" for m in made) + f"\n  {credit}  (put the credit line in every post)")


if __name__ == "__main__":
    main()
