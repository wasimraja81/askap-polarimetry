#!/usr/bin/env python
"""Build a per-SBID metadata table: observation time (UTC and local), Sun
altitude at the telescope, and the pipeline processing timestamp.

Inputs are public: the CASDA TAP service and the top of each POSSUM
validation report (HTML) on the Pawsey object store. No login is needed.
Output: <output_dir>/sbid_metadata.csv (the table), <cache_dir>/report_headers_cache.csv (requests already made).

The report header carries the POLVAL version, report generation time and
the holography model used. Early reports do not have the POLVAL line. No
ASKAPsoft pipeline version is in that report; the ASKAPsoft and pipeline
versions are in the EMU continuum validation report (project AS201).
The pipeline run timestamp from the TAP evaluation file names is also kept.
"""
import argparse
import os
import re
import urllib.error
import urllib.request

import numpy as np
import pandas as pd
from astroquery.utils.tap.core import Tap
from astropy.coordinates import AltAz, EarthLocation, get_sun
from astropy.time import Time
import astropy.units as u

TAP_URL = "https://casda.csiro.au/casda_vo_tools/tap"
# Murchison Radio-astronomy Observatory (ASKAP). Western Australia does not
# observe daylight saving, so local time is UTC+8 all year.
MRO = EarthLocation(lat=-26.696 * u.deg, lon=116.631 * u.deg, height=377 * u.m)
LOCAL_UTC_OFFSET_H = 8
N_SUN_SAMPLES = 21

# Pipeline run stamp, e.g. calibration-metadata-processing-logs-SB60585_2024-04-18-201452.tar
STAMP_RE = re.compile(r"(\d{4}-\d{2}-\d{2}-\d{6})")

# The casda.csiro.au/validation/ URLs redirect here and the redirect appends
# "/index.html" to the path, which gives a 404; use the object store directly.
REPORT_URL = ("https://ingest.pawsey.org.au/casda-support-files/validation/ASKAP/{sb}/AS203/"
              "POSSUM-validation-{field}.SB{sb}.contcube/{field}/index.html")
# The summary block is at the top of the page; this many bytes cover it.
REPORT_HEAD_BYTES = 30000
# EMU continuum validation report (project AS201): ASKAPsoft and pipeline versions.
EMU_REPORT_URL = ("https://ingest.pawsey.org.au/casda-support-files/validation/ASKAP/{sb}/AS201/"
                  "validation_image.i.{field}.SB{sb}.cont.taylor.0.restored.conv/index.html")
# Label in the report -> column name.
REPORT_LABELS = {
    "POLVAL version used": "polval_version",
    "Report generated at": "report_generated",
    "Holography model file": "holography_model",
    "Holography observation date": "holography_date",
    "Bandpass Field Name": "bandpass_field",
    "RMS of Field (microJy/beam)": "field_rms_uJy",
    "Dist to the Sun (deg)": "sun_dist_deg",
}


def parse_args():
    p = argparse.ArgumentParser(description="Per-SBID observation and processing metadata.")
    p.add_argument("--output_dir", default="results", help="Directory for sbid_metadata.csv")
    p.add_argument("--cache_dir", default="data", help="Directory for report_headers_cache.csv")
    return p.parse_args()


def query_observations(tap):
    """EMU continuum images: SBID, field, quality flag, observation start/end (MJD)."""
    job = tap.launch_job_async(
        "SELECT filename,quality_level,t_min,t_max FROM ivoa.obscore "
        "WHERE obs_collection LIKE 'EMU' AND dataproduct_subtype='cont.restored.t0' "
        "AND filename LIKE 'image.i%%0.restored.conv.fits'")
    r = job.get_results().to_pandas()
    parts = r.filename.str.split(".")
    return pd.DataFrame({
        "SB": parts.str[3].str[2:],
        "field": parts.str[2],
        "status": r.quality_level,
        "mjd_start": r.t_min,
        "mjd_end": r.t_max,
    })


def query_pipeline_stamps(tap):
    """Pipeline run timestamp per SBID from the AS201 evaluation filenames."""
    job = tap.launch_job_async(
        "SELECT sbid,filename FROM casda.observation_evaluation_file "
        "WHERE filename LIKE 'pipelineConfig__%' OR filename LIKE 'calibration-metadata-processing-logs-%'")
    r = job.get_results().to_pandas()
    r["stamp"] = r.filename.str.extract(STAMP_RE, expand=False)
    r = r.dropna(subset=["stamp"])
    # One SBID can carry more than one processing run; keep the earliest and
    # the latest so reprocessing is visible.
    g = r.groupby("sbid").stamp.agg(["min", "max", "nunique"])
    g.index = g.index.astype(str)
    return g.rename(columns={"min": "pipeline_stamp_first", "max": "pipeline_stamp_last",
                             "nunique": "n_pipeline_runs"}).reset_index().rename(columns={"sbid": "SB"})


def parse_report_header(html):
    """Return {column: value} for the labels in REPORT_LABELS found in html."""
    html = re.sub(r"<(script|style).*?</\1>", "", html, flags=re.S)
    lines = [x.strip() for x in re.sub(r"<[^>]+>", "\n", html).split("\n") if x.strip()]
    out = {}
    for i, line in enumerate(lines[:-1]):
        if line in REPORT_LABELS:
            out[REPORT_LABELS[line]] = lines[i + 1]
    return out


