# Code description

Run scripts as `python src/<script>.py` from the repository root with the
project virtualenv (see the README). Scripts in `src/` import `leakage.py`
from their own directory, so do not run them with `python -I`.

## Layout

| Path | Content |
|---|---|
| `src/download_filtered.py` | Fetch `filtered.csv` per SBID from CASDA; older per-SBID fits and plots (original analysis) |
| `src/sbid_metadata.py` | Per-SBID observation time, Sun position, software versions, holography model |
| `src/leakage.py` | The leakage estimate (shared by the scripts below) |
| `src/build_results_table.py` | The results table, one row per SBID in observation order |
| `src/plot_history.py` | The fact plots of historical leakage |
| `src/make_movie.py` | Movie with one frame per SBID (not tracked; see below) |
| `src/fetch_filtered.py` | Download only the `filtered.csv` files listed in the results table |
| `.github/` | Workflow that publishes the movie, the script that decides when, and the private-information check |
| `results/` | `sbid_metadata.csv`, `sbs_all_time_ordered.csv`, `filtered_manifest.csv` (tracked) |
| `figures/` | Output of `plot_history.py` (tracked) |
| `diagnostics/` | Scripts that look for causes; `diagnostics/outputs/` holds their figures |
| `data/`, `scratch/` | Downloads, run folders, caches, throwaway work (not tracked) |

Order of use:

```
python src/download_filtered.py --output_dir data/all_filtered     # filtered.csv files (and the original plots)
python src/sbid_metadata.py                                          # results/sbid_metadata.csv
python src/build_results_table.py --filtered_dir data/all_filtered   # results/sbs_all_time_ordered.csv
python src/plot_history.py --filtered_dir data/all_filtered          # figures/
python src/make_movie.py --filtered_dir data/all_filtered            # movies/leakage_history.mp4 (needs ffmpeg)
python diagnostics/plot_bands.py                                     # diagnostics/outputs/
```

## The leakage estimate (`leakage.py`)

For one SBID, using every component in its `filtered.csv` (no polarisation
S/N selection):

1. Bin the components in log Stokes I, 20 bins from 10 to 2000 mJy/beam.
2. In each bin that holds at least 10 components, take a percentile
   (10th or 25th) of the fractional polarisation, in percent.
3. Fit `frac(I) = c + a / I` to the bin values by least squares, weighted by
   the bin value. At least 4 bins are required.

`c` is reported as an upper limit on the instrumental leakage, in percent of
Stokes I. The reasoning and its assumptions:

- Leakage is measured at high Stokes I. At low Stokes I the fractional
  polarisation is biased by noise; the `a / I` term absorbs that.
- Intrinsically polarised sources add polarisation, so a low percentile
  (which ignores the polarised tail) is used. p25 includes more such sources
  than p10 and is higher (median difference 0.16 %).
- The result is an upper limit only if the leakage amplitude is the same for
  every source, i.e. beam-dependent leakage has been corrected. Beam and
  position dependence has not been examined yet.
- A selection `pol_peak_fit_snr < N`, used by the original analysis, was
  dropped: at high Stokes I a source with leakage-level polarisation exceeds
  the S/N limit and is removed, so the selected sample falls as 1/I and no
  leakage floor appears.
- `c` is returned as fitted. No SBID has a negative `c`.

Monthly values pool the components of all SBIDs observed in a calendar month
and fit once. Their range is a bootstrap over SBIDs. A pick selects one of the
month's SBIDs at random and puts it back, so it can be picked again. A
bootstrap sample is nSB picks, where nSB is the number of SBIDs the month has;
about 63 % of the distinct SBIDs appear in a sample, some more than once. The
components of the sample are pooled and fitted once, giving one value of `c`.
This is repeated for `--n_boot` bootstrap samples (default 100, independent of
nSB, seed 1, SBIDs in observation order), so 100 x nSB picks in total. The 16th
and 84th percentiles of the resulting values are reported; for a bell-shaped
spread they correspond to +-1 sigma. The range
covers which SBIDs were observed, not the choice of percentile or model, and
with 100 draws the ends are good to a few hundredths of a percent.

Months with fewer than 3 SBIDs with data get no pooled value or range: with one
SBID every redraw is identical and the range would be zero. Every month with
data in the current table has at least 3.

Separately, the per-SBID values in a month are summarised directly (mean, median,
16th and 84th percentile, minimum, maximum, standard deviation). That is the
spread between SBIDs; the bootstrap range is the uncertainty of the pooled
level (median ratio of its half-width to std/sqrt(n) is 1.2).

