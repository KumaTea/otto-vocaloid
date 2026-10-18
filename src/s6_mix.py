"""Stage 6: the mix. The chosen render (render.default) becomes one Otto bus, which goes over the bed.

  bus        Stage 5's panned stack (lead in the centre, doubles at their pans), high-passed at `highpass_hz`
  reverb     a fixed, light amount of a small room (Freeverb), as glue with the bed. Measured on the original
             humming: where a rest is clean (most hold breaths or narration), its tail falls 25–30 dB within 0.3 s,
             so the reverb is short and light, not a hall.
  level      the bus's loudness (EBU R128, K-weighted: roughly how loud it sounds) over the notes equals the original
             humming's over the same notes, narration excluded, + `level_offset_db`. Measured after the reverb, on
             what is heard.
  no compressor: the bus is already less dynamic than the humming (its median 10 ms peak sits 10 dB below its
             loudest, the humming's 13 dB), so compressing would only flatten it further.
  mix        bed + bus over the whole video. Within the excerpt, a look-ahead limiter catches true peaks above
             `ceiling_dbtp` (none at the default level: the excerpt peaks at −2.6 dBTP). Outside it, the bed is left
             exactly as mastered, its own peaks included (+0.5 dBTP after 2:10).
Outputs: out/final/ (24-bit WAV; the excerpt and the full length from the video's 0:00, with and without the bed),
out/daw/ (float, full length: otto_bus_dry, otto_bus, full_mix), out/reports/mix.json.
"""
import json

import numpy as np
import pyloudnorm as pyln
from pedalboard import HighpassFilter, Pedalboard, Reverb
from scipy import ndimage, signal

from . import common as C


def note_spans(x, notes, hints):
    """x over the notes, end to end, leaving out notes the narration overlaps."""
    return np.concatenate([x[C.sec(n["start"]):C.sec(n["end"])] for n in notes
                           if not any(a < n["end"] and n["start"] < b for a, b in hints)])


def true_peak_db(x):
    """dBTP: the peak of the 4× oversampled signal, i.e. including the peaks between samples a DAC or encoder meets."""
    return 20 * np.log10(max(float(np.abs(signal.resample_poly(x, 4, 1, axis=0)).max()), 1e-12))


def limiter_gain(x, ceiling_db, window_ms=80):
    """Gain curve of a look-ahead true-peak limiter: 1 wherever nothing passes the ceiling.

    Around each too-loud peak the gain eases down over `window_ms` before it and back up over `window_ms` after
    (a moving average of a held minimum), so it never lets the peak through and never clicks. (pedalboard's Limiter
    is JUCE's, which also compresses everything above −10 dBFS at 4:1 and adds make-up gain: not a safety net.)"""
    c = 10 ** (ceiling_db / 20)
    os_ = np.abs(signal.resample_poly(x, 4, 1, axis=0)).max(axis=1)
    peak = os_[:4 * len(x)].reshape(len(x), 4).max(axis=1)
    need = np.minimum(1.0, c / np.maximum(peak, 1e-12))
    w = int(window_ms / 1000 * C.SR)
    return ndimage.uniform_filter1d(ndimage.minimum_filter1d(need, size=2 * w + 1), size=w)


def fx(x, *plugins):
    """Run x (samples, channels) through pedalboard plugins (which take float32, channels first)."""
    return Pedalboard(list(plugins))(x.T.astype(np.float32), C.SR).T.astype(np.float64)


def tag(seg):
    """'1m10-2m08': the excerpt's place in the video, for file names."""
    def mmss(s):
        return f"{int(s // 60)}m{int(round(s % 60)):02d}"
    return f"{mmss(seg['start'])}-{mmss(seg['end'])}"


def excerpt(x, seg, fade_ms):
    y = x[C.sec(seg["start"]):C.sec(seg["end"])].copy()
    f = int(fade_ms / 1000 * C.SR)
    y[:f] *= np.linspace(0, 1, f)[:, None]
    y[-f:] *= np.linspace(1, 0, f)[:, None]
    return y


