"""Stage 4: choose a "ha" for every note of every layer, and write score.json.

Choosing is a small optimisation: every (note, unit) pair gets a cost, the cheapest wins. The cost, per the user's
taste (natural rather than tuned; don't stretch hard; longer laughs for longer notes; the laughs tire as they go):
  shift      |pitch shift| in semitones from the unit's own centre to the note, growing quadratically past
             free_shift_st (large shifts sound tuned, not natural)
  stretch    how far the note's length is beyond what the unit covers comfortably (log2 of the excess)
  exhaustion |unit's exhaustion − the note's place in the song|: fresh laughs early, spent ones late
  repeat     the same unit as this layer's previous note
  reuse      how often the unit has been used already (spreads the work over all units)
  clash      the same unit as another layer on the same note (two copies of one "ha" just make one phasey "ha")
score.json is hand-editable; it is never overwritten without --force.
"""
import json
import random

import librosa
import numpy as np
import pretty_midi

from . import common as C


def load(cfg):
    notes = json.loads((C.REPORTS / "notes_final.json").read_text())
    units = json.loads((C.REPORTS / "units.json").read_text())
    return notes, units


def natural_len(u):
    """Seconds a unit covers from its vowel start to its end: what a note gets without stretching."""
    return u["end"] - u["vowel_start"]


def core_stretch(u, dur, rc):
    """The stretch the renderer applies: only the vowel's middle stretches (the first onset_hold_ms and the last
    release_ms play at 1×), so a short "ha" needs far more than dur / its length."""
    fixed = (rc["onset_hold_ms"] + rc["release_ms"]) / 1000
    core = max(0.01, natural_len(u) - fixed)
    return max(0.001, dur - fixed) / core


def choose_transpose(notes, pool, setting):
    if setting != "auto":
        return int(setting)
    centres = np.array([u["midi"] for u in pool])
    best = None
    for k in (-12, 0, 12):
        cost = np.median([np.min(np.abs(n["midi"] + k - centres)) for n in notes])
        if best is None or cost < best[0]:
            best = (cost, k)
    return best[1]


def cost_terms(n, u, prog, sc, prev_unit, used, taken, k, rc):
    w = sc["weights"]
    shift = n["midi"] + k - u["midi"]
    stretch = core_stretch(u, n["dur"], rc)
    excess = max(0.0, abs(np.log2(stretch)) - np.log2(sc["comfort_stretch"]))
    big = max(0.0, abs(shift) - sc["free_shift_st"])          # large shifts sound tuned, not natural
    return {
        "shift": w["shift"] * (abs(shift) + 0.5 * big ** 2),
        "stretch": w["stretch"] * excess,
        "exhaustion": w["exhaustion"] * abs(u["exhaustion"] - prog),
        "repeat": w["repeat"] * (u["id"] == prev_unit),
        "reuse": w["reuse"] * used.get(u["id"], 0),
        "clash": w["layer_clash"] * (u["id"] in taken),
    }, shift, stretch


