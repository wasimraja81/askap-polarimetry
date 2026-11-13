#!/usr/bin/env python
"""Movie of the leakage measurement, one frame per SBID in observation order.

Each frame shows, for one SBID, the fractional polarisation of its components
against Stokes I, the p10 and p25 point in each Stokes I bin, the fitted
c + a/I curves and the resulting leakage c, with a card of the SBID's metadata
and a strip with the whole history and a cursor at the current SBID. The axes
are the same in every frame. The faint curves are the p10 and p25 fits of all SBIDs
pooled, a fixed reference; the dotted horizontal lines and their labels at the
left mark the pooled c.

SBIDs without a filtered.csv get a frame that says so.
"""
import argparse
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.animation as animation
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

import leakage

P10, P25 = "tab:purple", "tab:orange"
XLIM = (leakage.BINS[0], leakage.BINS[-1])
YLIM = (0.02, 30)


def parse_args():
    p = argparse.ArgumentParser(description="Render the leakage movie.")
    p.add_argument("--table", default="results/sbs_all_time_ordered.csv")
    p.add_argument("--filtered_dir", required=True, help="Directory with filtered_SB<id>.csv files")
    p.add_argument("--output", default="movies/leakage_history.mp4")
    p.add_argument("--fps", type=int, default=12)
    p.add_argument("--dpi", type=int, default=100)
    p.add_argument("--limit", type=int, default=0, help="Render only the first N frames (testing)")
    p.add_argument("--first", type=int, default=0, help="Index of the first frame (testing)")
    return p.parse_args()


def pooled_reference(table, filtered_dir):
    """p10 and p25 of every bin and their fits, for all SBIDs pooled."""
    flux, frac = [], []
    for sb in table.SB[table.has_filtered_csv]:
        f, r = leakage.read_components(os.path.join(filtered_dir, f"filtered_SB{sb}.csv"))
        flux.append(f)
        frac.append(r)
    flux, frac = np.concatenate(flux), np.concatenate(frac)
    xs = np.logspace(np.log10(XLIM[0]), np.log10(XLIM[1]), 200)
    ref = {}
    for pct in (10, 25):
        y = leakage.binned_percentile(flux, frac, 10, pct)
        c, a, c_err, _ = leakage.fit_params(flux, frac, percentile=pct)
        ref[pct] = (y, c + a / xs, c, c_err)
    return ref, xs


def card_text(row, ref, n_pooled):
    def val(key, fmt="{}"):
        v = row[key]
        return "-" if pd.isna(v) else fmt.format(v)
    lines = [
        f"SBID        {row.SB}",
        f"field       {row.field}",
        f"UTC         {row.date_utc}",
        f"AWST        {row.date_local_awst}",
        f"quality     {row.status}",
        "",
        f"ASKAPsoft   {val('askapsoft_version')}",
        f"pipeline    {val('pipeline_version')}",
        f"POLVAL      {val('polval_version')}",
        f"holography  {val('holography_model_sb')}",
        f"run stamp   {val('pipeline_run_first')}",
        "",
    ]
    pooled = [f"all {int(n_pooled)} SBIDs pooled:", f"  p10  c = {ref[10][2]:.2f} %", f"  p25  c = {ref[25][2]:.2f} %"]
    if row.has_filtered_csv:
        lines += [
            f"components  {val('n_components', '{:.0f}')}",
            f"  above 50 mJy/beam  {val('n_above_50mJy', '{:.0f}')}",
            "",
            f"p10  c = {row.c_p10_pct:.2f} +- {row.c_p10_err:.2f} %",
            f"p25  c = {row.c_p25_pct:.2f} +- {row.c_p25_err:.2f} %",
        ]
        if not pd.isna(row.c_p10_sbid_median):
            lines += ["", f"month {row.month}: {val('n_sb_in_month', '{:.0f}')} SBIDs",
                      f"  median p10 {row.c_p10_sbid_median:.2f} %",
                      f"  median p25 {row.c_p25_sbid_median:.2f} %"]
    else:
        lines += ["no filtered.csv available", "for this SBID"]
    return "\n".join(lines + [""] + pooled)


