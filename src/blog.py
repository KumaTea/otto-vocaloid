"""Data for the blog post (blog/index.html): every curve and number its charts show, measured from this project's files.

`uv run build.py blog` writes blog/data.js (`window.BLOG = {...}`), a script rather than JSON so the page also works
opened straight from disk, and the short audio clips the charts play (blog/audio/, Opus in WebM plus AAC in M4A for
browsers without WebM). The clips are excerpts of other people's recordings (the PV, the laughs): the page works
without that folder, its play buttons just disappear.
"""
import json

import librosa
import numpy as np
import pyloudnorm as pyln
import soundfile as sf

from . import common as C
from .s1_align import drift, xcorr_coarse, xcorr_fine
from .s2_units import HOP, analyse, balanced_mono, cut_score, level_db
from .s4_score import choose_transpose, core_stretch, cost_terms, natural_len
from .s5_render import analyse_unit, pitch_check, render_note

BLOG = C.ROOT / "blog"
AUDIO = BLOG / "audio"
VOCALS_SPAN = (73.5, 130.0)           # what the pitch, choir and casting charts play: the original and the Otto version
RENDER_ALPHAS, RENDER_DURS = (0.0, 0.5, 1.0), (0.5, 1.0, 2.0)


def r(x, nd=2):
    """Round for JSON; NaN/inf → None."""
    if x is None:
        return None
    a = np.asarray(x, dtype=float)
    if a.ndim == 0:
        return None if not np.isfinite(a) else round(float(a), nd)
    return [None if not np.isfinite(v) else round(float(v), nd) for v in a]


def peak_keep(z, k):
    """Downsample a curve by k, keeping each bin's largest-magnitude value (so peaks survive)."""
    n = len(z) // k
    b = z[:n * k].reshape(n, k)
    return b[np.arange(n), np.argmax(np.abs(b), axis=1)]


# ---------------------------------------------------------------- 1. alignment

def align_data():
    yt = C.mono(C.read_wav(C.RAW / "yt.wav"))
    out = []
    for sid, name in (("w_orig", "原音乐 (the music, lossless)"), ("w_bed", "伴奏 (accompaniment)"),
                      ("w_vocals", "人声 (vocals)"), ("w_music_hum", "音乐加男声吟唱 (music + humming)")):
        x = C.mono(C.read_wav(C.RAW / f"{sid}.wav"))
        c, sign, (lags_s, z) = xcorr_coarse(yt, x)
        lag, (off_ms, zf), peak = xcorr_fine(yt, x, c)
        k = 20                                                    # 8 kHz → 2.5 ms per point
        coarse = {"t": r(peak_keep(lags_s, k), 4), "z": r(peak_keep(z, k), 4)}
        zf_ = zf[::4]
        fine = {"t": r((c + off_ms[::4] / 1000 * C.SR) / C.SR * 1000, 3), "z": r(zf_, 5)}
        d = drift(yt, x, lag)
        out.append({"id": sid, "name": name, "lag_samples": round(float(lag), 3), "lag_ms": round(lag / C.SR * 1000, 4),
                    "peak": round(peak, 3), "coarse": coarse, "fine": fine,
                    "drift": {"t": r([p["t_x"] for p in d], 1), "dev": r([p["dev_samples"] for p in d], 3)}})
        print(f"  align {sid}: {lag / C.SR * 1000:.3f} ms, peak {peak:.3f}, drift max "
              f"{max(abs(p['dev_samples']) for p in d):.3f} samples over {len(d)} windows")
    rep = json.loads((C.REPORTS / "align.json").read_text())
    return {"sources": out, "mixture_residual_db": rep["fits"]["reference ≈ bed + guide (all)"]["residual_db"],
            "yt_vs_lossless_db": rep["fits"]["yt ≈ reference (segment)"]["residual_db"]}


# ---------------------------------------------------------------- 2. pitch and notes

