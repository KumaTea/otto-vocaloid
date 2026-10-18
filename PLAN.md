# coronal-otto — a 人力 test: Otto's laughter hums 「日冕」

> **v2, 2026-10-05.** Revised in Claude Code after the user's notes. v1 is kept as `PLAN.v1.md`. "Changes from v1" at the end lists what moved and why.

## Goal

Replace the male humming in the Phainon PV 「日冕」 (YouTube `BEKGuF5tY9E`, Chinese version), from 1:14 to 2:08, with 电棍 (Otto)'s laughter:

- one "ha" per note;
- each "ha" stretched to the note's length;
- tuned to the melody, keeping half of each laugh's own pitch movement. The user picked this: tuning is fine; what to avoid is the over-smooth sound of AI voice models (VITS, SoVITS);
- where the original stacks several hums in unison (1:27–1:57), a stack of several Ottos.

Deliverables:

- the audio for the excerpt 1:10–2:08, with no narration, aligned to that YouTube video, which the user lays onto the video;
- a set of DAW-ready intermediate files (stems, one WAV per vocal layer, MIDI), so the user can keep improving the result in Melodyne, FL Studio or any DAW.

This is a test of the method, not a full production. Keep it small, inspectable, and re-runnable.

---

## Working agreement (Claude Code: read this first)

1. **Teach as you go.** The user wants to understand the method, not just receive output.
   - Before each stage, explain its core idea in 2–3 sentences with a concrete example.
   - After each stage, show the evidence: numbers in `out/reports/`, and plots in `out/plots/`. You can read the PNGs yourself.
2. **Claude can't listen.** In this setup Claude reads text and images, not audio.
   - Check yourself with what you *can* read: alignment residuals in dB, pitch error in cents, onset error in ms, loudness, true peak, spectrograms, and f0 drawn over note bars.
   - Some things only an ear can judge: whether it sounds like Otto, whether it's funny, whether a long stretch sounds frozen or buzzy, whether a stack sounds like several people. Those belong to the user.
   - **LISTEN (user)** steps: stop and wait for the user's verdict. Each one names the files, the time range, and what to listen for.
   - Keep a local page, `out/review.html`, with an audio player and the relevant plots for each current LISTEN item. The user opens it in Chrome over the NAS share. It stays local; never publish it, because it embeds copyrighted audio.
3. **Everything is driven by files.**
   - Settings live in `config.yaml`. Note-by-note decisions live in `score.json`.
   - No hand-edited audio. `uv run build.py <stage>` must reproduce the outputs.
   - `score.json` is hand-editable. Never regenerate it over the user's edits unless asked (`--force`).
4. **Logins.**
   - **Bilibili:** log in by QR code (Stage 0). The user has offered their password, but the QR flow doesn't need it and keeps it out of the conversation log. Never print cookie values.
   - **YouTube:** no login expected. If yt-dlp hits a bot check, ask the user to export a `cookies.txt` from Chrome into `secrets/`. This machine has no browser, so `--cookies-from-browser` is not an option.
5. **Keep intermediates.**
   - Never delete intermediate files. A stage overwrites only its own outputs when it is re-run.
   - Everything the user might import into a DAW also goes into `out/daw/`, following the conventions in "DAW export" below.
6. **Git.**
   - The user has run `git init`. `.gitignore` covers `data/`, `out/` and `secrets/`.
   - Never commit; the user does that.
7. **Environment.**
   - Debian 13 LXC: 28 cores, 16 GB RAM, no GPU. The Intel DG1 on host `ai` is not worth using here, because every model in this plan runs fine on the CPU.
   - Use a uv project on Python 3.11 (already installed by uv). ffmpeg 7.1 is on the PATH.
   - Don't install Node. Deno is approved, for yt-dlp only.
   - Ask before any download over ~1 GB.
8. **Learning mode (optional).** At the start of Stage 5, ask whether the user wants to write the core render function themselves. If yes, provide a skeleton, docstrings and tests; review their code instead of writing it.
9. In Stage 0, create a short `CLAUDE.md` that says: "Read PLAN.md; follow the working agreement; current stage is N." Keep the stage number current.
10. **This plan is a guide, not a contract.** If a measurement contradicts it, say so and propose a change before working around it.

---

## Master clock

All times in `config.yaml` and `score.json` are **seconds on the YouTube `BEKGuF5tY9E` timeline**. That is the Hoyoverse upload, which has no watermark, and it is the video the user will put the new audio on. The official Bilibili upload (`BV1HfKiz3Ezf`) is watermarked and is not used.

Each Bilibili stem gets an offset measured in Stage 1 (it came out at −33.3 ms, one video frame, for all three). Never hard-code an offset.

## Sources

| id | content | URL |
|---|---|---|
| `yt` | official PV, zh: music + humming + narration | https://www.youtube.com/watch?v=BEKGuF5tY9E |
| `p1` | music + humming + breaths + effects (not sample-consistent with `p2`; unused) | https://www.bilibili.com/video/BV1QYgfzcEpF?p=1 |
| `p2` | music + effects: **the bed** | https://www.bilibili.com/video/BV1QYgfzcEpF?p=2 |
| `p3` | 人声: humming + narration: **the guide** | https://www.bilibili.com/video/BV1QYgfzcEpF?p=3 |
| `sp` | splash animation 开屏动画: music + humming (a different edit; unused) | https://www.bilibili.com/video/BV1Tk3Jz1EMP |
| `otto` | laugh clip at 2:00–2:06 of part 1 (the 6:46 cut) | https://www.bilibili.com/video/BV1Zs411g7Kg?p=1 |

The user's Bilibili account has 大会员. If that unlocks Hi-Res (FLAC) audio for the stems, use it: lossless stems make the subtraction in Stage 1 nearly perfect. *Stage 0 result: no Hi-Res is offered for these videos. The best is AAC (format 30280, ~190 kbps, 44.1 kHz).*

