"""Stage 3d: adopt the user's reviewed notes (FL Studio MIDI) as the notes, on the YouTube clock.

The automatic transcription (Stage 3a) was a first draft; the user corrected it by hand in FL Studio. From here on
that file is the truth. This stage places it on the yt clock, checks the placement against the guide's pitch,
compares it with the draft, and writes the note list Stage 4 reads (out/reports/notes_final.json).
"""
import json

import mido
import numpy as np
import pretty_midi

from . import common as C
from .s1_align import xcorr_coarse, xcorr_fine
from .s3_transcribe import name, plot_notes, tones

PPQ = 960


def place(cfg):
    """Offset (s) that moves the user's MIDI times onto the yt clock, from the anchor the user gave."""
    um = cfg["transcribe"]["user_midi"]
    pm = pretty_midi.PrettyMIDI(str(C.ROOT / um["path"]))
    notes = sorted((n for inst in pm.instruments for n in inst.notes), key=lambda n: n.start)
    anchor = C.mono(C.read_wav(C.RAW / f"{um['anchor_source']}.wav"))
    yt = C.mono(C.read_wav(C.RAW / "yt.wav"))
    c, _, _ = xcorr_coarse(yt, anchor)
    lag, _, peak = xcorr_fine(yt, anchor, c)
    offset = lag / C.SR + (um["first_note_at_s"] - um["anchor_at_s"]) - notes[0].start
    tempi = pm.get_tempo_changes()[1]
    return pm, notes, offset, {"anchor_on_yt_s": round(lag / C.SR, 5), "anchor_corr": round(peak, 3),
                               "offset_s": round(offset, 5), "midi_tempi": [round(float(x), 3) for x in tempi]}


def pitch_fit(notes, t, m, off):
    """Share of sung frames inside each note that sit within ±50 cents of it, and their median deviation (cents)."""
    out, hit, tot = [], 0, 0
    for n in notes:
        k = (t >= n["start"] + off) & (t < n["end"] + off) & ~np.isnan(m)
        dev = (m[k] - n["midi"]) * 100
        ok = np.abs(dev) < 50
        hit, tot = hit + ok.sum(), tot + k.sum()
        out.append((float(ok.mean()) if k.any() else None, float(np.median(dev)) if k.any() else None))
    return out, hit / max(tot, 1)


def compare(final, draft):
    """How the user's notes differ from the automatic draft."""
    def ov(a, b):
        return max(0.0, min(a["end"], b["end"]) - max(a["start"], b["start"]))
    rows, counts = [], {"same": 0, "moved": 0, "pitch changed": 0, "missing in draft": 0, "draft split it": 0}
    for f in final:
        cover = [d for d in draft if ov(f, d) > 0]
        best = max(cover, key=lambda d: ov(f, d)) if cover else None
        if best is None or ov(f, best) < 0.3 * (f["end"] - f["start"]):
            st = "missing in draft"
        elif best["midi"] != f["midi"]:
            st = "pitch changed"
        elif abs(best["start"] - f["start"]) > 0.12:
            st = "moved"
        else:
            st = "same"
        counts[st] += 1
        same_pitch = [d for d in cover if d["midi"] == f["midi"]]
        if len(same_pitch) >= 2:
            counts["draft split it"] += 1
        rows.append({"i": f["i"], "start": f["start"], "name": f["name"], "status": st,
                     "draft": None if best is None else {"i": best["i"], "name": best["name"],
                                                         "start": best["start"], "end": best["end"]}})
    deleted = [d for d in draft if sum(ov(f, d) for f in final) < 0.3 * (d["end"] - d["start"])]
    merged = [d for d in draft if sum(1 for f in final if ov(f, d) > 0.3 * (f["end"] - f["start"])) >= 2]
    same = [r for r in rows if r["status"] == "same"]
    shift = [f["start"] - r["draft"]["start"] for f, r in zip(final, rows) if r["status"] == "same"]
    return {"counts": {**counts, "draft notes deleted": len(deleted), "draft notes that were 2+ notes": len(merged)},
            "onset_shift_same_notes_ms": {"median": round(float(np.median(shift)) * 1000, 1),
                                          "p90_abs": round(float(np.percentile(np.abs(shift), 90)) * 1000, 1)}
            if same else None,
            "deleted": [{"i": d["i"], "start": d["start"], "name": d["name"], "flags": d["flags"]} for d in deleted],
            "merged": [{"i": d["i"], "start": d["start"], "end": d["end"], "name": d["name"]} for d in merged],
            "notes": rows}