def pitch_data(cfg):
    d = np.load(C.WORK / "transcribe_f0.npz")
    s = slice(None, None, 2)                                       # 5 ms → 10 ms
    t, f0, vp, fh, ms = d["t"][s], d["f0"][s], d["vprob"][s], d["harvest"][s], d["midi_smooth"][s]
    pyin = np.where((vp > 0.25) & (f0 > 0), librosa.hz_to_midi(np.maximum(f0, 1)), np.nan)
    harv = np.where(fh > 0, librosa.hz_to_midi(np.maximum(fh, 1)), np.nan)
    draft = json.loads((C.REPORTS / "notes.json").read_text())
    final = json.loads((C.REPORTS / "notes_final.json").read_text())
    rep = json.loads((C.REPORTS / "notes_final_report.json").read_text())
    cmp_ = json.loads((C.REPORTS / "notes_compare.json").read_text())
    tr = json.loads((C.REPORTS / "transcribe.json").read_text()) if (C.REPORTS / "transcribe.json").exists() else {}
    return {"t0": round(float(t[0]), 3), "dt": 0.01, "sung": r(ms), "pyin": r(pyin), "harvest": r(harv),
            "draft": [[n["start"], n["end"], n["midi"]] for n in draft],
            "final": [[n["start"], n["end"], n["midi"]] for n in final],
            "narration": cfg["transcribe"]["narration_hints"],
            "grid": {"phase": rep["grid_phase_s"], "period": 60 / cfg["export"]["tempo"]},
            "compare": cmp_["counts"], "pitch_fit": rep["pitch_fit_at_offset"], "offset_s": rep["offset_s"],
            "tempo_tracked": tr.get("tempo_bpm"), "tempo": cfg["export"]["tempo"], "draft_count": len(draft)}


# ---------------------------------------------------------------- 3. how many voices

def stack_data(cfg):
    st = json.loads((C.REPORTS / "stack.json").read_text())
    layers = cfg["stack"]["layers_by_phrase"]
    return {"notes": [{"i": n["i"], "s": n["start"], "e": n["end"], "name": n["name"], "narr": n["narration"],
                       "width_db": n["side_mid_db"], "z": n["z"]} for n in st["notes"]],
            "phrases": [{"p": p["phrase"], "s": p["start"], "e": p["end"], "measured": p["proposed_layers"],
                         "layers": layers[p["phrase"]]} for p in st["phrases"]],
            "baseline_end": cfg["stack"]["baseline_end"]}


# ---------------------------------------------------------------- 4. cutting the laughs

def units_data(cfg):
    uc = cfg["units"]
    units = json.loads((C.REPORTS / "units.json").read_text())
    out = []
    for src, sc in uc["sources"].items():
        full = balanced_mono(C.read_wav(C.RAW / f"{sc['wav']}.wav"))
        a0, a1 = sc.get("window", [0, len(full) / C.SR])
        m = full[C.sec(a0):C.sec(a1)]
        lv = level_db(m)
        f0, sung = analyse(m, uc)
        score = cut_score(lv, f0, sung)
        n = min(len(lv), len(f0))
        midi = np.where(sung[:n], librosa.hz_to_midi(np.maximum(f0[:n], 1)), np.nan)
        us = [u for u in units if u["source"] == src]
        out.append({"src": src, "t0": a0, "dt": HOP, "level": r(lv[:n], 1), "midi": r(midi, 2),
                    "score": r(score[:n], 2),
                    "units": [{"id": u["id"], "s": u["start"], "e": u["end"], "v": u["vowel_start"],
                               "midi": u["midi"], "note": librosa.midi_to_note(u["midi"]) if u["midi"] else None,
                               "dur_ms": u["dur_ms"], "pre_ms": u["preutter_ms"], "tired": u["exhaustion"],
                               "breath": u["is_breath"]} for u in us]})
    return out


# ---------------------------------------------------------------- 5. casting: which "ha" sings which note