def main():
    args = parse_args()
    table = pd.read_csv(args.table)
    table["obs"] = pd.to_datetime(table.date_utc)
    assert table.obs.is_monotonic_increasing, "table must be in observation order"
    ref, xs = pooled_reference(table, args.filtered_dir)

    fig = plt.figure(figsize=(12.8, 7.2))
    gs = fig.add_gridspec(2, 2, width_ratios=[3, 1.25], height_ratios=[3.2, 1], hspace=0.28, wspace=0.05,
                          left=0.07, right=0.98, top=0.93, bottom=0.08)
    ax = fig.add_subplot(gs[0, 0])
    axc = fig.add_subplot(gs[0, 1]); axc.axis("off")
    axt = fig.add_subplot(gs[1, :])

    # Fixed elements of the main panel.
    ax.set_xscale("log"); ax.set_yscale("log")
    ax.set_xlim(XLIM); ax.set_ylim(YLIM)
    ax.set_xlabel("Stokes I (mJy/beam)")
    ax.set_ylabel("Fractional polarisation (%)")
    ax.grid(alpha=.3, which="major")
    for pct, colour in ((25, P25), (10, P10)):
        y, curve, c, c_err = ref[pct]
        ax.plot(xs, curve, "-", color=colour, lw=1, alpha=.25, label=f"all SBIDs pooled, p{pct} fit")
        ax.axhline(c, color=colour, lw=1, ls=":", alpha=.45)
        ax.text(XLIM[0], c, f"  all SBIDs pooled, p{pct}: c = {c:.3f} +- {c_err:.3f} %", color=colour, alpha=.8,
                va="top", ha="left", fontsize=8)
    sc = ax.scatter([], [], s=6, color="lightgray", label="components of this SBID", zorder=1)
    pts, fits, hlines, ctexts = {}, {}, {}, {}
    for pct, colour, marker in ((25, P25, "s"), (10, P10, "o")):
        pts[pct], = ax.plot([], [], marker, color=colour, mec="k", ms=6, zorder=3,
                            label=f"p{pct} point (one Stokes I bin)")
        fits[pct], = ax.plot([], [], "--", color=colour, lw=1.4, zorder=2, label=f"p{pct} fit: c + a/I")
        hlines[pct] = ax.axhline(np.nan, color=colour, lw=1, ls=":")
        ctexts[pct] = ax.text(XLIM[1], np.nan, "", color=colour, va="bottom", ha="right", fontsize=10, fontweight="bold")
    ax.legend(loc="upper right", fontsize=7.5)
    note = ax.text(0.5, 0.5, "", transform=ax.transAxes, ha="center", va="center", fontsize=14, color="gray")
    title = ax.set_title("", fontsize=11)
    card = axc.text(0.0, 1.0, "", va="top", ha="left", family="monospace", fontsize=9.5, transform=axc.transAxes)

    # History strip with a cursor.
    valid = table[table.has_filtered_csv]
    axt.plot(valid.obs, valid.c_p25_pct, ".", color=P25, ms=3, alpha=.6, label="p25")
    axt.plot(valid.obs, valid.c_p10_pct, ".", color=P10, ms=3, alpha=.6, label="p10")
    axt.set_ylim(bottom=0)
    axt.set_ylabel("c (%)")
    axt.set_xlim(table.obs.min() - pd.Timedelta(days=15), table.obs.max() + pd.Timedelta(days=15))
    axt.xaxis.set_major_locator(mdates.MonthLocator(bymonth=[1, 4, 7, 10]))
    axt.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))
    axt.tick_params(axis="x", labelsize=8)
    axt.grid(alpha=.3)
    axt.legend(loc="upper left", fontsize=7, ncol=2)
    cursor = axt.axvline(table.obs.iloc[0], color="crimson", lw=1.2)
    dot10, = axt.plot([], [], "o", color=P10, mec="k", ms=7)
    dot25, = axt.plot([], [], "s", color=P25, mec="k", ms=7)

    def draw(i):
        row = table.iloc[i]
        title.set_text(f"SBID {row.SB}   {row.field}   {row.date_utc} UTC   ({i + 1} of {len(table)})")
        card.set_text(card_text(row, ref, table.has_filtered_csv.sum()))
        cursor.set_xdata([row.obs, row.obs])
        if row.has_filtered_csv:
            flux, frac = leakage.read_components(os.path.join(args.filtered_dir, f"filtered_SB{row.SB}.csv"))
            keep = frac > 0
            sc.set_offsets(np.column_stack([flux[keep], frac[keep]]))
            note.set_text("")
            for pct in (10, 25):
                y = leakage.binned_percentile(flux, frac, 10, pct)
                c, a, _, _ = leakage.fit_params(flux, frac, percentile=pct)
                pts[pct].set_data(leakage.CENTRES, y)
                fits[pct].set_data(xs, c + a / xs)
                hlines[pct].set_ydata([c, c])
                ctexts[pct].set_position((XLIM[1], c)); ctexts[pct].set_text(f" c = {c:.2f} %")
            dot10.set_data([row.obs], [row.c_p10_pct]); dot25.set_data([row.obs], [row.c_p25_pct])
        else:
            sc.set_offsets(np.empty((0, 2)))
            note.set_text("no filtered.csv available for this SBID")
            for pct in (10, 25):
                pts[pct].set_data([], []); fits[pct].set_data([], [])
                hlines[pct].set_ydata([np.nan, np.nan]); ctexts[pct].set_text("")
            dot10.set_data([], []); dot25.set_data([], [])

    first = args.first
    last = len(table) if not args.limit else min(len(table), first + args.limit)
    os.makedirs(os.path.dirname(args.output) or ".", exist_ok=True)
    writer = animation.FFMpegWriter(fps=args.fps, codec="libx264", bitrate=-1,
                                    extra_args=["-pix_fmt", "yuv420p", "-crf", "20"])
    with writer.saving(fig, args.output, args.dpi):
        for i in range(first, last):
            draw(i)
            writer.grab_frame()
            if (i - first + 1) % 50 == 0:
                print(f"  frame {i - first + 1}/{last - first}", flush=True)
    print(f"{last - first} frames written to {args.output}")


if __name__ == "__main__":
    main()
