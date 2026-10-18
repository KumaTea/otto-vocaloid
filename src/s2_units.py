"""Stage 2: cut the laughs into single "ha" units (and the inhale), with the facts the renderer needs.

A laugh is a train of bursts: its loudness dips between "ha"s, though in a fast laugh the "h" never reaches
silence. So: (1) split the clip into groups at its largest gaps (the known structure, e.g. 6 / 1 / 4 / 3),
(2) inside each group cut at the most prominent loudness dips, (3) measure each unit: where its vowel starts
(the "h" before it is the pre-utterance), its pitch, how voiced it is, how loud and how bright.
Positions are kept relative to the source clip; the WAVs written here are for listening and DAWs.
"""
import warnings

import librosa
import numpy as np
from scipy import ndimage, signal

warnings.filterwarnings("ignore", category=UserWarning, module="pyworld")
import pyworld  # noqa: E402

from . import common as C

warnings.filterwarnings("ignore", category=UserWarning)
HOP = 0.005


def level_db(x, smooth_ms=10):
    n = int(HOP * C.SR)
    k = len(x) // n
    e = 10 * np.log10(np.mean(x[:k * n].reshape(k, n) ** 2, 1) + 1e-12)
    return ndimage.uniform_filter1d(e, max(1, int(smooth_ms / 1000 / HOP)))


def runs(mask):
    d = np.diff(np.r_[0, mask.astype(int), 0])
    return list(zip(np.where(d == 1)[0], np.where(d == -1)[0]))


def groups_from_gaps(active, n_groups):
    """Split active frames into n_groups at the largest gaps between active runs."""
    rs = runs(active)
    if len(rs) < n_groups:
        raise RuntimeError(f"found {len(rs)} active stretches, need at least {n_groups}")
    gaps = sorted(range(len(rs) - 1), key=lambda i: rs[i + 1][0] - rs[i][1], reverse=True)[:n_groups - 1]
    cuts = sorted(gaps)
    out, s = [], rs[0][0]
    for i in cuts:
        out.append((s, rs[i][1]))
        s = rs[i + 1][0]
    out.append((s, rs[-1][1]))
    return out


