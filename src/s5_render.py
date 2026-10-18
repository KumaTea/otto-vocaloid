"""Stage 5: render every layer of score.json with the WORLD vocoder, once per variant.

WORLD splits a "ha" into its pitch curve (f0), its spectral envelope (the timbre: Otto saying "a") and its
aperiodicity (breathiness). Pitch and timing can then change while the timbre stays.

Per note:
  time map   the "h" and the first `onset_hold_ms` of the vowel play at 1×, the vowel's middle is stretched (or
             compressed) to fill the note, the last `release_ms` play at 1×. A variant's `max_stretch` caps the
             stretch: a longer note lets the "ha" end early instead (the other layers carry the note).
  pitch      f_out = f_note · (f_unit / centre_unit)^alpha. alpha 1 keeps the laugh's own movement shifted onto the
             note, alpha 0 is hard-tuned.
  sustain    a stretched "ha" would turn its natural decay into a long fade: `sustain_flatten` evens that out.
  joins      the vowel lands on the note start, so the "h" starts early; when it starts before the previous "ha"
             has ended, the previous one is cut with a short crossfade.
The inhale plays untouched. Also written: raw placements (each unit placed on its note, not stretched or retuned),
material for tuning by hand in FL's Newtone or Melodyne.
"""
import json
import warnings

import librosa
import numpy as np

from . import common as C
from .s2_units import balanced_mono

warnings.filterwarnings("ignore", category=UserWarning, module="pyworld")
import pyworld as pw  # noqa: E402

FP = 5.0                      # WORLD frame period, ms
DT = FP / 1000


# ---------------------------------------------------------------- analysis (cached per unit)

def analyse_unit(u, clips, cache):
    if u["id"] in cache:
        return cache[u["id"]]
    path = C.WORK / "world" / f"{u['id']}.npz"
    if path.exists():
        d = dict(np.load(path))
    else:
        x = clips[u["clip"]][C.sec(u["start"]):C.sec(u["end"])].astype(np.float64)
        lo, hi = (u["midi_range"] or [u["midi"] or 60, u["midi"] or 60]) if not u["is_breath"] else [48, 72]
        floor, ceil = librosa.midi_to_hz(min(lo, hi) - 7), librosa.midi_to_hz(max(lo, hi) + 7)
        f0, t = pw.harvest(x, C.SR, f0_floor=max(60.0, floor), f0_ceil=min(1100.0, ceil), frame_period=FP)
        fft = pw.get_cheaptrick_fft_size(C.SR, 60.0)
        sp = pw.cheaptrick(x, f0, t, C.SR, fft_size=fft)
        ap = pw.d4c(x, f0, t, C.SR, fft_size=fft)
        d = {"f0": f0, "sp": sp, "ap": ap}
        path.parent.mkdir(parents=True, exist_ok=True)
        np.savez(path, **d)
    cache[u["id"]] = d
    return d


# ---------------------------------------------------------------- one note

def time_map(u, note_dur, rc, max_stretch):
    """Input frame position for every output frame, and how the note was fitted.

    Output starts at the unit's start (the "h"), the vowel start lands on the note start, output ends at the note end
    (or earlier when the stretch is capped)."""
    n_in = int(round((u["end"] - u["start"]) / DT))
    v = (u["vowel_start"] - u["start"]) / DT                    # vowel start, in input frames
    hold = rc["onset_hold_ms"] / 1000 / DT
    rel = rc["release_ms"] / 1000 / DT
    core_a = min(v + hold, n_in - rel - 1)                       # stretch region in the input
    core_b = max(core_a + 1, n_in - rel)
    pre_out = core_a                                             # output frames before the stretch region (1×)
    want_core = note_dur / DT + v - pre_out - rel                # output frames available for the core
    nat_core = core_b - core_a
    stretch = want_core / nat_core if nat_core > 0 else 1.0
    fit = "fit"
    if max_stretch is not None and stretch > max_stretch:
        stretch, fit = max_stretch, "ends early"
    cut = None
    if stretch < rc["min_stretch"]:                              # a short note: compress a little, then cut the end
        stretch, fit = rc["min_stretch"], "cut"
        cut = int(round(note_dur / DT + v))
    out_core = max(1, int(round(nat_core * stretch)))
    p = np.concatenate([np.arange(int(np.floor(pre_out))),                          # onset at 1×
                        core_a + np.arange(out_core) / out_core * nat_core,          # stretched core
                        core_b + np.arange(int(np.ceil(rel)))])                      # release at 1×
    p = p[p < n_in - 1]
    if cut is not None:
        p = p[:cut]
    return p, stretch, fit, (int(np.floor(pre_out)), int(np.floor(pre_out)) + out_core)


