"""Stage 3a/3b: transcribe the guide (人声: humming + breaths + narration) into notes, with tempo and key checks.

Pitch tracking is librosa's pYIN, cross-checked with WORLD's Harvest. Notes are stretches where the pitch holds
near one semitone; a loudness dip on the same pitch splits repeated notes. The guide still contains narration,
so some notes will be speech: the user deletes those in the MIDI review (`notes_edited.mid`).
"""
import warnings

import librosa
import numpy as np
import pretty_midi
from scipy import ndimage

from . import common as C

warnings.filterwarnings("ignore", category=UserWarning, module="pyworld")
import pyworld  # noqa: E402  (imports pkg_resources and warns)

SR_T = 16000           # analysis sample rate
HOP = 80               # 5 ms
FRAME = 1024           # 64 ms: at least 3 periods of the lowest pitch
DT = HOP / SR_T
NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
# Krumhansl–Kessler key profiles
MAJOR = np.array([6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88])
MINOR = np.array([6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17])
SCALE = {"major": [0, 2, 4, 5, 7, 9, 11], "minor": [0, 2, 3, 5, 7, 8, 10, 11]}  # minor: natural + raised 7th


def name(m):
    return f"{NAMES[int(m) % 12]}{int(m) // 12 - 1}"


# ---------------------------------------------------------------- pitch tracking

def track(x16, cfg):
    tc = cfg["transcribe"]
    # fill_na=None: pYIN also reports its best pitch guess on frames it calls unvoiced
    f0, vflag, vprob = librosa.pyin(x16, fmin=tc["fmin"], fmax=tc["fmax"], sr=SR_T, fill_na=None,
                                    frame_length=FRAME, hop_length=HOP, center=True)
    t = librosa.times_like(f0, sr=SR_T, hop_length=HOP)
    fh, th = pyworld.harvest(x16.astype(np.float64), SR_T, f0_floor=tc["fmin"], f0_ceil=tc["fmax"],
                             frame_period=DT * 1000)
    fh = np.interp(t, th, fh)
    rms = librosa.feature.rms(y=x16, frame_length=FRAME, hop_length=HOP, center=True)[0][:len(t)]
    # pYIN's voicing is conservative on breathy, stacked humming. A frame also counts as sung when the two
    # independent trackers agree on its pitch within 60 cents.
    agree = (fh > 0) & (np.abs(1200 * np.log2(np.maximum(fh, 1e-6) / f0)) < 60)
    sung = (vflag & (vprob > 0.25)) | agree
    return t, f0, sung, vprob, fh, 20 * np.log10(rms + 1e-10)


# ---------------------------------------------------------------- note segmentation

def runs(mask):
    """(start, end) index pairs of consecutive True values, end exclusive."""
    d = np.diff(np.r_[0, mask.astype(int), 0])
    return list(zip(np.where(d == 1)[0], np.where(d == -1)[0]))


