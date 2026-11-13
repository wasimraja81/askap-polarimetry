import sys, glob, warnings
import numpy as np, pandas as pd
from scipy.optimize import curve_fit
warnings.filterwarnings("ignore")
indir = sys.argv[1]
rng = np.random.default_rng(1)
cols = ["flux_I_median (mJy/beam)", "pol_peak/flux_I_med"]
sbs = []
for f in sorted(glob.glob(indir + "/filtered_SB*.csv")):
    d = pd.read_csv(f, usecols=cols).dropna().values
    sbs.append((d[:, 0], d[:, 1] * 100))
bins = np.logspace(1, np.log10(2000), 21)
cen = np.sqrt(bins[:-1] * bins[1:])
lin = lambda x, c, a: c + a / x
quad = lambda x, c, a: np.sqrt(c**2 + (a / x)**2)

def fit(idx, q, Imin=20):
    I = np.concatenate([sbs[i][0] for i in idx]); F = np.concatenate([sbs[i][1] for i in idx])
    y = np.array([np.percentile(F[(I >= lo) & (I < hi)], q) if ((I >= lo) & (I < hi)).sum() >= 20 else np.nan
                  for lo, hi in zip(bins[:-1], bins[1:])])
    m = (cen >= Imin) & ~np.isnan(y)
    out = []
    for f in (lin, quad):
        p, _ = curve_fit(f, cen[m], y[m], p0=[0.1, 5], sigma=y[m], maxfev=20000)
        out.append(abs(p[0]))
    return out

n = len(sbs); allidx = np.arange(n)
for q in (10, 25):
    base = fit(allidx, q)
    boots = np.array([fit(rng.choice(allidx, n), q) for _ in range(200)])
    for k, name in enumerate(("c + a/I", "quadrature")):
        lo, med, hi = np.percentile(boots[:, k], [16, 50, 84])
        print(f"p{q} {name:11s} c = {base[k]:.3f} %   bootstrap 16-84%: {lo:.3f} - {hi:.3f}   (std {boots[:,k].std():.3f})")
