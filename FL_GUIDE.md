# coronal-otto in FL Studio

Everything you need is in `out/fl/`, and `out/README.txt` lists every file. This guide walks through four exercises, from easiest to most hands-on. Each one teaches one part of FL Studio.

FL's menu names here are from memory, and they shift a little between versions. If something isn't exactly where this guide says, look nearby.

## 0. One rule: drop everything at bar 1

Every file in `out/fl/` is on **your own project's clock**: the clock `user/tuned.mid` came from. That means 135 BPM from bar 1, with the music's beats on the grid. So:

- New project, tempo **135**, 4/4.
- Drag a file in so it starts **at bar 1** (snap to the bar).
- Then everything lines up: your notes, the 伴奏, every Otto layer.

That clock runs **0.538 s ahead of the video**: the video's 0:00 sits at 0.538 s in FL. You never have to deal with that offset by hand; section 6 explains how a finished export gets back onto the video's clock.

Where things are on the grid:

| what | video | FL (bar.beat) |
|---|---|---|
| excerpt start (cut point) | 1:10.000 | 40.3.71 |
| first note | 1:14.13 | 43.1 |
| choir builds (2 → 3 layers) | 1:24.1 / 1:27.9 | 48.3.5 / 50.4 |
| 4 layers, the long notes | 1:41.9–1:52.0 | 58.3.5–64.3 |
| back to one voice | 1:56.4 | 66.4 |
| last phrase (3 layers) | 2:03.5 | 70.4 |
| excerpt end (cut point) | 2:08.000 | 73.2.21 |

## 1. Set up the project (10 min)

1. **Tempo** to 135 (the tempo box in the toolbar).
2. From Explorer, **drag these into the Playlist at bar 1:**
   - `bed.wav`
   - `otto_L0.wav` … `otto_L3.wav`
   - `otto_with_bed.wav`
   - optionally `original_humming.wav`

   Each becomes an audio clip on its own track.
3. **Import `otto_score.mid`** (File → Import → MIDI file, the way you opened my first MIDI). It has four tracks:
   - the lead (layer 0),
   - doubles 1–3.

   The track names hold each double's pan, detune and level. The first note is at bar 43. The file also carries three markers: video 0:00, excerpt start and excerpt end. Whether FL shows them depends on its import options.
4. **Check the alignment.** Zoom in on bar 43:
   - The first "ha" in `otto_L0` begins a little *before* the note: that's the "h".
   - The vowel starts on the note.

   This is how a singer does it, and section 4 uses it.
