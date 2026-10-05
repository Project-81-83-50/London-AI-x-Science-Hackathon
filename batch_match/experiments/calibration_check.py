r"""
Calibration test: are the per-image error bars of get4.py the right size?

One image is preprocessed and segmented once, exactly as get4.py does, then cut into
non-overlapping square crops. Each crop is analysed as if it were its own image
(get4.analyse_phase), giving a predicted SE. If those SEs are honest, the crops' phase
fractions should scatter around each other by about that much:

    ratio    = observed sd of crop phi / RMS predicted SE        (should be ~1)
    coverage = share of crops whose phi lies within 1.96 SE of the
               mean of the OTHER crops                           (should be ~95%)

ratio > 1: error bars too small (overconfident). ratio < 1: too large (cautious).
Shown for the full SE (area + regularity) and the area-only SE, so the effect of
the overdispersion correction D is visible. "full-image C" predicts every crop's SE
from the WHOLE image's C(r) instead: if that ratio is ~1 but the per-crop one is not,
the error model is right and small crops just estimate their feature size badly.

Segmentation is shared by all crops, so this tests the SAMPLING uncertainty only,
not the segmentation range.

    python experiments/calibration_check.py IMAGE_BSE.tif     # from batch_match/; chart in out/calibration.png
"""

import argparse
import sys
from pathlib import Path

import numpy as np
from scipy import stats

PROJECT_DIR = Path(__file__).resolve().parents[1]  # batch_match/
sys.path.insert(0, str(PROJECT_DIR))  # so batch_classifier / get4 import when run from anywhere

import get4  # noqa: E402


def prepare_labels(path):
    """Same loading, preprocessing and segmentation as get4.analyse_image."""
    meta = get4.read_meta(path)
    px = meta["pixel_size_nm"]
    img, info = get4.load_image(path, meta, px_nm=px, target_nm=px)
    quality = get4.image_quality(img)
    img, _ = get4.flatten_shading(img)
    img, applied = get4.destripe(img, quality)
    labels, thresholds, _ = get4.segment_bse(img)
    return labels, px, info, applied


def crops(labels, side):
    h, w = labels.shape
    ny, nx = h // side, w // side
    y0, x0 = (h - ny * side) // 2, (w - nx * side) // 2
    for i in range(ny):
        for j in range(nx):
            yield labels[y0 + i * side : y0 + (i + 1) * side, x0 + j * side : x0 + (j + 1) * side]