def casting_data(cfg):
    """Replays Stage 4's greedy choice and keeps, for the lead of every note, the cost of every candidate."""
    sc, st, rc = cfg["score"], cfg["stack"], cfg["render"]
    notes = json.loads((C.REPORTS / "notes_final.json").read_text())
    units = json.loads((C.REPORTS / "units.json").read_text())
    score = json.loads((C.ROOT / "score.json").read_text())
    ha = [u for u in units if not u["is_breath"] and u["midi"] is not None]
    lead_pool = [u for u in ha if u["source"] in sc["lead_sources"]]
    double_pool = [u for u in ha if u["source"] in sc["double_sources"]]
    k = choose_transpose(notes, lead_pool, sc["transpose"])
    t0, t1 = notes[0]["start"], notes[-1]["end"]
    used, prev, rows = {}, {}, []
    for n, sn in zip(notes, score["notes"]):
        prog = (n["start"] - t0) / (t1 - t0)
        n_layers = st["layers_by_phrase"][n["phrase"]]
        taken = set()
        for layer in range(n_layers):
            pool = lead_pool if layer == 0 else double_pool
            cands = []
            for u in pool:
                terms, shift, stretch = cost_terms(n, u, prog, sc, prev.get(layer), used, taken, k, rc)
                cands.append((sum(terms.values()), u, terms, shift, stretch))
            cands.sort(key=lambda c: c[0])
            best = cands[0][1]
            assert best["id"] == sn["layers"][layer]["unit"], f"replay differs at note {n['i']} layer {layer}"
            if layer == 0:
                rows.append({"i": n["i"], "s": n["start"], "e": n["end"], "midi": n["midi"], "name": n["name"],
                             "progress": round(prog, 3), "layers": n_layers,
                             "cands": [{"id": u["id"], "total": round(c, 2), "shift": round(sh, 2),
                                        "stretch": round(sx, 2), "terms": {a: round(b, 2) for a, b in te.items()}}
                                       for c, u, te, sh, sx in cands[:6]]})
            taken.add(best["id"])
            used[best["id"]] = used.get(best["id"], 0) + 1
            prev[layer] = best["id"]
    return {"notes": rows, "weights": sc["weights"], "free_shift_st": sc["free_shift_st"],
            "comfort_stretch": sc["comfort_stretch"],
            "units": {u["id"]: {"midi": u["midi"], "len": round(natural_len(u), 3), "tired": u["exhaustion"]}
                      for u in ha}}


# ---------------------------------------------------------------- 6. WORLD: one "ha" taken apart, and the time map

def world_data(cfg, ids=("otto_07", "otto_13", "otto2_03")):
    units = {u["id"]: u for u in json.loads((C.REPORTS / "units.json").read_text())}
    out = []
    for uid in ids:
        u = units[uid]
        d = np.load(C.WORK / "world" / f"{uid}.npz")
        sp_db = 10 * np.log10(d["sp"] + 1e-16)
        nb = sp_db.shape[1]
        f = np.arange(nb) * C.SR / (2 * (nb - 1))
        fb = np.geomspace(60, 16000, 72)                         # log-spaced bins: how the ear spaces pitch
        env = np.stack([np.interp(fb, f, row) for row in sp_db])
        env -= env.max()
        band = (f >= 500) & (f <= 5000)
        out.append({"id": uid, "note": librosa.midi_to_note(u["midi"]), "midi": u["midi"],
                    "start": u["start"], "vowel": u["vowel_start"], "end": u["end"], "dt": 0.005,
                    "f0": r(d["f0"], 1), "freqs": r(fb, 1), "env": [r(row, 1) for row in env],
                    "ap": r(d["ap"][:, band].mean(1), 3)})
    rc = cfg["render"]
    notes = json.loads((C.REPORTS / "notes_final.json").read_text())
    n46 = notes[46]
    return {"units": out, "onset_hold_ms": rc["onset_hold_ms"], "release_ms": rc["release_ms"],
            "example_note": {"i": n46["i"], "midi": n46["midi"], "name": n46["name"], "dur": n46["dur"]}}


