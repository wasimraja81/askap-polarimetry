#!/usr/bin/env python
"""Plots that record the historical instrumental leakage of ASKAP.

Facts only: no software, holography or day/night annotations (those are in
diagnostics/). All values are upper limits on the leakage, in percent of
Stokes I, assuming a constant leakage amplitude. p10 and p25 are the 10th and
25th percentile of fractional polarisation among all components, with no
polarisation S/N selection; p25 is higher because it includes more
intrinsically polarised sources.

Figures written to --outdir:
  history_timeline.png      per-SBID p10 and p25 against observation date, with monthly pooled values
  history_overall.png       all components pooled: fractional polarisation against Stokes I
  history_monthly_stats.png per-month statistics of the per-SBID values (mean, median, std, 16-84%, min-max)
  history_distribution.png  histogram of per-SBID leakage
  history_coverage.png      SBIDs per month with and without a leakage measurement
"""
import argparse
import glob
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

import leakage

P10, P25 = "tab:purple", "tab:orange"


def parse_args():
    p = argparse.ArgumentParser(description="Plot the historical ASKAP instrumental leakage.")
    p.add_argument("--table", default="results/sbs_all_time_ordered.csv")
    p.add_argument("--filtered_dir", required=True, help="Directory with filtered_SB<id>.csv files")
    p.add_argument("--outdir", default="figures")
    return p.parse_args()


def date_axis(ax, lo, hi):
    ax.set_xlim(lo, hi)
    ax.xaxis.set_major_locator(mdates.MonthLocator(bymonth=[1, 4, 7, 10]))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))
    ax.tick_params(axis="x", labelsize=8, labelrotation=45)


def timeline(t, out):
    f = t.dropna(subset=["c_p10_pct"])
    mo = t.dropna(subset=["c_p10_monthly"]).groupby("month").first().reset_index()
    mo["date"] = mo.month.map(t.obs.groupby(t.month).mean())
    fig, ax = plt.subplots(figsize=(12, 6))
    ax.errorbar(f.obs, f.c_p25_pct, f.c_p25_err, fmt="o", ms=3, color=P25, alpha=.25, lw=.4, label="p25, one SBID (bar: fit error)")
    ax.errorbar(f.obs, f.c_p10_pct, f.c_p10_err, fmt="o", ms=3, color=P10, alpha=.35, lw=.4, label="p10, one SBID (bar: fit error)")
    # Per month: thick translucent bar = 16th-84th percentile of the per-SBID values.
    for pct, colour, dx in ((25, P25, 3), (10, P10, -3)):
        x = mo.date + pd.Timedelta(days=dx)
        ax.vlines(x, mo[f"c_p{pct}_sbid_p16"], mo[f"c_p{pct}_sbid_p84"], color=colour, lw=7, alpha=.3,
                  label=f"p{pct}, month: 16-84% of the SBID values")
    for pct, colour in ((25, P25), (10, P10)):
        lo = (mo[f"c_p{pct}_monthly"] - mo[f"c_p{pct}_monthly_lo16"]).clip(lower=0)
        hi = (mo[f"c_p{pct}_monthly_hi84"] - mo[f"c_p{pct}_monthly"]).clip(lower=0)
        ax.errorbar(mo.date, mo[f"c_p{pct}_monthly"], [lo, hi], fmt="s-", color=colour, mec="k", ms=5, lw=1.5,
                    label=f"p{pct}, month: pooled fit (bar: bootstrap over SBIDs, 16-84%)")
    ax.set_ylim(bottom=0)
    ax.set_xlabel("Observation start (UTC)")
    ax.set_ylabel("Leakage amplitude (% of Stokes I)")
    ax.set_title(f"ASKAP instrumental leakage, {len(f)} SBIDs with a measurement")
    ax.grid(alpha=.3)
    ax.legend(loc="upper left", fontsize=7)
    date_axis(ax, t.obs.min() - pd.Timedelta(days=20), t.obs.max() + pd.Timedelta(days=20))
    fig.tight_layout()
    fig.savefig(out, dpi=110)
    plt.close(fig)


