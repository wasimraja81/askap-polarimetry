#!/usr/bin/env python
"""Leakage against observation time and against processing time (diagnostic).

Observations are processed some time after they are taken, and may be
reprocessed with a newer software version. If the leakage follows the software,
it should line up with processing time and not with observation time.

Panels (shared date axis):
  1. p10 leakage per SBID against OBSERVATION start.
  2. The same values against the PIPELINE RUN stamp (first run of the SBID).
  3. One bar per ASKAPsoft build from its first to last pipeline run stamp.
A second figure plots processing time against observation time, coloured by
the leakage; points off the diagonal are SBIDs processed later.

The pipeline run stamp is the timestamp in the CASDA evaluation file names;
its time zone is not stated there.
"""
import argparse

import matplotlib
matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


def parse_args():
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--table", default="results/sbs_all_time_ordered.csv")
    p.add_argument("--outdir", default="diagnostics/outputs")
    return p.parse_args()


def extent_bars(ax, t, col, label):
    """One bar per distinct value of `col` from its first to its last time in
    t[col + '_t0'/'_t1']; overlapping bars or labels go on separate rows."""
    g = t.groupby(col).agg(t0=("proc", "min"), t1=("proc", "max"), n=("SB", "size")).sort_values("t0")
    lanes, rows, texts = [], [], []
    for v, r in g.iterrows():
        text = f"{label(v)} (n={r.n})"
        half = pd.Timedelta(days=len(text) * 3.2)
        mid = r.t0 + (r.t1 - r.t0) / 2
        e0, e1 = min(r.t0, mid - half), max(r.t1, mid + half)
        for k, end in enumerate(lanes):
            if e0 > end:
                lanes[k] = e1; rows.append(k); break
        else:
            lanes.append(e1); rows.append(len(lanes) - 1)
        texts.append(text)
    colours = plt.cm.tab20(np.arange(20))
    for i, ((v, r), k, text) in enumerate(zip(g.iterrows(), rows, texts)):
        ax.barh(k, (r.t1 - r.t0) + pd.Timedelta(days=2), left=r.t0, height=.8, color=colours[i % 20],
                alpha=.85, edgecolor="k", lw=.4)
        ax.text(r.t0 + (r.t1 - r.t0) / 2, k, text, ha="center", va="center", fontsize=6.5)
    ax.set_ylim(-.6, len(lanes) - .4)
    ax.invert_yaxis()
    ax.set_yticks([])


def main():
    args = parse_args()
    t = pd.read_csv(args.table)
    t["obs"] = pd.to_datetime(t.date_utc)
    t["proc"] = pd.to_datetime(t.pipeline_run_first, format="%Y-%m-%d-%H%M%S")
    t["lag_days"] = (t.proc - t.obs).dt.total_seconds() / 86400
    f = t.dropna(subset=["c_p10_pct"])

    xlo = min(t.obs.min(), t.proc.min()) - pd.Timedelta(days=20)
    xhi = max(t.obs.max(), t.proc.max()) + pd.Timedelta(days=20)
    fig, ax = plt.subplots(3, 1, figsize=(13, 11), gridspec_kw={"height_ratios": [2, 2, 2.6]})
    for a, x, name in ((ax[0], "obs", "observation start (UTC)"), (ax[1], "proc", "pipeline run stamp")):
        a.errorbar(f[x], f.c_p10_pct, f.c_p10_err, fmt="o", ms=3, color="purple", alpha=.4, lw=.4)
        a.set_ylabel("p10 leakage c (%)")
        a.set_xlabel(name)
        a.grid(alpha=.3)
    extent_bars(ax[2], t, "askapsoft_version", lambda v: v.partition("-")[0] + ("-" + v.partition("-")[2][:8] if "-" in v else ""))
    ax[2].set_xlabel("pipeline run stamp (ASKAPsoft build extents)")
    ax[0].set_title("Leakage by observation time (top) and by processing time (middle)")
    for a in ax:
        a.set_xlim(xlo, xhi)
        a.xaxis.set_major_locator(mdates.MonthLocator(bymonth=[1, 4, 7, 10]))
        a.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))
        a.tick_params(axis="x", labelsize=8, labelrotation=45)
    fig.tight_layout()
    fig.savefig(f"{args.outdir}/obs_vs_processing_time.png", dpi=110)
    plt.close(fig)

    fig, a = plt.subplots(figsize=(7, 6.5))
    sc = a.scatter(f.obs, f.proc, c=f.c_p10_pct, s=10, cmap="viridis", vmin=0, vmax=0.5)
    lim = [xlo, xhi]
    a.plot(lim, lim, "k:", lw=.8)
    a.set_xlim(lim); a.set_ylim(lim)
    a.set_xlabel("observation start (UTC)"); a.set_ylabel("pipeline run stamp")
    a.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m")); a.yaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))
    a.tick_params(axis="x", labelrotation=45)
    fig.colorbar(sc, label="p10 leakage c (%), clipped at 0.5")
    a.set_title("Processing time against observation time")
    fig.tight_layout()
    fig.savefig(f"{args.outdir}/obs_vs_processing_scatter.png", dpi=110)

    print(f"{len(f)} SBIDs plotted; processing lag (days): median {f.lag_days.median():.1f}, "
          f"90th percentile {f.lag_days.quantile(.9):.1f}, max {f.lag_days.max():.1f}; "
          f"SBIDs processed more than 30 days after observation: {(f.lag_days > 30).sum()}")


if __name__ == "__main__":
    main()
