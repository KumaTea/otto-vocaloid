# coronal-otto — a 人力 test: Otto's laughter hums 「日冕」

## Goal

Replace the male humming in the Phainon PV 「日冕」 (YouTube `BEKGuF5tY9E`, Chinese version), from 1:14 to 2:08, with 电棍 (Otto)'s laughter:

- one "ha" per note;
- each "ha" stretched to the note's length;
- hard-tuned to the melody.

The deliverable is an audio track aligned to that YouTube video, which the user lays onto the original video. Audio only.

This is a test of the method, not a full production. Keep it small, inspectable, and re-runnable.

---

## Working agreement (Claude Code: read this first)

1. **Teach as you go.** The user wants to understand the method, not just receive output.
   - Before each stage, explain its core idea in 2–3 sentences with a concrete example.
   - After each stage, show the evidence: numbers in `out/reports/`, and plots in `out/plots/`. You can read the PNGs yourself.
2. **You cannot hear.** Every stage must produce a measurable check or a plot. Steps marked **LISTEN (user)** are the user's ears: stop there and wait for their verdict before continuing.
3. **Everything is driven by files.**
   - Settings live in `config.yaml`. Note-by-note decisions live in `score.json`.
   - No hand-edited audio. `python build.py <stage>` must reproduce the outputs.
   - `score.json` is hand-editable. Never regenerate it over the user's edits unless asked (`--force`).
4. **Never ask for the user's password.** Downloads authenticate with browser cookies (Stage 0).
5. **Keep copyrighted audio and cookies out of git.** Add `data/`, `out/`, `cookies.txt` to `.gitignore`.
6. **Learning mode (optional).** At the start of Stage 5, ask whether the user wants to write the core render function themselves. If yes, provide a skeleton, docstrings and tests; review their code instead of writing it.
7. In Stage 0, create a short `CLAUDE.md` that says: "Read PLAN.md; follow the working agreement; current stage is N." Keep the stage number current.

---

## Master clock

All times in `config.yaml` and `score.json` are **seconds on the YouTube `BEKGuF5tY9E` timeline**.

The Bilibili stems have the opening logo trimmed, so each source gets an offset measured in Stage 1. Never hard-code an offset.

## Sources

| id | content | URL |
|---|---|---|
| `yt` | official PV, zh: music + humming + narration | https://www.youtube.com/watch?v=BEKGuF5tY9E |
| `p1` | music + male humming | https://www.bilibili.com/video/BV1QYgfzcEpF?p=1 |
| `p2` | music, no humming | https://www.bilibili.com/video/BV1QYgfzcEpF?p=2 |
| `p3` | humming + narration, no music | https://www.bilibili.com/video/BV1QYgfzcEpF?p=3 |
| `otto` | laugh clip at 2:00–2:06 of part 1 (the 6:46 cut) | https://www.bilibili.com/video/BV1Zs411g7Kg?p=1 |

User-supplied landmarks on the `yt` clock. These are approximate; Stage 3 refines the humming boundaries.

| time | event |
|---|---|
| 1:10 | segment start (splice in) |
| 1:14 | humming starts |
| 1:27 | reverb on the humming starts growing |
| 1:42 | reverb at its maximum |
| 1:57 | humming back to dry |
| 2:08 | segment end (splice out) |

The Otto clip contains, in order:

- laugh 1: 6 "ha"
- one inhale
- laugh 2: 4 "ha"
- laugh 3: 3 "ha"

That gives **13 "ha" units + 1 breath**. The laughs are loud, mostly voiced chest voice, and dominate any background noise.

## Decisions already made

- **One note = one "ha".** The vowel is stretched or compressed to the note length. No laugh trains.
- **Pitch is hard-snapped** to note centres.
- **The single inhale** goes before phrases that follow a long rest. It is not pitched.
- **Reverb on the laugh vocal** follows the original humming's reverb arc.
- **Otto clip denoise** is off by default. A config flag enables a separation model.
- **Narration:** if any exists inside the segment, keep it.
- **Output:** audio only.

---

## Repo layout

