"""Stage 0: Bilibili QR login, then download each source's audio and decode it to 48 kHz float32 WAV."""
import http.cookiejar
import io
import json
import os
import re
import sys
import time

import qrcode
import requests
import soundfile as sf
import yt_dlp

from . import common as C

UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/140.0.0.0 Safari/537.36")
PASSPORT = "https://passport.bilibili.com/x/passport-login/web/qrcode"
POLL_STATUS = {86101: "waiting for scan", 86090: "scanned, confirm on the phone",
               86038: "QR expired", 0: "confirmed"}


# ---------------------------------------------------------------- login

def _session():
    s = requests.Session()
    s.headers.update({"User-Agent": UA, "Referer": "https://www.bilibili.com/"})
    return s


def _nav(s):
    """Login state from the nav API. Returns only non-secret flags."""
    d = s.get("https://api.bilibili.com/x/web-interface/nav", timeout=10).json().get("data") or {}
    return {"isLogin": d.get("isLogin", False), "vipStatus": d.get("vipStatus"),
            "vipType": d.get("vipType"), "vip_label": (d.get("vip_label") or {}).get("text")}


def login(cfg, timeout=175):
    """Show a QR code, wait for the user to scan and confirm it in the Bilibili app, save cookies."""
    C.ensure_dirs()
    cookie_path = C.ROOT / cfg["auth"]["bilibili_cookies"]
    qr_png, qr_txt = C.SECRETS / "login_qr.png", C.SECRETS / "login_qr.txt"
    s = _session()

    r = s.get(f"{PASSPORT}/generate", timeout=10).json()
    if r.get("code") != 0:
        sys.exit(f"QR generate failed: {r.get('message')}")
    url, key = r["data"]["url"], r["data"]["qrcode_key"]

    qr = qrcode.QRCode(border=2)
    qr.add_data(url)
    qr.make(fit=True)
    qr.make_image().save(qr_png)
    buf = io.StringIO()
    qr.print_ascii(out=buf, invert=True)  # dark modules as spaces: reads correctly on a dark terminal
    ascii_qr = buf.getvalue().replace("\xa0", " ")
    qr_txt.write_text(ascii_qr)
    print(ascii_qr)
    print(f"Scan with the Bilibili app within {timeout} s (also saved as {qr_png}).", flush=True)

    t0, last = time.time(), None
    try:
        while True:
            if time.time() - t0 > timeout:
                sys.exit("Timed out waiting for the scan. Run `build.py login` again.")
            d = s.get(f"{PASSPORT}/poll", params={"qrcode_key": key}, timeout=10).json()["data"]
            if d["code"] != last:
                print(f"[{time.time() - t0:4.0f} s] {POLL_STATUS.get(d['code'], d)}", flush=True)
                last = d["code"]
            if d["code"] == 0:
                break
            if d["code"] == 86038:
                sys.exit("QR expired. Run `build.py login` again.")
            time.sleep(2)
    finally:
        qr_png.unlink(missing_ok=True)
        qr_txt.unlink(missing_ok=True)

    jar = http.cookiejar.MozillaCookieJar(str(cookie_path))
    for c in s.cookies:
        jar.set_cookie(c)
    jar.save(ignore_discard=True, ignore_expires=True)
    os.chmod(cookie_path, 0o600)

    state = _nav(s)
    print(f"Saved cookies to {cookie_path.relative_to(C.ROOT)} ({len(jar)} cookies). Login state: {state}")
    if not state["isLogin"]:
        sys.exit("The nav API says not logged in; the cookies may be incomplete.")


def check_login(cfg):
    cookie_path = C.ROOT / cfg["auth"]["bilibili_cookies"]
    if not cookie_path.exists():
        return {"isLogin": False}
    s = _session()
    jar = http.cookiejar.MozillaCookieJar(str(cookie_path))
    jar.load(ignore_discard=True, ignore_expires=True)
    s.cookies.update(jar)
    return _nav(s)


# ---------------------------------------------------------------- download

def _audio_formats(formats):
    return [f for f in formats
            if f.get("vcodec") in (None, "none") and f.get("acodec") not in (None, "none")]


def _pick_audio(formats):
    """Best plain audio format: FLAC, then Opus (48 kHz native, no resampling), then the highest bitrate.

    Excluded: Dolby / E-AC-3 (can be a different mix) and YouTube's DRC variants (loudness-compressed).
    On YouTube, auto-dubbed tracks are dropped in favour of the original language.
    """
    fs = [f for f in _audio_formats(formats)
          if not re.search(r"ec-3|eac3|ac-3|ac3", f.get("acodec") or "")
          and "drc" not in (f.get("format_id") or "").lower()]
    if not fs:
        raise RuntimeError("no usable audio-only format")
    best_lang = max(f.get("language_preference") if f.get("language_preference") is not None else -1
                    for f in fs)
    fs = [f for f in fs if (f.get("language_preference") if f.get("language_preference") is not None else -1)
          == best_lang]
    codec_rank = {"flac": 2, "opus": 1}
    return max(fs, key=lambda f: (codec_rank.get((f.get("acodec") or "").split(".")[0], 0),
                                  f.get("abr") or f.get("tbr") or 0))