def write_midi_video_clock(notes, bpm, lead, path, track_name):
    """MIDI whose t = 0 is the start of the video, with the 1/16 grid on the music's beats.

    The first beat is `lead` seconds long (a tempo event), and 135 BPM from then on, so a DAW's grid lines up
    with the music although the video does not start on a beat.
    """
    def tick(s):
        if s < lead:
            return int(round(s / lead * PPQ))
        return PPQ + int(round((s - lead) * bpm / 60 * PPQ))
    mf = mido.MidiFile(type=1, ticks_per_beat=PPQ)
    t0 = mido.MidiTrack()
    t0.append(mido.MetaMessage("time_signature", numerator=4, denominator=4, time=0))
    t0.append(mido.MetaMessage("set_tempo", tempo=int(round(lead * 1e6)), time=0))
    t0.append(mido.MetaMessage("set_tempo", tempo=mido.bpm2tempo(bpm), time=PPQ))
    mf.tracks.append(t0)
    t1 = mido.MidiTrack()
    t1.append(mido.MetaMessage("track_name", name=track_name, time=0))
    ev = []
    for n in notes:
        ev.append((tick(n["start"]), 1, mido.Message("note_on", note=n["midi"], velocity=n["velocity"])))
        ev.append((tick(n["end"]), 0, mido.Message("note_off", note=n["midi"], velocity=0)))
    now = 0
    for tk, _, msg in sorted(ev, key=lambda e: (e[0], e[1])):
        t1.append(msg.copy(time=tk - now))
        now = tk
    mf.tracks.append(t1)
    mf.save(str(path))