def monthly_stats(t, out):
    """Direct statistics of the per-SBID leakage values in each month, with the
    pooled fit of the month (bootstrap range) overlaid, for p10 and p25."""
    mo = t.dropna(subset=["c_p10_monthly"]).groupby("month").first().reset_index()
    mo["date"] = mo.month.map(t.obs.groupby(t.month).mean())
    fig, axes = plt.subplots(2, 1, figsize=(12, 8.5), sharex=True)
    for ax, pct, colour in zip(axes, (10, 25), (P10, P25)):
        g = lambda name: mo[f"c_p{pct}_sbid_{name}"]
        ax.vlines(mo.date, g("min"), g("max"), color="gray", lw=1, label="minimum to maximum over SBIDs")
        ax.vlines(mo.date, g("p16"), g("p84"), color=colour, lw=7, alpha=.35, label="16th to 84th percentile over SBIDs")
        ax.errorbar(mo.date, g("mean"), g("std"), fmt="D", ms=4, color="k", capsize=2, lw=1, label="mean +- 1 std over SBIDs")
        ax.plot(mo.date, g("median"), "o", ms=6, mfc=colour, mec="k", label="median over SBIDs")
        lo = (mo[f"c_p{pct}_monthly"] - mo[f"c_p{pct}_monthly_lo16"]).clip(lower=0)
        hi = (mo[f"c_p{pct}_monthly_hi84"] - mo[f"c_p{pct}_monthly"]).clip(lower=0)
        ax.errorbar(mo.date + pd.Timedelta(days=6), mo[f"c_p{pct}_monthly"], [lo, hi], fmt="s", ms=6, mfc="white",
                    mec=colour, mew=2, ecolor=colour, elinewidth=1.8, capsize=3,
                    label="pooled fit of the month (bar: bootstrap over SBIDs, 16th-84th percentile)")
        ax.set_ylim(bottom=0)
        ax.set_ylabel("Leakage amplitude (% of Stokes I)")
        ax.grid(alpha=.3)
        ax.legend(loc="upper left", fontsize=8, title=f"Leakage characterised by p{pct}")
        ax.set_title(f"p{pct}: the {pct}th percentile of fractional polarisation per Stokes I bin", fontsize=10, loc="right")
    fig.suptitle("Leakage per month: statistics over the SBIDs observed in the month, and the pooled fit "
                 "(months with at least 3 SBIDs)", fontsize=11)
    axes[1].set_xlabel("Observation month (UTC)")
    date_axis(axes[1], t.obs.min() - pd.Timedelta(days=20), t.obs.max() + pd.Timedelta(days=20))
    fig.tight_layout(rect=(0, 0, 1, 0.96))
    fig.savefig(out, dpi=110)
    plt.close(fig)


def overall(filtered_dir, out):
    flux, frac = [], []
    for path in sorted(glob.glob(os.path.join(filtered_dir, "filtered_SB*.csv"))):
        fl, fr = leakage.read_components(path)
        flux.append(fl)
        frac.append(fr)
    flux, frac = np.concatenate(flux), np.concatenate(frac)
    keep = (flux >= leakage.BINS[0]) & (flux < leakage.BINS[-1]) & (frac > 0)
    fig, ax = plt.subplots(figsize=(8.5, 6))
    xb = leakage.BINS
    xfine = np.logspace(np.log10(xb[0]), np.log10(xb[-1]), 80)
    yb = np.logspace(-2, 2.3, 80)
    h, _, _ = np.histogram2d(flux[keep], frac[keep], bins=[xfine, yb])
    ax.pcolormesh(xfine, yb, np.where(h.T > 0, h.T, np.nan), cmap="Greys", norm=matplotlib.colors.LogNorm(), rasterized=True)
    xs = np.logspace(np.log10(xb[0]), np.log10(xb[-1]), 200)
    summary = []
    for pct, colour in ((10, P10), (25, P25), (50, "tab:green")):
        y = leakage.binned_percentile(flux, frac, 10, pct)
        ax.plot(leakage.CENTRES, y, "o-", color=colour, ms=4, label=f"p{pct} of each Stokes I bin")
        if pct != 50:
            c, a, e, _ = leakage.fit_params(flux, frac, percentile=pct)
            ax.plot(xs, c + a / xs, "--", color=colour, lw=1)
            ax.axhline(c, color=colour, lw=.8, ls=":")
            summary.append(f"p{pct}: c = {c:.3f} +/- {e:.3f} %")
    ax.set_xscale("log"); ax.set_yscale("log")
    ax.set_xlabel("Stokes I (mJy/beam)")
    ax.set_ylabel("Fractional polarisation (%)")
    ax.set_title(f"All components of all SBIDs pooled ({keep.sum()} with positive polarisation)\n"
                 "Pooled over the whole history: mixes the epochs shown in the timeline", fontsize=10)
    ax.text(.97, .97, "\n".join(summary) + "\n(fit: c + a/I)", transform=ax.transAxes, ha="right", va="top",
            fontsize=9, bbox=dict(fc="white", ec="gray", alpha=.8))
    ax.legend(loc="lower left", fontsize=8)
    ax.grid(alpha=.3, which="major")
    fig.tight_layout()
    fig.savefig(out, dpi=110)
    plt.close(fig)
    return summary


