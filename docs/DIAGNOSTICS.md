# Diagnostics: what the leakage history may depend on

These are findings from `diagnostics/`. They are associations, not
established causes. The measurements themselves are in `figures/` and
`results/`.

## The leakage has two levels and a transient

Per-SBID p10 leakage (percent of Stokes I), monthly pooled:

| Period (observation date) | Level |
|---|---|
| May to Jul 2023 | about 0.35 |
| Sep 2023 to Apr 2025 | 0.07 to 0.13 |
| May to Jul 2025 | about 0.3 |
| Aug to Sep 2025 | up to 0.64 (transient) |
| Dec 2025 to Nov 2026 | 0.31 to 0.41 |

## The level follows the ASKAPsoft build

Median p10 leakage by ASKAPsoft build (SBIDs with a measurement):

| State | Builds | Median (%) |
|---|---|---|
| high | 1.11.0, 1.11.1 | 0.27 to 0.33 |
| low | 1.13.0, 1.14.1, 1.15.0, 1.16.1, 1.16.1-lustrefix, 1.17.5, 1.18.1-446f | 0.04 to 0.08 |
| high | 1.18.3 and later (1.18.3-casarest-fix, 1.21.2, 1.22.x, 1.23.x, 1.24.0) | 0.30 to 0.34 |
| elevated | 1.19.0 | 0.49 |

Evidence that it is the build and not the date:

- SB52121 (1.11.1, high) was observed after SB52096 (1.13.0, low).
- Of 40 SBIDs processed more than 60 days after observation, 33 observed in
  Aug to Nov 2023 and processed later with 1.13.0 to 1.15.0 give 0.06 to 0.11 %
  (monthly medians), although neighbouring SBIDs observed in Aug 2023 give
  about 0.28 %; 5 observed in Feb to Apr 2025 and reprocessed in Jul 2025 with
  1.18.3 builds give 0.26 to 0.46 % (SB70566, 70567, 70569, 71709, 72907),
  against a median of 0.080 % for the 25 SBIDs of build 1.17.5 observed in the
  same weeks. The 2025 group is only 5 SBIDs. The remaining 2 of the 40
  (SB74627 on 1.22.0 and SB74690 on 1.21.2, observed in Jun and Jul 2025 and
  processed in Mar 2026 and Dec 2025) give 0.17 and 0.18 %, below the 0.30 %
  those builds otherwise give.
- Counting high/low state switches along the SBID sequence, ordering by
  processing time gives fewer switches than ordering by observation time
  (20 against 36 at a 0.15 % threshold, 32 against 48 at 0.18 %, 60 against 68
  at 0.22 %). A rolling-median scatter measure shows no difference.

In the quiet period between the first two changes, 10 of the 13 SBIDs above
0.2 % ran a high-state build (Fisher exact p = 9e-16); the other three, at
declinations -9, -4 and +4 degrees, are consistent with noise given their
errors but lie in the equatorial band (3 of 111 SBIDs within +-10 degrees
against 0 of 206 elsewhere, chance about 4 %).

## Release notes that match the changes

From the ASKAPsoft release notes (checked against the page text):

- 1.13.0 (20/9/23): "aimed primarily at correcting the treatment of Stokes Q
  and U in linmos", including renormalising the off-axis correction by
  subtracting the on-axis leakage already applied before imaging.
- 1.18.2 (05/04/25) patched a linmos bug in which "the calculation of taylor.1
  images or wide-field leakage was done incorrectly"; 1.18.2 was superseded by
  1.18.3 (16/04/25), so 1.18.3 is the first deployed build with the change. The
  page lists this under Pipelines 2.15.0 (05/05/25), the date of the first
  SBID on pipeline 2.15.
- 1.19.0 (31/7/25) has no leakage item; the Aug to Sep 2025 transient is
  not explained.

Whether the pipeline switches the off-axis leakage removal on
(`REMOVE_LEAKAGE_OFF_AXIS_*`, default false) is in the `pipelineConfig` files,
which need a CASDA login and have not been read.

## Other properties checked

Sun-up fraction, field RMS, Sun distance, observation duration and number of
bright sources show no difference between high and low SBIDs in the quiet
period. There are 11 holography models (10 changes); judging by the monthly
curve, only one change coincides with a step, and the step is four days later,
at the same SBID as the software change. POLVAL changes often and shows no matching step. The CASDA quality
flag REJECTED is more common among the high SBIDs (7 of 13 against 23 %),
partly because of the build.

## Open

- Q, U and V leakage separately (`med_QI_leakage`, `med_UI_leakage`,
  `med_VI_leakage` in `filtered.csv`).
- The equatorial outliers: Galactic latitude, A/B field footprints.
- The Aug to Sep 2025 transient.
- Beam-dependent leakage.
- Bandpass SBID is not in the report header; only the bandpass field name
  appears, and only in recent reports.