## `download_filtered.py`

Entry point `main()`. Options: `--output_dir` (default `filtered_files`),
`--polSNR` (default 10), `--hide-missing`.

1. `getSB()` queries the CASDA TAP service (`ivoa.obscore`, EMU collection)
   for SBID, field, `quality_level` and `t_min`, the observation start in MJD.
   The result is sorted by `t_min`; TAP returns rows in no particular order.
2. For each SBID `filtered_SB<id>.csv` is read from `--output_dir`, or
   downloaded from the object store
   `https://ingest.pawsey.org.au/casda-support-files/validation/ASKAP/<SB>/AS203/POSSUM-validation-<field>.SB<SB>.contcube/<field>/validation/filtered.csv`.
3. Original per-SBID analysis: components with `pol_peak_fit_snr < polSNR`,
   fit of `c + a / I`, binned-median floor, per-SBID and combined plots.

Outputs: `filtered_SB<id>.csv`, `dLPvsI_SB<id>.png`, `validation_stats.csv`
(`SB, field, status, mjd, date_utc, min_frac, min_frac_binned`),
`problem_report.txt` (indices are positions in observation order),
`combined_polfrac_vs_I.png`, `combined_bin_centers_and_median_frac.csv`,
`min_frac_vs_time.png`.

Changes from the imported version:

1. The combined-bins CSV was written to a closed file handle; fixed.
2. A leftover block after the first `except` used undefined names; removed.
3. `--polSNR` default changed from 1 (selects nothing) to 10, the value used
   for the earlier results.
4. Per-SBID result lists were not appended on the download path and fell out
   of step with the SBID list; local and downloaded files now share one path.
5. Unused options `--hide-maxI` and `--plot-combined-fit` removed.
6. The x axis of the min-fraction plot is observation time, not SBID rank.
7. `casda.csiro.au/validation/...` now redirects to the object store and the
   redirect appends `/index.html`, which gives a 404 and made 254 SBIDs look
   missing. The object store URL is used directly.

The 53 earliest SBIDs (Nov 2022 to May 2023) have no validation report and
remain missing.

## `sbid_metadata.py`

Writes `results/sbid_metadata.csv` with no login:

- from TAP: SBID, field, quality flag, observation start and end (MJD), the
  pipeline run stamps from the evaluation file names (`pipeline_stamp_first`,
  `pipeline_stamp_last`, `n_pipeline_runs`; the stamp's time zone is not
  stated);
- computed: UTC and local time (AWST, UTC+8, no daylight saving), Sun altitude
  and the fraction of each observation with the Sun above the horizon at the
  MRO (-26.696, 116.631);
- from the POSSUM validation report (first 30 KB): POLVAL version,
  report generation time, holography model file and date, bandpass field,
  field RMS, Sun distance. Reports before Oct 2023 lack the POLVAL and
  holography lines;
- from the EMU continuum validation report (project AS201): ASKAPsoft and
  pipeline versions, available for all 786 SBIDs.

Requests already answered are cached in `data/report_headers_cache.csv`.

## `build_results_table.py`

One row per SBID in observation order (`obs_index`, asserted), written to
`results/sbs_all_time_ordered.csv`:

| Column | Meaning |
|---|---|
| `obs_index`, `SB`, `field`, `status` | Rank by observation time, SBID, field, CASDA quality flag |
| `date_utc`, `date_local_awst` | Observation start |
| `c_p10_pct`, `c_p10_err` | Leakage upper limit from p10 and its fit error, percent of Stokes I |
| `c_p25_pct`, `c_p25_err` | The same from p25 |
| `n_above_50mJy`, `n_components`, `fit_nbins` | Components above 50 mJy/beam, all components, bins in the fit |
| `has_filtered_csv` | False for SBIDs with no `filtered.csv`; their leakage columns are empty |
| `askapsoft_version`, `pipeline_version`, `polval_version`, `holography_model_sb` | Software and calibration model used |
| `pipeline_run_first`, `pipeline_run_last`, `n_pipeline_runs` | Pipeline run stamps (processing, not observation, time) |
| `frac_sun_up` | Fraction of the observation with the Sun above the horizon |
| `month`, `c_p10_monthly[_lo16/_hi84]`, `c_p25_monthly[_lo16/_hi84]`, `n_sb_in_month` | Monthly pooled value, its bootstrap 16-84 % range, and the number of SBIDs with data |
| `c_p10_sbid_*`, `c_p25_sbid_*` (`mean`, `median`, `p16`, `p84`, `min`, `max`, `std`) | Summary of the per-SBID values in the month |

