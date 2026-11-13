import argparse
import numpy as np, pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
ap = argparse.ArgumentParser(description="Leakage timeline with software, holography and jump annotations (diagnostic).")
ap.add_argument("--table", default="results/sbs_all_time_ordered.csv")
ap.add_argument("--metadata", default="results/sbid_metadata.csv")
ap.add_argument("--outdir", default="diagnostics/outputs")
args = ap.parse_args()
main = pd.read_csv(args.table)
r = main.dropna(subset=["c_p10_pct"]).rename(columns={"c_p10_pct": "c_pct", "c_p10_err": "c_err"})[["SB", "c_pct", "c_err"]]
# Monthly pooled values: one row per month, placed at the mean date of all that month's SBIDs.
mm = main.dropna(subset=["c_p10_monthly"]).groupby("month").first().reset_index()
mm["date"] = mm.month.map(pd.to_datetime(main.date_utc).groupby(main.month).mean())
m = mm.rename(columns={"c_p10_monthly": "c_pct", "c_p10_monthly_lo16": "lo16", "c_p10_monthly_hi84": "hi84"})
md = pd.read_csv(args.metadata); md["SB"] = md.SB.astype(int)
d = r.merge(md, on="SB"); d["date"] = pd.to_datetime(d.date_utc)
md["date"] = pd.to_datetime(md.date_utc)
md = md.sort_values("date")
# Pipeline versions grouped by major.minor (about 100 distinct strings otherwise).
md["pipeline_minor"] = md.pipeline_version.where(md.pipeline_version.str.match(r"^\d+\.\d+"), "other").str.extract(r"^(\d+\.\d+|other)", expand=False)
med_c = d.groupby("askapsoft_version").c_pct.median().to_dict()
med_c_pipe = d.assign(pm=d.pipeline_version.str.extract(r"^(\d+\.\d+)", expand=False)).groupby("pm").c_pct.median().to_dict()

def extent_bars(ax, col, label, title):
    """One horizontal bar per distinct value of `col`, from its first to last SBID
    date, labelled with its SB count. Rows are assigned so that neither the bars
    nor their labels overlap."""
    g = md.dropna(subset=[col]).groupby(col).date.agg(["min", "max", "size"]).sort_values("min")
    DAYS_PER_CHAR = 6.5  # label width at font size 6.5 on this figure
    lane_end, rows, texts = [], [], []
    for v, (t0, t1, n) in g.iterrows():
        text = f"{label(v)} (n={n})"
        half = pd.Timedelta(days=len(text) * DAYS_PER_CHAR / 2)
        mid = t0 + (t1 - t0) / 2
        e0, e1 = min(t0, mid - half), max(t1, mid + half)
        for k, e in enumerate(lane_end):
            if e0 > e:
                lane_end[k] = e1; rows.append(k); break
        else:
            lane_end.append(e1); rows.append(len(lane_end) - 1)
        texts.append(text)
    cols = plt.cm.tab20(np.arange(20))
    for i, ((v, (t0, t1, n)), k, text) in enumerate(zip(g.iterrows(), rows, texts)):
        ax.barh(k, (t1 - t0) + pd.Timedelta(days=2), left=t0, height=.8, color=cols[i % 20], alpha=.8, edgecolor="k", lw=.4)
        ax.text(t0 + (t1 - t0) / 2, k, text, ha="center", va="center", fontsize=6.5)
    ax.set_ylim(-.6, len(lane_end) - .4); ax.invert_yaxis(); ax.set_yticks([])
    ax.set_ylabel(title, rotation=0, ha="right", va="center", fontsize=8)
    return list(g["min"])

fig, ax = plt.subplots(7, 1, figsize=(13, 20), sharex=False, gridspec_kw={"height_ratios": [3, 2, 2.4, 3.6, 1.5, 2.5, 1.2]})
ax[0].errorbar(d.date, d.c_pct, d.c_err, fmt="o", ms=3, color="purple", alpha=.35, lw=.4)
ax[0].set_yscale("symlog", linthresh=0.1); ax[0].set_ylabel("per-SB c (%)")
lo = (m.c_pct - m.lo16).clip(lower=0); hi = (m.hi84 - m.c_pct).clip(lower=0)
ax[1].errorbar(m.date, m.c_pct, [lo, hi], fmt="s-", color="k"); ax[1].set_ylabel("monthly pooled c (%)")
holo_starts = extent_bars(ax[2], "holography_model", lambda v: v.split(".")[-3], "holography\nmodel SB")
extent_bars(ax[3], "polval_version", lambda v: v.rsplit("-", 1)[0] + "-" + v.rsplit("-", 1)[1][:4], "POLVAL\nversion")
def short_asoft(v):
    base, _, tail = v.partition("-")
    return base + ("-" + tail[:8] if tail else "") + f" c={med_c.get(v, float('nan')):.2f}"
