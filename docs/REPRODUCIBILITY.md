# Reproducibility of the earlier results

Reference: `~/DATA/askap-pol/test_output/` (August 2025).
Environment: Python 3.9.6, `requirements.txt` (pandas 2.3.3, numpy
1.26.4, scipy 1.13.1, matplotlib 3.9.4, astroquery 0.4.11). The
original library versions are not recorded.

Method: `src/download_filtered.py` run unchanged, with the 479
existing `filtered_SB*.csv` linked into a fresh output directory
(`data/repro_snr*`), so nothing in the source directory was modified.
The input files in `filtered_files/` and `test_output/` are
byte-identical (checked by file list and `cmp` on one file).

## Findings

1. **The settings differ from the script defaults.** With the default
   `--polSNR 1` every `min_frac` is NaN (one fit succeeded, all others
   had no components). With `--polSNR 8` all 476 values differ from the
   earlier output. SBID 49990 was used to locate the setting: the
   earlier value 0.313159 % matches `--polSNR 10` (0.3132 %), not 8
   (0.3076 %) or 15 (0.2736 %).
2. **Per-SBID `min_frac` reproduced at `--polSNR 10`.** 532 SBIDs in the
   earlier `validation_stats.csv`; 476 finite in both, 56 NaN in both
   (same SBIDs, no NaN/finite mismatch). Maximum absolute difference
   2.3e-8 percent (least-squares tolerance); field and status columns
   identical.
3. **Combined curve reproduced.** Pooling the components with
   `pol_peak_fit_snr < 10` and fraction >= 0 gives 109752 points (67
   negative fractions dropped; 109819 selected in total, which matches
   the count from `all_filtered.csv`). Binning in 15 log bins
   reproduces `combined_bin_centers_and_median_frac.csv` with bin
   centres identical and medians within a relative 4e-14. The floor
   (mean of the top three bins) is 0.0951 %.
   The script itself could not regenerate this CSV (bug 1 in
   `CODE.md`); the check above recomputes it independently from the
   same logic.
4. **The CASDA list has grown.** The TAP query now returns 786 SBIDs
   (532 in August 2025). The 254 new SBIDs have no local file and the
   download returned errors, so the rerun reports 307 missing instead
   of 53. The extra SBIDs also change status counts (631 GOOD, 134
   REJECTED, 18 NOT_VALIDATED, 2 UNCERTAIN, 1 BAD now).
5. **`problem_report.txt` negative-value sections reproduced.** The
   same SBIDs appear in the negative-minimum and negative-fraction
   lists with equal values (to about 1e-9). The `Index` of later SBIDs
   differs because the sorted SBID list now contains the new SBIDs.
6. **`min_frac_vs_index.png` not compared.** It is affected by bug 4 in
   `CODE.md` when SBIDs are missing, and was not checked against the
   earlier image. It is not claimed as reproduced.

## Reproduce

```
mkdir -p data/repro && ln -s ~/DATA/askap-pol/filtered_files/filtered_SB*.csv data/repro/
MPLBACKEND=Agg .venv/bin/python src/download_filtered.py --output_dir data/repro --polSNR 10
```

Compare `data/repro/validation_stats.csv` with the earlier file on the
SBIDs present in both.

## Rebuilding the results table

`src/build_results_table.py` reproduces the per-SBID values of the first
results table (computed with inline code before the script existed) exactly:
`c_p10_pct`, `c_p10_err`, the source counts, the fit bins and the monthly
pooled values are identical, and the table is unchanged by the later refactor
of `leakage.py`. Two things differ from that first table:

- The monthly 16-84 % ranges moved by up to 0.017 %. The first run drew its
  bootstrap resamples in the order returned by the TAP query, which is not
  observation order. The script now uses observation order, so the ranges
  are a different draw of the same resampling.
- The first table folded fitted values to positive with `abs()`. No SBID has
  a negative fit (p10 minimum 0.002 %, p25 minimum 0.027 %), so no value
  changed.

The results table, figures and downloaded `filtered.csv` files other than the
479 in the original working directory were produced with the object store
URL in `download_filtered.py`.