def segment(t, f0, vflag, vprob, rms_db, cfg):
    """Return notes as dicts with start/end (s), midi, and frame indices."""
    tc = cfg["transcribe"]
    min_n = max(1, int(round(tc["min_note_ms"] / 1000 / DT)))
    m = np.where(vflag, librosa.hz_to_midi(f0), np.nan)        # vflag here = "sung" from track()
    loud = rms_db > rms_db.max() - 40
    ok = vflag & loud
    ok = ndimage.binary_closing(ok, structure=np.ones(7))         # bridge gaps up to ~30 ms
    m = np.where(ok, m, np.nan)
    # fill tiny pitch holes inside voiced runs, then smooth over 25 ms
    for a, b in runs(ok):
        seg = m[a:b]
        bad = np.isnan(seg)
        if bad.all():
            ok[a:b] = False
            continue
        if bad.any():
            idx = np.arange(len(seg))
            seg[bad] = np.interp(idx[bad], idx[~bad], seg[~bad])
        m[a:b] = ndimage.median_filter(seg, size=5, mode="nearest")

    notes = []
    for a, b in runs(ok):
        if b - a < min_n:
            continue
        # hysteresis: a note continues while the pitch stays within 0.6 semitone of its running centre;
        # it ends when the pitch has left that band for min_note frames in a row
        s, ref, out = a, np.median(m[a:a + min_n]), 0
        i = a + 1
        while i < b:
            if abs(m[i] - ref) > 0.6:
                out += 1
                if out >= min_n:
                    cut = i - out + 1
                    if cut - s >= min_n:
                        notes.append([s, cut])
                    s, out = cut, 0
                    ref = np.median(m[s:min(s + min_n, b)])
            else:
                out = 0
                ref = np.median(m[s:i + 1]) if i - s < 40 else ref   # settle the centre over the first 200 ms
            i += 1
        if b - s >= min_n:
            notes.append([s, b])

    # pitch of each note: median over its middle 60 %, rounded to a semitone
    out = []
    for s, e in notes:
        k = max(1, (e - s) // 5)
        mid = m[s + k:e - k] if e - s > 2 * k else m[s:e]
        p = float(np.nanmedian(mid))
        out.append({"s": s, "e": e, "midi_f": p, "midi": int(round(p))})

    # merge neighbours on the same semitone with no gap; then split repeated notes at loudness dips
    merged = []
    for n in out:
        if merged and n["midi"] == merged[-1]["midi"] and n["s"] - merged[-1]["e"] <= 1:
            merged[-1]["e"] = n["e"]
        else:
            merged.append(n)
    final = []
    for n in merged:
        final.extend(split_at_dips(n, rms_db, min_n))
    final = tidy(final, int(tc["glide_merge_ms"] / 1000 / DT), int(tc["blip_drop_ms"] / 1000 / DT))
    for n in final:
        n["start"], n["end"] = float(t[n["s"]]), float(t[min(n["e"], len(t) - 1)])
    return final, m


def tidy(notes, glide_max, blip_max, touch=4):
    """Fold glides into real notes, and drop isolated blips (all lengths in frames).

    - A short note that touches the next one and lies between its neighbours' pitches is the middle of a slide:
      it joins the note the voice slides to (that note now starts where the slide began).
    - A short note that touches only the previous one is a falling tail: it joins the previous note.
    - A short note touching nothing is a blip (a stray syllable, a breath, a tracking error): dropped.
    """
    out = [dict(n) for n in notes]
    i = len(out) - 1
    while i >= 0:
        n = out[i]
        if n["e"] - n["s"] < glide_max:
            pv = out[i - 1] if i > 0 else None
            nx = out[i + 1] if i + 1 < len(out) else None
            t_prev = pv is not None and n["s"] - pv["e"] <= touch
            t_next = nx is not None and nx["s"] - n["e"] <= touch
            between = t_prev and t_next and min(pv["midi"], nx["midi"]) < n["midi"] < max(pv["midi"], nx["midi"])
            if t_next and (between or not t_prev):
                nx["s"] = n["s"]
                del out[i]
            elif t_prev and not t_next:
                pv["e"] = n["e"]
                del out[i]
        i -= 1
    return [n for n in out if not (n["e"] - n["s"] < blip_max and _isolated(n, out, touch))]


def _isolated(n, notes, touch):
    return all(not (0 <= o["s"] - n["e"] <= touch or 0 <= n["s"] - o["e"] <= touch) for o in notes if o is not n)


def split_at_dips(n, rms_db, min_n, depth=6.0):
    """Split a note where its loudness dips by `depth` dB below the peaks on both sides (repeated notes)."""
    s, e = n["s"], n["e"]
    r = ndimage.uniform_filter1d(rms_db[s:e], 5)
    cuts = []
    for i in range(min_n, len(r) - min_n):
        if r[i] == r[max(0, i - 6):i + 7].min():
            left, right = r[max(0, i - 30):i].max(), r[i + 1:i + 31].max()
            if min(left, right) - r[i] >= depth and (not cuts or i - cuts[-1] >= min_n):
                cuts.append(i)
    if not cuts:
        return [n]
    bounds = [s] + [s + c for c in cuts] + [e]
    return [{**n, "s": a, "e": b} for a, b in zip(bounds[:-1], bounds[1:])]


# ---------------------------------------------------------------- tempo and key

def tempo_and_key(bed, a, b):
    y = librosa.resample(C.mono(bed[C.sec(a):C.sec(b)]), orig_sr=C.SR, target_sr=22050)
    tempo, beats = librosa.beat.beat_track(y=y, sr=22050, units="time")
    tempo = float(np.atleast_1d(tempo)[0])
    beats = beats + a
    ibi = np.diff(beats)
    chroma = librosa.feature.chroma_cqt(y=y, sr=22050).mean(1)
    scores = []
    for tonic in range(12):
        for mode, prof in (("major", MAJOR), ("minor", MINOR)):
            scores.append((float(np.corrcoef(chroma, np.roll(prof, tonic))[0, 1]), tonic, mode))
    scores.sort(reverse=True)
    return tempo, beats, ibi, scores


def grid_offsets_ms(onsets, beats, div=4):
    """Distance of each onset to the nearest 1/div-beat grid line, interpolated between tracked beats."""
    out = []
    if len(beats) < 2:
        return [None] * len(onsets)
    for o in onsets:
        if o < beats[0] or o >= beats[-1]:
            out.append(None)
            continue
        k = np.searchsorted(beats, o) - 1
        b0, b1 = beats[k], beats[k + 1]
        step = (b1 - b0) / div
        frac = (o - b0) / step
        out.append(float((frac - round(frac)) * step * 1000))
    return out


# ---------------------------------------------------------------- outputs

def tones(notes, n_samples, level=0.12):
    """Simple organ-like tones for the check renders: fundamental + 2 soft harmonics, 10 ms attack, 30 ms release."""
    y = np.zeros(n_samples)
    for n in notes:
        a, b = C.sec(n["start"]), C.sec(n["end"])
        if b <= a:
            continue
        tt = np.arange(b - a) / C.SR
        f = librosa.midi_to_hz(n["midi"])
        w = np.sin(2 * np.pi * f * tt) + 0.4 * np.sin(4 * np.pi * f * tt) + 0.15 * np.sin(6 * np.pi * f * tt)
        env = np.minimum(1, np.minimum(tt / 0.01, (tt[-1] - tt) / 0.03 + 1e-9))
        y[a:b] += level * w * np.clip(env, 0, 1)
    return y


def write_midi(notes, bpm, path):
    pm = pretty_midi.PrettyMIDI(initial_tempo=bpm, resolution=960)
    inst = pretty_midi.Instrument(program=52, name="guide melody")   # Choir Aahs
    louds = np.array([n["loud_db"] for n in notes])
    lo, hi = np.percentile(louds, 5), np.percentile(louds, 95)
    for n in notes:
        vel = int(np.clip(50 + 70 * (n["loud_db"] - lo) / max(hi - lo, 1e-6), 30, 120))
        inst.notes.append(pretty_midi.Note(velocity=vel, pitch=n["midi"], start=n["start"], end=n["end"]))
    pm.instruments.append(inst)
    pm.write(str(path))


def plot_notes(t, m, fh, rms_db, notes, a, b, path, landmarks):
    plt = C.plt()
    k = (t >= a) & (t < b)
    fig, ax = plt.subplots(2, 1, figsize=(16, 7), sharex=True, gridspec_kw={"height_ratios": [4, 1]})
    mh = np.where(fh > 0, librosa.hz_to_midi(np.where(fh > 0, fh, 1.0)), np.nan)
    ax[0].plot(t[k], mh[k], ".", ms=1.5, color="0.65", label="Harvest")
    ax[0].plot(t[k], m[k], lw=1.2, color="C0", label="pitch used (pYIN where sung, smoothed)")
    for n in notes:
        if n["end"] < a or n["start"] > b:
            continue
        col = "C3" if n["flags"] else "C1"
        ax[0].add_patch(plt.Rectangle((n["start"], n["midi"] - 0.4), n["end"] - n["start"], 0.8,
                                      color=col, alpha=0.45, lw=0))
        ax[0].text(n["start"], n["midi"] + 0.5, f"{n['i']}", fontsize=7)
    vals = m[k][~np.isnan(m[k])]
    lo, hi = (np.floor(vals.min()) - 2, np.ceil(vals.max()) + 2) if len(vals) else (48, 72)
    ax[0].set_ylim(lo, hi)
    ax[0].set_yticks(range(int(lo), int(hi) + 1))
    ax[0].set_yticklabels([name(v) for v in range(int(lo), int(hi) + 1)], fontsize=7)
    ax[0].set_title(f"guide pitch and notes, {a:.0f}–{b:.0f} s (orange = note, red = flagged; numbers = note index)")
    ax[0].legend(loc="upper right")
    ax[1].plot(t[k], rms_db[k], lw=0.8)
    ax[1].set_ylabel("dB")
    for axi in ax:
        for x in landmarks:
            if a <= x <= b:
                axi.axvline(x, color="c", lw=0.8, ls=":")
    ax[1].set_xlabel("time on the YouTube clock (s)")
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)