```
coronal-otto/
├─ PLAN.md
├─ CLAUDE.md            # created in Stage 0
├─ config.yaml
├─ build.py             # python build.py <fetch|align|units|transcribe|score|render|mix|verify|all>
├─ requirements.txt
├─ src/
│  ├─ common.py         # audio IO, time conversion, plotting helpers
│  ├─ s0_fetch.py
│  ├─ s1_align.py
│  ├─ s2_units.py
│  ├─ s3_transcribe.py
│  ├─ s4_score.py
│  ├─ s5_render.py
│  ├─ s6_mix.py
│  └─ s7_verify.py
├─ data/raw/  data/work/   # gitignored
└─ out/                    # gitignored: wavs, reports/, plots/, variants/
```

## Initial `config.yaml`

```yaml
timeline: "youtube:BEKGuF5tY9E"   # all times are seconds on this video's clock

segment:
  start: 70.0        # 1:10 splice in
  hum_start: 74.0    # 1:14 (refined in Stage 3)
  end: 128.0         # 2:08 splice out
  xfade_ms: 100

sources:
  yt:   {url: "https://www.youtube.com/watch?v=BEKGuF5tY9E"}
  p1:   {url: "https://www.bilibili.com/video/BV1QYgfzcEpF?p=1"}
  p2:   {url: "https://www.bilibili.com/video/BV1QYgfzcEpF?p=2"}
  p3:   {url: "https://www.bilibili.com/video/BV1QYgfzcEpF?p=3"}
  otto: {url: "https://www.bilibili.com/video/BV1Zs411g7Kg?p=1", clip: [118.0, 128.0]}  # 2:00–2:06 plus margin

cookies: {browser: firefox}   # or {file: cookies.txt}

units:
  expect_groups: [6, 1, 4, 3]   # laugh1, inhale, laugh2, laugh3
  denoise: false

transcribe:
  fmin: 60
  fmax: 600
  min_note_ms: 60
  phrase_rest_ms: 400

score:
  transpose: auto              # or -12 / 0 / 12
  weights: {shift: 1.0, repeat: 2.0, intensity: 0.5}
  breath_min_rest_ms: 400
  breath_gain_db: -6

render:
  frame_ms: 5
  release_ms: 40
  sustain_normalize: true
  vibrato_cents: 0
  vibrato_hz: 5.5
  borrow_guide_contour: 0.0    # beta; 0 = perfectly flat
  variants:
    - {name: flat}
    - {name: vib20, vibrato_cents: 20}

mix:
  level_offset_db: 0
  reverb: {room_size: 0.85, damping: 0.4, width: 1.0, max_wet: 0.6}
  reverb_keys: [[87, 0.0], [102, 1.0], [117, 0.0]]   # 1:27, 1:42, 1:57
  reverb_curve: cosine
```

---

## Stage 0 — fetch (`s0_fetch.py`)

**Idea:** get every source into one uniform format once, so no later stage has to think about codecs.

1. Download audio only, in the native codec, with **yt-dlp**.
   - Use `-f bestaudio` and do not transcode to MP3, since each lossy transcode adds damage.
   - Bilibili parts are addressed with `?p=N`.
2. Cut the Otto clip with ffmpeg at the configured `clip` window (2:00–2:06 with a 2 s margin).
3. Authenticate with cookies only:
   - use `--cookies-from-browser firefox`, or `--cookies cookies.txt` exported by the user;
   - reading Chrome's cookies on Windows has been unreliable because of Chrome's cookie encryption, so prefer Firefox or a cookies.txt export;
   - keep yt-dlp up to date. If YouTube extraction fails, follow yt-dlp's error message, which may ask for a JavaScript runtime such as Deno.
4. Decode everything to **48 kHz float32 WAV**, keeping stereo, in `data/raw/`.
5. Write `out/reports/sources.json` with codec, bitrate and duration per source (from ffprobe).

**Check:**
- `p1`, `p2` and `p3` should have near-equal durations (~3:18–3:19).
- `yt` should be ~3:22.
- All sources at 48 kHz.

## Stage 1 — align and derive stems (`s1_align.py`)

**Idea: cross-correlation.** Slide one recording against another and find the lag at which they match best.

- *Example:* if `p2` peaks best when shifted 4.213 s later, the trimmed logo was 4.213 s long.
- Audio alignment is exact to 1/48000 s. Video frame matching is only exact to about 33 ms at 30 fps, and two copies of the same music 33 ms apart produce an audible flam during a crossfade.
- Frame comparison is fine as a sanity check, but alignment uses audio.