def calibrate(phis, ses):
    """Observed scatter vs predicted SE, with a 90% interval on the ratio."""
    phis, ses = np.asarray(phis), np.asarray(ses)
    k = len(phis)
    observed = phis.std(ddof=1)
    predicted = np.sqrt(np.mean(ses**2))
    ratio = observed / predicted
    dof = k - 1
    ratio_90 = [ratio * np.sqrt(dof / stats.chi2.ppf(0.95, dof)), ratio * np.sqrt(dof / stats.chi2.ppf(0.05, dof))]
    loo_mean = (phis.sum() - phis) / (k - 1)
    z = (phis - loo_mean) / np.sqrt(ses**2 + np.mean(ses**2) / (k - 1))
    return {
        "ratio": ratio,
        "ratio_90": ratio_90,
        "coverage": float(np.mean(np.abs(z) < get4.Z95)),
        "observed_sd": observed,
        "predicted_se": predicted,
    }


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("image")
    p.add_argument("--sides", default="952,476,317,238", help="crop side lengths in analysed px")
    p.add_argument("--out", default=str(PROJECT_DIR / "out" / "calibration.png"), help="where to save the chart")
    args = p.parse_args()

    labels, px, info, applied = prepare_labels(args.image)
    h, w = labels.shape
    print(
        f"{Path(args.image).name}: {h} x {w} px at {px:.2f} nm/px"
        + (f", removed {', '.join(applied)}" if applied else "")
    )
    print(
        "ratio = observed scatter / predicted SE (want ~1, 90% interval in brackets); "
        "coverage of 95% intervals (want ~95%)\n"
    )

    full_lag = min(h, w) // 2
    full_cov = {}
    for k, name in get4.PHASES.items():
        cov, phi = get4.normalised_covariance(labels == k, full_lag)
        lx, ly = get4.correlation_length(cov, full_lag, "x"), get4.correlation_length(cov, full_lag, "y")
        full_cov[name] = (get4.integral_range(cov, full_lag, np.sqrt(lx * ly) if lx and ly else None)[3], phi)

    rows = []
    for side in (int(s) for s in args.sides.split(",")):
        sizes = np.unique(np.geomspace(4, side // 2, 16).astype(int))
        per_phase = {name: {"phi": [], "se": [], "se_area": [], "D": []} for name in get4.PHASES.values()}
        for crop in crops(labels, side):
            for k, name in get4.PHASES.items():
                r = get4.analyse_phase(crop == k, side // 2, None, sizes, 1.0)
                d = per_phase[name]
                d["phi"].append(r["phi"])
                d["se"].append(r["se_image"])
                d["se_area"].append(np.sqrt(r["var_area"]))
                d["D"].append(r["dispersion"]["D"] if r["dispersion"] else np.nan)
        n = len(per_phase[get4.PHASES[0]]["phi"])
        print(f"crops {side} x {side} px ({side * px / 1000:.1f} um), n = {n}")
        for name, d in per_phase.items():
            full = calibrate(d["phi"], d["se"])
            area = calibrate(d["phi"], d["se_area"])
            lo, hi = full["ratio_90"]
            cov_trunc, phi_all = full_cov[name]
            whole = full["observed_sd"] / get4.predicted_se(cov_trunc, full_lag, phi_all, side, side)
            full["whole_ratio"] = whole
            full["whole_ratio_90"] = [whole * b / full["ratio"] for b in full["ratio_90"]]
            print(
                f"  {name:13s} phi {np.mean(d['phi']):.4f}  observed sd {full['observed_sd']:.4f}  "
                f"predicted SE {full['predicted_se']:.4f}  ratio {full['ratio']:.2f} [{lo:.2f}-{hi:.2f}]  "
                f"coverage {100 * full['coverage']:.0f}%   | area-only: ratio {area['ratio']:.2f}, "
                f"coverage {100 * area['coverage']:.0f}%   | median D {np.nanmedian(d['D']):.2f}"
                f"   | full-image C: ratio {whole:.2f}"
            )
            rows.append((side, name, full, area))
        print()

    bad = [(s, n, f) for s, n, f, _ in rows if not f["ratio_90"][0] <= 1 <= f["ratio_90"][1]]
    if not bad:
        print("RESULT: predicted SEs match the observed scatter at every crop size (1 inside every 90% interval).")
    else:
        print("RESULT: mismatch (1 outside the 90% interval) for:")
        for s, n, f in bad:
            kind = "too SMALL (overconfident)" if f["ratio"] > 1 else "too LARGE (cautious)"
            print(f"  {s} px {n}: error bars {kind} by x{f['ratio']:.2f}")
        print("Some misses are expected by chance (each check is a 90% interval).")

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    plot_calibration(rows, px / 1000, min(h, w), Path(args.image).name, out)
    print(f"\nchart: {out}")


def plot_calibration(rows, px_um, full_side, image_name, out_png):
    """Ratio (observed / predicted) vs crop size: each crop's own SE, and SE from the full image's C(r)."""
    plt = get4._style()
    panels = [
        ("ratio", "ratio_90", "Each crop's own error bar\n(what GET4 does for every image)"),
        ("whole_ratio", "whole_ratio_90", "Error bar using the full image's feature size\n(isolates the error model)"),
    ]
    fig, axes = plt.subplots(1, 2, figsize=(12, 5), sharey=True, facecolor=get4.SURFACE)
    sides = sorted({s for s, *_ in rows})
    dodge = {name: 1 + 0.035 * (i - 1) for i, name in enumerate(get4.PHASES.values())}
    for ax, (key, key90, title) in zip(axes, panels):
        ax.set_facecolor(get4.SURFACE)
        ax.axhspan(0.8, 1.25, color=get4.GRID, alpha=0.6, lw=0, zorder=0)
        ax.axhline(1, color=get4.INK2, lw=1, zorder=1)
        ax.axvline(full_side * px_um, color=get4.INK2, lw=1, ls=":", zorder=1)
        ax.text(full_side * px_um, 2.3, " full image\n (shortest side)", color=get4.INK2, fontsize=9, va="top")
        for k, name in get4.PHASES.items():
            pts = sorted((s, f) for s, n, f, _ in rows if n == name)
            x = np.array([s * px_um for s, _ in pts]) * dodge[name]
            y = np.array([f[key] for _, f in pts])
            err = np.array([[f[key] - f[key90][0], f[key90][1] - f[key]] for _, f in pts]).T
            c = get4.PHASE_COLORS[k]
            ax.plot(x, y, "-", color=c, lw=2, zorder=2)
            ax.errorbar(
                x,
                y,
                yerr=err,
                fmt="o",
                color=c,
                ms=8,
                mec=get4.SURFACE,
                mew=2,
                elinewidth=1.5,
                capsize=0,
                zorder=3,
                label=name,
            )
        ax.set_xscale("log")
        ax.set_yscale("log")
        ax.set_xticks([s * px_um for s in sides] + [full_side * px_um])
        ax.set_xticklabels([f"{s * px_um:.0f}" for s in sides] + [f"{full_side * px_um:.0f}"])
        ax.set_yticks([0.5, 0.67, 0.8, 1, 1.25, 1.5, 2])
        ax.set_yticklabels(["0.5", "0.67", "0.8", "1", "1.25", "1.5", "2"])
        ax.minorticks_off()
        ax.set_ylim(0.45, 2.4)
        ax.grid(True, axis="y", color=get4.GRID, lw=0.8)
        ax.set_xlabel("image (crop) side length, um")
        ax.set_title(title, loc="left", color=get4.INK, fontsize=11)
        for s in ax.spines.values():
            s.set_visible(False)
    axes[0].set_ylabel("observed scatter / predicted error bar")
    axes[0].text(
        0.02,
        0.97,
        "above 1: error bar too small (overconfident)",
        transform=axes[0].transAxes,
        color=get4.INK2,
        fontsize=9,
        va="top",
    )
    axes[0].text(
        0.02,
        0.03,
        "below 1: error bar too large (cautious)",
        transform=axes[0].transAxes,
        color=get4.INK2,
        fontsize=9,
        va="bottom",
    )
    axes[1].legend(loc="upper right", frameon=False, fontsize=9)
    fig.suptitle(
        f"Are the error bars the right size?  {image_name} cut into crops  "
        "(grey band = within 20%, bars = 90% interval)",
        x=0.01,
        ha="left",
        color=get4.INK,
        fontsize=12,
    )
    fig.tight_layout()
    fig.savefig(out_png, dpi=130, facecolor=get4.SURFACE, bbox_inches="tight")
    plt.close(fig)


if __name__ == "__main__":
    main()