5. **Check that FL didn't stretch anything.** All the WAV clips should end at the same place (2:10.5). If one ends somewhere else, FL time-stretched it: double-click the clip and reset its time-stretch settings.
6. **Mute `otto_with_bed`** (that's my mix, for comparing).

Press play from bar 40: with the 伴奏 and the four layers unmuted, it should sound like my mix without the reverb.

## 2. Exercise A: mix it yourself

*Mixer inserts, buses, pan, EQ, send effects, a limiter, and comparing by ear.*

**Routing.** Open the Mixer (F9). Give each clip's channel its own mixer insert: select the channel in the Channel Rack and press Ctrl+L, or set the channel's mixer-track number by hand.
- `bed` goes to insert 1.
- `otto_L0`–`L3` go to inserts 2–5.
- Insert 6 is the **Otto bus**. Send inserts 2–5 *only* to insert 6: select each one, then right-click the small arrow at the bottom of insert 6 and choose "route to this track only".
- Insert 6 goes to the Master.

A bus lets you treat four voices as one choir: one fader, one EQ, one reverb.

**Levels and pans.** The files are already at the levels I mixed them at (doubles −3 dB), so start with every fader at 0 dB. Then set the pans:

| insert | layer | pan | (baked into the file) |
|---|---|---|---|
| 2 | lead | centre | |
| 3 | double 1 | 40 % left | −6 cents, −3 dB |
| 4 | double 2 | 40 % right | +6 cents, −3 dB |
| 5 | double 3 | 80 % left | −12 cents, −3 dB |

The slight detune and the different "ha"s keep the doubles from collapsing into one voice. Panning spreads them out the way the original's overdubs are spread. (Double 3 only sings in 1:42–1:52. Panning it right instead would balance the four-voice part; try it.)

**EQ on the bus.** Put **Fruity Parametric EQ 2** in an effect slot of insert 6 and set band 1 to a high-pass at **80 Hz**. Otto's lowest note is D#3 (156 Hz), so anything below 80 Hz is just rumble from the stream's microphone.

**Reverb as a send.** Insert 7 is the **reverb**: put **Fruity Reeverb 2** on it and set it 100 % wet, 0 % dry.
- Send insert 6 to insert 7 as well as to the Master: left-click insert 7's arrow while insert 6 is selected, and a send knob appears.
- Turn the send down to about **−16 dB**. That's what I used: 15 % wet, a short room, about 1 s of decay.

Why a send? The dry choir stays untouched on its own fader, and the reverb gets its own fader to blend in. The original humming's reverb is short: where a rest is clean, it dies away in about 0.3 s. So keep the reverb light, or Otto drowns.

**Master.** **Fruity Limiter** with its ceiling at −1 dB is a safety net. In my mix it never acts: the loudest peak is −2.6 dB.

**Compare.** Solo your mix (the Master), then mute everything except `otto_with_bed`. Flip between the two. Volume tricks your ears (louder sounds "better"), so match the levels before you judge.

**Export.** File → Export → WAVE file. Choose Full song and 24-bit. Choose 48 kHz if the dialog offers it; if it doesn't, the `from-fl` step below converts it anyway.

## 3. Exercise B: retune one note

*Slicing clips, the clip's pitch control, Newtone.*

Say one note of the lead sounds off.
1. Find it. `out/plots/score.png` shows which "ha" sings each note; the table in section 0 gets you to the bar.
2. **Slice** `otto_L0` just before and just after that note with the slice tool (the knife). Do it in a rest if you can, or right where the next "h" starts.
3. The slice is now its own clip. Double-click it. In its time-stretch/pitch settings, turn **Pitch** by a few cents or semitones. For a voice, use a mode meant for monophonic sources ("E3 mono" or similar).

**Newtone** (FL's Melodyne; it comes with the Signature edition and up) does this properly. Load the layer or the slice into it, and it shows each note as a blob on a piano roll:
- Drag a blob up or down to retune it.
- Its controls can also flatten the pitch movement inside a note.

That flattening is exactly the choice you made between my versions:
- `natural` kept 100 % of the laugh's own movement.
- `flat` removed all of it.
- `half_full`, your pick, keeps half.

Newtone lets you decide that note by note.

## 4. Exercise C: build a note by hand (the real 人力VOCALOID craft)

*Working the way UTAU users and 鬼畜 makers do: one sample, placed, tuned and stretched.*

The material:
- `otto_L*_raw.wav`: every "ha" already sitting on its note, untouched (not tuned, not stretched). It's what my code started from.
- `units/`: every cut "ha" as a separate file. `units.csv` lists each one's own note: for example, `otto_03` is about E4, and `otto2_*` sit around G3–A3.

How to place one "ha" on a note:
1. **Timing: the preutterance.** A "ha" has a breathy "h", then the vowel "a". Your ear hears the vowel as the beat. So put the **vowel's start on the note**, which means the "h" starts *before* the beat. `units.csv` gives each unit's "h" length (`preutterance_ms`): usually a few tens of milliseconds, up to 200 ms. UTAU calls this 先行発声.
2. **Pitch.** Shift it by (the note − the unit's note) semitones, with the clip's Pitch control or in Newtone.

   The smaller the shift, the more natural it sounds. That's why my code prefers "ha"s that are already near the note, why low notes get `otto2` and high ones get `otto`, and why tired laughs go late in the song.
3. **Length.** A "ha" is about 0.2 s; a note can be 2 s.
   - If you stretch the whole clip, the "h" gets slow and mushy too.
   - The trick: slice the "ha" into the "h", the vowel, and the last few tens of milliseconds. Stretch **only the middle of the vowel**, and keep the start and the end at normal speed.

   That's exactly what my renderer does: "onset 1×, core stretched, release 1×".

Try one long note, for example the 2-second one at bar 59.3 (1:43.5). See how far you can stretch it by hand before it stops sounding like a laugh. In `half_full`, the version you picked, the lead's "ha" there is stretched 5.6×, and the doubles' shorter "ha"s up to 8×.

## 5. Exercise D: the old-school 鬼畜 way (Sampler + piano roll)

*Channel Rack, Sampler, root note, piano roll.*

1. Drag `units/otto_03.wav` onto the **Channel Rack**. It becomes a Sampler channel.
2. Set its **root note** to E4, the "ha"'s own pitch from `units.csv`. That's the key at which the sample plays unchanged; I believe you set it by right-clicking that key on the small keyboard in the channel settings.
3. Copy the lead's notes from `otto_score.mid` into this channel's piano roll and press play.

Every note now triggers the "ha" re-pitched, and pitch and speed are tied together:
- High notes come out faster and squeakier (the chipmunk effect).
- Low notes come out slower and darker.
- Long notes just stop when the sample runs out.

That *is* the classic 鬼畜 sound, and it shows what my WORLD renderer does differently. It separates the three things the Sampler ties together: pitch, timbre (Otto's "a") and time.

## 6. Back to the video

Export your mix from FL starting at bar 1 (Full song), then run:

```
uv run build.py from-fl --file "C:/path/to/your export.wav"
```

(or tell me the file). It finds where your export sits on the FL clock by matching it against the 伴奏, or against my Otto bus if you left the 伴奏 out. That works even for a selection that starts somewhere in the middle. It then writes two files to `out/from_fl/`:
- `<name>_video_full.wav`, from the video's 0:00;
- `<name>_1m10-2m08.wav`, the excerpt.

Doing it by hand: in your video editor, put the FL export **0.538 s earlier** than the video.

## 7. If you change the notes or want a re-render

- **New notes:** save the edited MIDI from FL over `user/tuned.mid` (same project, same clock) and tell me. I re-run notes → score → render → mix → deliver.
- **Reverb amount, Otto's level:** `config.yaml` → `mix:` has `reverb.wet` (0 = dry, as in the Stage 5 previews) and `level_offset_db` (+ = louder Otto). Then run `uv run build.py mix` and `uv run build.py deliver`.
- **Which "ha" sings which note:** `score.json` (`"unit"` for each note and layer), then `uv run build.py render`, then `mix`, then `deliver`.
