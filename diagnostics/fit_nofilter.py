import sys, glob, warnings
import numpy as np, pandas as pd
from scipy.optimize import curve_fit
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
warnings.filterwarnings("ignore")

indir, outpng = sys.argv[1], sys.argv[2]
cols = ["flux_I_median (mJy/beam)", "pol_peak/flux_I_med"]
files = sorted(glob.glob(indir + "/filtered_SB*.csv"))
d = pd.concat([pd.read_csv(f, usecols=cols) for f in files]).dropna()
d.columns = ["I", "frac"]
d["frac"] *= 100  # percent

lin = lambda x, c, a: c + a / x
quad = lambda x, c, a: np.sqrt(c**2 + (a / x)**2)

bins = np.logspace(np.log10(10), np.log10(2000), 21)
cen = np.sqrt(bins[:-1] * bins[1:])
Q = {q: [] for q in (10, 25, 50)}
N = []
for lo, hi in zip(bins[:-1], bins[1:]):
    x = d.frac[(d.I >= lo) & (d.I < hi)].values
    N.append(len(x))
    for q in Q:
        Q[q].append(np.percentile(x, q) if len(x) >= 20 else np.nan)
N = np.array(N)

rows = []
fig, ax = plt.subplots(1, 3, figsize=(15, 4.5), sharey=True)
for a_, q in zip(ax, Q):
    y = np.array(Q[q])
    a_.plot(cen, y, "ko", label=f"p{q} of the components in each Stokes I bin")
    for Imin, ls in ((10, "-"), (20, "--"), (50, ":")):
        m = (cen >= Imin) & ~np.isnan(y)
        for name, f, col in (("c+a/I", lin, "tab:red"), ("quad", quad, "tab:blue")):
            try:
                p, cov = curve_fit(f, cen[m], y[m], p0=[0.1, 5], sigma=y[m], absolute_sigma=False, maxfev=20000)
                e = np.sqrt(np.diag(cov))
                rows.append((q, Imin, name, p[0], e[0], p[1], m.sum()))
                xx = np.logspace(np.log10(Imin), np.log10(2000), 100)
                a_.plot(xx, f(xx, *p), ls, color=col, alpha=.7,
                        label=f"{'c + a/I' if name == 'c+a/I' else 'quadrature'} fit, I>{Imin}: c={p[0]:.3f} %" if Imin == 20 else None)
            except Exception as ex:
                rows.append((q, Imin, name, np.nan, np.nan, np.nan, m.sum()))
    a_.set_xscale("log"); a_.set_yscale("log"); a_.set_title(f"p{q}: {q}th percentile of fractional polarisation per Stokes I bin\n{len(files)} SBIDs, {len(d)} components, no polarisation S/N selection", fontsize=9)
    a_.set_xlabel("Stokes I (mJy/beam)"); a_.grid(alpha=.3); a_.legend(fontsize=8)
ax[0].set_ylabel("fractional polarisation (%)")
fig.tight_layout(); fig.savefig(outpng)
t = pd.DataFrame(rows, columns=["pctl", "I>", "model", "c_pct", "c_err", "a_mJy_pct", "nbins"])
print(t.round(4).to_string(index=False))
print("sources per bin (I>=10):", dict(zip(np.round(cen).astype(int), N)))