def _summarise(f):
    return {k: f.get(k) for k in ("format_id", "format_note", "acodec", "abr", "asr", "audio_channels", "language")}


def _download(cfg, sid, url):
    """Download the best audio-only format for one source into data/raw/native/. Returns a report dict."""
    is_bili = "bilibili.com" in url
    cookies = cfg["auth"]["bilibili_cookies"] if is_bili else cfg["auth"]["youtube_cookies"]
    seen = {}

    def choose(ctx):
        seen["available"] = [_summarise(f) for f in _audio_formats(ctx["formats"])]
        best = _pick_audio(ctx["formats"])
        seen["chosen"] = _summarise(best)
        yield best

    opts = {
        "format": choose,
        "outtmpl": str(C.NATIVE / f"{sid}.%(ext)s"),
        "noplaylist": True,
        "quiet": True,
        "noprogress": True,
        "overwrites": True,
    }
    if cookies and (C.ROOT / cookies).exists():
        opts["cookiefile"] = str(C.ROOT / cookies)
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=True)
    path = info["requested_downloads"][0]["filepath"]
    return {"url": url, "title": info.get("title"), "native": os.path.relpath(path, C.ROOT),
            "logged_in": bool(opts.get("cookiefile")), **seen}


def _download_file(sid, url):
    """A direct link to an audio file: plain HTTP download, no format choice."""
    ext = os.path.splitext(url.split("?")[0])[1] or ".bin"
    path = C.NATIVE / f"{sid}{ext}"
    r = requests.get(url, headers={"User-Agent": UA}, timeout=60)
    r.raise_for_status()
    path.write_bytes(r.content)
    return {"url": url, "native": os.path.relpath(path, C.ROOT)}


DIRECT = (".mp3", ".wav", ".flac", ".m4a", ".ogg", ".opus")


def fetch(cfg, only=None, force=False):
    C.ensure_dirs()
    report_path = C.REPORTS / "sources.json"
    report = {}
    if report_path.exists():
        report = json.loads(report_path.read_text())

    sids = [s for s in cfg["sources"] if not only or s in only]
    if any("bilibili.com" in cfg["sources"][s].get("url", "") for s in sids):
        state = check_login(cfg)
        print(f"Bilibili login: {state}")
        if not state["isLogin"]:
            print("  Not logged in: formats may be limited. Run `build.py login` first for the best audio.")

    for sid in sids:
        src = cfg["sources"][sid]
        existing = sorted(C.NATIVE.glob(f"{sid}.*"))
        if "path" in src:  # a local file the user put in place
            entry = {"path": src["path"], "native": src["path"]}
        elif existing and not force and sid in report:
            print(f"{sid}: already downloaded ({existing[0].name}); use --force to redo")
            entry = report[sid]
        elif src["url"].split("?")[0].lower().endswith(DIRECT):
            print(f"{sid}: downloading {src['url']}", flush=True)
            entry = _download_file(sid, src["url"])
        else:
            print(f"{sid}: downloading {src['url']}", flush=True)
            entry = _download(cfg, sid, src["url"])
            c = entry["chosen"]
            print(f"  chose {c['format_id']} ({c['acodec']}, {c['abr']} kbps, {c['asr']} Hz)"
                  f" out of {len(entry['available'])} audio formats")
        native = C.ROOT / entry["native"]
        entry["probe"] = C.ffprobe(native)

        if "clip" in src:  # only the window we need, sample-exact
            a, b = src["clip"]
            wav = C.RAW / f"{sid}_clip.wav"
            C.decode(native, wav, start=a, end=b)
            entry["clip"] = [a, b]
        else:
            wav = C.RAW / f"{sid}.wav"
            C.decode(native, wav)
        info = sf.info(wav)
        entry["wav"] = {"path": os.path.relpath(wav, C.ROOT), "sample_rate": info.samplerate,
                        "channels": info.channels, "duration": info.frames / info.samplerate}
        report[sid] = entry
        C.write_json(report_path, report)

    _check(report)


def _check(report):
    print("\n id              codec      kbps   native Hz  ch  duration   wav")
    for sid, e in report.items():
        p, w = e["probe"], e["wav"]
        kbps = f"{p['bit_rate'] / 1000:.0f}" if p["bit_rate"] else "?"
        print(f" {sid:15} {p['codec']:9} {kbps:>5}  {p['sample_rate']:>9}  {p['channels']:>2}  "
              f"{C.fmt_time(p['duration']):>9}  {w['sample_rate']} Hz, {w['duration']:.3f} s")

    problems = []
    stems = [report[s]["probe"]["duration"] for s in ("p1", "p2", "p3") if s in report]
    if len(stems) == 3 and max(stems) - min(stems) > 1.0:
        problems.append(f"p1/p2/p3 durations differ by {max(stems) - min(stems):.2f} s")
    if "yt" in report and not 195 < report["yt"]["probe"]["duration"] < 210:
        problems.append(f"yt is {report['yt']['probe']['duration']:.1f} s, expected ~202 s")
    if any(e["wav"]["sample_rate"] != C.SR for e in report.values()):
        problems.append("not every WAV is 48 kHz")
    print("\nChecks: " + ("all passed" if not problems else "; ".join(problems)))