extent_bars(ax[4], "askapsoft_version", short_asoft, "ASKAPsoft\nversion\n(median c %)")
extent_bars(ax[5], "pipeline_minor", lambda v: f"{v} c={med_c_pipe.get(v, float('nan')):.2f}", "pipeline\nversion (X.Y)\n(median c %)")
ax[6].scatter(md.date, md.frac_sun_up, s=4, c=md.frac_sun_up, cmap="coolwarm"); ax[6].set_ylabel("Sun-up fraction")
for a in ax[:2]:
    for h in holo_starts: a.axvline(h, color="gray", lw=.6, ls=":")
for a in (ax[0], ax[1], ax[6]): a.grid(alpha=.3)
# Jumps found from the per-SB medians (10 SBIDs each side): (last SB before, first SB after).
JUMPS = [(51964, 52096), (73465, 73478), (75105, 76041)]
ds = d.sort_values("date").reset_index(drop=True)
for k, (sb_lo, sb_hi) in enumerate(JUMPS):
    i_lo = ds.index[ds.SB == sb_lo][0]; i_hi = ds.index[ds.SB == sb_hi][0]
    t_mid = ds.date[i_lo] + (ds.date[i_hi] - ds.date[i_lo]) / 2
    for a_ in ax:
        a_.axvline(t_mid, color="crimson", lw=1, ls="--", zorder=5)
    up = 1 if k != 1 else -1   # jump 2 labels go below the points; 1 and 3 above
    pick = [i_lo - 1, i_lo, i_hi, i_hi + 1]
    for j, i in enumerate(pick):
        side = -1 if i <= i_lo else 1
        row = ds.loc[i]
        ax[0].annotate(f"SB{int(row.SB)}", xy=(row.date, row.c_pct), xytext=(side * 45, up * (30 + 16 * (j % 2))),
                       textcoords="offset points", fontsize=6.5, color="crimson", ha="center", va="center",
                       arrowprops=dict(arrowstyle="-", color="crimson", lw=.5), bbox=dict(boxstyle="round,pad=.1", fc="white", ec="none", alpha=.85))
    ax[0].annotate(f"jump {k + 1}", xy=(t_mid, 1), xycoords=("data", "axes fraction"), xytext=(0, 4), textcoords="offset points",
                   color="crimson", fontsize=8, ha="center", va="bottom")
import matplotlib.dates as mdates
xlo, xhi = md.date.min() - pd.Timedelta(days=20), md.date.max() + pd.Timedelta(days=20)
for a_ in ax:
    a_.set_xlim(xlo, xhi)
    a_.xaxis.set_major_locator(mdates.MonthLocator(bymonth=[1, 4, 7, 10]))
    a_.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))
    a_.tick_params(axis="x", labelbottom=True, labelsize=8, labelrotation=45)
ax[6].set_xlabel("Observation start (UTC)")
fig.tight_layout()
fig.savefig(f"{args.outdir}/leakage_vs_time_bands.png", dpi=110)


# Companion zoom figure: +-10 SBIDs around each jump, every label shown.
zf, zax = plt.subplots(1, 3, figsize=(15, 4.6))
for k, (sb_lo, sb_hi) in enumerate(JUMPS):
    i_lo = ds.index[ds.SB == sb_lo][0]; i_hi = ds.index[ds.SB == sb_hi][0]
    sub = ds.iloc[max(i_lo - 9, 0): i_hi + 10]
    z = zax[k]
    z.errorbar(range(len(sub)), sub.c_pct, sub.c_err, fmt="o", ms=4, color="purple", lw=.6)
    n_before = i_lo - max(i_lo - 9, 0) + 1
    z.axvline(n_before - .5, color="crimson", ls="--", lw=1)
    z.set_xticks(range(len(sub)))
    z.set_xticklabels([f"SB{int(x)}\n{t:%m-%d %H:%M}" for x, t in zip(sub.SB, sub.date)], rotation=90, fontsize=6)
    z.set_title(f"jump {k + 1}: SB{sb_lo} -> SB{sb_hi}", fontsize=9)
    z.set_ylabel("per-SB c (%)" if k == 0 else ""); z.grid(alpha=.3)
zf.tight_layout(); zf.savefig(f"{args.outdir}/leakage_jumps_zoom.png", dpi=110)
