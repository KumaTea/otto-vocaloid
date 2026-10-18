"""Shared helpers: paths, config, JSON, ffprobe/ffmpeg wrappers, time formatting."""
import json
import subprocess
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"
NATIVE = RAW / "native"          # downloads in their original codec
WORK = ROOT / "data" / "work"
OUT = ROOT / "out"
REPORTS = OUT / "reports"
PLOTS = OUT / "plots"
DAW = OUT / "daw"
SECRETS = ROOT / "secrets"

SR = 48000  # every decoded file is 48 kHz float32


def load_config():
    with open(ROOT / "config.yaml") as f:
        return yaml.safe_load(f)


def ensure_dirs():
    for d in (NATIVE, WORK, REPORTS, PLOTS, DAW):
        d.mkdir(parents=True, exist_ok=True)
    SECRETS.mkdir(mode=0o700, exist_ok=True)


def write_json(path, obj):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False) + "\n")


def run(cmd):
    """Run a command, raising with its stderr on failure."""
    p = subprocess.run([str(c) for c in cmd], capture_output=True, text=True)
    if p.returncode != 0:
        raise RuntimeError(f"{cmd[0]} failed ({p.returncode}):\n{p.stderr[-2000:]}")
    return p.stdout


def ffprobe(path):
    """Codec, bitrate, sample rate, channels and duration of the first audio stream."""
    d = json.loads(run(["ffprobe", "-v", "error", "-select_streams", "a:0",
                        "-show_entries", "stream=codec_name,sample_rate,channels,bit_rate:format=duration,bit_rate",
                        "-of", "json", path]))
    s, f = d["streams"][0], d["format"]
    bit_rate = s.get("bit_rate") or f.get("bit_rate")
    return {
        "codec": s["codec_name"],
        "sample_rate": int(s["sample_rate"]),
        "channels": int(s["channels"]),
        "bit_rate": int(bit_rate) if bit_rate else None,
        "duration": float(f["duration"]),
    }


def decode(src, dst, start=None, end=None):
    """Decode to 48 kHz float32 WAV, keeping channels. Seeking is done after decoding, so cuts are sample-exact."""
    cmd = ["ffmpeg", "-v", "error", "-y", "-i", src]
    if start is not None:
        cmd += ["-ss", f"{start:.6f}"]
    if end is not None:
        cmd += ["-to", f"{end:.6f}"]
    cmd += ["-vn", "-af", f"aresample={SR}:resampler=soxr:precision=28", "-c:a", "pcm_f32le", dst]
    run(cmd)


def fmt_time(sec):
    m, s = divmod(sec, 60)
    return f"{int(m)}:{s:06.3f}"


# ---------------------------------------------------------------- audio

def read_wav(path):
    """Float64 array shaped (samples, channels)."""
    import soundfile as sf
    x, sr = sf.read(path, dtype="float64", always_2d=True)
    assert sr == SR, f"{path}: {sr} Hz, expected {SR}"
    return x


def write_wav(path, x, subtype="FLOAT"):
    """32-bit float by default (DAW files); subtype="PCM_24" for the deliverables (any video editor reads it)."""
    import soundfile as sf
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    sf.write(path, x.astype("float32"), SR, subtype=subtype)


def mono(x):
    return x.mean(axis=1) if x.ndim == 2 else x


def place(x, offset, length):
    """Put x on another clock: x's sample 0 lands at `offset` samples (may be fractional or negative).

    The fractional part is applied as a linear-phase delay in the frequency domain.
    """
    import numpy as np
    n0 = int(np.floor(offset))
    frac = offset - n0
    if abs(frac) > 1e-6:
        n = len(x) + 1
        f = np.fft.rfftfreq(n)
        x = np.fft.irfft(np.fft.rfft(x, n=n, axis=0) * np.exp(-2j * np.pi * f * frac)[:, None], n=n, axis=0)
    out = np.zeros((length, x.shape[1]))
    a, b = max(n0, 0), min(n0 + len(x), length)
    if b > a:
        out[a:b] = x[a - n0:b - n0]
    return out


def db(power_ratio):
    import numpy as np
    return float(10 * np.log10(max(power_ratio, 1e-20)))


def sec(t):
    """Seconds → sample index."""
    return int(round(t * SR))


def link(src, dst):
    """Hard-link src to dst (no extra disk space); copy if linking is not possible."""
    import os
    import shutil
    dst = Path(dst)
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.unlink(missing_ok=True)
    try:
        os.link(src, dst)
    except OSError:
        shutil.copy2(src, dst)


def daw_link(src, name):
    """Expose a full-length work file in out/daw/ (t = 0 is the start of the YouTube video)."""
    link(src, DAW / name)


# ---------------------------------------------------------------- plots and review page

def plt():
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as p
    p.rcParams.update({"figure.dpi": 110, "font.size": 9, "axes.grid": True, "grid.alpha": 0.3})
    return p


def review_section(key, title, items):
    """Record one stage's LISTEN items and re-render out/review.html.

    items: dicts with kind 'audio' (path relative to out/, optional start/end in seconds, note)
    or 'image' (path relative to out/, note), or 'text' (note).
    """
    index = REPORTS / "review.json"
    sections = json.loads(index.read_text()) if index.exists() else {}
    sections[key] = {"title": title, "items": items}
    write_json(index, sections)

    import html
    parts = []
    for k in sorted(sections, reverse=True):
        s = sections[k]
        parts.append(f"<section><h2>{html.escape(s['title'])}</h2>")
        for it in s["items"]:
            note = f"<p>{html.escape(it.get('note', ''))}</p>" if it.get("note") else ""
            if it["kind"] == "audio":
                frag = ""
                if "start" in it:
                    frag = f"#t={it['start']}" + (f",{it['end']}" if "end" in it else "")
                parts.append(f"<div class=item><b>{html.escape(it['path'])}</b>{note}"
                             f"<audio controls preload=none src=\"{it['path']}{frag}\"></audio></div>")
            elif it["kind"] == "image":
                parts.append(f"<div class=item>{note}<a href=\"{it['path']}\"><img src=\"{it['path']}\"></a></div>")
            else:
                parts.append(f"<div class=item>{note}</div>")
        parts.append("</section>")
    page = f"""<!doctype html><meta charset=utf-8><title>coronal-otto review</title>
<style>
body{{font:15px/1.5 system-ui,sans-serif;max-width:1100px;margin:0 auto;padding:16px;background:#fafafa;color:#222}}
h2{{border-bottom:1px solid #ccc;padding-bottom:4px}} .item{{margin:12px 0}} audio{{width:100%}}
img{{max-width:100%;border:1px solid #ddd}}
@media (prefers-color-scheme:dark){{body{{background:#1b1b1b;color:#ddd}} img{{border-color:#444}}}}
</style>
<h1>coronal-otto: listening and plots</h1>
<p>Times on the players are seconds on the YouTube video's clock. Newest stage first.</p>
{''.join(parts)}"""
    (OUT / "review.html").write_text(page)
