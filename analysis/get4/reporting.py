"""Console reports: per-image summary, imaging flags, batch summary and lot comparison."""

import numpy as np
from scipy import stats

from .constants import Z95


def print_comparison(c: dict, name_a: str, name_b: str, tol_note: str) -> None:
    """Human-readable report of compare_lots()."""
    print(f"\n=== {name_b} vs {name_a} (baseline) ===")
    sa, sb = c["scale_nm"]

    def scale_text(s: float | None) -> str:
        return f"{s:.2f}" if s else "unknown"

    print(
        f"  scale: {scale_text(sa)} vs {scale_text(sb)} nm/px"
        + ("  -> MISMATCH, not comparable" if c["scale_mismatch"] else "")
    )
    print(f"  tolerances: {tol_note}")
    if c["flagged_images"]:
        print(f"  imaging flagged in: {', '.join(c['flagged_images'])}")
    for r in c["phases"]:
        rel = f" ({100 * r['delta_rel']:+.0f}%)" if r["delta_rel"] is not None else ""
        lo, hi = r["interval95"]
        print(
            f"\n  {r['phase']:13s} {name_a} {r['phi_a']:.4f} -> {name_b} {r['phi_b']:.4f}:  "
            f"delta {r['delta']:+.4f}{rel}, 95% interval [{lo:+.4f}, {hi:+.4f}], tolerance +-{r['tolerance']:.4f}"
        )
        t95 = float(stats.t.ppf(0.975, r["dof"])) if np.isfinite(r["dof"]) else Z95
        dof_text = f"t, {r['dof']:.1f} dof" if np.isfinite(r["dof"]) else "z"
        print(
            f"  {'':13s} interval = sampling +-{t95 * r['se_sampling']:.4f} ({dof_text})"
            f" (images {r['n_images'][0]} vs {r['n_images'][1]}) + systematic +-{r['systematic_halfwidth']:.4f}"
            f" ({r['systematic_kind']})"
        )
        w = r["interval_width"]
        print(
            f"  {'':13s} width from: "
            + ", ".join(f"{k} +-{v:.4f}" for k, v in w.items())
            + f"  (largest: {max(w, key=w.get)})"
        )
        pd_, pb = r["p_direction"], r["p_beyond_tolerance"]
        print(
            f"  {'':13s} real change ({'up' if r['delta'] >= 0 else 'down'}):"
            f"  P = {pd_[0]:.2f}-{pd_[1]:.2f}  -> {r['how_sure_real_change']}"
        )
        print(
            f"  {'':13s} change beyond +-{r['tolerance']:.4f}:  P = {pb[0]:.2f}-{pb[1]:.2f}"
            f"  -> {r['how_sure_beyond_tolerance']}"
        )
        for cav in r["caveats"]:
            print(f"  {'':13s}    note: {cav}")
        if r["to_settle"]:
            print(f"  {'':13s}    to be sure: {r['to_settle']}")
    s = next(r for r in c["phases"] if r["phase"] == c["strongest_evidence"])
    print(
        f"\n  strongest evidence of a change beyond tolerance: {s['phase']} "
        f"(P = {s['p_beyond_tolerance'][0]:.2f}-{s['p_beyond_tolerance'][1]:.2f})"
    )
    print("  P ranges span the segmentation bias bound; they say how sure we are, not what to decide.")