**Idea: least-squares gain.** If y ≈ g·x, the best g is Σxy / Σx².

1. **Offsets.**
   - Find a coarse lag on mono mixdowns at 8 kHz using `scipy.signal.correlate(..., method="fft")`.
   - Refine at 48 kHz within ±50 ms.
   - Align `p1` to `yt`. Then align `p2` to `p1` (shared music) and `p3` to `p1` (shared humming).
   - The three stems probably share one trim; report and verify that.
2. **Guide humming.**
   - Fit the gain in a humming-free region (`yt` 70–73.5 s).
   - Compute `hum = p1 − g·p2`.
   - Report the residual in that humming-free region, in dB relative to `p1`.
   - The guide is never heard in the final mix; it only has to be trackable. Faint music residue is fine.
3. **Narration.**
   - Compute `narr = p3 − g'·hum`.
   - Report whether narration has energy inside 70–128 s, and where.
4. **Bed vs `yt`.**
   - Fit `g_yt` so that `g_yt·(p2 + hum + narr) ≈ yt` over the segment.
   - Report the residual. This is what makes the splice seamless.
5. **Plots:** the correlation peaks, and waveform overlays (`yt` vs rebuilt) for ±1 s around 70 s and 128 s.

**Fallbacks:**
- If the residual is high, try sub-sample alignment (upsample 4× around the correlation peak).
- If it is still poor, run a vocal-separation model on `p1` to get the guide.

**LISTEN (user):** `data/work/hum.wav` and `data/work/narr.wav`.

## Stage 2 — slice the laughs (`s2_units.py`)

**Idea:** a laugh is bursts separated by near-silence, so a loudness envelope with a threshold cuts it into units.

1. Compute an RMS envelope with a 10 ms hop.
   - Threshold it relative to the clip's peak.
   - Merge gaps shorter than 30 ms. Drop blobs shorter than 40 ms.
2. Expect **exactly 14 units**, falling into time groups of 6 / 1 / 4 / 3.
   - Search the threshold within a range until the count matches.
   - If no threshold works, fail loudly with a plot. Never guess.
3. For each unit, record in `units.json`:
   - `start` and `end`
   - `vowel_start`: the first voiced frame from `pyworld.harvest`. The unvoiced "h" before it is the unit's **pre-utterance**.
   - `vowel_end`
   - median f0, as a fractional MIDI number
   - voiced ratio
   - peak RMS
   - spectral centroid (a proxy for strain or intensity)
   - `is_breath`: voiced ratio < 0.2. This should be exactly the 7th unit.
4. Write `data/work/units/u00.wav … u13.wav`, plus a contact-sheet PNG showing each unit's waveform and f0.
5. If `units.denoise` is true, run `audio-separator` with a vocal model on the clip before slicing.

**LISTEN (user):** the 14 unit files, individually.

## Stage 3 — transcribe the guide (`s3_transcribe.py`)

**Idea:** a pitch tracker gives a continuous pitch curve. Notes are the stretches where that curve sits near one semitone.

1. Track the f0 of `hum` over 72–130 s.
   - Primary tracker: `librosa.pyin`, with `fmin`/`fmax` from config and a 5 ms hop.
   - Cross-check with `pyworld.harvest`. Flag any region where the two disagree by more than 50 cents.
2. Segment into notes.
   - A note needs voiced frames, confident pitch, and energy above a threshold.
   - Quantise f0 to the nearest semitone using the median over each stable region.
   - Split where the quantised pitch changes and holds for at least `min_note_ms`.
   - Also split at onset-strength peaks, so repeated notes of the same pitch are separated.
   - Merge blips shorter than `min_note_ms` into a neighbour.
3. **Known hazard, 1:27–1:57: the humming is reverberant.**
   - Each note's tail bleeds into the next, so notes look too long and tails can create ghost notes.
   - Decide note starts from onset strength.
   - End a note at the next onset or where the direct sound drops, not where the reverb tail dies.
   - Expect the user to hand-fix this section.
4. **Phrases** are separated by rests of at least `phrase_rest_ms`.
5. **Outputs:**
   - `notes.mid` via pretty_midi;
   - `notes.json` with start, end, midi, guide RMS and phrase index per note;
   - per-10 s plots of the guide f0 (in cents) with note bars drawn over it.
