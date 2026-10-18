# Rebuilding the audio

On 2026-10-18 the media files (audio, video, plots) were deleted to save space. Everything that can't be downloaded again is still here; this note says how to get the rest back.

**Tested on 2026-10-18:** a clean rebuild from commit `17d3ff7` plus the files below, with every stage run in order.
- The four files in `out/final/` came out byte-for-byte identical (their hashes are in `REBUILD.sha256`).
- Every other WAV had identical samples. Their hashes still differ, because a 32-bit float WAV stores the time it was written in its header.

## What is still here

- The git repo: the code, `config.yaml`, `score.json`, `user/tuned.mid`.
- `data/raw/native/otto2.mp3`: the second laugh, from the otto-hzys fan site. It is kept because that site may not stay online. It fills 46 of the 176 notes in `score.json`.
- `out/reports/sources.json`: it tells `fetch` that otto2 is already there, and it records the formats that were downloaded.
- The small non-media files in `out/` (MIDI, CSV, JSON, `README.txt`, `review.html`). The stages rewrite them.
- `REBUILD.sha256`: the hashes, for `sha256sum -c`.

## Files to get again

| Put it at | Where it comes from | Used for |
|---|---|---|
| `data/raw/native/yt.webm` | YouTube `BEKGuF5tY9E`, format 251 (Opus, 48 kHz). `fetch` downloads it. | the master clock: the stems are aligned to it |
| `data/raw/native/otto.m4a` | Bilibili `BV1Zs411g7Kg` p1, format 30280 (AAC, 44.1 kHz), downloaded while logged in. `fetch` downloads it. | the 14 units of the first laugh |
| `data/raw/BV1QYgfzcEpF/原音乐.WAV` | the Baidu Netdisk share from the uploader of `BV1QYgfzcEpF`: copy by hand, same name | reference (伴奏 + 人声 = this) |
| `data/raw/BV1QYgfzcEpF/人声.wav` | the same share | the guide: humming + breaths + narration |
| `data/raw/BV1QYgfzcEpF/音乐无吟唱(伴奏).wav` | the same share | the bed under the laughs |
| `data/raw/BV1QYgfzcEpF/吟唱部分去除白厄被刀版.WAV` | the same share | places `tuned.mid` on the video's clock |
| `data/raw/BV1QYgfzcEpF/音乐加男声吟唱.WAV` | the same share | only `build.py blog` |
| `data/raw/BV1QYgfzcEpF/吟唱原版.WAV` | the same share | nothing now (hash kept for reference) |

The names must match exactly: `config.yaml` points at them.

No longer needed:
- the Bilibili parts `p1`/`p2`/`p3` and the splash animation `sp` (`config.yaml` still lists them; `fetch --only` skips them);
- the videos and clips that were in `data/` (the build never read them).

## Steps

Run these in the project folder. In Claude Code, type them with `!` in front.

1. `uv sync`: only needed if `.venv/` is gone.
2. `uv run build.py login`, then scan the QR code with the Bilibili app. Without a login, Bilibili may offer the Otto clip only in a lower format, and the laughs would come out slightly different.
3. Copy the Baidu files into `data/raw/BV1QYgfzcEpF/`.
4. `sha256sum -c --ignore-missing REBUILD.sha256`: the Baidu files and `otto2.mp3` should say `OK`.
5. `uv run build.py fetch --only yt,otto,otto2,w_orig,w_vocals,w_bed,w_chant_nostab`
   - A plain `fetch` stops at the first missing Baidu file.
   - For the blog, add `w_music_hum` to the list.
6. `sha256sum -c --ignore-missing REBUILD.sha256` again: `yt.webm` and `otto.m4a` should now say `OK` too.
   - If one fails, the site now serves a different encode.
   - The result will then sound the same, but its hashes in step 8 won't match.
7. Run the stages in order (`build.py all` doesn't exist):
   ```
   for s in align units transcribe notes stack score render mix deliver; uv run build.py $s; end
   ```
   That loop is for fish. In bash: `for s in align units transcribe notes stack score render mix deliver; do uv run build.py $s; done`
   - `score` keeps the existing `score.json`. Never pass `--force` here: it would overwrite the score.
   - `render` takes the longest.
8. `sha256sum -c REBUILD.sha256`: all 13 lines should say `OK`.
9. Optional: `uv run build.py blog` rewrites `blog/data.js` and `blog/audio/`.

If YouTube refuses the download, yt-dlp is probably out of date: `uv lock --upgrade-package yt-dlp`, then `uv sync`.