def render_note(u, d, note, layer, rc, var, transpose):
    p, stretch, fit, (ca, cb) = time_map(u, note["dur"], rc, var["max_stretch"])
    i0 = np.floor(p).astype(int)
    w = (p - i0)[:, None]
    i1 = np.minimum(i0 + 1, len(d["f0"]) - 1)
    sp = np.exp((1 - w) * np.log(d["sp"][i0] + 1e-16) + w * np.log(d["sp"][i1] + 1e-16))
    ap = (1 - w) * d["ap"][i0] + w * d["ap"][i1]

    # pitch: the note, times the laugh's own movement around its centre, raised to alpha
    f_in = d["f0"][i0]
    voiced = (f_in > 0) & (d["f0"][i1] > 0)
    f_in = np.where(voiced, np.exp((1 - w[:, 0]) * np.log(np.maximum(d["f0"][i0], 1)) +
                                   w[:, 0] * np.log(np.maximum(d["f0"][i1], 1))), 0.0)
    # the centre is the laugh's pitch as it will sound on this note (after the time map), so alpha 1 keeps its
    # movement but always centres it on the note, even when the stretched part sits away from the unit's median
    centre = float(np.exp(np.median(np.log(f_in[voiced])))) if voiced.sum() >= 3 else librosa.midi_to_hz(u["midi"])
    target = librosa.midi_to_hz(note["midi"] + transpose) * 2 ** (layer.get("detune_c", 0.0) / 1200)
    f_out = np.where(voiced, target * (np.maximum(f_in, 1) / centre) ** var["alpha"], 0.0)

    # sustain: even out the natural decay over the stretched core, by sustain_flatten
    if stretch > 1.0 and cb - ca > 4 and rc["sustain_flatten"] > 0:
        e = sp[ca:cb].sum(1)
        g = (np.median(e) / np.maximum(e, 1e-16)) ** rc["sustain_flatten"]
        g = np.clip(g, 0.25, 4.0)
        sp[ca:cb] *= g[:, None]

    y = pw.synthesize(np.ascontiguousarray(f_out), np.ascontiguousarray(sp), np.ascontiguousarray(ap), C.SR,
                      frame_period=FP)
    f = min(len(y) // 2, int((0.015 if fit == "cut" else 0.005) * C.SR))   # fade the end; longer where cut short
    y[-f:] *= np.linspace(1, 0, f)
    return y, stretch, fit


# ---------------------------------------------------------------- a layer

def place(track, y, start_s, xfade):
    """Add y at start_s; whatever is already sounding from there on (the previous tail) is faded out first."""
    a = C.sec(start_s)
    if a < 0:
        y, a = y[-a:], 0
    b = min(len(track), a + len(y))
    tail = track[a:b].copy()
    fade = np.ones(b - a)
    k = min(xfade, b - a)
    fade[:k] = np.linspace(1, 0, k)
    fade[k:] = 0
    track[a:b] = tail * fade + y[:b - a]


def run(cfg):
    C.ensure_dirs()
    rc = cfg["render"]
    score = json.loads((C.ROOT / "score.json").read_text())
    units = {u["id"]: u for u in json.loads((C.REPORTS / "units.json").read_text())}
    clips = {}
    for u in units.values():
        if u["clip"] not in clips:
            clips[u["clip"]] = balanced_mono(C.read_wav(C.RAW / f"{u['clip']}.wav"))
    N = len(C.read_wav(C.WORK / "stems" / "bed.wav"))
    xf = int(rc["xfade_ms"] / 1000 * C.SR)
    n_layers = max(len(n["layers"]) for n in score["notes"])
    cache, report = {}, {}

    for var in rc["variants"]:
        print(f"variant {var['name']}: alpha {var['alpha']}, max stretch {var['max_stretch']} …", flush=True)
        tracks = [np.zeros(N) for _ in range(n_layers)]
        fits = []
        for layer_i in range(n_layers):
            for n in score["notes"]:
                if layer_i == 0 and n["breath_before"]:
                    b = units[n["breath_before"]["unit"]]
                    y = clips[b["clip"]][C.sec(b["start"]):C.sec(b["end"])].copy()
                    y *= 10 ** (n["breath_before"]["gain_db"] / 20)
                    place(tracks[0], y, n["breath_before"]["start"], xf)
                if layer_i >= len(n["layers"]):
                    continue
                lay = n["layers"][layer_i]
                u = units[lay["unit"]]
                d = analyse_unit(u, clips, cache)
                y, stretch, fit = render_note(u, d, n, lay, rc, var, score["transpose"])
                g = n["gain_db"] + lay.get("gain_db", 0.0)
                start = n["start"] - (u["vowel_start"] - u["start"]) + lay.get("offset_ms", 0.0) / 1000
                place(tracks[layer_i], y * 10 ** (g / 20), start, xf)
                fits.append({"i": n["i"], "layer": layer_i, "unit": u["id"], "stretch": round(stretch, 2), "fit": fit})
        vdir = C.OUT / "variants" / var["name"]
        for k, tr in enumerate(tracks):
            C.write_wav(vdir / f"layer_{k}.wav", tr)
        stack = pan_mix(tracks, score)
        C.write_wav(vdir / "stack.wav", stack)
        preview(cfg, stack, vdir)
        report[var["name"]] = {"fits": {f: sum(1 for x in fits if x["fit"] == f) for f in ("fit", "ends early", "cut")},
                               "pitch_check": pitch_check(tracks[0], score, var) if var["name"] == rc["default"] else None}
        if var["name"] == rc["default"]:
            for k in range(n_layers):
                C.daw_link(vdir / f"layer_{k}.wav", f"otto_L{k}.wav")
            C.daw_link(vdir / "stack.wav", "otto_stack_dry.wav")
            plot_pitch(tracks[0], score, var)

    raw = raw_placement(score, units, clips, N, n_layers, xf)
    for k, tr in enumerate(raw):
        C.write_wav(C.WORK / "raw" / f"otto_L{k}_raw.wav", tr)
        C.daw_link(C.WORK / "raw" / f"otto_L{k}_raw.wav", f"otto_L{k}_raw.wav")
    C.write_json(C.REPORTS / "render.json", report)
    review(cfg)
    for name, r in report.items():
        print(f"{name}: notes per fit {r['fits']}" + (f"; pitch check {r['pitch_check']['summary']}" if r["pitch_check"] else ""))


def pan_mix(tracks, score):
    """Lead in the centre, each double at its fixed pan (constant power)."""
    pans = {0: 0.0}
    for n in score["notes"]:
        for lay in n["layers"][1:]:
            pans[lay["layer"]] = lay["pan"]
    out = np.zeros((len(tracks[0]), 2))
    for k, tr in enumerate(tracks):
        th = (pans.get(k, 0.0) + 1) * np.pi / 4
        out[:, 0] += tr * np.cos(th)
        out[:, 1] += tr * np.sin(th)
    return out


def preview(cfg, stack, vdir):
    """A quick listen: the stack over the bed for the excerpt, the stack's level matched to the original humming.
    (The proper mix, with reverb and loudness, is Stage 6.)"""
    seg = cfg["segment"]
    a, b = C.sec(seg["start"]), C.sec(seg["end"])
    bed = C.read_wav(C.WORK / "stems" / "bed.wav")[a:b]
    guide = C.read_wav(C.WORK / "stems" / "hum_guide.wav")[a:b]
    st = stack[a:b]
    g = np.sqrt(np.mean(guide ** 2) / (np.mean(st ** 2) + 1e-12))
    mix = bed + g * st
    f = int(0.01 * C.SR)
    mix[:f] *= np.linspace(0, 1, f)[:, None]
    mix[-f:] *= np.linspace(1, 0, f)[:, None]
    peak = np.abs(mix).max()
    if peak > 0.98:
        mix *= 0.98 / peak
    C.write_wav(vdir / "preview.wav", mix)
    C.write_wav(vdir / "preview_vocals.wav", g * st)


def raw_placement(score, units, clips, N, n_layers, xf):
    tracks = [np.zeros(N) for _ in range(n_layers)]
    for k in range(n_layers):
        for n in score["notes"]:
            if k >= len(n["layers"]):
                continue
            lay = n["layers"][k]
            u = units[lay["unit"]]
            y = clips[u["clip"]][C.sec(u["start"]):C.sec(u["end"])].copy()
            start = n["start"] - (u["vowel_start"] - u["start"]) + lay.get("offset_ms", 0.0) / 1000
            place(tracks[k], y, start, xf)
    return tracks


def pitch_check(lead, score, var):
    """Re-track the rendered lead and compare each note's median pitch with its target (cents)."""
    errs = []
    notes = score["notes"]
    for j, n in enumerate(notes):
        a, b = n["start"] + 0.2 * n["dur"], n["end"] - 0.2 * n["dur"]
        if j + 1 < len(notes):                       # stop where the next note's "h" may already sound
            b = min(b, notes[j + 1]["start"] - 0.13)
        x = lead[C.sec(a):C.sec(b)].astype(np.float64)
        if len(x) < C.SR // 20:
            continue
        f0, _ = pw.harvest(x, C.SR, f0_floor=70, f0_ceil=1000, frame_period=FP)
        v = f0[f0 > 0]
        if len(v) < 3:
            continue
        err = 1200 * np.log2(np.median(v) / librosa.midi_to_hz(n["midi"] + score["transpose"]))
        errs.append({"i": n["i"], "cents": round(float(err))})
    e = np.array([abs(x["cents"]) for x in errs])
    return {"notes": errs, "summary": {"median_abs_cents": int(np.median(e)), "over_30": int((e > 30).sum()),
                                       "over_100": int((e > 100).sum()), "checked": len(e)}}


def plot_pitch(lead, score, var):
    plt = C.plt()
    t0, t1 = score["notes"][0]["start"] - 0.3, score["notes"][-1]["end"] + 0.3
    x = lead[C.sec(t0):C.sec(t1)].astype(np.float64)
    f0, t = pw.harvest(x, C.SR, f0_floor=70, f0_ceil=1000, frame_period=FP)
    t = t + t0
    m = np.where(f0 > 0, librosa.hz_to_midi(np.maximum(f0, 1)), np.nan)
    rows = 3
    span = (t1 - t0) / rows
    fig, ax = plt.subplots(rows, 1, figsize=(18, 11))
    for r in range(rows):
        a, b = t0 + r * span, t0 + (r + 1) * span
        k = (t >= a) & (t < b)
        ax[r].plot(t[k], m[k], ".", ms=1.5, color="C0")
        for n in score["notes"]:
            if n["end"] > a and n["start"] < b:
                y = n["midi"] + score["transpose"]
                ax[r].add_patch(plt.Rectangle((n["start"], y - 0.4), n["dur"], 0.8, color="C1", alpha=0.35, lw=0))
        ax[r].set_xlim(a, b)
        ax[r].set_ylim(45, 75)
        ax[r].set_yticks(range(45, 76, 2))
        ax[r].set_yticklabels([librosa.midi_to_note(v) for v in range(45, 76, 2)], fontsize=7)
    ax[0].set_title(f"rendered lead ({var['name']}): its pitch (blue) over the notes (orange)")
    ax[-1].set_xlabel("time on the YouTube clock (s)")
    fig.tight_layout()
    fig.savefig(C.PLOTS / "render_pitch.png")
    plt.close(fig)


def review(cfg):
    rc = cfg["render"]
    notes = {"natural": "The laugh's own pitch movement, shifted onto each note (alpha 1). Long notes capped at 2.5×.",
             "half": "Half the laugh's own movement (alpha 0.5).",
             "flat": "Hard-tuned: every note flat on its pitch (alpha 0).",
             "natural_full": "Like 'natural', but the five long notes are stretched over their full length.",
             "half_full": "Half the movement, long notes stretched over their full length: the pick for the final."}
    seg = cfg["segment"]
    items = [{"kind": "text", "note": "A/B: the same score rendered four ways, over the bed (1:10–2:08). "
                                      "Pitch: natural vs half vs flat. Long notes (1:43–1:56): natural vs natural_full."}]
    for v in rc["variants"]:
        items.append({"kind": "audio", "path": f"variants/{v['name']}/preview.wav",
                      "note": f"{v['name']}: {notes.get(v['name'], '')}"})
    items += [{"kind": "audio", "path": f"variants/{rc['default']}/preview_vocals.wav",
               "note": f"{rc['default']}, the Otto stack alone (no bed)."},
              {"kind": "image", "path": "plots/render_pitch.png"}]
    C.review_section("5", "Stage 5: rendered A/B (LISTEN)", items)