6. **Check renders:**
   - `check_midi_over_bed.wav`: simple sine tones of the MIDI mixed over `p2`.
   - `check_midi_vs_hum.wav`: the humming in the left channel, the sines in the right channel.

**LISTEN (user):**
- Do the sines play the same tune as the humming?
- If not, the user corrects the MIDI in any piano-roll editor and saves it as `notes_edited.mid`. Stage 4 prefers that file when it exists.

## Stage 4 — build the score (`s4_score.py`)

**Idea:** choosing a "ha" for each note is a small optimisation. Give every (note, unit) pair a cost and pick the cheapest.

1. **Transpose.**
   - Choose k ∈ {−12, 0, +12} to minimise the mean |note + k − unit pitch centre|.
   - Shifting a voice by more than about 7 semitones tends to sound buzzy, and an octave move keeps the tune and its harmony intact.
   - Record the chosen k. Config can override it.
2. **Assignment.** For each note, pick the "ha" unit with the lowest cost:
   ```
   cost = w_shift     · |pitch shift in semitones|
        + w_repeat    · [same unit as the previous note]
        + w_intensity · |intensity rank of unit − loudness rank of note|
   ```
   - The intensity term carries the emotional build-up. The most strained "ha"s land on the loudest guide notes, which are the climax.
   - This answers the problem that all the "ha"s sound alike.
3. **Breath.**
   - Before the first note of a phrase, add the breath if the preceding rest is at least `breath_min_rest_ms`.
   - Place it so it ends at that note's h-onset, which is the note start minus the unit's pre-utterance.
   - Apply `breath_gain_db`. Leave its pitch untouched.
4. **Write `score.json`.** One entry per note, for example:
   ```json
   {"i": 17, "start": 101.250, "end": 102.900, "midi": 57, "transpose": 12,
    "unit": "u03", "shift_st": -2.4, "gain_db": -1.5, "phrase": 4,
    "breath_before": false}
   ```
   - `gain_db` follows the guide's RMS for that note, so the dynamics of the original humming carry over.
   - Print a summary table with each unit's usage count and the maximum shift.

## Stage 5 — render the vocal (`s5_render.py`, the core)

**Idea: the WORLD vocoder.** It splits a voice into three parts:

- pitch (f0);
- spectral envelope (the vowel and the timbre: "this is Otto saying 'a'");
- aperiodicity (breathiness).

Changing f0 while keeping the other two retunes the voice without turning it into a chipmunk. Changing the timing of the frames stretches it.

Before starting, ask about learning mode (working agreement, point 6).

For each note in `score.json`:

1. **Analyse the unit** with WORLD (`harvest` / `cheaptrick` / `d4c`, fs 48 kHz, 5 ms frames, f0 range 70–800 Hz). Cache the result per unit.
2. **Build a time map.**
   - The onset region, from unit start to `vowel_start + 20 ms`, plays at 1×.
   - The vowel core is stretched or compressed to fill the note.
   - The last `release_ms` plays at 1×.
   - Interpolate the spectral envelope and aperiodicity between frames in the **log domain**.
3. **Normalise the sustain.**
   - A real "ha" decays. Stretched tenfold, that decay becomes a long fade-out.
   - Flatten per-frame energy over the core to its mean, then apply a note envelope: 10 ms attack, `release_ms` release.
4. **Set f0 on voiced frames.** Unvoiced frames stay at 0.
   ```
   f(t) = f_note · 2^(vibrato_cents · sin(2π · vibrato_hz · t) / 1200) · (guide(t) / guide_centre)^β
   ```
   - `f_note` is the transposed note's frequency.
   - The defaults `vibrato_cents = 0` and `β = 0` give a perfectly flat, hard-snapped note.
   - `β > 0` borrows the original humming's micro-wobble while keeping the note centre. It is the same α idea as before, applied to the guide instead of the clip.
5. **Synthesise and place.**
   - The vowel start lands exactly on the note start. The "h" therefore begins early, by the unit's pre-utterance. Example: a 70 ms "h" starts 70 ms before the beat.
   - Apply `gain_db`.
