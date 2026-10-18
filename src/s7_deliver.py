"""Stage 7: verify and deliver.

  verify     every deliverable has the length it must have: the excerpt exactly segment.end − segment.start, every
             full-length file as long as the video's audio, every WAV at 48 kHz.
  FL set     out/fl/: the material for FL Studio, on the clock of the user's own FL project (the one user/tuned.mid
             comes from): 135 BPM from bar 1 with the music's beats on the grid. That clock runs `fl_shift` s ahead
             of the video's (the video's 0:00 is at 0.538 s in FL), so every file here starts with that much
             silence: dropped at bar 1, everything lines up with tuned.mid and with each other.
  manifest   out/README.txt: what every file is.
  from-fl    (build.py from-fl --file x.wav) brings an FL export back onto the video's clock and cuts the excerpt.
"""
import json
from pathlib import Path

import mido
import numpy as np
import soundfile as sf

from . import common as C
from .s1_align import xcorr_coarse, xcorr_fine
from .s6_mix import excerpt, tag

FL = C.OUT / "fl"
FL_END_S = 130.0          # the FL set covers the video up to 2:10 (the excerpt ends at 2:08)
PPQ = 96                  # as FL Studio writes it
TEMPO_US = 444444         # 135 BPM as FL Studio writes it (µs per beat)

DESCRIBE = {
    # out/final
    "otto_with_bed_": "THE RESULT: 伴奏 + Otto, the excerpt only. Starts at the video's {start}.",
    "otto_vocals_": "Otto alone (reverb included), the excerpt only: exactly what is in the mix. Over the 伴奏 at 0 dB "
                    "it gives the mix.",
    "otto_with_bed_full.wav": "伴奏 + Otto over the whole video, from its 0:00 (cut wherever you like).",
    "otto_vocals_full.wav": "Otto alone over the whole video, from its 0:00.",
    # out/daw
    "bed.wav": "伴奏 (music + effects, no humming, no narration), aligned to the video.",
    "hum_guide.wav": "人声 (the original humming + breaths + narration), aligned to the video.",
    "yt_original.wav": "The video's own audio (YouTube BEKGuF5tY9E).",
    "check_final_vs_hum.wav": "Check: the original humming (left) against tones at your notes (right).",
    "check_final_over_bed.wav": "Check: tones at your notes over the 伴奏.",
    "check_midi_vs_hum.wav": "Old check of the automatic draft (superseded by your notes).",
    "check_midi_over_bed.wav": "Old check of the automatic draft (superseded by your notes).",
    "notes.mid": "The automatic draft transcription (superseded by user/tuned.mid).",
    "notes.csv": "The automatic draft transcription, as a table.",
    "notes_final.mid": "Your notes (user/tuned.mid) on the video's clock (a lead-in tempo puts the grid on the beats).",
    "notes_final.csv": "Your notes on the video's clock, as a table (times in seconds).",
    "score.mid": "The score: one track per Otto layer, on the video's clock.",
    "otto_stack_dry.wav": "The four layers panned together, dry, as rendered (before level and reverb).",
    "otto_bus_dry.wav": "The Otto bus at mix level, high-passed, no reverb.",
    "otto_bus.wav": "The Otto bus as mixed (= out/final/otto_vocals_full.wav, in float).",
    "full_mix.wav": "伴奏 + Otto (= out/final/otto_with_bed_full.wav, in float).",
    # out/fl
    "original_humming.wav": "人声: the original humming (+ breaths + narration), for comparing by ear.",
    "otto_vocals.wav": "My Otto bus as mixed (reverb included): a reference to A/B your own mix against.",
    "otto_with_bed.wav": "My final mix: a reference.",
    "otto_score.mid": "The score: one track per Otto layer, notes on the 135 BPM grid (the same notes as tuned.mid).",
    "units/": "Every cut unit, one file each, as cut from the laughs: the \"ha\"s and the inhale (otto_06). "
              "units.csv lists each one's pitch, length, \"h\" length (preutterance) and tiredness.",
}


