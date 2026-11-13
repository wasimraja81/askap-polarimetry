#!/usr/bin/env python
import re
import urllib.request
import pandas as pd
from astroquery.utils.tap.core import Tap
from urllib.request import urlretrieve
import pdb
import matplotlib.pyplot as plt
from scipy.optimize import curve_fit
import numpy as np
import argparse
import os, sys

def parse_args():
    parser = argparse.ArgumentParser(description="Download and process filtered EMU validation files.")
    parser.add_argument('--output_dir', type=str, default='filtered_files', help='Directory to save output files (default: filtered_files)')
    parser.add_argument('--hide-missing', action='store_true', help='Hide missing SBIDs in min_frac plot')
    parser.add_argument('--polSNR', type=float, default=10, help='Keep components with pol_peak_fit_snr below this value (default: 10)')
    args = parser.parse_args()
    return args.output_dir, args.hide_missing, args.polSNR

def model(x, a):
    return a / x

# New model: a/x + c
def model_offset(x, a, c):
    return a / x + c

def get_all_values(df, snr_val=8):
    
    snr = df["pol_peak_fit_snr"]
    i = df["flux_I_median (mJy/beam)"]
    frac = df["pol_peak/flux_I_med"]   
    goodfrac = frac[snr<snr_val]
    goodi = i[snr<snr_val]
    x = goodi # your x data
    y = goodfrac  # your y data

    # Fit offset model (a/x + c)
    try:
        popt, pcov = curve_fit(model_offset, x, y, p0=[1, 0])
        a_fit, c_fit = popt
        xs = np.linspace(np.nanmin(x), np.nanmax(x), 100)
        y_fit = model_offset(xs, a_fit, c_fit)
        y_fit = np.clip(y_fit, 0, None)
        # min_frac at highest I in data (as percentage)
        min_frac = (a_fit / np.nanmax(x) + c_fit) * 100
    except Exception as e:
        a_fit, c_fit = np.nan, np.nan
        xs = np.linspace(1, 1, 1)
        y_fit = np.full_like(xs, np.nan)
        min_frac = np.nan
    return x, y, xs, y_fit, min_frac, a_fit, c_fit

def make_plot(SB, fieldname, goodi, goodfrac, xs, y_fit, saveas, a_fit, c_fit, polSNR):
    fig = plt.figure()
    plt.scatter(goodi, goodfrac, s=1)

    # Bin Stokes-I and compute median polFrac in each bin
    nbins = 10
    if len(goodi) > 0:
        I_min = max(1, np.nanmin(goodi))
        I_max = np.nanmax(goodi)
        bins = np.logspace(np.log10(I_min), np.log10(I_max), nbins+1)
        bin_centers = np.sqrt(bins[:-1] * bins[1:])
        median_frac = []
        for i in range(nbins):
            mask = (goodi >= bins[i]) & (goodi < bins[i+1])
            if np.any(mask):
                median_frac.append(np.nanmedian(goodfrac[mask]))
            else:
                median_frac.append(np.nan)
        plt.plot(bin_centers, median_frac, 'ko-', label='Binned median', markersize=4, lw=1)

        # Empirical baseline: mean of highest N binned medians
        N_high = 3
        median_frac_arr = np.array(median_frac)
        valid_idx = np.where(~np.isnan(median_frac_arr))[0]
        if len(valid_idx) >= N_high:
            high_bins = median_frac_arr[valid_idx[-N_high:]]
            empirical_baseline = np.mean(high_bins)
            min_frac = empirical_baseline * 100
            plt.axhline(empirical_baseline, color='red', linestyle=':', label=f'Instrumental pol: {min_frac:.3g}% \n(Mean of highest {N_high} bins)')
            label_text = f"Instrumental pol: {min_frac:.3f}%\n(Mean of highest {N_high} binned medians)"
        else:
            empirical_baseline = np.nan
            label_text = "Not enough bins for empirical baseline"
    else:
        label_text = "No valid data for binning"

    plt.title(f"SB{SB} - {fieldname} (pol S/N < {polSNR})")
    plt.xlabel("Stokes I peak flux (mJy/beam)")
    plt.ylabel("Linear polarized fraction")
    plt.legend()
    fig.savefig(saveas)
    plt.close(fig)