# ---------------------------------------------------------------- 7. did the render land on the notes?

def variants_data(cfg):
    score = json.loads((C.ROOT / "score.json").read_text())
    out = {}
    for v in cfg["render"]["variants"]:
        if v["name"] == "natural_full":
            continue
        lead = C.read_wav(C.OUT / "variants" / v["name"] / "layer_0.wav")[:, 0]
        pc = pitch_check(lead, score, v)
        out[v["name"]] = {"alpha": v["alpha"], "full": v["max_stretch"] is None, "notes": pc["notes"],
                          "summary": pc["summary"]}
        print(f"  pitch check {v['name']}: {pc['summary']}")
    starts = {n["i"]: n["start"] for n in score["notes"]}
    return {"variants": out, "starts": starts}


# ---------------------------------------------------------------- 8. mixing by measurement

def mix_data(cfg):
    notes = json.loads((C.ROOT / "score.json").read_text())["notes"]
    guide = C.read_wav(C.WORK / "stems" / "hum_guide.wav")
    bus = C.read_wav(C.WORK / "mix" / "otto_bus.wav")
    a, b = C.sec(73), C.sec(127)
    blk = int(0.01 * C.SR)

    def peaks(x):
        x = x[a:b]
        n = len(x) // blk
        pk = 20 * np.log10(np.abs(x[:n * blk]).reshape(n, blk, -1).max(axis=(1, 2)) + 1e-9)
        act = pk[pk > pk.max() - 30]
        below = pk.max() - act
        h, _ = np.histogram(below, bins=np.arange(0, 31, 1))
        return {"hist": r(h / h.sum() * 100, 2), "median_below": round(float(np.median(below)), 1)}

    def tail(x, e):
        x = C.mono(x)
        ref = 10 * np.log10(np.mean(x[C.sec(e - 0.15):C.sec(e)] ** 2) + 1e-20)
        ts = np.arange(-0.15, 0.6, 0.01)
        return r([10 * np.log10(np.mean(x[C.sec(e + s):C.sec(e + s + 0.01)] ** 2) + 1e-20) - ref for s in ts], 1)

    ends = [79.02, 86.80, 119.46]                 # phrase ends whose rest is clean (no breath, no narration)
    end_of = {round(n["end"], 2): n["end"] for n in notes}
    ends = [end_of[e] for e in ends]
    meter = pyln.Meter(C.SR)
    yt = C.read_wav(C.WORK / "stems" / "yt_original.wav")[C.sec(70):C.sec(128)]
    fin, _ = sf.read(C.OUT / "final" / "otto_with_bed_1m10-2m08.wav", always_2d=True)
    mix = json.loads((C.REPORTS / "mix.json").read_text())
    return {"peaks": {"humming": peaks(guide), "otto": peaks(bus)},
            "tails": {"t_ms": list(range(-150, 600, 10)), "ends": r(ends, 2),
                      "humming": [tail(guide, e) for e in ends], "otto": [tail(bus, e) for e in ends]},
            "lufs_original": round(meter.integrated_loudness(yt), 1), "lufs_ours": round(meter.integrated_loudness(fin), 1),
            "mix": mix}


# ---------------------------------------------------------------- audio the charts play

def encode(x, name, kbps):
    """x (samples[, channels]) → audio/<name>.webm (Opus) and audio/<name>.m4a (AAC, for browsers without WebM)."""
    tmp = C.WORK / "blog" / f"{name}.wav"
    C.write_wav(tmp, x if x.ndim == 2 else x[:, None])
    AUDIO.mkdir(parents=True, exist_ok=True)
    C.run(["ffmpeg", "-v", "error", "-y", "-i", tmp, "-c:a", "libopus", "-b:a", f"{kbps}k", AUDIO / f"{name}.webm"])
    C.run(["ffmpeg", "-v", "error", "-y", "-i", tmp, "-c:a", "aac", "-b:a", f"{int(kbps * 1.5)}k",
           "-movflags", "+faststart", AUDIO / f"{name}.m4a"])


