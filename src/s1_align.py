"""Stage 1: put the bed and the guide on the YouTube clock.

The stems are the uploader's lossless WAVs (config `stems`): bed = 伴奏 (music + effects), guide = 人声
(humming + breaths + narration), and bed + guide = 原音乐 exactly. Nothing is separated or edited here:
only alignment and one gain per stem (the user's rule: never split sources by editing spectra).

Lag convention: "x sits at lag L on ref's clock" means ref[n] ≈ x[n - L], i.e. x's sample 0 lands at ref sample L.
"""
import numpy as np
from scipy import signal

from . import common as C

LANDMARKS = [(74, "1:14"), (87, "1:27"), (102, "1:42"), (117, "1:57")]
SEARCH = 0.05        # s, fine search range around the coarse lag


# ---------------------------------------------------------------- cross-correlation

def xcorr_coarse(ref, x, sr_low=8000):
    """Coarse lag on 8 kHz mono copies. Returns (lag in 48 kHz samples, sign, (lags_s, curve) for plotting)."""
    q = C.SR // sr_low
    a, b = signal.resample_poly(ref, 1, q), signal.resample_poly(x, 1, q)
    z = signal.correlate(a, b, mode="full", method="fft") / np.sqrt(np.sum(a * a) * np.sum(b * b))
    lags = signal.correlation_lags(len(a), len(b), mode="full")
    k = int(np.argmax(np.abs(z)))
    keep = np.abs(lags - lags[k]) <= 2 * sr_low  # ±2 s around the peak, for the plot
    return int(lags[k]) * q, float(np.sign(z[k])), (lags[keep] / sr_low, z[keep])


def xcorr_fine(ref, x, lag0, span=None, search=SEARCH):
    """Refine a lag at 48 kHz within ±search s, with parabolic sub-sample interpolation.

    span: (start, end) sample range of x to use. Returns (fractional lag, (offsets_ms, curve), peak value).
    """
    w = int(search * C.SR)
    a0, a1 = span or (0, len(x))
    xs = x[a0:a1]
    r0, r1 = a0 + lag0 - w, a1 + lag0 + w
    rs = np.zeros(r1 - r0)
    s0, s1 = max(r0, 0), min(r1, len(ref))
    rs[s0 - r0:s1 - r0] = ref[s0:s1]
    z = signal.correlate(rs, xs, mode="valid", method="fft")
    z = z / (np.sqrt(np.sum(xs * xs) * np.sum(rs * rs)) + 1e-20)
    k = int(np.argmax(z))
    d = 0.0
    if 0 < k < len(z) - 1:
        y0, y1, y2 = z[k - 1:k + 2]
        d = 0.5 * (y0 - y2) / (y0 - 2 * y1 + y2)
    offsets_ms = (np.arange(len(z)) - w) / C.SR * 1000
    return lag0 - w + k + d, (offsets_ms, z), float(z[k])


def drift(ref, x, lag, win_s=10.0, hop_s=15.0):
    """Local lag minus the global lag, measured in windows along x. Detects clock drift between encodes."""
    out = []
    n, h = int(win_s * C.SR), int(hop_s * C.SR)
    lag_i = int(round(lag))
    peak = np.max(np.abs(x))
    for a in range(0, len(x) - n, h):
        seg = x[a:a + n]
        if np.sqrt(np.mean(seg ** 2)) < peak * 10 ** (-45 / 20):
            continue  # too quiet to measure
        if a + lag_i - int(SEARCH * C.SR) < 0 or a + n + lag_i + int(SEARCH * C.SR) > len(ref):
            continue
        local, _, peak_corr = xcorr_fine(ref, x, lag_i, span=(a, a + n))
        out.append({"t_x": (a + n / 2) / C.SR, "dev_samples": local - lag, "corr": peak_corr})
    return out


# ---------------------------------------------------------------- helpers

def fit(target, comps, sl):
    """Least-squares gains so that target ≈ Σ g_i·comp_i over slice sl. Returns (gains, residual dB re target)."""
    A = np.stack([c[sl].ravel() for c in comps], 1)
    b = target[sl].ravel()
    g, *_ = np.linalg.lstsq(A, b, rcond=None)
    return [float(v) for v in g], C.db(np.mean((b - A @ g) ** 2) / np.mean(b ** 2))