def print_image_summary(result: dict) -> None:
    """Console summary of analyse_image()."""
    px, target = result["pixel_size_nm_used"], result["target_pixel_nm"]
    h, w = result["shape_px"]
    ah, aw = result["shape_analysed"]
    px_text = f"{px:.2f} nm/px" if px else "pixel size unknown"
    scale_text = f"analysed at {target:.2f} nm/px" if target else "analysed in binned px"
    bar_text = f", {result['databar_rows']} databar rows cropped" if result["databar_rows"] else ""
    print(f"\n=== {result['image']}  ({w} x {h} px, {px_text}{bar_text}; {scale_text} -> {aw} x {ah}) ===")
    q = result["quality"]
    print(
        f"  imaging: sharpness {q['sharpness']:.3f}, x/y blur ratio {q['anisotropy']:.2f}, noise {q['noise']:.3f}, "
        f"separability {q['separability']:.2f}, "
        f"clipped black/white {100 * q['clipped_black']:.1f}/{100 * q['clipped_white']:.1f}%, "
        f"curtaining {q['stripes_curtaining']:.2f} ({q['stripes_curtaining_angle']:+.0f} deg), "
        f"scan lines {q['stripes_scan_lines']:.2f}"
    )
    if result["preprocessing"]:
        print(f"  preprocessing: {'; '.join(result['preprocessing'])}")
    n_refit, n_tiles = result["local_threshold_tiles"]
    print(f"  local thresholds re-fitted in {n_refit}/{n_tiles} tiles")
    for name, r in result["phases"].items():
        d = r["dispersion"]
        reg = f"D={d['D']:.2f} [{d['D_90'][0]:.2f}-{d['D_90'][1]:.2f}]" if d else "D=n/a (image too small)"
        trend = r["depth_trend"]
        tr = f"top->bottom {trend['change_top_to_bottom']:+.3f} +- {Z95 * trend['se']:.3f}" if trend else ""
        estimate = "phi" if result["detector"] == "BSE" else "fraction"
        print(
            f"  {name:22s} {estimate}={r['phi']:.4f}  +- {Z95 * r['se_image']:.4f} (95%)  "
            f"N_eff~{r['n_eff']:,.0f}  regularity {reg}  {tr}"
        )
        if d and d["D_90"][0] > 1:
            print(
                f"  {'':13s} -> image is NOT statistically regular for {name}: error bar inflated x{np.sqrt(d['D']):.2f}"
            )
        if trend and abs(trend["change_top_to_bottom"]) > Z95 * trend["se"]:
            print(f"  {'':13s} -> significant through-thickness gradient (if image y is the electrode depth)")
        lo, hi = r["threshold_range"]
        print(
            f"  {'':13s} systematic: threshold {lo:.4f}-{hi:.4f}, local shading/roughness shift {r['shading_shift']:+.4f}"
        )
        if r["resolution_limited"]:
            print(f"  {'':13s} -> RESOLUTION-LIMITED: features < 5 px at this scale, phi biased by edge pixels")


def print_quality_report(results: list[dict], reference: str) -> None:
    """Console list of the imaging flags of every image."""
    print(f"\n=== imaging conditions vs {reference} ===")
    for r in results:
        flags = r["imaging_flags"]
        if flags:
            print(f"  {r['image']}: imaging differs from reference")
            for f in flags:
                print(f"      {f}")
        else:
            print(f"  {r['image']}: consistent")
    if any(r["imaging_flags"] for r in results):
        print("  -> differences in flagged images may come from imaging, not material: check these first.")


def print_batch_summary(batch: dict) -> None:
    """Console summary of analyse_batch()."""
    print("\n=== batch: pooled over fields of view (random effects) ===")
    for name, b in batch.items():
        bud = b["budget"]
        total = sum(bud.values())
        shares = ", ".join(f"{k} {100 * v / total:.0f}%" for k, v in bud.items())
        pi = b["prediction_interval_new_field"]
        print(
            f"  {name:13s} phi={b['phi']:.4f}  95% CI [{b['ci95'][0]:.4f}, {b['ci95'][1]:.4f}]"
            f"  ({b['n_images']} images, {b['bits']:.1f} bits)"
        )
        print(
            f"  {'':13s} field-to-field tau={b['tau']:.4f} ({b['tau2_source']}), I2={100 * b['I2']:.0f}%"
            + (f", a new field should land in [{pi[0]:.4f}, {pi[1]:.4f}]" if pi else "")
        )
        print(f"  {'':13s} uncertainty budget: {shares}")
        nx = b["next"]
        gain = nx["bits_more_fields"] - nx["bits_bigger_fields"]
        if gain > 0.05:
            best = f"MORE LOCATIONS beat bigger fields (+{nx['bits_more_fields']:.2f} vs +{nx['bits_bigger_fields']:.2f} bits)"
        else:
            best = f"bigger fields as good as more locations (+{nx['bits_bigger_fields']:.2f} bits), and cheaper"
        print(f"  {'':13s} next {b['n_images']}-fields' worth of imaging: {best}")
        lo, hi = b["systematic_range"]
        print(
            f"  {'':13s} systematic range {lo:.4f}-{hi:.4f} (threshold + shading/roughness, mean shading shift "
            f"{b['shading_shift_mean']:+.4f}; not reduced by more imaging)"
        )
        if b["n_images"] < 3 and "baseline" not in b["tau2_source"]:
            print(
                f"  {'':13s} WARNING: <3 images, field-to-field variation is unknown or poorly known; CI is optimistic."
            )
