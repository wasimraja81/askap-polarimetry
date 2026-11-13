"""Instrumental polarisation (leakage) estimate from POSSUM filtered.csv tables.

Method, applied to all components with no polarisation S/N selection:
  1. Bin components in log Stokes I (BINS).
  2. In each bin take the PERCENTILE-th percentile of the fractional
     polarisation (percent), when the bin holds at least `nmin_bin` components.
  3. Fit  frac(I) = c + a / I  to the bin values, weighted by the bin value.
     `c` is the leakage upper limit (percent of Stokes I), assuming a
     constant leakage amplitude; a / I absorbs the noise term at low I.

The fitted c is returned as it comes out of the fit. If the model is right
c cannot be negative, so a negative value marks a failed measurement and is
not hidden.
"""
import numpy as np
import pandas as pd
from scipy.optimize import curve_fit

PERCENTILE = 10
BINS = np.logspace(1, np.log10(2000), 21)          # mJy/beam
CENTRES = np.sqrt(BINS[:-1] * BINS[1:])
COLUMNS = ["flux_I_median (mJy/beam)", "pol_peak/flux_I_med"]


def model(x, c, a):
    return c + a / x


def read_components(path):
    """Stokes I (mJy/beam) and fractional polarisation (percent) of every component."""
    d = pd.read_csv(path, usecols=COLUMNS).dropna().values
    return d[:, 0], d[:, 1] * 100


def binned_percentile(flux, frac, nmin_bin, percentile=PERCENTILE):
    return np.array([
        np.percentile(frac[(flux >= lo) & (flux < hi)], percentile)
        if ((flux >= lo) & (flux < hi)).sum() >= nmin_bin else np.nan
        for lo, hi in zip(BINS[:-1], BINS[1:])])


def fit_params(flux, frac, nmin_bin=10, imin=10, min_bins=4, percentile=PERCENTILE):
    """Fit c + a / I to the binned percentile. Returns (c, a, error on c, bins used);
    c, a and the error are NaN when fewer than `min_bins` bins qualify or the fit fails."""
    y = binned_percentile(flux, frac, nmin_bin, percentile)
    ok = (CENTRES >= imin) & ~np.isnan(y)
    if ok.sum() < min_bins:
        return np.nan, np.nan, np.nan, int(ok.sum())
    try:
        p, cov = curve_fit(model, CENTRES[ok], y[ok], p0=[0.1, 5], sigma=y[ok], maxfev=20000)
        return float(p[0]), float(p[1]), float(np.sqrt(cov[0, 0])), int(ok.sum())
    except Exception:
        return np.nan, np.nan, np.nan, int(ok.sum())


def fit_leakage(flux, frac, nmin_bin=10, imin=10, min_bins=4, percentile=PERCENTILE):
    """Return (c, error on c, number of bins used); see fit_params."""
    c, _, err, nbins = fit_params(flux, frac, nmin_bin, imin, min_bins, percentile)
    return c, err, nbins


def pooled_monthly(per_sb, month_of, n_boot=100, seed=1, min_sb=3, percentile=PERCENTILE):
    """Leakage fitted to the pooled components of all SBIDs observed in each
    calendar month, with a 16-84 % range from resampling the SBIDs.

    per_sb: {sbid: (flux, frac)}; month_of: {sbid: 'YYYY-MM'} for ALL sbids
    (in time order). Months with fewer than `min_sb` SBIDs with data are skipped.
    Returns {month: (c, lo16, hi84, n_sb)}.
    """
    rng = np.random.default_rng(seed)
    out = {}
    for month in sorted(set(month_of.values())):
        sbs = [sb for sb, m in month_of.items() if m == month and sb in per_sb]
        if len(sbs) < min_sb:
            continue

        def pooled(idx):
            flux = np.concatenate([per_sb[sbs[i]][0] for i in idx])
            frac = np.concatenate([per_sb[sbs[i]][1] for i in idx])
            return fit_leakage(flux, frac, nmin_bin=20, imin=20, percentile=percentile)[0]

        base = pooled(range(len(sbs)))
        boots = np.array([pooled(rng.integers(0, len(sbs), len(sbs))) for _ in range(n_boot)])
        lo, hi = np.nanpercentile(boots, [16, 84])
        out[month] = (base, lo, hi, len(sbs))
    return out