def describe(name, seg):
    if name in DESCRIBE:
        return DESCRIBE[name].format(start=C.fmt_time(seg["start"]))
    m = Path(name).stem
    if m.startswith("otto_L") and m.endswith("_raw"):
        k = m[6:-4]
        return (f"Layer {k}: each \"ha\" placed on its note, its vowel on the note start, NOT stretched or tuned "
                "(material for Newtone / by hand).")
    if m.startswith("otto_L"):
        return f"Layer {m[6:]}" + (" (the lead)" if m[6:] == "0" else "") + ": rendered (tuned, stretched), dry, mono."
    for k, v in DESCRIBE.items():
        if k.endswith("_") and name.startswith(k):
            return v.format(start=C.fmt_time(seg["start"]))
    return ""


def fl_shift():
    """Seconds the FL clock runs ahead of the video's: the user's MIDI time = video time + this."""
    return -json.loads((C.REPORTS / "notes_final_report.json").read_text())["offset_s"]


def to_fl(x, shift_n, length):
    out = np.zeros((length, x.shape[1]))
    n = min(length - shift_n, len(x))
    out[shift_n:shift_n + n] = x[:n]
    return out


def bar_beat(t_fl):
    beats = round(t_fl * 1e6 / TEMPO_US * PPQ) / PPQ          # on the MIDI's tick grid
    return f"bar {int(beats // 4) + 1}, beat {beats % 4 + 1:.2f}"


def write_fl_midi(score, shift, path, seg):
    def tick(t):
        return int(round((t + shift) * 1e6 / TEMPO_US * PPQ))
    mf = mido.MidiFile(type=1, ticks_per_beat=PPQ)
    t0 = mido.MidiTrack()
    t0.append(mido.MetaMessage("time_signature", numerator=4, denominator=4, time=0))
    t0.append(mido.MetaMessage("set_tempo", tempo=TEMPO_US, time=0))
    now = 0
    for t, text in ((0.0, "video 0:00"), (seg["start"], f"excerpt start {C.fmt_time(seg['start'])}"),
                    (seg["end"], f"excerpt end {C.fmt_time(seg['end'])}")):
        t0.append(mido.MetaMessage("marker", text=text, time=tick(t) - now))
        now = tick(t)
    mf.tracks.append(t0)
    n_layers = max(len(n["layers"]) for n in score["notes"])
    for k in range(n_layers):
        lay = next(l for n in score["notes"] for l in n["layers"] if l["layer"] == k)
        name = "Otto lead (centre)" if k == 0 else \
            f"Otto double {k} (pan {lay['pan'] * 100:+.0f} %, {lay['detune_c']:+.0f} cents, {lay['gain_db']:+.0f} dB)"
        tr = mido.MidiTrack()
        tr.append(mido.MetaMessage("track_name", name=name, time=0))
        ev = []
        for n in score["notes"]:
            if k < len(n["layers"]):
                p = n["midi"] + n["transpose"]
                ev += [(tick(n["start"]), 1, mido.Message("note_on", note=p, velocity=100)),
                       (tick(n["end"]), 0, mido.Message("note_off", note=p, velocity=0))]
        now = 0
        for tk, _, msg in sorted(ev, key=lambda e: (e[0], e[1])):
            tr.append(msg.copy(time=tk - now))
            now = tk
        mf.tracks.append(tr)
    mf.save(str(path))


def build_fl(cfg):
    seg, var = cfg["segment"], cfg["render"]["default"]
    mix = json.loads((C.REPORTS / "mix.json").read_text())
    g = 10 ** (mix["bus_gain_db"] / 20)
    shift = fl_shift()
    sn = C.sec(shift)
    length = C.sec(FL_END_S) + sn
    vdir = C.OUT / "variants" / var
    n_layers = len(list(vdir.glob("layer_*.wav")))
    files = {"bed.wav": (C.WORK / "stems" / "bed.wav", 1.0),
             "original_humming.wav": (C.WORK / "stems" / "hum_guide.wav", 1.0)}
    for k in range(n_layers):
        files[f"otto_L{k}.wav"] = (vdir / f"layer_{k}.wav", g)            # at mix level: faders at 0 dB ≈ my mix
        files[f"otto_L{k}_raw.wav"] = (C.WORK / "raw" / f"otto_L{k}_raw.wav", g)
    files["otto_vocals.wav"] = (C.WORK / "mix" / "otto_bus.wav", 1.0)
    files["otto_with_bed.wav"] = (C.WORK / "mix" / "full_mix.wav", 1.0)
    for name, (src, gain) in files.items():
        C.write_wav(FL / name, to_fl(C.read_wav(src) * gain, sn, length))
    score = json.loads((C.ROOT / "score.json").read_text())
    write_fl_midi(score, shift, FL / "otto_score.mid", seg)
    for p in sorted((C.DAW / "units").iterdir()):
        C.link(p, FL / "units" / p.name)
    return {"shift_s": round(shift, 5), "shift_samples": sn, "length_s": round(length / C.SR, 3),
            "excerpt_in_fl_s": [round(seg["start"] + shift, 3), round(seg["end"] + shift, 3)],
            "excerpt_in_fl": [bar_beat(seg["start"] + shift), bar_beat(seg["end"] + shift)],
            "first_note_in_fl": bar_beat(score["notes"][0]["start"] + shift)}


