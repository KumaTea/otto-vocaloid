# coronal-otto

Read PLAN.md; follow its working agreement. All stages done 2026-10-10. The user picked the render `half_full` (alpha 0.5, full stretch). Stage 6 mix → out/final/ (the deliverables); Stage 7 `deliver` → out/fl/ (FL Studio set on the user's project clock), out/README.txt; FL_GUIDE.md is the user's FL walkthrough. blog/ is the user's technical blog post (index.html, plus index.zh.html in Chinese; style.css and charts.js are hand-written, and chart labels need an entry in charts.js's ZH_TEXT; data.js and audio/ come from `build.py blog`). Waiting for the user's listen to the final mix. The user writes no code: their learning goal is FL Studio. Stage 1 is done: bed = 伴奏 (w_bed), guide = 人声 (w_vocals), lossless; the result is the excerpt 1:10–2:08 with no narration.
Never separate sources by editing spectra in Python (the user's rule); see PLAN.md Stage 1.
Reports: out/reports/sources.json, out/reports/align.json. Listening page: out/review.html.

- Run stages with `uv run build.py <stage>`.
- `secrets/` holds the Bilibili login cookies: never print or copy their values.