def getSB():
    #casda_tap = Tap("https://casda.csiro.au/casda_vo_tools/tap")
    casda_tap = Tap(url="https://casda.csiro.au/casda_vo_tools/tap")
    sbList = []
    fieldList = []
    statusList = []
    mjdList = []

    job = casda_tap.launch_job_async("SELECT filename,quality_level,t_min FROM ivoa.obscore WHERE obs_collection LIKE 'EMU' AND dataproduct_subtype='cont.restored.t0' AND filename LIKE 'image.i%%0.restored.conv.fits'")
    results_table = job.get_results()
    for item in results_table:
        fdata = item['filename'].split('.')
        sbid = fdata[3][2:]
        field_name = fdata[2]
        sbList.append(sbid)
        fieldList.append(field_name)
        status = item['quality_level']
        statusList.append(status)
        # t_min: observation start, MJD (UTC)
        mjdList.append(float(item['t_min']))
    
    # TAP returns rows in no particular order. Everything downstream (indices
    # in the problem report, the time plot) follows observation time, not SBID
    # or processing order.
    order = np.argsort(mjdList, kind="stable")
    return ([sbList[i] for i in order], [fieldList[i] for i in order],
            [statusList[i] for i in order], [mjdList[i] for i in order])

def main():
    negative_polfrac_files = []
    negative_fracgood_files = []

    output_dir, hide_missing, polSNR = parse_args()
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    sbList, fieldList, statusList, mjdList = getSB()

    project_code = "AS203"

    all_i = []
    all_frac = []
    all_mins = []  # legacy: min_frac from all-points fit
    all_mins_median = []  # new: min_frac from asymptote of binned median fit
    not_found_SBs = []
    # For global combined plot
    all_igood = []
    all_fracgood = []

    validationStats = pd.DataFrame()
    nSB = len(sbList)
    #nSB = 20
    #for n in range(0, min(20, len(sbList))):
    for iSB in range(0, nSB):
        sb, field = sbList[iSB], fieldList[iSB]
        # casda.csiro.au/validation/ redirects to the object store and appends
        # "/index.html" to the path, which gives a 404; use the store directly.
        link = 'https://ingest.pawsey.org.au/casda-support-files/validation/ASKAP/' + sb + '/' + project_code + '/POSSUM-validation-' + field + '.SB' + sb + '.contcube/'
        filtered = link + field + "/validation/filtered.csv"
        outCSV = os.path.join(output_dir, 'filtered_SB' + sb + '.csv')
        outPlotName = os.path.join(output_dir, 'dLPvsI_SB' + sb + '.png')
        print(f"[{iSB+1}/{nSB}] SB: {sb}, Field: {field}")
        print(filtered)
        # Local copy first; download only when absent.
        if not os.path.exists(outCSV):
            try:
                urlretrieve(filtered, outCSV)
            except urllib.error.URLError:
                print(f"File not found for SB {sb}, field {field}")
        # One processing path for local and downloaded files, so every
        # per-SB list gets exactly one entry per SB and stays aligned
        # with sbList.
        try:
            df = pd.read_csv(outCSV)
            igood, fracgood, fit_i, fit_frac, minfrac, a_fit, c_fit = get_all_values(df, snr_val=polSNR)
            if np.any(fracgood < 0):
                print(f"NEGATIVE fracgood: SB={sb}, Field={field}, File={outCSV}, Min={np.nanmin(fracgood)}")
                negative_fracgood_files.append((sb, field, outCSV, np.nanmin(fracgood)))
            if minfrac < 0:
                negative_polfrac_files.append((sb, field, outCSV, minfrac))
            minfrac_median = np.nan
            if len(igood) > 0:
                nbins = 10
                I_min = max(1, np.nanmin(igood))
                I_max = np.nanmax(igood)
                bins = np.logspace(np.log10(I_min), np.log10(I_max), nbins+1)
                median_frac = []
                for i in range(nbins):
                    mask = (igood >= bins[i]) & (igood < bins[i+1])
                    if np.any(mask):
                        median_frac.append(np.nanmedian(fracgood[mask]))
                    else:
                        median_frac.append(np.nan)
                median_frac_arr = np.array(median_frac)
                valid_idx = np.where(~np.isnan(median_frac_arr))[0]
                N_high = 3
                if len(valid_idx) >= N_high:
                    minfrac_median = np.mean(median_frac_arr[valid_idx[-N_high:]]) * 100
            make_plot(sb, field, igood, fracgood, fit_i, fit_frac, outPlotName, a_fit, c_fit, polSNR)
            all_i.append(igood)
            all_frac.append(fracgood)
            all_mins.append(minfrac)
            all_mins_median.append(minfrac_median)
            all_igood.append(igood)
            all_fracgood.append(fracgood)
        except Exception as e:
            print(f"No usable data for SB {sb}: {e}")
            not_found_SBs.append((sb, field))
            all_i.append(np.nan)
            all_frac.append(np.nan)
            all_mins.append(np.nan)
            all_mins_median.append(np.nan)
    # Write problems to a report file
    report_path = os.path.join(output_dir, "problem_report.txt")
    # For index lookup, use sorted SBID order as in the plot
    # Index = position in observation-time order (sbList is already sorted by it).
    sbid_to_index = {sb: i for i, sb in enumerate(sbList)}
    with open(report_path, "w") as f:
        f.write(f"Missing SBs (filtered.csv not found): {len(not_found_SBs)}\n")
        for sb, field in not_found_SBs:
            idx = sbid_to_index.get(sb, 'N/A')
            f.write(f"  Index: {idx}, SB: {sb}, Field: {field}\n")
        f.write("\nFiles with negative minimum pol frac (before clipping):\n")
        if negative_polfrac_files:
            for sb, field, fname, minfrac in negative_polfrac_files:
                idx = sbid_to_index.get(sb, 'N/A')
                f.write(f"  Index: {idx}, SB: {sb}, Field: {field}, File: {fname}, min pol frac: {minfrac}\n")
        else:
            f.write("  None\n")
        f.write("\nFiles with negative values in fracgood (before clipping):\n")
        if negative_fracgood_files:
            for sb, field, fname, minfrac in negative_fracgood_files:
                idx = sbid_to_index.get(sb, 'N/A')
                f.write(f"  Index: {idx}, SB: {sb}, Field: {field}, File: {fname}, min fracgood: {minfrac}\n")
        else:
            f.write("  None\n")
    print(f"\nProblem report written to {report_path}")
    # After loop: combine all igood/fracgood and plot/fitting for all SBs
    if all_igood and all_fracgood:
        igood_all = np.concatenate(all_igood)
        fracgood_all = np.concatenate(all_fracgood)
        # Clip fracgood_all and igood_all to exclude negatives
        mask = fracgood_all >= 0
        igood_all_clip = igood_all[mask]
        fracgood_all_clip = fracgood_all[mask]
        try:
            # Bin the data in I and plot the median fractional polarization in each bin
            nbins = 15
            I_min = max(1, np.nanmin(igood_all_clip))
            I_max = min(3000, np.nanmax(igood_all_clip))
            bins = np.logspace(np.log10(I_min), np.log10(I_max), nbins+1)
            bin_centers = np.sqrt(bins[:-1] * bins[1:])
            median_frac = []
            for i in range(nbins):
                mask = (igood_all_clip >= bins[i]) & (igood_all_clip < bins[i+1])
                if np.any(mask):
                    median_frac.append(np.nanmedian(fracgood_all_clip[mask]))
                else:
                    median_frac.append(np.nan)

            # Write bin_centers and median_frac to a CSV file for the combined plot
            combined_bins_file = os.path.join(output_dir, 'combined_bin_centers_and_median_frac.csv')
            try:
                df_bins = pd.DataFrame({'bin_center': bin_centers, 'median_frac': median_frac})
                df_bins.to_csv(combined_bins_file, index=False)
                print(f'Combined bin centers and median frac written to {combined_bins_file}')
            except Exception as e:
                print(f'Could not write combined bin centers and median frac: {e}')

            plt.figure(figsize=(8,6))
            xmax = np.nanmax(bin_centers)
            plt.xlim(0, xmax)
            plt.scatter(igood_all_clip, fracgood_all_clip, s=6, alpha=0.2, label='All SBs', linewidths=0)
            plt.plot(bin_centers, median_frac, 'ko-', label='Binned median (log bins)', markersize=5, lw=2, zorder=10)

            # Calculate empirical baseline: mean of highest N binned medians
            N_high = 3
            median_frac_arr = np.array(median_frac)
            # Only use non-NaN bins
            valid_idx = np.where(~np.isnan(median_frac_arr))[0]
            if len(valid_idx) >= N_high:
                high_bins = median_frac_arr[valid_idx[-N_high:]]
                empirical_baseline = np.mean(high_bins)
            else:
                empirical_baseline = np.nan
            plt.axhline(empirical_baseline, color='red', linestyle=':', label=f'Instrumental pol: {empirical_baseline*100:.3g}%\n(Mean of highest {N_high} bins)')

            plt.xlabel('Stokes I peak flux (mJy/beam)')
            plt.ylabel('Linear polarized fraction')
            plt.title(f'Combined Polarization Fraction vs Stokes I (All SBs with pol S/N < {polSNR})')
            plt.ylim(0, 0.2)
            #plt.xlim(0, 3000)
            plt.tight_layout()
            plt.legend()
            plt.savefig(os.path.join(output_dir, 'combined_polfrac_vs_I.png'))
            plt.close()
            print('Combined plot with empirical baseline saved as combined_polfrac_vs_I.png')
        except Exception as e:
            print(f'Could not process combined data: {e}')

    print("All done!")
    # Save the validation stats. min_frac is the a/I + c fit evaluated at
    # the brightest selected component; min_frac_binned is the mean of the
    # three highest-I binned medians. Both in percent.
    validationStats = pd.DataFrame({
        "SB": sbList,
        "field": fieldList,
        "status": statusList,
        "mjd": mjdList,
        "date_utc": pd.to_datetime(np.array(mjdList) + 2400000.5, unit="D", origin="julian").strftime("%Y-%m-%d %H:%M"),
        "min_frac": all_mins,
        "min_frac_binned": all_mins_median,
    })
    validationStats.to_csv(os.path.join(output_dir, "validation_stats.csv"), index=False)

    print(f"\nSummary:")
    print(f"  Total SBs queried: {nSB}")
    print(f"  SBs with missing filtered.csv: {len(not_found_SBs)}")
    if not_found_SBs:
        print("  List of missing SBs:")
        for sb, field in not_found_SBs:
            print(f"    SB: {sb}, field: {field}")
    
    ##############################################################################
    # Binned-median leakage floor per SBID against observation start time.
    order = np.argsort(mjdList)
    mjd_sorted = np.array(mjdList)[order]
    time_sorted = pd.to_datetime(mjd_sorted + 2400000.5, unit="D", origin="julian")
    floor_sorted = np.array(all_mins_median)[order]
    fig, ax = plt.subplots(figsize=(10, 5))
    mask_nan = np.isnan(floor_sorted)
    ax.scatter(time_sorted[~mask_nan], floor_sorted[~mask_nan], s=15, label='min_dLP (from binned median)', color='purple')
    if not hide_missing and np.any(mask_nan):
        ax.scatter(time_sorted[mask_nan], np.ones(np.sum(mask_nan)) * 1e-3, s=40, color='red', marker='x', label='Missing SBIDs')
    ax.set_xlabel('Observation start (UTC)')
    ax.set_ylabel('% Polarisation')
    ax.set_title('Min Fractional Linear Polarisation (all SBIDs)')
    ax.set_yscale('log')
    ax.set_ylim(1e-3, 20.0)
    fig.autofmt_xdate()
    total_SBIDs = len(sbList)
    missing_SBIDs = len(not_found_SBs)
    usable_SBIDs = total_SBIDs - missing_SBIDs
    mean_min_dlp = np.nanmean(floor_sorted)

    summary_text = (
        f"Total SBIDs: {total_SBIDs}\n"
        f"Missing: {missing_SBIDs}\n"
        f"Usable: {usable_SBIDs}\n"
        f"Mean Instrumental Pol: {mean_min_dlp:.3f}% \n(using binned median)\n"
        f"sources with pol S/N < {polSNR}"
    )
    ax.text(0.02, 0.98, summary_text, fontsize=10, ha='left', va='top', transform=ax.transAxes, bbox=dict(facecolor='white', alpha=0.7, edgecolor='gray'))
    ax.legend()
    fig.tight_layout()
    fig.savefig(os.path.join(output_dir, 'min_frac_vs_time.png'))
    plt.close(fig)


if __name__ == "__main__":
    main()