def distribution(t, out):
    f = t.dropna(subset=["c_p10_pct"])
    hi = np.ceil(max(f.c_p10_pct.max(), f.c_p25_pct.max()) * 20) / 20
    bins = np.linspace(0, hi, 41)
    fig, ax = plt.subplots(figsize=(8, 5))
    ax.hist(f.c_p25_pct, bins=bins, color=P25, alpha=.6, label=f"p25 (median {f.c_p25_pct.median():.2f} %)")
    ax.hist(f.c_p10_pct, bins=bins, color=P10, alpha=.6, label=f"p10 (median {f.c_p10_pct.median():.2f} %)")
    ax.set_xlabel("Leakage upper limit per SBID (% of Stokes I)")
    ax.set_ylabel("Number of SBIDs")
    ax.set_title(f"Distribution over {len(f)} SBIDs")
    ax.legend()
    ax.grid(alpha=.3)
    fig.tight_layout()
    fig.savefig(out, dpi=110)
    plt.close(fig)


def coverage(t, out):
    g = t.groupby("month").agg(with_fit=("has_filtered_csv", "sum"), total=("SB", "size"))
    g["without"] = g.total - g.with_fit
    fig, ax = plt.subplots(figsize=(12, 4.5))
    x = pd.to_datetime(g.index)
    ax.bar(x, g.with_fit, width=25, color="tab:blue", label="leakage measured")
    ax.bar(x, g.without, width=25, bottom=g.with_fit, color="lightgray", label="no filtered.csv available")
    ax.set_ylabel("SBIDs per month")
    ax.set_xlabel("Observation month (UTC)")
    ax.set_title(f"Coverage: {int(g.with_fit.sum())} of {int(g.total.sum())} SBIDs have a leakage measurement")
    ax.legend()
    ax.set_ylim(0, g.total.max() * 1.1)
    ax.grid(alpha=.3, axis="y")
    date_axis(ax, x.min() - pd.Timedelta(days=20), x.max() + pd.Timedelta(days=20))
    fig.tight_layout()
    fig.savefig(out, dpi=110)
    plt.close(fig)


def main():
    args = parse_args()
    os.makedirs(args.outdir, exist_ok=True)
    t = pd.read_csv(args.table)
    t["obs"] = pd.to_datetime(t.date_utc)
    assert t.obs.is_monotonic_increasing, "table must be in order of observation time"
    timeline(t, os.path.join(args.outdir, "history_timeline.png"))
    monthly_stats(t, os.path.join(args.outdir, "history_monthly_stats.png"))
    summary = overall(args.filtered_dir, os.path.join(args.outdir, "history_overall.png"))
    distribution(t, os.path.join(args.outdir, "history_distribution.png"))
    coverage(t, os.path.join(args.outdir, "history_coverage.png"))
    print("pooled over all SBIDs:", "; ".join(summary))
    print(f"figures written to {args.outdir}")


if __name__ == "__main__":
    main()