# ---------------------------------------------------------------- stage

def run(cfg):
    C.ensure_dirs()
    tc, seg = cfg["transcribe"], cfg["segment"]
    a, b = seg["hum_start"] - 0.5, seg["end"] + 2.0
    guide = C.read_wav(C.WORK / "stems" / "hum_guide.wav")
    bed = C.read_wav(C.WORK / "stems" / "bed.wav")
    x16 = librosa.resample(C.mono(guide[C.sec(a):C.sec(b)]), orig_sr=C.SR, target_sr=SR_T)

    print(f"tracking pitch over {a:.1f}–{b:.1f} s (pYIN + Harvest) …", flush=True)
    t, f0, vflag, vprob, fh, rms_db = track(x16, cfg)
    t = t + a
    notes, m = segment(t, f0, vflag, vprob, rms_db, cfg)

    # per-note facts and flags
    hints = tc.get("narration_hints", [])
    phrase, last_end = 0, None
    for i, n in enumerate(notes):
        s, e = n["s"], n["e"]
        n["i"] = i
        n["name"] = name(n["midi"])
        n["dur"] = n["end"] - n["start"]
        n["loud_db"] = float(np.median(rms_db[s:e]))
        both = (fh[s:e] > 0) & vflag[s:e]
        dis = np.abs(1200 * np.log2(fh[s:e][both] / f0[s:e][both])) if both.any() else np.array([0.0])
        n["tracker_gap_cents"] = float(np.median(dis))
        n["wobble_cents"] = float(np.nanstd(m[s:e]) * 100)
        if last_end is not None and n["start"] - last_end >= tc["phrase_rest_ms"] / 1000:
            phrase += 1
        n["phrase"], last_end = phrase, n["end"]
        n["flags"] = []
        if n["tracker_gap_cents"] > 50:
            n["flags"].append("trackers disagree")
        if any(h0 < n["end"] and n["start"] < h1 for h0, h1 in hints):
            n["flags"].append("narration nearby")

    print("tempo and key from the bed …", flush=True)
    tempo, beats, ibi, keys = tempo_and_key(bed, seg["start"], seg["end"])
    steady = float(np.std(ibi) / np.mean(ibi)) if len(ibi) > 2 else 1.0
    bpm = tempo if (cfg["export"]["tempo"] == "auto" and steady < 0.05) else \
        (cfg["export"]["tempo"] if cfg["export"]["tempo"] != "auto" else 120.0)
    _, tonic, mode = keys[0]
    scale = {(tonic + d) % 12 for d in SCALE[mode]}
    for n in notes:
        if n["midi"] % 12 not in scale:
            n["flags"].append("outside the key")
    offs = grid_offsets_ms([n["start"] for n in notes], beats)
    for n, o in zip(notes, offs):
        n["grid_ms"] = None if o is None else round(o, 1)

    # outputs ---------------------------------------------------------------
    keep = ["i", "start", "end", "dur", "midi", "name", "phrase", "loud_db", "tracker_gap_cents", "wobble_cents",
            "grid_ms", "flags"]
    rows = [{k: (round(n[k], 4) if isinstance(n[k], float) else n[k]) for k in keep} for n in notes]
    C.write_json(C.REPORTS / "notes.json", rows)
    with open(C.DAW / "notes.csv", "w") as f:
        f.write("i,start,end,dur,midi,name,phrase,loud_db,flags\n")
        for r in rows:
            f.write(f"{r['i']},{r['start']:.3f},{r['end']:.3f},{r['dur']:.3f},{r['midi']},{r['name']},"
                    f"{r['phrase']},{r['loud_db']:.1f},{'; '.join(r['flags'])}\n")
    write_midi(notes, bpm, C.DAW / "notes.mid")
    np.savez(C.WORK / "transcribe_f0.npz", t=t, f0=f0, vprob=vprob, harvest=fh, rms_db=rms_db, midi_smooth=m,
             beats=beats)

    print("check renders …", flush=True)
    N = len(guide)
    tn = tones(notes, N)
    g = C.mono(guide)
    g = g / (np.abs(g[C.sec(a):C.sec(b)]).max() + 1e-9) * 0.5
    C.write_wav(C.WORK / "check" / "check_midi_vs_hum.wav", np.stack([g, tn], 1))
    C.write_wav(C.WORK / "check" / "check_midi_over_bed.wav", bed + tn[:, None])
    for nm in ("check_midi_vs_hum.wav", "check_midi_over_bed.wav"):
        C.daw_link(C.WORK / "check" / nm, nm)

    landmarks = [74, 87, 102, 117]
    plots = []
    for p0 in np.arange(np.floor(a / 10) * 10, b, 10):
        path = C.PLOTS / f"notes_{int(p0):03d}.png"
        plot_notes(t, m, fh, rms_db, notes, p0, p0 + 10, path, landmarks)
        plots.append(path.name)

    rep = {
        "window_s": [a, b], "notes": len(notes), "phrases": phrase + 1,
        "hum_start_refined": round(notes[0]["start"], 3) if notes else None,
        "pitch_range": [name(min(n["midi"] for n in notes)), name(max(n["midi"] for n in notes))] if notes else None,
        "tempo_bpm": round(tempo, 2), "beat_steadiness_cv": round(steady, 3), "bpm_in_midi": round(bpm, 2),
        "beats_first8_s": [round(float(x), 3) for x in beats[:8]],
        "midi_grid_offset_s": round(float(beats[0] % (60 / bpm)), 3) if len(beats) else None,
        "key": f"{NAMES[tonic]} {mode}", "key_runners_up": [f"{NAMES[k]} {md} ({s:.2f})" for s, k, md in keys[1:4]],
        "key_score": round(keys[0][0], 3),
        "flagged": {f: [n["i"] for n in notes if f in n["flags"]]
                    for f in ("trackers disagree", "narration nearby", "outside the key")},
        "grid_offset_ms_median_abs": round(float(np.median([abs(o) for o in offs if o is not None])), 1)
        if any(o is not None for o in offs) else None,
        "durations_s": {"min": round(min(n["dur"] for n in notes), 3), "median": round(float(np.median([n["dur"] for n in notes])), 3),
                        "max": round(max(n["dur"] for n in notes), 3)} if notes else None,
        "plots": plots,
    }
    C.write_json(C.REPORTS / "transcribe.json", rep)

    items = [
        {"kind": "audio", "path": "daw/check_midi_vs_hum.wav", "start": 73, "end": 129,
         "note": "Left: the guide (人声). Right: tones at the transcribed notes. Same tune? Listen especially 1:27–1:57."},
        {"kind": "audio", "path": "daw/check_midi_over_bed.wav", "start": 70, "end": 129,
         "note": "The tones over the bed: do they fit the music like the humming did?"},
    ] + [{"kind": "image", "path": f"plots/{p}"} for p in plots]
    C.review_section("3", "Stage 3: transcription (LISTEN)", items)
    summarise(rep, notes)


def summarise(rep, notes):
    print(f"\n{rep['notes']} notes in {rep['phrases']} phrases, {rep['pitch_range'][0]}–{rep['pitch_range'][1]}; "
          f"first note at {rep['hum_start_refined']} s")
    print(f"durations: {rep['durations_s']}")
    print(f"tempo {rep['tempo_bpm']} BPM (beat-interval spread {rep['beat_steadiness_cv'] * 100:.1f} %), "
          f"written into MIDI: {rep['bpm_in_midi']}")
    print(f"first beats {rep['beats_first8_s']}; the music's beats sit {rep['midi_grid_offset_s']} s after the MIDI grid's")
    print(f"key {rep['key']} (score {rep['key_score']}); runners-up {rep['key_runners_up']}")
    print(f"onsets vs 1/16 grid: median |offset| {rep['grid_offset_ms_median_abs']} ms")
    for k, v in rep["flagged"].items():
        print(f"flag '{k}': {len(v)} notes {v[:40]}{' …' if len(v) > 40 else ''}")