def run(cfg):
    C.ensure_dirs()
    mc, seg, rv = cfg["mix"], cfg["segment"], cfg["mix"]["reverb"]
    var = cfg["render"]["default"]
    notes = json.loads((C.ROOT / "score.json").read_text())["notes"]
    hints = cfg["transcribe"]["narration_hints"]
    bed = C.read_wav(C.WORK / "stems" / "bed.wav")
    guide = C.read_wav(C.WORK / "stems" / "hum_guide.wav")
    stack = C.read_wav(C.OUT / "variants" / var / "stack.wav")

    dry = fx(stack, HighpassFilter(cutoff_frequency_hz=mc["highpass_hz"]))
    wet = fx(dry, Reverb(room_size=rv["room_size"], damping=rv["damping"], width=rv["width"],
                         wet_level=1.0, dry_level=0.0))
    bus = dry + rv["wet"] * wet

    meter = pyln.Meter(C.SR)
    l_hum = meter.integrated_loudness(note_spans(guide, notes, hints))
    l_bus = meter.integrated_loudness(note_spans(bus, notes, hints))
    gain_db = l_hum - l_bus + mc["level_offset_db"]
    g = 10 ** (gain_db / 20)
    dry, bus = dry * g, bus * g
    # the Stage 5 preview (which the user heard) matched plain RMS over the whole excerpt, narration included
    a, b = C.sec(seg["start"]), C.sec(seg["end"])
    g_prev = np.sqrt(np.mean(guide[a:b] ** 2) / (np.mean(stack[a:b] ** 2) + 1e-12))
    vs_preview = meter.integrated_loudness(note_spans(bus, notes, hints)) - \
        meter.integrated_loudness(note_spans(stack * g_prev, notes, hints))

    mix = bed + bus
    tp_before = true_peak_db(mix[a:b])
    gl = limiter_gain(mix[a:b], mc["ceiling_dbtp"])
    mix[a:b] *= gl[:, None]
    tp_after = true_peak_db(mix[a:b])
    limiter = {"max_gain_reduction_db": round(max(0.0, float(-20 * np.log10(gl.min()))), 2),
               "ms_reduced": int(round((gl < 0.999).sum() / C.SR * 1000))}

    fin, t = C.OUT / "final", tag(seg)
    C.write_wav(fin / f"otto_with_bed_{t}.wav", excerpt(mix, seg, mc["edge_fade_ms"]), subtype="PCM_24")
    C.write_wav(fin / f"otto_vocals_{t}.wav", excerpt(bus, seg, mc["edge_fade_ms"]), subtype="PCM_24")
    C.write_wav(fin / "otto_with_bed_full.wav", mix, subtype="PCM_24")
    C.write_wav(fin / "otto_vocals_full.wav", bus, subtype="PCM_24")
    for name, x in (("otto_bus_dry", dry), ("otto_bus", bus), ("full_mix", mix)):
        C.write_wav(C.WORK / "mix" / f"{name}.wav", x)
        C.daw_link(C.WORK / "mix" / f"{name}.wav", f"{name}.wav")

    ex = excerpt(mix, seg, mc["edge_fade_ms"])
    rep = {"variant": var, "humming_lufs_over_notes": round(l_hum, 2), "bus_gain_db": round(gain_db, 2),
           "vs_stage5_preview_db": round(vs_preview, 2), "reverb": rv, "highpass_hz": mc["highpass_hz"],
           "excerpt_true_peak_dbtp": {"before_limiter": round(tp_before, 2), "final": round(tp_after, 2)},
           "limiter": limiter, "excerpt": {"start": seg["start"], "end": seg["end"], "samples": len(ex),
                                           "lufs": round(meter.integrated_loudness(ex), 2)}}
    C.write_json(C.REPORTS / "mix.json", rep)
    C.review_section("6", "Stage 6: the final mix (LISTEN)", [
        {"kind": "audio", "path": f"final/otto_with_bed_{t}.wav",
         "note": f"The final: 伴奏 + Otto ({var}), light reverb, Otto as loud as the original humming."},
        {"kind": "audio", "path": f"final/otto_vocals_{t}.wav", "note": "The Otto bus alone, exactly as in the mix."},
        {"kind": "audio", "path": f"variants/{var}/preview.wav",
         "note": "For comparison: the Stage 5 preview of the same render (dry, levelled by plain RMS)."},
    ])
    print(f"variant {var}; humming {l_hum:.1f} LUFS over the notes; Otto bus gain {gain_db:+.1f} dB "
          f"({vs_preview:+.1f} dB vs the Stage 5 preview)")
    print(f"excerpt true peak {tp_before:.2f} dBTP → {tp_after:.2f} dBTP; limiter {limiter}; "
          f"excerpt {len(ex)} samples ({len(ex) / C.SR:.3f} s), {rep['excerpt']['lufs']} LUFS")