def run(cfg):
    C.ensure_dirs()
    tc = cfg["transcribe"]
    bpm = float(cfg["export"]["tempo"])
    pm, raw, off, rep = place(cfg)
    if any(abs(x - bpm) > 1e-3 for x in rep["midi_tempi"]):
        print(f"warning: the MIDI's tempo {rep['midi_tempi']} differs from export.tempo {bpm}")

    d = np.load(C.WORK / "transcribe_f0.npz")
    t, m, fh, rms_db = d["t"], d["midi_smooth"], d["harvest"], d["rms_db"]
    # the placement must also be where the user's notes fit the guide's pitch best
    offs = np.arange(off - 0.3, off + 0.3, 0.005)
    rawd = [{"start": n.start, "end": n.end, "midi": n.pitch} for n in raw]
    fits = [pitch_fit(rawd, t, m, o)[1] for o in offs]
    best = float(offs[int(np.argmax(fits))])
    rep["pitch_fit_at_offset"] = round(pitch_fit(rawd, t, m, off)[1], 3)
    rep["best_offset_by_pitch_s"] = round(best, 4)
    rep["best_pitch_fit"] = round(max(fits), 3)

    notes, phrase, last = [], 0, None
    per_note, _ = pitch_fit(rawd, t, m, off)
    for i, (n, (fit, dev)) in enumerate(zip(raw, per_note)):
        s, e = n.start + off, n.end + off
        if last is not None and s - last >= tc["phrase_rest_ms"] / 1000:
            phrase += 1
        last = e
        k = (t >= s) & (t < e)
        notes.append({"i": i, "start": round(s, 4), "end": round(e, 4), "dur": round(e - s, 4), "midi": n.pitch,
                      "name": name(n.pitch), "velocity": n.velocity, "phrase": phrase,
                      "loud_db": round(float(np.median(rms_db[k])), 1) if k.any() else None,
                      "fit": None if fit is None else round(fit, 2), "dev_cents": None if dev is None else round(dev),
                      "flags": []})
    for n in notes:   # notes whose sung pitch mostly sits elsewhere: worth a second listen, not necessarily wrong
        if n["fit"] is not None and n["fit"] < 0.4 and abs(n["dev_cents"]) > 50:
            n["flags"].append("pitch mostly elsewhere")
    C.write_json(C.REPORTS / "notes_final.json", notes)

    draft = json.loads((C.REPORTS / "notes.json").read_text())
    cmp_ = compare(notes, draft)
    C.write_json(C.REPORTS / "notes_compare.json", cmp_)

    # DAW and check files on the video clock
    lead = off % (60 / bpm)        # the user's grid lines on the yt clock: off + k·period
    rep["grid_phase_s"] = round(lead, 4)
    write_midi_video_clock(notes, bpm, lead, C.DAW / "notes_final.mid", "melody (user-reviewed)")
    with open(C.DAW / "notes_final.csv", "w") as f:
        f.write("i,start,end,dur,midi,name,phrase,loud_db,fit,dev_cents,flags\n")
        for n in notes:
            f.write(f"{n['i']},{n['start']:.4f},{n['end']:.4f},{n['dur']:.4f},{n['midi']},{n['name']},{n['phrase']},"
                    f"{n['loud_db']},{n['fit']},{n['dev_cents']},{'; '.join(n['flags'])}\n")
    guide = C.read_wav(C.WORK / "stems" / "hum_guide.wav")
    bed = C.read_wav(C.WORK / "stems" / "bed.wav")
    tn = tones(notes, len(guide))
    g = C.mono(guide)
    g = g / (np.abs(g[C.sec(70):C.sec(130)]).max() + 1e-9) * 0.5
    for nm, x in (("check_final_vs_hum.wav", np.stack([g, tn], 1)), ("check_final_over_bed.wav", bed + tn[:, None])):
        C.write_wav(C.WORK / "check" / nm, x)
        C.daw_link(C.WORK / "check" / nm, nm)

    plots = []
    for p0 in range(70, 130, 10):
        path = C.PLOTS / f"final_{p0:03d}.png"
        plot_notes(t, m, fh, rms_db, notes, p0, p0 + 10, path, [74, 87, 102, 117])
        plots.append(path.name)

    rep.update({"notes": len(notes), "phrases": phrase + 1,
                "range": [name(min(n["midi"] for n in notes)), name(max(n["midi"] for n in notes))],
                "first_note_s": notes[0]["start"], "last_end_s": notes[-1]["end"],
                "flagged": [n["i"] for n in notes if n["flags"]], "compare": cmp_["counts"],
                "onset_shift_vs_draft_ms": cmp_["onset_shift_same_notes_ms"]})
    C.write_json(C.REPORTS / "notes_final_report.json", rep)
    C.review_section("3d", "Stage 3d: the user's notes on the YouTube clock", [
        {"kind": "audio", "path": "daw/check_final_vs_hum.wav", "start": 73, "end": 129,
         "note": "Left: the guide. Right: tones at your notes. This is only a check that they landed in the right place."},
        {"kind": "audio", "path": "daw/check_final_over_bed.wav", "start": 70, "end": 129,
         "note": "Your notes as tones over the bed."},
    ] + [{"kind": "image", "path": f"plots/{p}"} for p in plots])
    summarise(rep, cmp_, notes)


def summarise(rep, cmp_, notes):
    print(f"anchor on yt {rep['anchor_on_yt_s']} s (corr {rep['anchor_corr']}); offset {rep['offset_s']:+.4f} s; "
          f"MIDI tempo {rep['midi_tempi']}")
    print(f"pitch fit at that offset {rep['pitch_fit_at_offset'] * 100:.1f} %; best by pitch "
          f"{rep['best_offset_by_pitch_s']:+.4f} s ({rep['best_pitch_fit'] * 100:.1f} %)")
    print(f"{rep['notes']} notes in {rep['phrases']} phrases, {rep['range'][0]}–{rep['range'][1]}, "
          f"{rep['first_note_s']:.3f}–{rep['last_end_s']:.3f} s; grid phase {rep['grid_phase_s']} s")
    print(f"vs the draft: {rep['compare']}; onset shift on unchanged notes {rep['onset_shift_vs_draft_ms']}")
    print(f"flagged for a second listen: {[(n['i'], n['name'], n['start'], n['fit'], n['dev_cents']) for n in notes if n['flags']]}")
