import sys, glob
import numpy as np, pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

indir, outpng = sys.argv[1], sys.argv[2]
cols = ["flux_I_median (mJy/beam)", "pol_peak/flux_I_med", "pol_peak_fit_snr"]
d = pd.concat([pd.read_csv(f, usecols=cols) for f in sorted(glob.glob(indir + "/filtered_SB*.csv"))])
d.columns = ["I", "frac", "snr"]
d = d.dropna()
bins = np.logspace(np.log10(10), np.log10(2000), 13)
c = np.sqrt(bins[:-1] * bins[1:])
rows = []
for sel, name in ((d.snr > -1, "all sources"), (d.snr < 10, "pol S/N < 10")):
    s = d[sel]
    for lo, hi, cc in zip(bins[:-1], bins[1:], c):
        x = s.frac[(s.I >= lo) & (s.I < hi)]
        if len(x) >= 20:
            rows.append((name, cc, len(x), *np.percentile(x, [10, 25, 50]) * 100))
t = pd.DataFrame(rows, columns=["sel", "I", "n", "p10", "p25", "p50"])
print(t.round(3).to_string())
fig, ax = plt.subplots(1, 2, figsize=(11, 4.5), sharey=True)
for a, name in zip(ax, ("all sources", "pol S/N < 10")):
    u = t[t.sel == name]
    for k, ls in (("p10", ":"), ("p25", "--"), ("p50", "-")):
        a.plot(u.I, u[k], ls, marker="o", label=k)
    a.set_xscale("log"); a.set_yscale("log"); a.set_title(name)
    a.set_xlabel("Stokes I (mJy/beam)"); a.grid(alpha=.3)
ax[0].set_ylabel("fractional polarisation (%)"); ax[0].legend()
fig.tight_layout(); fig.savefig(outpng)