def envelope_db(x, win=0.01):
    """Level per window of a mono signal, in dBFS, with window centres in seconds."""
    n = int(win * C.SR)
    m = len(x) // n
    p = np.mean(x[:m * n].reshape(m, n) ** 2, 1)
    return (np.arange(m) + 0.5) * win, 10 * np.log10(p + 1e-20)


# ---------------------------------------------------------------- stage

def run(cfg):
    C.ensure_dirs()
    work = C.WORK / "stems"
    st = cfg["stems"]
    ids = [st["bed"], st["guide"], st["reference"]]
    print("loading WAVs …", flush=True)
    yt = C.read_wav(C.RAW / "yt.wav")
    src = {k: C.read_wav(C.RAW / f"{k}.wav") for k in ids}
    N = len(yt)
    rep, curves = {"stems": st, "lags": {}}, {}

    # 1. offsets: each stem directly against yt ----------------------------------
    Y = {}
    for k, x in src.items():
        c, sgn, curves[f"{k}→yt coarse"] = xcorr_coarse(C.mono(yt), C.mono(x))
        lag, curves[f"{k}→yt fine"], peak = xcorr_fine(C.mono(yt), C.mono(x), c)
        rep["lags"][k] = {"coarse_samples": c, "lag_samples": round(lag, 3), "lag_s": round(lag / C.SR, 6),
                          "peak_corr": round(peak, 3), "polarity": sgn}
        Y[k] = C.place(x, lag, N)
        print(f"{k} sits at {lag:10.2f} samples ({lag / C.SR:8.4f} s) on the yt clock, peak corr {peak:.3f}", flush=True)
    d = drift(C.mono(yt), C.mono(src[st["bed"]]), rep["lags"][st["bed"]]["lag_samples"])
    rep["lags"][st["bed"]]["drift_max_abs_samples"] = round(max(abs(e["dev_samples"]) for e in d), 3)
    span = (max(v["lag_s"] for v in rep["lags"].values()),
            min(v["lag_s"] + len(src[k]) / C.SR for k, v in rep["lags"].items()))
    rep["stems_span_s"] = [round(span[0], 3), round(span[1], 3)]
    seg_a, seg_b = cfg["segment"]["start"], cfg["segment"]["end"]
    assert span[0] < seg_a and seg_b < span[1], f"the stems ({span}) do not cover the segment"
    del src

    # 2. how the stems relate ------------------------------------------------------
    seg = slice(C.sec(seg_a), C.sec(seg_b))
    allsp = slice(C.sec(span[0] + 1), C.sec(span[1] - 1))
    bed, guide, ref = Y[st["bed"]], Y[st["guide"]], Y[st["reference"]]
    rep["fits"] = {}
    for name, target, comps in [("reference ≈ bed + guide", ref, (bed, guide)),
                                ("yt ≈ reference", yt, (ref,)),
                                ("yt ≈ bed + guide", yt, (bed, guide))]:
        for where, sl in (("segment", seg), ("all", allsp)):
            g, r = fit(target, list(comps), sl)
            rep["fits"][f"{name} ({where})"] = {"gains": [round(v, 4) for v in g], "residual_db": round(r, 1)}
    (gb, gg), _ = fit(yt, [bed, guide], seg)

    # 3. export, scaled to the yt mix --------------------------------------------
    rep["gains"] = {"bed": round(gb, 4), "guide": round(gg, 4)}
    files = {"yt_original.wav": yt, "bed.wav": gb * bed, "hum_guide.wav": gg * guide}
    print("writing stems …", flush=True)
    for name, x in files.items():
        C.write_wav(work / name, x)
        C.daw_link(work / name, name)
    rep["files"] = {k: f"out/daw/{k}" for k in files}
    rep["note"] = (f"bed = {st['bed']} (music + effects), hum_guide = {st['guide']} (humming + breaths + narration), "
                   "both aligned to the YouTube clock and scaled by one gain; nothing else is done to them. "
                   "Every file starts at t = 0 of the YouTube video.")
    C.write_json(C.REPORTS / "align.json", rep)

    # 4. plots ---------------------------------------------------------------
    plot_xcorr(curves, ids)
    plot_drift(d)
    plot_edges(yt, gb * bed + gg * guide, gg * guide, (seg_a, seg_b))
    C.review_section("1", "Stage 1: stems on the YouTube clock (nothing to listen to)", [
        {"kind": "text", "note": f"bed.wav is {st['bed']} and hum_guide.wav is {st['guide']}, "
                                 "aligned to the YouTube clock and otherwise untouched."},
        {"kind": "image", "path": "plots/align_edges.png", "note": "yt against bed + guide at the excerpt edges."},
    ])
    summarise(rep)