def run(cfg, force=False):
    C.ensure_dirs()
    path = C.ROOT / "score.json"
    if path.exists() and not force:
        print(f"{path.name} exists and may hold hand edits: not overwritten (use --force)")
        rep = json.loads(path.read_text())
        summarise(rep, json.loads((C.REPORTS / "units.json").read_text()))
        return
    sc, st = cfg["score"], cfg["stack"]
    notes, units = load(cfg)
    ha = [u for u in units if not u["is_breath"] and u["midi"] is not None]
    breath = next((u for u in units if u["is_breath"] and u["source"] in sc["lead_sources"]), None)
    lead_pool = [u for u in ha if u["source"] in sc["lead_sources"]]
    double_pool = [u for u in ha if u["source"] in sc["double_sources"]]
    k = choose_transpose(notes, lead_pool, sc["transpose"])

    t0, t1 = notes[0]["start"], notes[-1]["end"]
    louds = np.array([n["loud_db"] for n in notes if n["loud_db"] is not None])
    ref_loud = float(np.median(louds))
    rng = random.Random(st["seed"])
    max_layers = max(st["layers_by_phrase"])
    doubles = []                                     # fixed per-layer character for layers 1..max_layers-1
    for j in range(1, max_layers):
        side = -1 if j % 2 else 1
        frac = (j + 1) // 2 / max(1, (max_layers - 1 + 1) // 2)
        doubles.append({"detune_c": round(side * st["detune_cents"] * frac, 1), "pan": round(side * st["pan_spread"] * frac, 2)})

    used = {}
    prev = {}
    out = []
    for n in notes:
        prog = (n["start"] - t0) / (t1 - t0)
        n_layers = st["layers_by_phrase"][n["phrase"]] if n["phrase"] < len(st["layers_by_phrase"]) else 1
        layers, taken = [], set()
        for layer in range(n_layers):
            pool = lead_pool if layer == 0 else double_pool
            best = None
            for u in pool:
                terms, shift, stretch = cost_terms(n, u, prog, sc, prev.get(layer), used, taken, k, cfg["render"])
                c = sum(terms.values())
                if best is None or c < best[0]:
                    best = (c, u, terms, shift, stretch)
            c, u, terms, shift, stretch = best
            entry = {"layer": layer, "unit": u["id"], "shift_st": round(shift, 2), "stretch": round(stretch, 2),
                     "cost": round(c, 2)}
            if layer > 0:
                d = doubles[layer - 1]
                entry.update({"detune_c": d["detune_c"], "pan": d["pan"],
                              "offset_ms": round(rng.uniform(-st["jitter_ms"], st["jitter_ms"]), 1),
                              "gain_db": st["double_gain_db"]})
            layers.append(entry)
            taken.add(u["id"])
            used[u["id"]] = used.get(u["id"], 0) + 1
            prev[layer] = u["id"]
        gain = 0.0 if n["loud_db"] is None else sc["dynamics"] * (n["loud_db"] - ref_loud)
        out.append({"i": n["i"], "start": n["start"], "end": n["end"], "dur": n["dur"], "midi": n["midi"],
                    "name": n["name"], "transpose": k, "phrase": n["phrase"], "progress": round(prog, 3),
                    "gain_db": round(gain, 1), "breath_before": False, "layers": layers})

    # the inhale: on the lead, only after a long note (the user's choice), when a rest follows it. It ends where the
    # next note's "h" starts if the rest is long enough, otherwise it starts right after the long note.
    if breath is not None:
        blen = breath["end"] - breath["start"]
        for a, b in zip(out[:-1], out[1:]):
            rest = b["start"] - a["end"]
            if a["dur"] >= sc["breath_after_note_s"] and rest * 1000 >= sc["breath_min_rest_ms"]:
                lead = next(u for u in units if u["id"] == b["layers"][0]["unit"])
                h = lead["vowel_start"] - lead["start"]
                start = max(a["end"], b["start"] - h - blen)
                b["breath_before"] = {"unit": breath["id"], "start": round(start, 4), "gain_db": sc["breath_gain_db"]}
    rep = {"transpose": k, "lead_sources": sc["lead_sources"], "double_sources": sc["double_sources"],
           "notes": out}
    C.write_json(path, rep)
    write_midi(out, units, cfg)
    plot(out, units)
    C.review_section("4", "Stage 4: the score (which 'ha' sings which note)", [
        {"kind": "image", "path": "plots/score.png",
         "note": "Lead in solid colours, extra layers faint, ▼ = inhale. Bottom: layers, and how tired each lead 'ha' is."},
    ])
    summarise(rep, units)


def write_midi(out, units, cfg):
    """score.mid: one track per layer, the notes at the pitch Otto sings (after transpose)."""
    pm = pretty_midi.PrettyMIDI(initial_tempo=float(cfg["export"]["tempo"]), resolution=960)
    n_layers = max(len(n["layers"]) for n in out)
    for layer in range(n_layers):
        inst = pretty_midi.Instrument(program=52, name=f"otto layer {layer}" + (" (lead)" if layer == 0 else ""))
        for n in out:
            if layer < len(n["layers"]):
                inst.notes.append(pretty_midi.Note(velocity=100, pitch=n["midi"] + n["transpose"],
                                                   start=n["start"], end=n["end"]))
        pm.instruments.append(inst)
    pm.write(str(C.DAW / "score.mid"))