def note_ticks(path):
    """(start tick, pitch) of every note in a MIDI file, scaled to PPQ."""
    mf = mido.MidiFile(path)
    out = []
    for tr in mf.tracks:
        now = 0
        for m in tr:
            now += m.time
            if m.type == "note_on" and m.velocity > 0:
                out.append((round(now * PPQ / mf.ticks_per_beat), m.note))
    return sorted(out)


def verify(cfg, fl):
    """Assert the lengths, rates and alignment every deliverable promises."""
    seg = cfg["segment"]
    n_video = sf.info(C.DAW / "yt_original.wav").frames
    n_ex = C.sec(seg["end"]) - C.sec(seg["start"])
    problems, checked = [], 0
    for p in sorted((C.OUT / "final").glob("*.wav")):
        i = sf.info(p)
        want = n_ex if p.name.startswith(("otto_with_bed_", "otto_vocals_")) and "_full" not in p.name else n_video
        checked += 1
        if i.samplerate != C.SR or i.frames != want:
            problems.append(f"final/{p.name}: {i.frames} samples at {i.samplerate} Hz, expected {want} at {C.SR}")
    for d, want in ((C.DAW, n_video), (FL, C.sec(FL_END_S) + fl["shift_samples"])):
        for p in sorted(d.glob("*.wav")):
            i = sf.info(p)
            checked += 1
            if i.samplerate != C.SR or i.frames != want:
                problems.append(f"{d.name}/{p.name}: {i.frames} samples at {i.samplerate} Hz, expected {want}")
    # the FL score's lead must be the user's own notes, tick for tick
    tuned = note_ticks(C.ROOT / cfg["transcribe"]["user_midi"]["path"])
    mf = mido.MidiFile(FL / "otto_score.mid")
    lead = []
    now = 0
    for m in mf.tracks[1]:
        now += m.time
        if m.type == "note_on" and m.velocity > 0:
            lead.append((now, m.note))
    off = [a[0] - b[0] for a, b in zip(lead, tuned)]
    if len(lead) != len(tuned) or any(a[1] != b[1] for a, b in zip(lead, tuned)) or any(off):
        problems.append(f"otto_score.mid's lead differs from tuned.mid: {len(lead)} vs {len(tuned)} notes, "
                        f"tick offsets {sorted(set(off))[:5]}")
    if problems:
        raise SystemExit("verify failed:\n  " + "\n  ".join(problems))
    return {"files_checked": checked, "video_samples": n_video, "excerpt_samples": n_ex,
            "fl_lead_matches_tuned_mid": True}


