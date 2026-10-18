"""Stage 3c: how thick is the humming, note by note? (the "stacking" in 1:27–1:57)

Per note of the reviewed MIDI, over the note's middle 60 %, measured on the guide (人声):
  side/mid    stereo width: overdubbed takes are usually panned, a single voice sits in the centre
  hnr         harmonics-to-noise ratio (Praat): several slightly detuned voices blur the harmonics
  beating     loudness wobble on harmonics 2–4: detuned voices on one note beat against each other
  off_harm    share of energy at pitches that are not the note's own harmonics: other voices
              holding other notes (a drone or chord), or the previous note still ringing
  sub_oct     energy one octave below the note, relative to the note: an octave-down layer
  tail        (notes followed by a rest) energy in the 150 ms after the note ends: reverb
Each is compared with the single-voice opening (notes before `stack.baseline_end`), and the stacking measures
are combined into a 0–1 thickness per note.
"""
import json

import librosa
import numpy as np
import parselmouth
from scipy import signal

from . import common as C

LANDMARKS = [74, 87, 102, 117]


def middle(n, frac=0.6):
    d = n["end"] - n["start"]
    a = n["start"] + d * (1 - frac) / 2
    return a, a + d * frac


def harmonic_mask(f, f0, kmax, cents=40):
    m = np.zeros_like(f, dtype=bool)
    for k in range(1, kmax + 1):
        fc = k * f0
        half = max(fc * (2 ** (cents / 1200) - 1), 1.5 * (f[1] - f[0]))
        m |= np.abs(f - fc) <= half
    return m


def band_energy(f, P, fc, cents=40):
    half = max(fc * (2 ** (cents / 1200) - 1), 1.5 * (f[1] - f[0]))
    return float(P[np.abs(f - fc) <= half].sum())


