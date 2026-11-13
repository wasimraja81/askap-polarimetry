#!/usr/bin/env python
"""Download the filtered.csv of every SBID that has a leakage measurement in the
results table, and nothing else.

Used by the movie workflow, where the component tables are not in the
repository. Files that already exist are kept, so a restored cache is not
downloaded again. Each file is checked for the columns the analysis reads. The
exit status is non-zero if any file could not be fetched or checked.

`--manifest` names a CSV (SB, bytes, sha256). With `--write-manifest` it is
written from the files in `--output_dir`; otherwise every file is compared with
it, so a changed or truncated download fails the run.
"""
import argparse
import hashlib
import os
import sys
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor

import pandas as pd

URL = ("https://ingest.pawsey.org.au/casda-support-files/validation/ASKAP/{sb}/AS203/"
       "POSSUM-validation-{field}.SB{sb}.contcube/{field}/validation/filtered.csv")
REQUIRED = ("flux_I_median (mJy/beam)", "pol_peak/flux_I_med")


def parse_args():
    p = argparse.ArgumentParser(description="Fetch the filtered.csv files listed in the results table.")
    p.add_argument("--table", default="results/sbs_all_time_ordered.csv")
    p.add_argument("--output_dir", required=True)
    p.add_argument("--workers", type=int, default=8)
    p.add_argument("--retries", type=int, default=4)
    p.add_argument("--manifest", default="results/filtered_manifest.csv")
    p.add_argument("--write-manifest", action="store_true", help="Write the manifest from the files present")
    p.add_argument("--no-verify", action="store_true", help="Do not compare the files with the manifest")
    p.add_argument("--limit", type=int, default=0, help="Fetch only the first N files (testing)")
    return p.parse_args()


def fetch(sb, field, out_dir, retries):
    """Return (sb, None) on success or (sb, reason) on failure."""
    path = os.path.join(out_dir, f"filtered_SB{sb}.csv")
    if os.path.exists(path) and os.path.getsize(path) > 0:
        return sb, None
    url = URL.format(sb=sb, field=field)
    reason = "unknown"
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(url, timeout=60) as r:
                data = r.read()
            header = data.split(b"\n", 1)[0].decode("utf-8", errors="replace")
            missing = [c for c in REQUIRED if c not in header]
            if missing:
                return sb, f"columns missing: {missing}"
            tmp = path + ".part"
            with open(tmp, "wb") as f:
                f.write(data)
            os.replace(tmp, path)
            return sb, None
        except urllib.error.HTTPError as e:
            reason = f"HTTP {e.code}"
            if e.code in (403, 404):
                break
        except Exception as e:
            reason = f"{type(e).__name__}: {e}"
        time.sleep(2 ** attempt)
    return sb, reason


def digest(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        h.update(f.read())
    return os.path.getsize(path), h.hexdigest()


def main():
    args = parse_args()
    t = pd.read_csv(args.table)
    t = t[t.has_filtered_csv]
    if args.limit:
        t = t.head(args.limit)
    os.makedirs(args.output_dir, exist_ok=True)
    jobs = list(zip(t.SB, t.field))
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        results = list(pool.map(lambda j: fetch(j[0], j[1], args.output_dir, args.retries), jobs))
    failed = [(sb, why) for sb, why in results if why]
    print(f"{len(jobs) - len(failed)} of {len(jobs)} files present in {args.output_dir}")
    for sb, why in failed:
        print(f"  SB{sb}: {why}")
    if failed:
        sys.exit(1)
    if args.write_manifest:
        rows = [(sb,) + digest(os.path.join(args.output_dir, f"filtered_SB{sb}.csv")) for sb, _ in jobs]
        pd.DataFrame(rows, columns=["SB", "bytes", "sha256"]).to_csv(args.manifest, index=False)
        print(f"manifest of {len(rows)} files written to {args.manifest}")
    elif not args.no_verify and not args.limit:
        m = pd.read_csv(args.manifest).set_index("SB")
        bad = []
        for sb, _ in jobs:
            got = digest(os.path.join(args.output_dir, f"filtered_SB{sb}.csv"))
            if sb not in m.index or got != (m.at[sb, "bytes"], m.at[sb, "sha256"]):
                bad.append(sb)
        print(f"{len(jobs) - len(bad)} of {len(jobs)} files match the manifest")
        for sb in bad:
            print(f"  SB{sb}: differs from the manifest")
        sys.exit(1 if bad else 0)
    sys.exit(0)


if __name__ == "__main__":
    main()