6. **Handle overlaps.**
   - If a unit's "h" starts before the previous note has ended, truncate the previous tail and crossfade over 15 ms.
   - If a note is shorter than onset + release, compress the onset proportionally. If it is still too short, truncate with a fade.
7. **Render each configured variant** to `out/variants/<name>/vocal_dry.wav`.

**Check:**
- Re-track f0 on the rendered vocal and compute each note's median error in cents.
- Flag any error above 30 cents, and any octave jump.
- Plot rendered f0 over the note bars.

**LISTEN (user):**
- the dry vocal alone;
- the dry vocal over `p2`;
- each variant, for A/B comparison.

## Stage 6 — effects, mix, splice (`s6_mix.py`)

1. **Level.**
   - Per-note gains already follow the guide.
   - Match the laugh bus's integrated loudness (pyloudnorm) to `hum`'s loudness over the segment, plus `level_offset_db`.
   - The laughs then sit where the humming sat.
2. **Light processing:** an 80 Hz high-pass filter and a gentle compressor (pedalboard).
3. **Reverb automation.**
   - Render the vocal once completely dry, and once 100 % wet (`pedalboard.Reverb`, wet = 1, dry = 0).
   - Then `out = dry + wet · env(t) · max_wet`, where `env` is interpolated from `reverb_keys` with a cosine curve.
   - Why not change reverb settings over time directly? Switching parameters chunk by chunk causes clicks ("zipper noise"). Blending two fixed renders is click-free.
4. **Reverb diagnostic.**
   - Estimate the original humming's reverb amount over time: energy in the 150 ms after each note ends, divided by the energy during the note.
   - Plot that curve alongside `env`, so the user can check the keyframes against what the PV actually did.
5. **Segment mix:** `g_yt · (p2 + narr) + laughs_wet`, aligned with the offsets from Stage 1.
6. **Splice.**
   - `full = yt`, with [`segment.start`, `segment.end`] replaced by the segment mix.
   - Use equal-power crossfades of `xfade_ms`: cosine fade-out, sine fade-in, centred on each boundary.
   - If an edge is audible, move it to the quietest point within ±1 s, or lengthen the crossfade.
   - Put a limiter on the output. Report the true peak.
7. **Outputs:**
   - `out/segment_mix.wav`
   - `out/full_audio.wav` (same length as `yt`)
   - `out/stems/`: bed, vocal_dry, vocal_wet

## Stage 7 — verify and deliver (`s7_verify.py`)

- Outside the segment and its crossfade zones, `full_audio` must equal `yt` sample for sample. Assert it.
- `full_audio` must have the same duration as `yt`. Assert it.
- Plot both splice edges (±0.5 s) with `yt` overlaid.
- Print the mux command (optional) for the user:
  ```
  ffmpeg -i pv.mp4 -i out/full_audio.wav -map 0:v -map 1:a -c:v copy -c:a aac -b:a 320k pv_otto.mp4
  ```

**LISTEN (user):** the full result against the video.

---

## Known risks and fallbacks

| risk | sign | fallback |
|---|---|---|
| subtraction leaves too much music in the guide | pitch-tracker disagreement, ghost notes | sub-sample alignment; separation model on `p1` |
| reverb smears notes 1:27–1:57 | notes too long, ghost notes in that range | user fixes `notes_edited.mid` |
| large stretches sound frozen | long notes sound static or robotic | A/B the `vib20` variant; try `β` 0.2–0.4 |
| big pitch shifts sound buzzy | many \|shift\| > 7 st in the report | change transpose; per-note warning |
| Otto background audible after shifting | noise moves with the pitch | `units.denoise: true` |
| WORLD octave errors on laughs | f0 jumps in the contact sheet | narrow the f0 range per unit |

## Not in this test

Laugh trains, multiple voice sources, lyrics, 说的道理-style fixed patterns, and video. Revisit after the user hears this one.

## Dependencies

- **Python packages:** numpy, scipy, soundfile, librosa, pyworld, pretty_midi, pedalboard, pyloudnorm, matplotlib, pyyaml.
- **Optional:** `audio-separator[cpu]`, used only when denoise is enabled.
- **On the PATH:** ffmpeg and yt-dlp.
- If pyworld fails to build on Windows, try Python 3.11 or install the MSVC build tools.