def beating(x, f0):
    """Mean modulation depth (std/mean of the 2–20 Hz envelope) on harmonics 2–4."""
    out = []
    for k in (2, 3, 4):
        fc = k * f0
        if fc * 1.03 > C.SR / 2:
            continue
        sos = signal.butter(4, [fc * 0.97, fc * 1.03], btype="band", fs=C.SR, output="sos")
        env = np.abs(signal.hilbert(signal.sosfiltfilt(sos, x)))
        sos2 = signal.butter(2, 20, btype="low", fs=C.SR, output="sos")
        env = signal.sosfiltfilt(sos2, env)[C.SR // 50:-C.SR // 50 or None]   # drop filter edges
        if len(env) > C.SR // 20 and env.mean() > 0:
            out.append(env.std() / env.mean())
    return float(np.mean(out)) if out else None


def measure(guide, n, f0_track, next_start):
    a, b = middle(n)
    seg = guide[C.sec(a):C.sec(b)]
    mid, side = C.mono(seg), (seg[:, 0] - seg[:, 1]) / 2
    if len(mid) < C.SR // 20:
        return None
    t, m = f0_track
    k = (t >= a) & (t < b) & ~np.isnan(m)
    sung = float(np.median(m[k])) if k.sum() > 5 else float(n["midi"])
    f0 = librosa.midi_to_hz(sung)

    nfft = 8192
    f, P = signal.welch(mid, C.SR, nperseg=min(nfft, len(mid)), noverlap=None)
    band = (f >= 80) & (f <= 2500)
    hm = harmonic_mask(f, f0, int(2500 // f0))
    off_harm = float(P[band & ~hm].sum() / P[band].sum())
    sub_oct = 10 * np.log10(band_energy(f, P, f0 / 2) / band_energy(f, P, f0) + 1e-12)

    snd = parselmouth.Sound(mid, sampling_frequency=C.SR)
    h = snd.to_harmonicity_cc(time_step=0.01, minimum_pitch=max(60.0, f0 * 0.6))
    hv = h.values[h.values > -200]
    hnr = float(np.mean(hv)) if hv.size else None

    out = {"sung_midi": round(sung, 2),
           "side_mid_db": round(10 * np.log10(np.mean(side ** 2) / np.mean(mid ** 2) + 1e-12), 2),
           "hnr_db": None if hnr is None else round(hnr, 2),
           "beating": None if (bt := beating(mid, f0)) is None else round(bt, 3),
           "off_harm": round(off_harm, 3), "sub_oct_db": round(sub_oct, 2), "tail_db": None}
    if next_start is None or next_start - n["end"] >= 0.25:
        body = C.mono(guide[C.sec(a):C.sec(b)])
        tail = C.mono(guide[C.sec(n["end"]):C.sec(n["end"] + 0.15)])
        out["tail_db"] = round(10 * np.log10(np.mean(tail ** 2) / np.mean(body ** 2) + 1e-12), 2)
    return out


def run(cfg):
    C.ensure_dirs()
    sc = cfg["stack"]
    guide = C.read_wav(C.WORK / "stems" / "hum_guide.wav")
    notes = json.loads((C.REPORTS / "notes_final.json").read_text())
    d = np.load(C.WORK / "transcribe_f0.npz")
    track = (d["t"], d["midi_smooth"])
    hints = cfg["transcribe"].get("narration_hints", [])

    rows = []
    for i, n in enumerate(notes):
        nxt = notes[i + 1]["start"] if i + 1 < len(notes) else None
        r = measure(guide, n, track, nxt)
        if r is None:
            continue
        r.update({"i": n["i"], "start": n["start"], "end": n["end"], "name": n["name"], "phrase": n["phrase"],
                  "narration": any(h0 < n["end"] and n["start"] < h1 for h0, h1 in hints)})
        rows.append(r)

    # The composite of all measures (z-scores against the single-voice opening) is kept for reference, but it is
    # noisy: fast gliding passages inflate hnr, beating and off_harm whatever the number of voices. Stereo width is
    # the measure that follows what the user hears, so thickness = width, scaled from the opening's median (0)
    # to the 95th percentile (1).
    base = [r for r in rows if r["end"] <= sc["baseline_end"] and not r["narration"]]
    feats = {"side_mid_db": +1, "off_harm": +1, "hnr_db": -1, "beating": +1}
    z = {}
    for k, sign in feats.items():
        bv = np.array([r[k] for r in base if r[k] is not None])
        mu, sd = float(np.median(bv)), float(np.std(bv)) + 1e-9
        for r in rows:
            z.setdefault(r["i"], {})[k] = None if r[k] is None else sign * (r[k] - mu) / sd
    w_lo = float(np.median([r["side_mid_db"] for r in base]))
    w_hi = float(np.percentile([r["side_mid_db"] for r in rows], 95))
    for r in rows:
        r["z"] = {k: (None if v is None else round(v, 2)) for k, v in z[r["i"]].items()}
        r["composite"] = round(float(np.mean([v for v in z[r["i"]].values() if v is not None])), 2)
        r["thickness"] = round(float(np.clip((r["side_mid_db"] - w_lo) / (w_hi - w_lo), 0, 1)), 3)

    phrases = []
    for p in sorted({r["phrase"] for r in rows}):
        allp = [r for r in rows if r["phrase"] == p]
        rs = [r for r in allp if not r["narration"]] or allp
        w = np.array([r["end"] - r["start"] for r in rs])
        th = float(np.average([r["thickness"] for r in rs], weights=w))
        sub = float(np.average([r["sub_oct_db"] for r in rs], weights=w))
        phrases.append({"phrase": p, "start": allp[0]["start"], "end": allp[-1]["end"], "thickness": round(th, 3),
                        "side_mid_db": round(float(np.average([r["side_mid_db"] for r in rs], weights=w)), 2),
                        "sub_oct_db": round(sub, 1),
                        "proposed_layers": 1 + int(round(th * (sc["max_layers"] - 1))),
                        "octave_down_layer": bool(sub > sc["octave_layer_db"])})
    tails = [(r["end"], r["tail_db"]) for r in rows if r["tail_db"] is not None]
    rep = {"baseline_notes": [r["i"] for r in base], "notes": rows, "phrases": phrases, "tails": tails}
    C.write_json(C.REPORTS / "stack.json", rep)
    plot(rows, phrases, tails, sc)
    C.review_section("3c", "Stage 3c: how thick the humming is", [
        {"kind": "image", "path": "plots/stack_curve.png",
         "note": "Per note and per phrase. Does it match what you hear: where the stacking starts, peaks and ends?"},
        {"kind": "image", "path": "plots/stack_features.png", "note": "The individual measures behind it."},
    ])
    print(f"width scale: {w_lo:.1f} dB (opening) → 0, {w_hi:.1f} dB → 1")
    print("phrase   start     end   width dB  thickness  layers  octave below dB")
    for p in phrases:
        print(f"  {p['phrase']:3d}   {C.fmt_time(p['start'])}  {C.fmt_time(p['end'])}  {p['side_mid_db']:6.1f}     {p['thickness']:.2f}       "
              f"{p['proposed_layers']}      {p['sub_oct_db']:6.1f}{'  ← octave-down layer' if p['octave_down_layer'] else ''}")


def plot(rows, phrases, tails, sc):
    plt = C.plt()
    t = [(r["start"] + r["end"]) / 2 for r in rows]
    fig, ax = plt.subplots(figsize=(15, 4.5))
    for r in rows:
        ax.plot([r["start"], r["end"]], [r["thickness"]] * 2, color="C3" if r["narration"] else "C0", lw=3, alpha=0.7)
    for p in phrases:
        ax.plot([p["start"], p["end"]], [p["thickness"]] * 2, color="k", lw=1.2, ls="--")
    k = sc["keys"]
    ax.plot([x for x, _ in k], [y for _, y in k], "o:", color="C2", label="your landmarks (stack.keys)")
    for x in LANDMARKS:
        ax.axvline(x, color="c", lw=0.7, ls=":")
    ax.set_ylim(-0.05, 1.05)
    ax.set_xlabel("time on the YouTube clock (s)")
    ax.set_title("thickness = stereo width, per note (blue; red = narration overlaps) and per phrase (dashed)")
    ax.legend(loc="upper left")
    fig.tight_layout()
    fig.savefig(C.PLOTS / "stack_curve.png")
    plt.close(fig)

    keys = [("side_mid_db", "stereo width: side/mid (dB)"), ("hnr_db", "harmonics-to-noise (dB, lower = blurrier)"),
            ("beating", "beating on harmonics 2–4"), ("off_harm", "energy off the note's harmonics (other voices)"),
            ("sub_oct_db", "octave below the note (dB re the note)")]
    fig, ax = plt.subplots(len(keys) + 1, 1, figsize=(15, 13), sharex=True)
    for a, (k, title) in zip(ax, keys):
        for r in rows:
            if r[k] is not None:
                a.plot([r["start"], r["end"]], [r[k]] * 2, color="C3" if r["narration"] else "C0", lw=3, alpha=0.7)
        a.axvline(sc["baseline_end"], color="C2", lw=0.8)
        a.set_title(title)
    if tails:
        ax[-1].plot([a for a, _ in tails], [b for _, b in tails], "o", color="C4")
    ax[-1].set_title("tail after notes followed by a rest: energy in the next 150 ms (dB re the note) = reverb")
    for a in ax:
        for x in LANDMARKS:
            a.axvline(x, color="c", lw=0.7, ls=":")
    ax[-1].set_xlabel("time on the YouTube clock (s); green line = end of the single-voice baseline")
    fig.tight_layout()
    fig.savefig(C.PLOTS / "stack_features.png")
    plt.close(fig)