User-supplied landmarks on the `yt` clock. These are approximate; Stage 3 measures the real boundaries and curve.

| time | event |
|---|---|
| 1:10 | excerpt start |
| 1:14 | humming starts, a single voice |
| 1:27 | stacking starts: more hums join, singing the same tune |
| 1:42 | thickest stack |
| 1:57 | back to a single hum |
| 2:08 | excerpt end |

**About "reverberation".** The user first called this section reverberated. What they actually hear is several hums singing the same tune at the same time (unison), compared with one dry hum. Stage 3 measures whether the stack builds gradually or in steps, and whether it thins out gradually or drops abruptly at 1:57. It also looks for octave doubling, because a layer an octave apart can sound like "the same tune".

The Otto clip contains, in order:

- laugh 1: 6 "ha"
- one inhale
- laugh 2: 4 "ha"
- laugh 3: 3 "ha"

That gives **13 "ha" units + 1 breath**. The laughs are loud, mostly voiced chest voice, and dominate any background noise.

## Decisions already made

- **One note = one "ha".** The vowel is stretched or compressed to the note length. No laugh trains.
- **Pitch is hard-snapped** to note centres.
- **The single inhale** goes before phrases that follow a long rest, on the lead layer only. It is not pitched.
- **The stack is a choir of Ottos.**
  - A lead line plays from 1:14.
  - Double layers join to sing the same notes.
  - Each double uses a different "ha" on each note, with a small detune and timing offset, panned across the stereo field.
  - The number of layers follows the original's measured stack curve.
