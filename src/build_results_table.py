#!/usr/bin/env python
"""Build the per-SBID results table: one row per EMU SBID in time order with
the observation time, quality flag, software versions and the leakage upper
limit measured from that SBID's filtered.csv.

Rows are in order of OBSERVATION time (start of the observation), not SBID or
processing order. Processing can happen later, or be repeated with a newer
software version; the pipeline run stamps are kept as separate columns.

Leakage columns: c_p10 and c_p25 are the leakage upper limits (percent of
Stokes I) from the 10th and 25th percentile of fractional polarisation; p25
is higher because it includes more intrinsically polarised sources.

Inputs:  sbid_metadata.csv (from sbid_metadata.py) and a directory of
         filtered_SB<id>.csv files (from download_filtered.py).
Output:  one CSV; SBIDs without a filtered.csv have empty leakage columns.
"""
import argparse
import os

import numpy as np
import pandas as pd

import leakage


def parse_args():
    p = argparse.ArgumentParser(description="Build the per-SBID leakage results table.")
    p.add_argument("--metadata", default="results/sbid_metadata.csv")
    p.add_argument("--filtered_dir", required=True, help="Directory with filtered_SB<id>.csv files")
    p.add_argument("--output", default="results/sbs_all_time_ordered.csv")
    p.add_argument("--n_boot", type=int, default=100, help="Resamples for the monthly range")
    p.add_argument("--seed", type=int, default=1)
    return p.parse_args()


def main():
    args = parse_args()
    md = pd.read_csv(args.metadata)
    md["SB"] = md.SB.astype(int)
    md = md.sort_values("mjd_start", kind="stable").reset_index(drop=True)
    assert md.mjd_start.is_monotonic_increasing and md.SB.is_unique
    md["obs_index"] = np.arange(len(md))

    per_sb, rows = {}, []
    for sb in md.SB:
        path = os.path.join(args.filtered_dir, f"filtered_SB{sb}.csv")
        if not os.path.exists(path):
            rows.append((sb,) + (np.nan,) * 7)
            continue
        flux, frac = leakage.read_components(path)
        per_sb[sb] = (flux, frac)
        c10, e10, nbins = leakage.fit_leakage(flux, frac, percentile=10)
        c25, e25, _ = leakage.fit_leakage(flux, frac, percentile=25)
        rows.append((sb, c10, e10, c25, e25, int((flux >= 50).sum()), nbins, len(flux)))
    fit = pd.DataFrame(rows, columns=["SB", "c_p10_pct", "c_p10_err", "c_p25_pct", "c_p25_err",
                                      "n_above_50mJy", "fit_nbins", "n_components"])

    t = md.merge(fit, on="SB", how="left")
    assert (t.SB.values == md.SB.values).all()
    t["has_filtered_csv"] = t.c_p10_pct.notna()
    t["month"] = pd.to_datetime(t.mjd_start + 2400000.5, unit="D", origin="julian").dt.to_period("M").astype(str)
    month_of = dict(zip(t.SB, t.month))
    for pct in (10, 25):
        monthly = leakage.pooled_monthly(per_sb, month_of, n_boot=args.n_boot, seed=args.seed, percentile=pct)
        for k, suffix in enumerate(["", "_lo16", "_hi84"]):
            t[f"c_p{pct}_monthly{suffix}"] = t.month.map({m: v[k] for m, v in monthly.items()})
        if pct == 10:
            t["n_sb_in_month"] = t.month.map({m: v[3] for m, v in monthly.items()})
        # Spread of the per-SBID values in each month that has a pooled value.
        per_sb_c = t.loc[t.month.isin(monthly), ["month", f"c_p{pct}_pct"]].dropna().groupby("month")[f"c_p{pct}_pct"]
        stats = per_sb_c.agg(mean="mean", median="median", p16=lambda x: x.quantile(.16), p84=lambda x: x.quantile(.84),
                             min="min", max="max", std="std")
        for name in stats.columns:
            t[f"c_p{pct}_sbid_{name}"] = t.month.map(stats[name])

    t["date_utc"] = t.date_utc.str[:16]
    t["date_local_awst"] = t.date_local.astype(str).str[:16]
    t["holography_model_sb"] = t.holography_model.str.extract(r"(SB\d+)", expand=False)
    t = t.rename(columns={"pipeline_stamp_first": "pipeline_run_first", "pipeline_stamp_last": "pipeline_run_last",
                          "n_pipeline_runs": "n_pipeline_runs"})
    cols = ["obs_index", "SB", "field", "status", "date_utc", "date_local_awst",
            "c_p10_pct", "c_p10_err", "c_p25_pct", "c_p25_err", "n_above_50mJy", "n_components", "fit_nbins",
            "has_filtered_csv", "askapsoft_version", "pipeline_version", "polval_version", "holography_model_sb",
            "pipeline_run_first", "pipeline_run_last", "n_pipeline_runs", "frac_sun_up", "month",
            "c_p10_monthly", "c_p10_monthly_lo16", "c_p10_monthly_hi84",
            "c_p25_monthly", "c_p25_monthly_lo16", "c_p25_monthly_hi84", "n_sb_in_month"]
    cols += [f"c_p{pct}_sbid_{n}" for pct in (10, 25) for n in ("mean", "median", "p16", "p84", "min", "max", "std")]
    os.makedirs(os.path.dirname(args.output) or ".", exist_ok=True)
    t[cols].to_csv(args.output, index=False)
    print(f"{len(t)} SBIDs ({int(t.has_filtered_csv.sum())} with a fit) written to {args.output}")


if __name__ == "__main__":
    main()