def manifest(cfg, fl, mix):
    seg = cfg["segment"]
    lines = [
        "coronal-otto: output files",
        "=" * 26,
        "",
        "All WAVs are 48 kHz. Times are on the clock of the YouTube video (BEKGuF5tY9E) unless said otherwise.",
        f"The render is '{mix['variant']}'; Otto is as loud as the original humming over the notes "
        f"(bus gain {mix['bus_gain_db']:+.1f} dB); light reverb (wet {mix['reverb']['wet']}).",
        "Walkthrough for FL Studio: FL_GUIDE.md in the project folder.",
        "",
    ]
    sections = [
        ("final/", "for the video: 24-bit PCM", C.OUT / "final"),
        ("daw/", "every step, full length, 32-bit float; t = 0 is the video's 0:00 (drop at 0:00 in any DAW or "
                 "video editor)", C.DAW),
        ("fl/", f"for FL Studio: 32-bit float, 0:00–{C.fmt_time(fl['length_s'])} on the FL clock. Drop every file at "
                f"bar 1 of a 135 BPM project. The FL clock runs {fl['shift_s']:.5f} s ({fl['shift_samples']} samples) "
                f"ahead of the video: the video's 0:00 is at {fl['shift_s']:.3f} s in FL, the excerpt is "
                f"{fl['excerpt_in_fl'][0]} to {fl['excerpt_in_fl'][1]}. To bring an FL export back onto the video's "
                "clock: uv run build.py from-fl --file <export.wav>", FL),
    ]
    for title, note, d in sections:
        lines += [f"{title}  ({note})", ""]
        for p in sorted(d.iterdir()):
            if p.is_dir():
                name, extra = p.name + "/", ""
            else:
                name = p.name
                if p.suffix == ".wav":
                    i = sf.info(p)
                    extra = f"  [{'mono' if i.channels == 1 else 'stereo'}, {i.frames / C.SR:.3f} s]"
                else:
                    extra = ""
            lines.append(f"  {name}{extra}")
            text = describe(name, seg)
            if text:
                lines.append(f"      {text}")
        lines.append("")
    (C.OUT / "README.txt").write_text("\n".join(lines))


def run(cfg):
    C.ensure_dirs()
    fl = build_fl(cfg)
    rep = {"fl": fl, "verify": verify(cfg, fl)}
    mix = json.loads((C.REPORTS / "mix.json").read_text())
    manifest(cfg, fl, mix)
    C.write_json(C.REPORTS / "deliver.json", rep)
    print(f"verified {rep['verify']['files_checked']} WAVs; FL set: shift {fl['shift_s']} s, excerpt in FL "
          f"{fl['excerpt_in_fl'][0]} → {fl['excerpt_in_fl'][1]}, first note at {fl['first_note_in_fl']}; "
          f"otto_score.mid's lead = tuned.mid, tick for tick")
    print(f"manifest: {C.OUT / 'README.txt'}")


def from_fl(cfg, path):
    """An FL Studio export (any length, rate or format) → the video's clock: full length and the excerpt.

    Where the export sits on the FL clock is measured, not assumed: it is matched against the 伴奏 (or, if the
    export has no 伴奏, against my Otto bus). Only if neither is found is it assumed to start at bar 1."""
    seg = cfg["segment"]
    path = Path(path).resolve()
    tmp = C.WORK / "from_fl" / f"{path.stem}.wav"
    tmp.parent.mkdir(parents=True, exist_ok=True)
    C.decode(path, tmp)
    x = C.read_wav(tmp)
    if x.shape[1] == 1:
        x = np.repeat(x, 2, axis=1)
    sn = C.sec(fl_shift())
    lag, how = 0.0, "assumed: starts at bar 1 (neither the 伴奏 nor my Otto bus was found in it)"
    for ref in ("bed.wav", "otto_vocals.wav"):
        r = C.mono(C.read_wav(FL / ref))
        coarse, _, _ = xcorr_coarse(C.mono(x), r)
        fine, _, peak = xcorr_fine(C.mono(x), r, coarse, span=(C.sec(60), C.sec(FL_END_S)))
        if peak > 0.3:
            lag, how = fine, f"measured against fl/{ref} (correlation {peak:.2f})"
            break
    # export sample i = FL sample i − lag = video sample i − lag − sn
    n_video = sf.info(C.DAW / "yt_original.wav").frames
    video = C.place(x, -(lag + sn), n_video)
    out = C.OUT / "from_fl"
    full, ex = out / f"{path.stem}_video_full.wav", out / f"{path.stem}_{tag(seg)}.wav"
    C.write_wav(full, video, subtype="PCM_24")
    C.write_wav(ex, excerpt(video, seg, cfg["mix"]["edge_fade_ms"]), subtype="PCM_24")
    print(f"{path.name}: starts at {-lag / C.SR:.4f} s on the FL clock, {bar_beat(-lag / C.SR)} ({how})")
    print(f"  {full.relative_to(C.ROOT)}  (from the video's 0:00)\n  {ex.relative_to(C.ROOT)}  (the excerpt)")