def plot(out, units):
    plt = C.plt()
    ids = sorted({l["unit"] for n in out for l in n["layers"]})
    cmap = plt.get_cmap("tab20")
    col = {u: cmap(i % 20) for i, u in enumerate(ids)}
    fig, ax = plt.subplots(2, 1, figsize=(18, 9), sharex=True, gridspec_kw={"height_ratios": [3, 1]})
    for n in out:
        for l in n["layers"]:
            y = n["midi"] + n["transpose"] + 0.25 * l["layer"]
            ax[0].add_patch(plt.Rectangle((n["start"], y - 0.12), n["dur"], 0.24, color=col[l["unit"]],
                                          alpha=1.0 if l["layer"] == 0 else 0.45, lw=0))
            if l["layer"] == 0:
                ax[0].text(n["start"], y + 0.3, l["unit"].replace("otto2_", "b").replace("otto_", "a"), fontsize=6)
        if n["breath_before"]:
            ax[0].plot(n["breath_before"]["start"], n["midi"] + n["transpose"], "v", color="k", ms=5)
    lo = min(n["midi"] + n["transpose"] for n in out) - 2
    hi = max(n["midi"] + n["transpose"] for n in out) + 3
    ax[0].set_ylim(lo, hi)
    ax[0].set_yticks(range(lo, hi + 1))
    ax[0].set_yticklabels([librosa.midi_to_note(v) for v in range(lo, hi + 1)], fontsize=7)
    ax[0].set_title("score: lead layer solid (labels: aNN = stream laugh otto_NN, bNN = otto2_NN), doubles faint, "
                    "▼ = inhale")
    ax[1].step([n["start"] for n in out], [len(n["layers"]) for n in out], where="post", label="layers")
    ex = {u["id"]: u["exhaustion"] for u in units}
    ax[1].plot([n["start"] for n in out], [1 + 3 * ex[n["layers"][0]["unit"]] for n in out], ".", color="C3",
               label="lead unit's exhaustion (scaled 1–4)")
    ax[1].legend(loc="upper left")
    ax[1].set_xlabel("time on the YouTube clock (s)")
    fig.tight_layout()
    fig.savefig(C.PLOTS / "score.png")
    plt.close(fig)


def summarise(rep, units):
    out = rep["notes"]
    um = {u["id"]: u for u in units}
    print(f"transpose {rep['transpose']:+d}; {len(out)} notes; layers per note: "
          f"{dict(sorted({k: sum(1 for n in out if len(n['layers']) == k) for k in range(1, 6)}.items()))}")
    lead = [n["layers"][0] for n in out]
    shifts = np.array([abs(l["shift_st"]) for l in lead])
    stretches = np.array([l["stretch"] for l in lead])
    print(f"lead: |shift| median {np.median(shifts):.1f} st, max {shifts.max():.1f}; "
          f"stretch median {np.median(stretches):.2f}×, max {stretches.max():.2f}× "
          f"({sum(stretches > 3)} notes above 3×)")
    allv = [l for n in out for l in n["layers"]]
    usage = {}
    for l in allv:
        usage[l["unit"]] = usage.get(l["unit"], 0) + 1
    print("unit usage (all layers): " + ", ".join(f"{k}×{v}" for k, v in sorted(usage.items())))
    print(f"inhales before notes: {[n['i'] for n in out if n['breath_before']]}")
    worst = sorted(out, key=lambda n: -n["layers"][0]["stretch"])[:5]
    print("longest stretches (lead): " + "; ".join(
        f"note {n['i']} {n['name']} {n['dur']:.2f}s ← {n['layers'][0]['unit']} ({um[n['layers'][0]['unit']]['end'] - um[n['layers'][0]['unit']]['vowel_start']:.2f}s) "
        f"{n['layers'][0]['stretch']}×" for n in worst))