# ---------------------------------------------------------------- plots and summary

def plot_xcorr(curves, names):
    plt = C.plt()
    fig, ax = plt.subplots(len(names), 2, figsize=(11, 7))
    for i, nm in enumerate(names):
        x, z = curves[f"{nm}→yt coarse"]
        ax[i, 0].plot(x, z, lw=0.6)
        ax[i, 0].set_title(f"{nm} vs yt: coarse correlation (8 kHz), ±2 s around the peak")
        ax[i, 0].set_xlabel("lag (s)")
        x, z = curves[f"{nm}→yt fine"]
        ax[i, 1].plot(x, z, lw=0.8)
        ax[i, 1].set_xlim(-2, 2)
        ax[i, 1].set_title(f"{nm} vs yt: fine correlation (48 kHz), ±2 ms around the coarse lag")
        ax[i, 1].set_xlabel("offset from coarse lag (ms)")
    fig.tight_layout()
    fig.savefig(C.PLOTS / "align_xcorr.png")
    plt.close(fig)


def plot_drift(d):
    plt = C.plt()
    fig, ax = plt.subplots(figsize=(10, 3))
    ax.plot([e["t_x"] for e in d], [e["dev_samples"] for e in d], "o-", ms=3)
    ax.set_xlabel("time on the bed's clock (s)")
    ax.set_ylabel("local − global lag (samples)")
    ax.set_title("Clock drift between the bed and yt (flat = no drift)")
    fig.tight_layout()
    fig.savefig(C.PLOTS / "align_drift.png")
    plt.close(fig)


def plot_edges(yt, reb, vocals, edges):
    plt = C.plt()
    fig, ax = plt.subplots(3, 2, figsize=(12, 8))
    for j, e in enumerate(edges):
        s = slice(C.sec(e - 1), C.sec(e + 1))
        tt = np.arange(s.start, s.stop) / C.SR
        ax[0, j].plot(tt, C.mono(yt[s]), lw=0.6, label="yt")
        ax[0, j].plot(tt, C.mono(reb[s]), lw=0.6, label="bed + guide", alpha=0.8)
        ax[0, j].set_title(f"excerpt edge at {e:.2f} s, ±1 s")
        s = slice(C.sec(e - 0.01), C.sec(e + 0.01))
        tt = np.arange(s.start, s.stop) / C.SR
        ax[1, j].plot(tt, C.mono(yt[s]), lw=0.8, label="yt")
        ax[1, j].plot(tt, C.mono(reb[s]), lw=0.8, label="bed + guide", alpha=0.8)
        ax[1, j].set_title(f"excerpt edge at {e:.2f} s, ±10 ms")
        t, lev = envelope_db(C.mono(vocals[C.sec(e - 1):C.sec(e + 1)]))
        ax[2, j].plot(t + e - 1, lev, lw=0.8, color="C2")
        ax[2, j].axvline(e, color="C3", lw=1)
        ax[2, j].set_ylim(-100, -10)
        ax[2, j].set_title("vocal level (guide, dBFS)")
        for i in (0, 1):
            ax[i, j].legend(loc="upper right")
    fig.tight_layout()
    fig.savefig(C.PLOTS / "align_edges.png")
    plt.close(fig)


def summarise(rep):
    print("\nOffsets on the yt clock")
    for k, v in rep["lags"].items():
        extra = f", drift ≤ {v['drift_max_abs_samples']} samples" if "drift_max_abs_samples" in v else ""
        print(f"  {k:12s} {v['lag_samples']:10.2f} samples ({v['lag_s']:.4f} s), corr {v['peak_corr']}{extra}")
    print("Fits (residual, lower is better)")
    for k, v in rep["fits"].items():
        print(f"  {k:36s} gains {v['gains']}  residual {v['residual_db']} dB")
    print(f"Gains used: {rep['gains']}")