def balanced_mono(x):
    """Mono with the channels level-matched first (per 50 ms): otto2's last part is panned 11 dB left,
    but both channels carry the same signal, so the quieter one is scaled up before averaging."""
    if x.ndim == 1:
        return x
    n = int(0.05 * C.SR)
    k = max(1, len(x) // n)
    rms = np.sqrt(np.mean(x[:k * n].reshape(k, n, 2) ** 2, axis=1)) + 1e-9      # (k, 2)
    g = np.clip(rms.max(1, keepdims=True) / rms, 1, 10)                          # quieter channel up, ≤ 20 dB
    centres = (np.arange(k) + 0.5) * n
    idx = np.arange(len(x))
    gs = np.stack([np.interp(idx, centres, g[:, c]) for c in (0, 1)], 1)
    return (x * gs).mean(1)


def cut_score(lv, f0, sung, w=0.06):
    """Per-frame evidence that one "ha" ends and the next begins. Each "ha" is a pitch arch, so a boundary is where
      dip:   the loudness sits below the louder peak within ±w on both sides (dB)
      reset: the pitch falls back (≥ 0.7 semitone) or jumps (≥ 3 semitones) from just before to just after
      gap:   the frames right there are unsung (the breathy "h" between two "ha"s)"""
    n = min(len(lv), len(f0))
    k = int(w / HOP)
    midi = np.where(sung[:n], librosa.hz_to_midi(f0[:n]), np.nan)
    out = np.zeros(n)
    for t in range(n):
        a, b = max(0, t - k), min(n, t + k + 1)
        dip = min(lv[a:t + 1].max(), lv[t:b].max()) - lv[t]
        bv, av = midi[a:max(a, t - 1)], midi[t + 2:b]
        bv, av = bv[~np.isnan(bv)], av[~np.isnan(av)]
        reset = 0.0
        if len(bv) >= 3 and len(av) >= 3:
            d = np.median(av[:max(3, len(av) // 2)]) - np.median(bv[-max(3, len(bv) // 2):])
            if d < -0.7 or abs(d) > 3:
                reset = min(abs(d), 6.0)
        gap = 1.0 - sung[max(0, t - 4):min(n, t + 5)].mean()
        out[t] = dip + 1.5 * reset + 2.0 * gap
    return out


def best_cuts(score, a, b, n, min_gap):
    """The n highest-scoring cut frames inside [a, b), at least min_gap apart and from the group's ends."""
    if n <= 0:
        return [], []
    idx, _ = signal.find_peaks(score[a:b], distance=min_gap)
    idx = [i for i in idx if min_gap <= i <= (b - a) - min_gap]       # a unit is never shorter than min_gap
    chosen = sorted(sorted(idx, key=lambda i: score[a + i], reverse=True)[:n])
    if len(chosen) < n:
        raise RuntimeError(f"only {len(chosen)} cut candidates in a group that should have {n + 1} units")
    return [a + i for i in chosen], [float(score[a + i]) for i in chosen]


def analyse(x, cfg):
    """Pitch and "sung" frames of a mono clip on the HOP grid: pYIN at 16 kHz, plus frames where pYIN's best guess
    and Harvest agree within 60 cents (pYIN alone calls much of a laugh unvoiced). Same recipe as Stage 3."""
    sr = 16000
    y = librosa.resample(x, orig_sr=C.SR, target_sr=sr)
    hop = int(HOP * sr)
    f0, vflag, vprob = librosa.pyin(y, fmin=cfg["fmin"], fmax=cfg["fmax"], sr=sr, fill_na=None,
                                    frame_length=1024, hop_length=hop, center=True)
    t = np.arange(len(f0)) * HOP
    fh, th = pyworld.harvest(y.astype(np.float64), sr, f0_floor=cfg["fmin"], f0_ceil=cfg["fmax"], frame_period=HOP * 1000)
    fh = np.interp(t, th, fh)
    agree = (fh > 0) & (np.abs(1200 * np.log2(np.maximum(fh, 1e-6) / f0)) < 60)
    return f0, (vflag & (vprob > 0.25)) | agree


def run(cfg):
    C.ensure_dirs()
    uc = cfg["units"]
    out_units, sheets = [], []
    for src, sc in uc["sources"].items():
        full = balanced_mono(C.read_wav(C.RAW / f"{sc['wav']}.wav"))
        a0, a1 = sc.get("window", [0, len(full) / C.SR])
        m = full[C.sec(a0):C.sec(a1)]
        lv = level_db(m)
        peak = lv.max()
        active = lv > peak - uc["active_db"]
        active = ndimage.binary_opening(active, np.ones(4))          # ignore blips shorter than 20 ms
        groups = sc["groups"]
        if groups == "auto":
            rs = runs(active)
            gspans = [(rs[0][0], rs[-1][1])]
        else:
            gspans = groups_from_gaps(active, len(groups))
        f0, sung = analyse(m, uc)
        score = cut_score(lv, f0, sung)
        min_gap = int(uc["min_unit_ms"] / 1000 / HOP)

        bounds, proms = [], []
        for gi, (s, e) in enumerate(gspans):
            if groups == "auto":
                idx, _ = signal.find_peaks(score[s:e], height=uc["auto_cut_score"], distance=min_gap)
                cuts = [s + i for i in idx if min_gap // 2 <= i <= (e - s) - min_gap // 2]
                pr = [float(score[c]) for c in cuts]
                n_units = len(cuts) + 1
            elif gi in sc.get("cuts", {}):           # cut times pinned by hand (clip seconds) for this group
                cuts = [int(round((c - a0) / HOP)) for c in sc["cuts"][gi]]
                pr = [float(score[c]) for c in cuts]
                n_units = len(cuts) + 1
                if n_units != groups[gi]:
                    raise RuntimeError(f"{src} group {gi}: {len(cuts)} pinned cuts but {groups[gi]} units expected")
            else:
                n_units = groups[gi]
                cuts, pr = best_cuts(score, s, e, n_units - 1, min_gap)
            edges = [s] + cuts + [e]
            for k in range(n_units):
                bounds.append((gi, edges[k], edges[k + 1]))
            proms += pr

        units = []
        for k, (gi, s, e) in enumerate(bounds):
            seg = slice(s, e)
            v = sung[seg]
            vr = float(v.mean())
            vi = np.where(v)[0]
            is_breath = (groups != "auto" and gi == sc.get("breath_group", -1)) or vr < 0.2
            vs = s + int(vi[0]) if len(vi) and not is_breath else s
            ve = s + int(vi[-1]) + 1 if len(vi) and not is_breath else e
            fm = librosa.hz_to_midi(f0[seg][v]) if v.any() else np.array([np.nan])
            xs = m[int(s * HOP * C.SR):int(e * HOP * C.SR)]
            cent = float(np.mean(librosa.feature.spectral_centroid(y=xs, sr=C.SR)))
            uid = f"{src}_{k:02d}"
            units.append({
                "id": uid, "source": src, "clip": sc["wav"], "group": gi,
                "start": round(a0 + s * HOP, 4), "end": round(a0 + e * HOP, 4),
                "vowel_start": round(a0 + vs * HOP, 4), "vowel_end": round(a0 + ve * HOP, 4),
                "preutter_ms": round((vs - s) * HOP * 1000, 1), "dur_ms": round((e - s) * HOP * 1000, 1),
                "midi": None if np.isnan(fm).all() else round(float(np.nanmedian(fm)), 2),
                "midi_range": None if np.isnan(fm).all() else [round(float(np.nanpercentile(fm, 10)), 2),
                                                               round(float(np.nanpercentile(fm, 90)), 2)],
                "vowel_ms": round((ve - vs) * HOP * 1000, 1),
                "voiced_ratio": round(vr, 2), "peak_db": round(float(lv[seg].max()), 1),
                "centroid_hz": round(cent), "is_breath": bool(is_breath),
            })
            # listening / DAW copy with 3 ms fades so the cut edges don't click
            y = full[C.sec(units[-1]["start"]):C.sec(units[-1]["end"])].copy()          # mono, balanced
            f = min(int(0.003 * C.SR), len(y) // 4)
            if f:
                y[:f] *= np.linspace(0, 1, f)
                y[-f:] *= np.linspace(1, 0, f)
            C.write_wav(C.WORK / "units" / f"{uid}.wav", y)
            C.daw_link(C.WORK / "units" / f"{uid}.wav", f"units/{uid}.wav")
        # laughs tire as they go on: the order of the "ha"s within a source is its exhaustion, 0 = fresh, 1 = spent
        ha = [u for u in units if not u["is_breath"]]
        for i, u in enumerate(ha):
            u["exhaustion"] = round(i / max(1, len(ha) - 1), 3)
        for u in units:
            u.setdefault("exhaustion", None)
        out_units += units
        sheet = C.PLOTS / f"units_{src}.png"
        contact_sheet(src, m, lv, f0, sung, a0, units, sheet, score)
        sheets.append(sheet.name)
        print(f"\n{src}: {len(units)} units in {len(gspans)} groups; cut scores: "
              f"{[round(p, 1) for p in proms]}")
        for u in units:
            print(f"  {u['id']}  {u['start']:8.3f}–{u['end']:8.3f}  {u['dur_ms']:5.0f} ms  h {u['preutter_ms']:4.0f} ms  "
                  f"{'BREATH' if u['is_breath'] else librosa.midi_to_note(u['midi']) if u['midi'] else '?':>6}  "
                  f"voiced {u['voiced_ratio']:.2f}  peak {u['peak_db']:6.1f} dB  centroid {u['centroid_hz']} Hz  "
                  f"exhaustion {u['exhaustion']}")

    C.write_json(C.REPORTS / "units.json", out_units)
    with open(C.DAW / "units" / "units.csv", "w") as f:
        f.write("id,source,start_s_in_clip,end_s_in_clip,dur_ms,preutterance_ms,vowel_ms,median_midi,note,voiced_ratio,"
                "peak_db,centroid_hz,exhaustion,breath\n")
        for u in out_units:
            note = librosa.midi_to_note(u["midi"]) if u["midi"] else ""
            f.write(f"{u['id']},{u['source']},{u['start']},{u['end']},{u['dur_ms']},{u['preutter_ms']},{u['vowel_ms']},"
                    f"{u['midi']},{note},{u['voiced_ratio']},{u['peak_db']},{u['centroid_hz']},{u['exhaustion']},"
                    f"{u['is_breath']}\n")
    C.review_section("2", "Stage 2: the laugh units (LISTEN)", [
        {"kind": "text", "note": "Each file should be exactly one 'ha' (or the inhale): no clipped 'h' at the start, "
                                 "no piece of the next 'ha' at the end."},
    ] + [{"kind": "audio", "path": f"daw/units/{u['id']}.wav",
          "note": f"{u['id']}: {u['dur_ms']:.0f} ms, " + ("inhale" if u["is_breath"] else
                  f"{librosa.midi_to_note(u['midi']) if u['midi'] else '?'}, 'h' {u['preutter_ms']:.0f} ms")}
         for u in out_units] + [{"kind": "image", "path": f"plots/{s}"} for s in sheets])


def contact_sheet(src, m, lv, f0, vflag, a0, units, path, score):
    plt = C.plt()
    t = a0 + np.arange(len(lv)) * HOP
    tf = a0 + np.arange(len(f0)) * HOP
    fig, ax = plt.subplots(4, 1, figsize=(18, 11), sharex=True, gridspec_kw={"height_ratios": [1.2, 1, 1, 0.8]})
    tw = a0 + np.arange(len(m)) / C.SR
    ax[0].plot(tw, m, lw=0.3, color="0.4")
    ax[0].set_title(f"{src}: waveform with unit cuts (red), vowel starts (green)")
    ax[1].plot(t, lv, lw=0.8)
    ax[1].set_title("level (dBFS, 10 ms smoothing)")
    ax[2].plot(tf, np.where(vflag, f0, np.nan), ".", ms=2)
    ax[2].set_yscale("log")
    ax[2].set_title("pitch on sung frames (pYIN where it agrees with Harvest), Hz")
    ax[3].plot(a0 + np.arange(len(score)) * HOP, score, lw=0.8, color="C4")
    ax[3].set_title("cut score = loudness dip (dB) + 1.5 × pitch reset (semitones) + 2 × unsung share")
    for u in units:
        for a in ax:
            a.axvline(u["start"], color="C3", lw=1)
            a.axvline(u["vowel_start"], color="C2", lw=0.8, ls="--")
        ax[0].text((u["start"] + u["end"]) / 2, ax[0].get_ylim()[1] * 0.85, u["id"].split("_")[-1], ha="center",
                   fontsize=9, color="C3" if u["is_breath"] else "k")
    for a in ax:
        a.axvline(units[-1]["end"], color="C3", lw=1)
    ax[-1].set_xlabel("time in the source clip (s)")
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)