- **Reverb is light glue**, not the main effect.
- **Otto clip denoise** is off by default. A config flag enables a separation model.
- **Narration:** none in the result (the user's decision). The bed is 伴奏, which has none.
- **Transcription (扒谱):** Claude makes the first pass, and the user checks it. If the automatic pass is poor, the user corrects it, or transcribes from scratch, in FL Studio or Melodyne.
- **Output:** `excerpt.wav` (1:10–2:08) on the YouTube clock, plus `out/daw/`. A muxed preview MP4 is optional (Stage 7).

---

## Repo layout

```
otto/                    # project root (this folder)
├─ PLAN.md  PLAN.v1.md
├─ CLAUDE.md             # created in Stage 0
├─ config.yaml
├─ pyproject.toml  uv.lock
├─ build.py              # uv run build.py <login|fetch|align|units|transcribe|score|render|mix|verify|all>
├─ notes_edited.mid      # optional, from the user (Stage 3)
├─ src/
│  ├─ common.py          # audio IO, time conversion, plotting, DAW-export and review-page helpers
│  ├─ s0_fetch.py        # includes the QR login
│  ├─ s1_align.py
│  ├─ s2_units.py
│  ├─ s3_transcribe.py   # melody, tempo/key, stack curve
│  ├─ s4_score.py
│  ├─ s5_render.py
│  ├─ s6_mix.py
│  └─ s7_verify.py
├─ secrets/              # gitignored, mode 700: cookies, login QR
├─ data/raw/  data/work/ # gitignored
└─ out/                  # gitignored: wavs, reports/, plots/, variants/, daw/, review.html
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

auth:
  bilibili_cookies: secrets/bilibili_cookies.txt   # written by `build.py login`
  youtube_cookies: null                            # set to secrets/youtube_cookies.txt only if a bot check appears

units:
  expect_groups: [6, 1, 4, 3]   # laugh1, inhale, laugh2, laugh3
  denoise: false

transcribe:
  fmin: 60
  fmax: 600
  min_note_ms: 60
  phrase_rest_ms: 400

stack:                          # the unison choir, 1:27–1:57
  source: measured              # measured | keys
  keys: [[87, 0.0], [102, 1.0], [117, 0.0]]   # fallback thickness curve: 1:27, 1:42, 1:57
  max_layers: 4                 # lead + up to 3 doubles
  change_at: phrase             # layer count changes at phrase starts (phrase) or per note (note)
  detune_cents: 12              # doubles' fixed detunes, spread across ±this
  jitter_ms: 20                 # random per-note onset offset for each double
  pan_spread: 0.8               # 0 = all centre, 1 = hard left/right
  double_gain_db: -3            # each double relative to the lead
  seed: 1

score:
  transpose: auto              # or -12 / 0 / 12
  weights: {shift: 1.0, repeat: 2.0, intensity: 0.5, layer_clash: 3.0}
  breath_min_rest_ms: 400
  breath_gain_db: -6

render:
  engine: world                # world | psola (fallback, see risks)
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
  reverb: {room_size: 0.6, damping: 0.5, width: 1.0, wet: 0.12, follow_stack: true}

export:
  sample_format: float32       # WAV in out/daw/; Melodyne, FL Studio and REAPER all read it
  tempo: auto                  # BPM written into MIDI; auto = beat-tracked from p2, else 120
```

---

## Stage 0 — set up, log in, fetch (`s0_fetch.py`)

**Idea:** get every source into one uniform format once, so no later stage has to think about codecs.

1. **Set up.**
   - `uv init` on Python 3.11 and add the dependencies (see the end of this plan), including `yt-dlp[default]`, which brings the YouTube JavaScript solver.
   - Add Deno as a project dependency: the official `deno` package on PyPI puts it in `.venv`, so nothing is installed globally. yt-dlp needs a JavaScript runtime for YouTube.
   - Write `.gitignore` and `CLAUDE.md`.
2. **Bilibili QR login (`build.py login`).**
   - Request a QR from `https://passport.bilibili.com/x/passport-login/web/qrcode/generate`. It returns a `url` and a `qrcode_key`.
   - Draw the `url` as a QR code in the terminal (the `qrcode` package), and also save it as `secrets/login_qr.png`.
   - Ask the user to run it as `! uv run build.py login`, so the QR appears in their own terminal, and to scan it with the Bilibili app.
   - Poll `…/qrcode/poll?qrcode_key=…` every 2 s for up to 3 min. The codes are: 86101 not scanned, 86090 scanned but not confirmed, 86038 expired, 0 success.
   - On success, write the returned cookies (`SESSDATA`, `bili_jct`, `DedeUserID`, `DedeUserID__ckMd5`, `sid`) as a Netscape `cookies.txt` with mode 600.
   - Verify with `https://api.bilibili.com/x/web-interface/nav`. Report only `isLogin` and the VIP status.
   - Tell the user that the session can be revoked from the app's login-device list once the project is done.
3. **Download audio only, in the native codec.**
   - Use `-f bestaudio` and do not transcode to MP3, since each lossy transcode adds damage.
   - For Bilibili, list the formats (`-F`) with cookies first. Prefer Hi-Res FLAC, then 192 kbps AAC. Never use Dolby/E-AC-3: it can be a different mix.
   - Bilibili parts are addressed with `?p=N`.
   - Record the chosen format per source.
4. Cut the Otto clip with ffmpeg at the configured `clip` window (2:00–2:06 with a 2 s margin).
5. Decode everything to **48 kHz float32 WAV**, keeping stereo, in `data/raw/`. Use the soxr resampler when the source is 44.1 kHz.
6. Write `out/reports/sources.json` with codec, bitrate, native sample rate, channels and duration per source (from ffprobe).

**Check:**
- `p1`, `p2` and `p3` should have near-equal durations (~3:18–3:19). *Measured: all 198.020 s.*
- `yt` should be ~3:24. *Measured: 204.0 s. The "3:22" in v1 was approximate.*
- All decoded files at 48 kHz.

## Stage 1 — align the bed and the guide (`s1_align.py`)

> **Revised three times on 2026-10-05.**
> - v2 assumed `p1 − p2` would leave the humming; it doesn't.
> - A spectral split of `p3` into humming and narration was then tried, and the user rejected it, because words went missing.
> - **Rule from the user: never separate sources by editing spectra in Python.** The only exception is a plain subtraction of supplied stems whose result is the humming itself. None exists, see below.
> - The uploader of BV1QYgfzcEpF then shared lossless WAVs, and those are what Stage 1 uses now.

**The sources** (the user's description, confirmed by measurement in `out/reports/align.json`):

| id | file | content | on the yt clock |
|---|---|---|---|
| `w_orig` | 原音乐.WAV | the PV's audio, lossless | +0.800 s |
| `w_bed` | 音乐无吟唱(伴奏).wav | music + effects: **the bed** | +0.800 s |
| `w_vocals` | 人声.wav | humming + breaths + narration: **the guide** | +0.800 s |
| `w_music_hum` | 音乐加男声吟唱.WAV | music + humming + breaths + effects | −0.033 s |
| `w_chant`, `w_chant_nostab` | 吟唱原版 / 吟唱部分去除白厄被刀版 | the chant section, everything but narration (the second one re-processed) | +73.933 s |

- **伴奏 + 人声 = 原音乐 exactly** (gains 1.000 / 1.000, residual −66.5 dB, the 16-bit floor). The separation is mixture-consistent, so the bed is the PV minus exactly its vocals.
- **原音乐 is the PV.** It matches `yt` at −20 dB, which is YouTube's lossy encoding.
- **No subtraction gives the humming alone.**
  - 音乐加男声吟唱 and 吟唱原版 match each other (−33 dB).
  - Neither matches the bed: −15 dB where the vocals are silent. They are separately made and normalised.
  - The two chant versions differ throughout (up to −20 dBFS), not only at the stab, so the stab can't be lifted out of the bed by subtraction either.
- The Bilibili parts `p1`/`p2`/`p3` are AAC copies of the same material, and the splash animation `sp` is a different edit. Neither is used any more.

**Decisions (the user's):**
- The humming does not need to be isolated. The guide is 人声: the user reviews the MIDI and deletes any notes the narration causes.
- **The result contains no narration.** It is the excerpt 1:10–2:08 built from the bed + Otto, so there is no splice with `yt`.

**Idea: cross-correlation.** Slide one recording against another and find the lag at which they match best.

- *Example:* the bed matches the YouTube audio best when moved 0.800 s later, so that is its offset.
- Audio alignment is exact to a fraction of a sample, while video frames are only exact to 33 ms.

1. **Offsets.** The bed, guide and reference (config `stems`), each against `yt` directly: a coarse lag on 8 kHz mono copies, then a refinement at 48 kHz within ±50 ms with sub-sample interpolation. Check for drift in 10 s windows.
2. **Fits.** Confirm `reference = bed + guide` and `yt ≈ bed + guide`, and take one gain per stem.
3. **Export, aligned and otherwise untouched:** `bed.wav`, `hum_guide.wav`, `yt_original.wav`.
4. **Plots:** `align_xcorr.png`, `align_drift.png`, `align_edges.png`.

## Stage 2 — slice the laughs (`s2_units.py`)

> **As built (2026-10-10):**
> - Two laugh sources, in config `units.sources`:
>   - `otto`: the stream clip, structure 6 / 1 / 4 / 3;
>   - `otto2`: the otto-hzys clip, cut at every dip of at least 6 dB.
> - Groups are split at the largest gaps, and units at the most prominent loudness dips inside each group.
> - Pitch and "sung" frames use the Stage 3 recipe: pYIN at 16 kHz, plus agreement with Harvest. The ceiling is 600 Hz, because with a higher one pYIN locks onto `otto2`'s ~1 kHz vowel resonance.
> - Result:
>   - `otto`: 13 "ha"s around E4/F#4, plus the inhale; laugh 3 is irregular.
>   - `otto2`: 7 units around G#3/A3; units 01 and 06 may each be two "ha"s.
> - Unit ids are `<source>_<nn>`. Files are in `out/daw/units/`, with `units.csv`.

**Idea:** a laugh is a train of bursts, so its loudness envelope has a dip between each "ha". In a fast laugh the "h" between two "ha"s may never reach silence. Cut at envelope minima and at voiced-to-unvoiced transitions, not at a silence threshold.

1. Compute an RMS envelope with a 10 ms hop, and a voicing track from `pyworld.harvest`.
2. Use the known structure as a constraint.
   - First find the 3 largest gaps, which separate laugh 1 / inhale / laugh 2 / laugh 3.
   - Then split each laugh into its expected count (6 / 4 / 3) at its deepest envelope dips.
   - If the dips are not clearly deeper than the surrounding signal, fail loudly with a plot. Never guess.
3. For each unit, record in `units.json`:
   - `start` and `end`
   - `vowel_start`: the first voiced frame. The unvoiced "h" before it is the unit's **pre-utterance**.
   - `vowel_end`
   - median f0, as a fractional MIDI number
   - voiced ratio
   - peak RMS
   - spectral centroid (a proxy for strain or intensity)
   - `is_breath`: voiced ratio < 0.2. This should be exactly the 7th unit.
4. Write `data/work/units/u00.wav … u13.wav`, plus a contact-sheet PNG showing each unit's waveform, cut points and f0.
5. If `units.denoise` is true, run `audio-separator` with a vocal model on the clip before slicing.
6. **DAW files:** `units/u00.wav … u13.wav` and `units.csv` (pitch and pre-utterance per unit), for FL's sampler or Slicex.

**LISTEN (user):** the 14 unit files, individually. Listen for:
- each file is exactly one "ha", or the inhale;
- no clipped "h" at the start;
- no piece of the next "ha" at the end.

## Stage 3 — transcribe the guide and measure the stack (`s3_transcribe.py`)

### 3a. Melody

> **As built (2026-10-05):**
> - The guide is 人声, which still contains narration. Tracking runs from `hum_start − 0.5` s to `end + 2` s.
> - pYIN's own voicing missed much clearly sung humming, so a frame also counts as sung when pYIN's best guess and Harvest agree within 60 cents.
> - Two rules clean up the notes. A passing note under `glide_merge_ms` (100 ms) in the middle of a slide joins the note slid to, and a short falling tail joins the note it falls from. A note under `blip_drop_ms` (100 ms) touching nothing is dropped.
> - First result: 91 notes in 17 phrases, C3–A#4, from 74.055 s. The bed is 136 BPM and E♭ major.
> - Flags in `notes.csv`: trackers disagree, narration nearby (approximate hints in config), outside the key.
> - 3c (the stack curve) runs after the user's MIDI review.

**Idea:** a pitch tracker gives a continuous pitch curve. Notes are the stretches where that curve sits near one semitone.

1. Track the f0 of the guide over 72–130 s.
   - Primary tracker: `librosa.pyin`, with `fmin`/`fmax` from config and a 5 ms hop.
   - Cross-check with `pyworld.harvest`. Flag any region where the two disagree by more than 50 cents.
2. Segment into notes.
   - A note needs voiced frames, confident pitch, and energy above a threshold.
   - Quantise f0 to the nearest semitone using the median over each stable region.
   - Split where the quantised pitch changes and holds for at least `min_note_ms`.
   - Also split at onset-strength peaks, so repeated notes of the same pitch are separated.
   - Merge blips shorter than `min_note_ms` into a neighbour.
3. **Known hazard, 1:27–1:57: the stack.**
   - In unison the layers sing the same notes, so the melody is still one pitch line.
   - But the takes are never exactly together. Onsets smear, note ends blur, and pitch confidence drops.
   - Decide note starts from onset strength. End a note at the next onset or where the direct sound drops.
   - If the trackers disagree badly, try RMVPE on that region. It is a pitch model built for voices in a mix, with ~180 MB of weights.
   - Expect the user to hand-fix some notes here.
4. **Phrases** are separated by rests of at least `phrase_rest_ms`.

### 3b. Tempo and key: self-checks Claude can read

- Beat-track `p2` to get the BPM. It is written into the MIDI so that FL's piano-roll grid lines up with the music.
- Estimate the key from `p2`'s chroma. Flag notes outside the key; they are likely transcription errors, or real chromatic notes for the user to confirm.
- Report each onset's distance to the nearest 1/16 grid line. This is only a report: do not quantise timing.

### 3c. Stack curve

> **As built (2026-10-10), `build.py stack`, per note of the reviewed MIDI:**
> - Harmonics-to-noise, beating and off-harmonic energy turned out too noisy to use: the gliding passages inflate them regardless of the number of voices.
> - Stereo width follows what the user hears:
>   - one voice at 1:14–1:23;
>   - wide from 1:24 to 1:53;
>   - narrow at 1:56–2:02;
>   - wide again on the final note.
> - So thickness = width. The proposed layers per phrase are smoothed into `stack.layers_by_phrase`, for the user to edit.
> - The spectrogram also shows a held low drone, G3/D4 under the melody, at 1:42.5–1:49, with energy an octave below the note up about 30 dB. It is offered as `stack.octave_down`, off until the user confirms.

**Idea:** one voice has sharp harmonics. Several voices on the same note are each slightly out of tune with the others. That smears each harmonic into a narrow band that beats (wobbles in loudness). Overdubbed takes are also usually panned, so the side (L−R) channel grows. Reverb is different: it mostly adds energy *after* notes end.

Measure, over the guide in 0.5 s windows from 70 to 128 s:
- the side/mid energy ratio;
- the harmonics-to-noise ratio (`praat-parselmouth`) in note middles;
- the beating depth on the first few harmonics in note middles;
- the tail energy in the 150 ms after each note ends (the reverb measure);
- octave layers: energy at 2·f0 and f0/2 relative to the single-voice section 1:14–1:27.

Then:
- Combine the stacking measures into a 0–1 thickness curve.
- Plot it with the user's landmarks (1:27, 1:42, 1:57) and the note bars.
- Report whether it builds gradually or in steps, where it peaks, whether it ends gradually or abruptly at 1:57, and whether an octave layer is present.

### 3d. The user's reviewed notes (`build.py notes`, `s3_notes.py`)

The user corrected the draft by hand in FL Studio: `user/tuned.mid`, 72 notes at 135 BPM on a 1/16 grid. From here on that file is the truth.

- **Placement on the yt clock comes from the user's anchors.** In their FL project, 吟唱部分去除白厄被刀版.WAV starts at 0.805 s and the first note at 1.000 s. That file's measured position on the yt clock gives an offset of −0.538 s.
- **The guide's pitch confirms it:** the best-fitting offset is within 30 ms.
- **Outputs:**
  - `out/reports/notes_final.json`, Stage 4's input;
  - `out/daw/notes_final.mid` on the video clock, with a short first beat so the 135 BPM grid sits on the music;
  - a comparison with the draft (`notes_compare.json`);
  - check renders.
- **Phrases 7 (1:30.4) and 14 (2:00.4)** fit the guide best about 0.2 s later. The user kept their timing.

### Outputs

- `notes.mid`, via pretty_midi, with the BPM from 3b;
- `notes.json` with start, end, midi, guide RMS and phrase index per note;
- `stack_curve.json`;
- per-10 s plots of the guide f0 (in cents) with note bars drawn over it, plus the stack plot;
- check renders:
  - `check_midi_over_bed.wav`: simple sine tones of the MIDI mixed over `p2`;
  - `check_midi_vs_hum.wav`: the humming in the left channel, the sines in the right channel.
- **DAW files:** `notes.mid` and `notes.csv`.

**LISTEN (user):**
- Do the sines play the same tune as the humming? Listen especially from 1:27 to 1:57.
- Does the stack plot match what you hear: where it starts, where it peaks, how it ends?
- To correct the notes, use either tool and save the result as `notes_edited.mid` in the project root. Stage 4 prefers that file when it exists.
  - FL Studio: import `out/daw/notes.mid` into the piano roll, fix it, and export it as MIDI.
  - Melodyne: let it detect notes on `out/daw/hum_guide.wav`, fix them, and export MIDI.
- If the automatic pass is too far off, the user can transcribe from scratch into the same file.

## Stage 4 — build the score (`s4_score.py`)

> **As built (2026-10-10), revised for the user's taste: natural rather than tuned, don't stretch hard, longer laughs for longer notes, the laughs tire as they go.**
> - The cost per (note, unit) adds:
>   - shift: 1 per semitone, quadratic past `free_shift_st` = 3;
>   - stretch: log2 of the stretch beyond `comfort_stretch` = 1.5×, weight 6;
>   - exhaustion: |the unit's place in its laugh − the note's place in the song|, weight 4;
>   - repeat, reuse and layer clash.
> - Lead and doubles both draw on both laughs: the stream laugh sits around E4 and `otto2` around A3, so the register picks.
> - Doubles get a fixed detune and pan per layer, and a seeded onset jitter per note.
> - The layer count comes from `stack.layers_by_phrase`.
> - First result:
>   - transpose 0;
>   - lead shifts: median 1.9 st, max 4.1 st;
>   - stretch: median 1.41×; only the five 1.8–2.0 s held notes need 4–4.9×;
>   - 14 inhales.
> - Exhaustion only breaks ties after pitch and stretch, so the tiredness arc is loose.
> - `score.json` is in the project root and hand-editable; `--force` rebuilds it.

**Idea:** choosing a "ha" for each note is a small optimisation. Give every (note, unit) pair a cost and pick the cheapest. The stack adds one rule: two copies of the same "ha" at almost the same time and pitch don't sound like two people. They comb-filter into one phasey voice, so doubles must use different "ha"s.

1. **Transpose.**
   - Choose k ∈ {−12, 0, +12} to minimise the mean |note + k − unit pitch centre|.
   - Shifting a voice by more than about 7 semitones tends to sound buzzy, and an octave move keeps the tune and its harmony intact.
   - Record the chosen k. Config can override it.
2. **Layer plan.**
   - Map the stack thickness, from `stack_curve.json` or from `stack.keys` when `source: keys`, to the number of active layers: 1 to `max_layers`.
   - With `change_at: phrase`, layers enter and leave only at phrase starts, the way overdubbed takes usually do.
   - The lead (layer 0) plays every note from `hum_start`.
   - Give each double a fixed detune, spread across ±`detune_cents`, and a fixed pan, spread across ±`pan_spread`.
   - Give each double, on each note, an onset offset drawn from ±`jitter_ms`, using `seed`.
3. **Assignment.** For each note, the lead picks first, then each active double:
   ```
   cost = w_shift       · |pitch shift in semitones|
        + w_repeat      · [same unit as this layer's previous note]
        + w_intensity   · |intensity rank of unit − loudness rank of note|
        + w_layer_clash · [same unit as another layer on this note]
   ```
   - The intensity term carries the emotional build-up. The most strained "ha"s land on the loudest guide notes, which are the climax.
   - With 13 units and at most 4 layers, every layer can always get a distinct unit.
4. **Breath.**
   - On the lead only: before the first note of a phrase, add the breath if the preceding rest is at least `breath_min_rest_ms`.
   - Place it so it ends at that note's h-onset, which is the note start minus the unit's pre-utterance.
   - Apply `breath_gain_db`. Leave its pitch untouched.
5. **Write `score.json`.** One entry per note, for example:
   ```json
   {"i": 17, "start": 101.250, "end": 102.900, "midi": 57, "transpose": 12,
    "phrase": 4, "gain_db": -1.5, "breath_before": false,
    "layers": [
      {"layer": 0, "unit": "u03", "shift_st": -2.4},
      {"layer": 1, "unit": "u08", "shift_st": 1.1, "detune_c": 8, "offset_ms": 14, "pan": -0.6}
    ]}
   ```
   - `gain_db` follows the guide's RMS for that note, so the dynamics of the original humming carry over.
   - Print a summary table: each unit's usage count, the maximum shift, and the layer count per phrase.
6. **DAW file:** `score.mid`, with one MIDI track per layer.

## Stage 5 — render the vocal (`s5_render.py`, the core)

> **As built (2026-10-10).** The user chose not to write the renderer (their learning goal is FL Studio).
> - **Variants are A/B on the user's two questions:**
>   - pitch: `natural` (alpha 1, the laugh's own movement shifted onto the note), `half` (0.5), `flat` (0, hard-tuned);
>   - long notes: capped at 2.5× (the "ha" ends early) vs `natural_full`.
> - **Only the vowel's middle stretches.** The first 20 ms of the vowel and the last 40 ms play at 1×. Stage 4 measures stretch the same way.
> - **Pitch is centred on the note.** The centre is the laugh's pitch as it will sound on that note (after the time map), so alpha 1 keeps the movement but stays centred.
> - **Sustain:** half of a stretched "ha"'s natural decay is evened out.
> - **Joins and extras:**
>   - the next "h" cuts the previous tail with a 15 ms crossfade;
>   - the inhale plays untouched, only after long notes;
>   - raw placements are exported for tuning by hand.
> - **Pitch check on the rendered lead:**
>   - `flat`: 0 cents median, none over 30;
>   - `half`: 8 cents median, max 70;
>   - `natural`: 16 cents median, 4 notes over a semitone (the laughs' own movement).
> - **Previews:** the stack over the bed for 1:10–2:08, level-matched to the original humming. The proper mix is Stage 6.
> - **The user's pick (2026-10-10): `half_full`.**
>   - The user's verdict: `natural` didn't sit in harmony with the bed; `flat` was too tuned to sound natural.
>   - So: half the movement (alpha 0.5), and long notes stretched over their full length, which was liked in `natural_full`.
>   - It became the fifth variant and `render.default`. Pitch check: 8 cents median, none over 100.

**Idea: the WORLD vocoder.** It splits a voice into three parts:

- pitch (f0);
- spectral envelope (the vowel and the timbre: "this is Otto saying 'a'");
- aperiodicity (breathiness).

Changing f0 while keeping the other two retunes the voice without turning it into a chipmunk. Changing the timing of the frames stretches it.

Before starting, ask about learning mode (working agreement, point 8).

For each layer, and each of its notes in `score.json`:

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
   f(t) = f_note · 2^(detune_c/1200) · 2^(vibrato_cents · sin(2π · vibrato_hz · t) / 1200) · (guide(t) / guide_centre)^β
   ```
   - `f_note` is the transposed note's frequency. `detune_c` is 0 for the lead.
   - The defaults `vibrato_cents = 0` and `β = 0` give a perfectly flat, hard-snapped note.
   - `β > 0` borrows the original humming's micro-wobble while keeping the note centre. It is the same α idea as before, applied to the guide instead of the clip.
5. **Synthesise and place.**
   - The vowel start lands exactly on the note start, plus the layer's `offset_ms`. The "h" therefore begins early, by the unit's pre-utterance. Example: a 70 ms "h" starts 70 ms before the beat.
   - Apply `gain_db`, and `double_gain_db` for doubles.
6. **Handle overlaps** within a layer.
   - If a unit's "h" starts before the previous note has ended, truncate the previous tail and crossfade over 15 ms.
   - If a note is shorter than onset + release, compress the onset proportionally. If it is still too short, truncate with a fade.
7. **Render each configured variant** to `out/variants/<name>/layer_<k>.wav` (mono, unpanned).
8. **Raw placement, for working by hand.** Also write `raw_layer_<k>.wav`: each unit placed with its vowel on the note start and its gain applied, but not stretched or retuned. This is the cleanest material for tuning and stretching in Melodyne or FL's Newtone.

**Check:**
- Re-track f0 on each rendered layer and compute each note's median error in cents, relative to the target including detune.
- Flag any error above 30 cents, and any octave jump.
- Plot rendered f0 over the note bars.

**DAW files:** `otto_L0.wav …` (the flat variant, dry, unpanned) and `otto_L0_raw.wav …`.

**LISTEN (user):**
- the lead layer dry, alone;
- the lead over `p2`;
- the full stack over `p2`, from 1:27 to 1:57: does it sound like several Ottos or one phasey Otto?
- `flat` vs `vib20`, for A/B comparison.

## Stage 6 — effects, mix, splice (`s6_mix.py`)

> **As built (2026-10-10), `build.py mix`.** Measured first, then built:
> - **Chain:** the Stage 5 stack (already panned) → 80 Hz high-pass → light reverb → level match.
> - **No compressor.** The bus is already less dynamic than the humming: its median 10 ms peak sits 10 dB below its loudest, the humming's 13 dB below.
> - **Reverb is a fixed amount, not following the stack.**
>   - In most rests, the guide's tails are masked by breaths or narration.
>   - Where a rest is clean, the tail falls 25–30 dB within 0.3 s.
>   - So: Freeverb, room 0.5, wet 0.15 (a send at about −16.5 dB).
> - **Level:** EBU R128 loudness over the notes (narration excluded), matched to the humming. That is 1.1 dB quieter than the Stage 5 previews, whose plain RMS included the narration. `level_offset_db` restores it.
> - **Limiter.**
>   - pedalboard's `Limiter` is JUCE's: it compresses everything above −10 dBFS at 4:1 and adds make-up gain. Not used.
>   - Instead, a look-ahead true-peak gain curve, applied inside the excerpt only.
>   - It doesn't act: the excerpt peaks at −2.6 dBTP. Outside the excerpt the bed stays as mastered (+0.5 dBTP after 2:10).
> - **Result:** the excerpt is −17.4 LUFS (the original PV over the same span: −17.0). Mix = bed + vocals, exactly (−126 dB residual).
> - **Outputs:**
>   - `out/final/`, 24-bit: `otto_with_bed_1m10-2m08.wav`, `otto_vocals_1m10-2m08.wav`, and `*_full.wav` from the video's 0:00;
>   - DAW, float: `otto_bus_dry`, `otto_bus`, `full_mix`;
>   - `out/reports/mix.json`.

1. **Level.**
   - Per-note gains already follow the guide.
   - Match the Otto bus's integrated loudness (pyloudnorm) to the guide's loudness over the segment, plus `level_offset_db`. The guide includes four short narration phrases; leave them out of the measurement.
   - The laughs then sit where the humming sat.
2. **Pan** the doubles with a constant-power pan law. The lead stays centred.
3. **Light processing:** an 80 Hz high-pass filter and a gentle compressor on the bus (pedalboard).
4. **Reverb as glue.**
   - Render the bus once completely dry, and once 100 % wet (`pedalboard.Reverb`, wet = 1, dry = 0).
   - Then `out = dry + wet · w(t)`, where `w = wet` from config. With `follow_stack`, it is scaled by `0.5 + 0.5 · thickness(t)`.
   - Why not change reverb settings over time directly? Switching parameters chunk by chunk causes clicks ("zipper noise"). Blending two fixed renders is click-free.
5. **Stack diagnostic.** Plot the Otto stack (active layers over time) against the original's thickness curve and the tail-energy curve from Stage 3.
6. **Excerpt mix:** `bed + otto_bus` over [`segment.start`, `segment.end`], where `bed` is 伴奏, aligned in Stage 1.
7. **Edges.** No splice with `yt` any more, since the result has no narration. Fade the excerpt in and out over 10 ms so it doesn't click. Put a limiter on the output. Report the true peak.
8. **Outputs:**
   - `out/excerpt.wav`: 1:10–2:08 only, starting at 1:10 of the video
   - **DAW files:** `otto_bus_dry.wav`, `otto_bus_wet.wav` and `full_audio.wav` (full length, silent outside the excerpt, so it lines up at 0:00).

## Stage 7 — verify and deliver (`s7_deliver.py`)

> **As built (2026-10-10), `build.py deliver`.** The user makes the video themselves, so there is no mux or preview MP4.
> - **Verify:**
>   - the excerpt is exactly 58.000 s;
>   - every `daw/` and `final/*_full` file is as long as the video's audio, and every `fl/` file is as long as the FL set;
>   - everything is at 48 kHz;
>   - the FL score's lead equals `user/tuned.mid`, tick for tick.
> - **`out/fl/`, the FL Studio set,** for the user's learning goal.
>   - It is on the clock of the user's own FL project: the one `tuned.mid` came from, 135 BPM with the beats on the grid. That clock is the video + 0.53826 s (−`offset_s` from Stage 3d).
>   - Every file starts with that much silence, so everything drops at bar 1.
>   - Contents: the 伴奏, the humming, the layers at mix level, the raw placements, my bus and mix as references, `otto_score.mid` (one track per layer, plus markers), and the units.
> - **`build.py from-fl --file x.wav`** brings an FL export back to the video's clock: full length and the excerpt. Its position is measured against the 伴奏, or against the Otto bus if the 伴奏 is absent. Tested with a 44.1 kHz MP3 of the whole song (0 samples off) and a vocals-only selection (0 samples off).
> - **`out/README.txt`** lists every file. **`FL_GUIDE.md`** (project root) walks the user through four FL exercises: mixing, retuning a note, building a note by hand, and the Sampler 鬼畜 way.

- `excerpt.wav` must be exactly `segment.end − segment.start` long. Assert it.
- Every file in `out/daw/` must have the same length and sample rate. Assert it, and write `out/daw/README.txt` listing the files.
- If the user has their own copy of the video, cross-correlate its audio track with `yt` and confirm the offset is 0 before they mux.
- Print the mux command:
  ```
  ffmpeg -ss 70 -to 128 -i pv.mp4 -i out/excerpt.wav -map 0:v -map 1:a -c:v libx264 -crf 16 -c:a aac -b:a 320k pv_otto.mp4
  ```
- Optional: download the YouTube video (~0.3–0.6 GB at 4K; ask first) and write `out/preview.mp4`.

**LISTEN (user):** the full result against the video.

---

## Blog post (`blog/`, `build.py blog`)

> **Added 2026-10-10, at the user's request:** a technical blog post about the audio analysis, to be hosted in the GitHub repository.
> - `blog/index.html` (the text), `style.css`, and `charts.js` (plain SVG charts with hover, keyboard support and playheads; no libraries) are hand-written.
> - `blog/data.js` and `blog/audio/` are generated by `src/blog.py` from the project's own results:
>   - it re-measures the alignment curves and the pitch checks;
>   - it replays Stage 4's casting and asserts it matches `score.json`;
>   - it renders the time-map demo clips with Stage 5's own `render_note`.
> - **Audio:** short excerpts (Opus/WebM plus AAC/M4A, 5.2 MB), added at the user's request. They are other people's recordings. Without `blog/audio/` the page still works and its players hide themselves.
> - **Chinese version:** `blog/index.zh.html`, a translation of `index.html`. The page sets `lang="zh-CN"`, and `charts.js` then takes every chart label from its `ZH_TEXT` table (English is the key); the sentences built from data have an inline Chinese variant. Both pages link to each other. A string added to the charts needs a `ZH_TEXT` entry too.
> - **Checked** in headless Chromium (light, dark, 390 px wide): no script errors, no horizontal overflow. Playback and seeking were tested from file://; Python's `http.server` can't seek, because it has no range requests.

## DAW export (`out/daw/`)

The point is that the user can pick up any intermediate step in Melodyne, FL Studio or another DAW, without re-aligning anything.

- **One time origin.** Every WAV starts at t = 0 of the YouTube video and is full length (the same length as `yt`): 48 kHz, 32-bit float. Drop them all at the very start of an FL playlist (or 0:00 in any DAW) and they line up with each other and with the video.
- **MIDI.** Note times are exact in seconds. The BPM only decides how the grid lines up. If no steady tempo is found, 120 BPM is written; the grid then won't match the bars, but note times stay exact.
- **Size.** About 78 MB per stereo file, around 1–1.5 GB in total. That is fine on this disk.

| file | stage | use |
|---|---|---|
| `yt_original.wav` | 1 | reference, A/B |
| `hum_guide.wav` | 1 | 人声: humming + breaths + narration, for Melodyne note detection |
| `bed.wav` | 1 | 伴奏: music + effects, no humming, no narration |
| `units/u00…u13.wav`, `units.csv` | 2 | samples for a sampler or Slicex |
| `notes.mid`, `notes.csv` | 3 | the melody: FL piano roll |
| `score.mid` | 4 | one track per layer |
| `otto_L0.wav`, `otto_L1.wav` … | 5 | tuned dry layers, unpanned |
| `otto_L0_raw.wav` … | 5 | placed but untouched: tune and stretch by hand |
| `otto_bus_dry.wav`, `otto_bus.wav` | 6 | the Otto bus at mix level, before and after reverb |
| `full_mix.wav` | 6 | 伴奏 + Otto, full length (= `out/final/otto_with_bed_full.wav`, in float) |

The deliverables for the video are in `out/final/` (24-bit). An FL Studio set on the user's project clock is in `out/fl/` (see Stage 7 and `FL_GUIDE.md`).

---

## Known risks and fallbacks

| risk | sign | fallback |
|---|---|---|
| yt-dlp fails on YouTube | bot check, or only low formats | update yt-dlp; check Deno is on the PATH; Chrome `cookies.txt` export |
| Bilibili gives limited formats or 412 | no FLAC/192k, HTTP 412 | re-run `build.py login`; check `nav` VIP status |
| narration in the guide makes false notes | notes during spoken words | the user deletes them in the MIDI review |
| the stack smears notes 1:27–1:57 | notes too long, ghost notes in that range | onset-based ends; RMVPE; user fixes `notes_edited.mid` |
| stack curve unclear | the measures disagree with each other or with the user's ears | `stack.source: keys`, adjusted by ear |
| doubles sound like one phasey voice | "flanging" or comb-filter colour | more detune or jitter, wider pan, check that units are distinct |
| large stretches sound frozen | long notes sound static or robotic | A/B the `vib20` variant; try `β` 0.2–0.4 |
| WORLD sounds buzzy | metallic long notes | `render.engine: psola` (parselmouth: a flat pitch tier and a duration tier on the real waveform) |
| big pitch shifts sound buzzy | many \|shift\| > 7 st in the report | change transpose; per-note warning |
| Otto background audible after shifting | noise moves with the pitch | `units.denoise: true` |
| WORLD octave errors on laughs | f0 jumps in the contact sheet | narrow the f0 range per unit |

## Not in this test

Laugh trains, other people's voices, lyrics, 说的道理-style fixed patterns, harmony parts, and video. Revisit after the user hears this one.

## Dependencies

- **Python 3.11 via uv:** numpy, scipy, soundfile, librosa, pyworld, pretty_midi, pedalboard, pyloudnorm, matplotlib, pyyaml, praat-parselmouth, qrcode, requests, `yt-dlp[default]`, deno.
- **Optional:** `audio-separator[cpu]` (only when denoise is enabled); RMVPE weights (~180 MB, only if pyin and harvest fail on the stack).
- **System:** ffmpeg 7.1 (installed, with soxr).

---

## Changes from v1

- **Platform.** v1 assumed Windows. This runs in a Debian LXC with uv, so the Windows notes on pyworld builds and Chrome cookie encryption are gone.
- **Logins.** Bilibili now uses QR-code login. The user has 大会员, so Hi-Res stems may be available. YouTube needs no login, only Deno for yt-dlp. Firefox is no longer involved; Chrome matters only as a fallback for exporting `cookies.txt`.
- **"Reverb" was really stacking.** The user hears several hums in unison, so the main effect is now a choir of Otto layers, with distinct "ha"s, detune, timing jitter and panning. Reverb is light glue. The v1 reverb diagnostic became the stack curve (Stage 3c), which also checks tails and octave layers.
- **Master clock confirmed:** the YouTube upload, which has no watermark.
- **DAW export.** A new `out/daw/` set has one time origin, per-layer WAVs, raw placements for tuning by hand, units and MIDI with tempo.
- **Transcription.** Claude does the first pass and adds tempo and key self-checks. The user corrects it in FL or Melodyne, or transcribes it themselves.
- **Can't listen, stated precisely.** The agreement now says what Claude can verify from numbers and images, and what is left to the user's ear. LISTEN steps say what to listen for, and `out/review.html` gathers them.
- **Smaller fixes:**
  - laughs are cut at envelope dips using the 6/1/4/3 structure, not at silence;
  - bed B (`yt − hum`) is a fallback if `yt` has sounds the stems lack;
  - `p3` can serve as the guide directly where there's no narration;
  - PSOLA is a fallback render engine;
  - the dependencies use uv and `pyproject.toml`.