## `plot_history.py`

Records the measurements without interpretation: `history_timeline.png`
(per-SBID p10 and p25 and monthly pooled values against observation date),
`history_overall.png` (all components pooled, with the fits),
`history_monthly_stats.png` (mean, median, standard deviation, 16-84 % band and
minimum to maximum of the per-SBID values in each month, with the pooled fit and
its bootstrap range overlaid), `history_distribution.png`
and `history_coverage.png`. The pooled figure
mixes the epochs seen in the timeline and its `c` (0.17 % for p10) is an
average over them.

## `make_movie.py`

Renders `movies/leakage_history.mp4` (1280 x 720, H.264, 12 frames per second,
786 frames, about 65 s), one frame per SBID in observation order. The `movies/`
directory is not tracked (the file is about 10 MB); regenerate it with the
script. `ffmpeg` must be installed. Options: `--fps`, `--dpi`, and `--first`
with `--limit` to render a few frames for testing.

Each frame has fixed axes (Stokes I 10 to 2000 mJy/beam, fractional
polarisation 0.02 to 30 %): the components of the SBID, its p10 and p25 point
in each Stokes I bin, the fitted `c + a/I` curves with `c` marked and labelled,
and, as a fixed reference in every frame, the p10 and p25 fitted curves of all
SBIDs pooled (faint), with the pooled `c` and its fit error marked by dotted
horizontal lines and labelled at the left. A card at the right gives the SBID, field, UTC and local time, quality flag, software versions,
holography model, pipeline run stamp, component counts, `c` with its error for
p10 and p25, the month's median, and the pooled `c`. A strip at the bottom shows `c` for every
SBID against observation date with a cursor at the current frame. SBIDs without
a `filtered.csv` get a frame that says so.

## Publishing the movie

`.github/workflows/publish-movie.yml` renders the movie on GitHub and attaches it
to a release called `movie-latest`. The MP4 is never stored in the repository.

- **When.** On every push to `main`, the workflow asks
  `.github/scripts/develop_merged.sh` whether the tip of `develop` is newly part
  of `main`. That is true for a fast-forward or merge-commit merge of `develop`,
  and false for a direct commit to `main` or any push after the merge. Only then
  does it continue. The check is tested against throwaway repositories by
  `.github/scripts/test_develop_merged.sh <new directory>`.
- **By hand.** From the Actions tab the workflow can be started with the option
  "Replace the movie attached to the movie-latest release" switched on or off;
  with it off, the movie is kept as a workflow artifact for 7 days.
- **Steps.** Install the packages in `requirements.txt` and `ffmpeg`; restore or
  fetch the component tables of the SBIDs in `results/sbs_all_time_ordered.csv`
  with `src/fetch_filtered.py` (about 460 MB, cached on the hash of the table);
  run `src/make_movie.py`; check that the movie has one frame per table row;
  create the release if needed and replace the file attached to it. The movie
  therefore matches the committed table, not the state of CASDA on the day.
- **The page.** At the same time the workflow deploys a page with the movie in a
  video player and two figures to GitHub Pages
  (`https://wasimraja81.github.io/askap-polarimetry/`). The page is
  `.github/site/index.html`. The repository's Pages source must be set to
  "GitHub Actions", and the `github-pages` environment must allow deployments
  from the branches that publish (`main`, and `develop` for manual runs).
- **The release.** `movie-latest` is not marked as the latest release. The tag
  stays at the commit that first created it; the release notes give the commit
  that the attached file was rendered from.
- **Input data.** Only the `filtered.csv` files are fetched, anonymously from the
  public object store; no login or secret is used. `results/filtered_manifest.csv`
  holds the size and SHA-256 of each of the 733 files, and `fetch_filtered.py`
  fails if any file differs (`--write-manifest` rewrites it, `--no-verify`
  skips the comparison). The downloaded files are never committed.
- **Private-information check.** `.github/scripts/check_private_info.sh` fails on
  absolute home paths, e-mail addresses (except example.org), password or token
  assignments and private keys. Run it before each commit;
  `.github/workflows/checks.yml` runs it on every push.
- **Not yet run on GitHub.** The fetch, render and frame-count steps have been
  run locally in the same order (733 files fetched, 786 frames, identical to an
  earlier render); the workflow file, the release step and the runner
  environment have not.

## Diagnostics

See `docs/DIAGNOSTICS.md`.