def peak_norm(x, db=-1.0):
    return x * (10 ** (db / 20) / (np.abs(x).max() + 1e-12))


def audio(cfg, world):
    a, b = (C.sec(t) for t in VOCALS_SPAN)
    orig = C.read_wav(C.WORK / "stems" / "hum_guide.wav")[a:b]
    otto = C.read_wav(C.WORK / "mix" / "otto_bus.wav")[a:b]
    g = 10 ** (-1 / 20) / max(np.abs(orig).max(), np.abs(otto).max())      # one gain for both: their balance stays
    encode(orig * g, "vocals_orig", 64)
    encode(otto * g, "vocals_otto", 64)
    seg = cfg["segment"]
    fin, _ = sf.read(C.OUT / "final" / f"otto_with_bed_{int(seg['start'] // 60)}m{int(seg['start'] % 60):02d}-"
                                      f"{int(seg['end'] // 60)}m{int(seg['end'] % 60):02d}.wav", always_2d=True)
    encode(fin, "result", 96)
    for src, sc in cfg["units"]["sources"].items():
        x = C.read_wav(C.RAW / f"{sc['wav']}.wav")
        a0, a1 = sc.get("window", [0, len(x) / C.SR])
        encode(peak_norm(x[C.sec(a0):C.sec(a1)]), f"laugh_{src}", 64)
    units = {u["id"]: u for u in json.loads((C.REPORTS / "units.json").read_text())}
    rc = cfg["render"]
    clips, cache = {}, {}
    for w in world["units"]:
        u = units[w["id"]]
        if u["clip"] not in clips:
            clips[u["clip"]] = balanced_mono(C.read_wav(C.RAW / f"{u['clip']}.wav"))
        encode(peak_norm(clips[u["clip"]][C.sec(u["start"]):C.sec(u["end"])], -3), f"ha_{u['id']}", 64)
        d = analyse_unit(u, clips, cache)
        for al in RENDER_ALPHAS:
            for du in RENDER_DURS:
                y, _, _ = render_note(u, d, {"dur": du, "midi": int(round(u["midi"]))}, {}, rc,
                                      {"alpha": al, "max_stretch": None}, 0)
                encode(peak_norm(y, -3), f"tm_{u['id']}_a{int(al * 100)}_d{int(du * 100)}", 64)
    size = sum(p.stat().st_size for p in AUDIO.iterdir())
    print(f"  audio: {len(list(AUDIO.iterdir()))} files, {size / 1e6:.1f} MB")
    return {"vocals_t0": VOCALS_SPAN[0], "result_t0": seg["start"], "alphas": RENDER_ALPHAS, "durs": RENDER_DURS}


def run(cfg):
    BLOG.mkdir(exist_ok=True)
    print("measuring …", flush=True)
    data = {"align": align_data(), "pitch": pitch_data(cfg), "stack": stack_data(cfg), "units": units_data(cfg),
            "casting": casting_data(cfg), "world": world_data(cfg), "variants": variants_data(cfg),
            "mix": mix_data(cfg),
            "lines_of_python": sum(len(p.read_text().splitlines()) for p in (C.ROOT / "src").glob("*.py"))
            + len((C.ROOT / "build.py").read_text().splitlines())}
    data["audio"] = audio(cfg, data["world"])
    js = "window.BLOG = " + json.dumps(data, ensure_ascii=False, separators=(",", ":")) + ";\n"
    (BLOG / "data.js").write_text(js)
    print(f"blog/data.js: {len(js) / 1024:.0f} KB")