def parse_emu_versions(html):
    """ASKAPsoft and pipeline versions: the first two cells of the data row of
    the table whose header row starts with 'ASKAPsoft version'."""
    i = html.find("ASKAPsoft")
    if i < 0:
        return {}
    j = html.find("</tr>", i)
    cells = re.findall(r"<td[^>]*>(.*?)(?:<br>|</td>)", html[j:], flags=re.S)
    if len(cells) < 2:
        return {}
    return {"askapsoft_version": re.sub(r"<[^>]+>", "", cells[0]).strip(),
            "pipeline_version": re.sub(r"<[^>]+>", "", cells[1]).strip()}


def fetch_emu_versions(sb, field):
    """Fetch the AS201 report; emu_report_http is the HTTP status, or -1 when the request failed."""
    try:
        with urllib.request.urlopen(EMU_REPORT_URL.format(sb=sb, field=field), timeout=60) as r:
            rec = parse_emu_versions(r.read().decode("utf-8", errors="replace"))
            rec["emu_report_http"] = r.status
    except urllib.error.HTTPError as e:
        rec = {"emu_report_http": e.code}
    except Exception:
        rec = {"emu_report_http": -1}
    return rec


def fetch_report_header(sb, field):
    """Read the top of the validation report; the record has report_http set
    to the HTTP status, or to -1 when the request itself failed."""
    req = urllib.request.Request(REPORT_URL.format(sb=sb, field=field),
                                 headers={"Range": f"bytes=0-{REPORT_HEAD_BYTES - 1}"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            rec = parse_report_header(r.read().decode("utf-8", errors="replace"))
            rec["report_http"] = r.status
    except urllib.error.HTTPError as e:
        rec = {"report_http": e.code}
    except Exception:
        rec = {"report_http": -1}
    return rec


def sun_altitude_deg(mjd):
    t = Time(mjd, format="mjd", scale="utc")
    return get_sun(t).transform_to(AltAz(obstime=t, location=MRO)).alt.deg


def classify(alt):
    """Sun altitude bins: day above the horizon, then civil/nautical/astronomical twilight."""
    return np.select([alt > 0, alt > -6, alt > -12, alt > -18], ["day", "civil twilight", "nautical twilight", "astronomical twilight"], "night")


def report_headers(df, cache_dir):
    """Report-header fields for every SBID, one request at a time. Requests that
    gave a definite answer (200/206/404) are kept from the cache file."""
    cache = os.path.join(cache_dir, "report_headers_cache.csv")
    old = pd.read_csv(cache, dtype={"SB": str}) if os.path.exists(cache) else pd.DataFrame(columns=["SB"])
    for c in ("report_http", "emu_report_http"):
        if c not in old:
            old[c] = np.nan
    final = {200, 206, 404}
    rec = {r["SB"]: r for r in old.to_dict("records")}
    todo = [(sb, f) for sb, f in zip(df.SB, df.field)
            if rec.get(sb, {}).get("report_http") not in final or rec.get(sb, {}).get("emu_report_http") not in final]
    for n, (sb, field) in enumerate(todo, 1):
        row = dict(rec.get(sb, {"SB": sb}))
        if row.get("report_http") not in final:
            row.update(fetch_report_header(sb, field))
        if row.get("emu_report_http") not in final:
            row.update(fetch_emu_versions(sb, field))
        rec[sb] = row
        if n % 50 == 0:
            pd.DataFrame(rec.values()).to_csv(cache, index=False)
            print(f"  report headers: {n}/{len(todo)}")
    out = pd.DataFrame([rec[sb] for sb in df.SB])
    out.to_csv(cache, index=False)
    return out


def main():
    args = parse_args()
    os.makedirs(args.output_dir, exist_ok=True)
    os.makedirs(args.cache_dir, exist_ok=True)
    tap = Tap(url=TAP_URL)
    obs = query_observations(tap)
    stamps = query_pipeline_stamps(tap)
    df = obs.merge(stamps, on="SB", how="left")
    df = df.merge(report_headers(df, args.cache_dir), on="SB", how="left")
    df["n_pipeline_runs"] = df.n_pipeline_runs.fillna(0).astype(int)

    # Use the middle of the observation for the Sun position.
    mjd_mid = 0.5 * (df.mjd_start + df.mjd_end)
    df["date_utc"] = pd.to_datetime(df.mjd_start + 2400000.5, unit="D", origin="julian").dt.round("s")
    df["date_local"] = df.date_utc + pd.Timedelta(hours=LOCAL_UTC_OFFSET_H)
    df["duration_h"] = (df.mjd_end - df.mjd_start) * 24
    df["local_hour_start"] = df.date_local.dt.hour + df.date_local.dt.minute / 60
    df["sun_alt_mid_deg"] = sun_altitude_deg(mjd_mid.values)
    df["sun_class_mid"] = classify(df.sun_alt_mid_deg.values)
    # Observations last about 10 h, so one label per SBID hides partial day
    # observations: sample the Sun altitude across each observation.
    frac = np.linspace(0, 1, N_SUN_SAMPLES)
    grid = df.mjd_start.values[:, None] + frac[None, :] * (df.mjd_end - df.mjd_start).values[:, None]
    alt = sun_altitude_deg(grid.ravel()).reshape(grid.shape)
    df["frac_sun_up"] = (alt > 0).mean(axis=1)
    df["sun_alt_max_deg"] = alt.max(axis=1)
    df = df.sort_values("mjd_start").reset_index(drop=True)
    out = os.path.join(args.output_dir, "sbid_metadata.csv")
    df.to_csv(out, index=False)
    print(f"{len(df)} SBIDs written to {out}")
    print(df.sun_class_mid.value_counts().to_string())


if __name__ == "__main__":
    main()
