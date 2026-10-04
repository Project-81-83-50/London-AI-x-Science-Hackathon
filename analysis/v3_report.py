"""
General and detailed batch reports built on lucas-sem-analysis v3 (frontend: General report / Detailed report).

Every number comes from Lucas's committed v3 outputs for the 31 reference locations
(lucas-sem-analysis-v3/outputs/metrics), so it reflects v3's U-Net four-phase segmentation, not the intensity
classes of analysis.kpis. Nothing is re-segmented here, and the v3 model weights are not needed.

Per location:
- composition, three phases first (pore / carbon / SiOx, binder merged into carbon; 87% agreement with an
  independent annotator), then four (graphite and binder, binder precision ~0.5), with pore split into deep and
  open (grey-floored) pores, v3's standard errors and its segmentation stability;
- SiOx particles from v3's instance table (particle_sizes.csv): density, sizes, shape, clustering (Clark-Evans)
  and where in the field the SiOx sits;
- supplementary image KPIs (v3 src/kpi.py: thresholds, texture, orientation, spectra; no segmentation), with
  Lucas's session-sensitivity flags.

Per metric across the three batches: means, Kruskal-Wallis p, a session-stratified permutation p (labels
shuffled only within image-height groups, i.e. imaging sessions), Benjamini-Hochberg q, Holm-corrected pairwise
Mann-Whitney p and Cliff's delta of this batch against the other two.

The unknown batch (data/processed/v3_report/batch_unknown.json) has the same structure, with the unknown
locations as the report's own batch (even a single location). Its measurements come from analysis.v3_unknown,
which segments the unknown images with v3's CPU-trained teacher (or a one-detector model distilled from it), and
it is compared with the reference batches as segmented by the SAME teacher.

    python -m analysis.v3_report                  # batch_{1,2,3}.json, and batch_unknown.json if measured
    python -m analysis.v3_report --unknown-only   # only batch_unknown.json (used after uploads)
"""

import argparse
import csv
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from scipy import stats

ROOT = Path(__file__).resolve().parents[1]
V3 = ROOT / "lucas-sem-analysis-v3"
METRICS = V3 / "outputs" / "metrics"
OUT = ROOT / "data" / "processed" / "v3_report"
BATCHES = ["Batch_1", "Batch_2", "Batch_3"]
PX_UM = 0.05            # v3 working resolution (50 nm/px); n_valid_px is counted at it
RAW_PX_UM = 0.025       # raw resolution; the height group is the raw image height in px
N_PERM = 5000
ALPHA = 0.05

# id: (name, unit, group, description). Units: "%" are percent of the analysed field.
SEGMENTATION_METRICS = {
    "pore_pct": ("Pore", "%", "composition", "Pore fraction (deep + open pores)"),
    "carbon_pct": ("Carbon (graphite + binder)", "%", "composition", "Graphite and binder together"),
    "SiOx_pct": ("SiOx", "%", "composition", "Silicon-oxide additive fraction"),
    "graphite_pct": ("Graphite", "%", "four_phase", "Graphite flakes"),
    "CBD_pct": ("Carbon-binder domain", "%", "four_phase", "Binder; precision ~0.5, an indication only"),
    "pore_deep_pct": ("Deep pores", "%", "four_phase", "Pores with a dark floor"),
    "pore_open_pct": ("Open pores", "%", "four_phase", "Pores with a grey floor (sub-surface visible)"),
    "siox_per_1000um2": ("SiOx particle density", "per 1000 µm²", "siox", "SiOx particles per 1000 µm²"),
    "siox_median_ecd_um": ("SiOx median diameter", "µm", "siox", "Median equivalent-circle diameter"),
    "siox_area_d50_um": ("SiOx area-weighted diameter", "µm", "siox",
                         "Diameter below which half of the SiOx area lies"),
    "siox_p90_ecd_um": ("SiOx 90th-percentile diameter", "µm", "siox", "Large-particle end of the size range"),
    "siox_aspect_median": ("SiOx aspect ratio", "ratio", "siox", "Median major/minor axis ratio"),
    "siox_clark_evans": ("SiOx spacing (Clark-Evans)", "ratio", "siox",
                         "Nearest-neighbour spacing vs random: <1 clustered, >1 evenly spread"),
    "siox_top_share": ("SiOx in top half of field", "%", "siox", "Share of SiOx area in the upper half"),
}
IMAGE_KPI_NAMES = {
    "thr_dark_frac": ("Dark (pore) fraction, threshold", "%"),
    "thr_dark_frac_fixed020": ("Dark fraction, fixed threshold 0.20", "%"),
    "thr_bright_frac": ("Bright (SiOx) fraction, threshold", "%"),
    "bse_siox_contrast_ratio": ("SiOx contrast ratio", "ratio"),
    "bse_mid_skew": ("Mid-grey skewness", ""),
    "bse_mid_kurtosis": ("Mid-grey kurtosis", ""),
    "bse_entropy": ("BSE grey-level entropy", "bits"),
    "bse_edge_density": ("BSE edge density", "per µm²"),
    "inlens_edge_density": ("InLens edge density", "per µm²"),
    "dark_n_per_1000um2": ("Pore count density", "per 1000 µm²"),
    "dark_median_ecd_um": ("Pore median diameter", "µm"),
    "dark_p90_ecd_um": ("Pore 90th-percentile diameter", "µm"),
    "dark_aspect_aw": ("Pore aspect ratio (area-weighted)", "ratio"),
    "dark_solidity_aw": ("Pore solidity (area-weighted)", "ratio"),
    "dark_circularity_med": ("Pore circularity", "ratio"),
    "dark_horizontal_order": ("Pore horizontal alignment", "−1…1"),
    "dark_clark_evans": ("Pore spacing (Clark-Evans)", "ratio"),
    "dark_boundary_fractal_dim": ("Pore boundary fractal dimension", ""),
    "dark_chord_H_over_V": ("Pore chord, horizontal / vertical", "ratio"),
    "dark_cv_10um": ("Pore heterogeneity (10 µm windows, CV)", "ratio"),
    "dark_top_over_bottom": ("Pore fraction, top / bottom half", "ratio"),
    "dark_lacunarity_5um": ("Pore lacunarity (5 µm)", ""),
    "bright_n_per_1000um2": ("Bright particle density", "per 1000 µm²"),
    "bright_median_ecd_um": ("Bright particle median diameter", "µm"),
    "bright_p90_ecd_um": ("Bright particle 90th-percentile diameter", "µm"),
    "bright_aspect_aw": ("Bright particle aspect ratio", "ratio"),
    "bright_solidity_aw": ("Bright particle solidity", "ratio"),
    "bright_circularity_med": ("Bright particle circularity", "ratio"),
    "bright_horizontal_order": ("Bright particle horizontal alignment", "−1…1"),
    "bright_clark_evans": ("Bright particle spacing (Clark-Evans)", "ratio"),
    "bright_cv_25um": ("Bright heterogeneity (25 µm windows, CV)", "ratio"),
    "flake_coherence_mean": ("Flake orientation coherence", "0…1"),
    "flake_order_parameter": ("Flake orientation order", "0…1"),
    "flake_tilted_frac": ("Tilted flake share (>30°)", "0…1"),
    "psd_slope": ("Power-spectrum slope", ""),
    "psd_anisotropy": ("Power-spectrum anisotropy", "ratio"),
}


def read_csv(name):
    with open(METRICS / name, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def location_metrics():
    """One row per reference location: v3 segmentation metrics, SEs, stability, SiOx particles."""
    phases = read_csv("phase_fractions.csv")
    se = {r["sample_id"]: r for r in read_csv("v3_material_se.csv")}
    stab = {r["sample_id"]: r for r in read_csv("stability.csv")}
    siox = {r["sample_id"]: r for r in read_csv("siox_summary.csv")}
    particles = {}
    for r in read_csv("particle_sizes.csv"):
        particles.setdefault(r["sample_id"], []).append(r)
    facts = {p.stem: json.loads(p.read_text(encoding="utf-8")) for p in (V3 / "outputs" / "batchid").glob("*.json")}
    rows = []
    for r in phases:
        sid = r["sample_id"]
        height_px = int(r["height_group"].lstrip("h"))
        area = float(r["n_valid_px"]) * PX_UM ** 2
        m = {k: num(r[k]) for k in ("pore_pct", "graphite_pct", "SiOx_pct", "CBD_pct", "pore_deep_pct",
                                    "pore_open_pct", "excluded_pct")}
        m["carbon_pct"] = m["graphite_pct"] + m["CBD_pct"]
        s = siox.get(sid, {})
        m["siox_per_1000um2"] = num(s.get("per_1000um2"))
        m["siox_median_ecd_um"] = num(s.get("eq_diam_median_um"))
        m["siox_p90_ecd_um"] = num(s.get("eq_diam_p90_um"))
        ps = particles.get(sid, [])
        a = np.array([float(p["area_um2"]) for p in ps])
        d = np.array([float(p["eq_diam_um"]) for p in ps])
        inside = np.array([p["touches_excluded"] != "True" for p in ps])
        if len(a):
            order = np.argsort(d)
            cum = np.cumsum(a[order]) / a.sum()
            m["siox_area_d50_um"] = float(d[order][np.searchsorted(cum, 0.5)])
            m["siox_aspect_median"] = float(np.median([float(p["aspect_ratio"]) for p in np.array(ps)[inside]]))
            xy = np.array([[float(p["centroid_x_um"]), float(p["centroid_y_um"])] for p in ps])
            if len(xy) > 3:
                from scipy.spatial import cKDTree
                nn = cKDTree(xy).query(xy, k=2)[0][:, 1].mean()
                m["siox_clark_evans"] = float(nn / (0.5 / np.sqrt(len(xy) / area)))
            m["siox_top_share"] = float(100 * a[xy[:, 1] < height_px * RAW_PX_UM / 2].sum() / a.sum())
        decision = (facts.get(sid) or {}).get("decision") or {}
        rows.append({
            "sample_id": sid, "batch": r["batch"], "session": r["height_group"], "field_area_um2": round(area, 1),
            "metrics": {k: (round(v, 4) if v is not None else None) for k, v in m.items()},
            "standard_error_pp": {k: num(se.get(sid, {}).get(f"{k}_se_pp")) for k in ("pore", "carbon", "SiOx")},
            "stability_sd_pp": {k: num(stab.get(sid, {}).get(f"{k}_sd")) for k in ("pore", "graphite", "SiOx", "CBD")},
            "siox_particle_count": int(num(s.get("n_particles")) or 0),
            "decision": {"answer": decision.get("answer"), "answer_type": decision.get("answer_type"),
                         "confidence": decision.get("confidence")} if decision else None,
            "summary_sentences": (facts.get(sid) or {}).get("summary_sentences", []),
            # Overlays exist once run_cpu_pipeline.py has rebuilt the label maps (from the CPU teacher, so they can
            # differ slightly from the U-Net numbers in this report).
            **({"overlay": f"/batches/{r['batch'][-1]}/lucas-report/overlays/{sid}",
                "model_label": "overlay: v3 teacher (CPU rebuild); numbers: v3 U-Net",
                "segmented_from": ["BSE", "InLens"]}
               if (V3 / "outputs" / "segmentation" / r["batch"] / sid / "overlay.jpg").is_file() else {}),
        })
    return rows


def holm(ps):
    order = np.argsort(ps)
    out, running = [0.0] * len(ps), 0.0
    for rank, i in enumerate(order):
        running = max(running, min(1.0, (len(ps) - rank) * ps[i]))
        out[i] = running
    return out


def bh(ps):
    ps = np.asarray(ps, float)
    order = np.argsort(ps)
    q = ps[order] * len(ps) / np.arange(1, len(ps) + 1)
    q = np.minimum.accumulate(q[::-1])[::-1]
    out = np.empty_like(q)
    out[order] = np.minimum(q, 1)
    return out.tolist()


def cliffs_delta(a, b):
    a, b = np.asarray(a)[:, None], np.asarray(b)[None, :]
    return float(((a > b).sum() - (a < b).sum()) / (a.size * b.size))


def session_p(v, y, strata, rng):
    """Kruskal-Wallis H with labels permuted only inside each imaging session."""
    h0 = stats.kruskal(*[v[y == b] for b in BATCHES]).statistic
    groups = [np.nonzero(strata == s)[0] for s in np.unique(strata)]
    hits = 0
    for _ in range(N_PERM):
        yp = y.copy()
        for g in groups:
            yp[g] = rng.permutation(y[g])
        if len({*yp}) == 3 and stats.kruskal(*[v[yp == b] for b in BATCHES]).statistic >= h0 - 1e-12:
            hits += 1
    return (hits + 1) / (N_PERM + 1)


def compare(values, y, strata, rng):
    """Cross-batch statistics for one metric (values aligned with y)."""
    v = np.asarray(values, float)
    ok = np.isfinite(v)
    v, yy, ss = v[ok], y[ok], strata[ok]
    out = {"batch": {}}
    for b in BATCHES:
        x = v[yy == b]
        out["batch"][b] = {"n": int(len(x)), "mean": float(x.mean()), "sd": float(x.std(ddof=1)),
                           "median": float(np.median(x)), "min": float(x.min()), "max": float(x.max())}
    out["kruskal_p"] = float(stats.kruskal(*[v[yy == b] for b in BATCHES]).pvalue)
    out["session_stratified_p"] = float(session_p(v, yy, ss, rng))
    pairs = [("Batch_1", "Batch_2"), ("Batch_1", "Batch_3"), ("Batch_2", "Batch_3")]
    raw = [float(stats.mannwhitneyu(v[yy == a], v[yy == b]).pvalue) for a, b in pairs]
    out["pairwise_holm_p"] = {f"{a[-1]}v{b[-1]}": round(p, 4) for (a, b), p in zip(pairs, holm(raw))}
    out["cliffs_delta_vs_rest"] = {b: round(cliffs_delta(v[yy == b], v[yy != b]), 3) for b in BATCHES}
    return out


def describe(batch, mid, name, unit, s, robust):
    """One plain-language finding: where this batch sits on a metric that differs between batches."""
    means = {b: s["batch"][b]["mean"] for b in BATCHES}
    rank = sorted(BATCHES, key=lambda b: means[b])
    pos = "lowest" if rank[0] == batch else "highest" if rank[-1] == batch else "middle"
    fmt = ((lambda x: f"{x:.1f}%") if unit == "%" else (lambda x: f"{x:.3f}") if unit == "ratio"
           else (lambda x: f"{x:.2f} {unit}"))
    others = ", ".join(f"{fmt(means[b])} in batch {b[-1]}" for b in BATCHES if b != batch)
    differs = [k for k, p in s["pairwise_holm_p"].items() if batch[-1] in k and p < ALPHA]
    vs = " and ".join(f"batch {k.replace('v', '').replace(batch[-1], '')}" for k in differs)
    text = (f"{name}: batch {batch[-1]} is {pos if pos != 'middle' else 'between the other two'} at "
            f"{fmt(means[batch])} (vs {others})")
    text += f"; clearly different from {vs} (Holm p < 0.05)." if vs else "."
    if not robust:
        text += " The difference does not hold within imaging sessions, so it may partly reflect how the images were taken."
    return {"metric": mid, "position": pos, "robust": robust, "text": text,
            "session_stratified_p": round(s["session_stratified_p"], 4), "kruskal_p": round(s["kruskal_p"], 4)}


UNKNOWN_MEASUREMENTS = ROOT / "data" / "processed" / "v3_unknown" / "measurements.json"


def size_histogram(rows, edges):
    d = np.concatenate([np.array(r["siox_diameters_um"], float) for r in rows]) if rows else np.array([])
    a = np.concatenate([np.array(r["siox_areas_um2"], float) for r in rows]) if rows else np.array([])
    return {"count_share": (np.histogram(d, edges)[0] / max(len(d), 1)).round(4).tolist(),
            "area_share": (np.histogram(d, edges, weights=a)[0] / max(a.sum(), 1e-9)).round(4).tolist(),
            "n_particles": int(len(d))}


def own_stats(values):
    """Summary of one set of values; the SD needs two locations."""
    x = np.array([v for v in values if v is not None], float)
    if not len(x):
        return None
    return {"n": int(len(x)), "mean": float(x.mean()), "sd": float(x.std(ddof=1)) if len(x) > 1 else None,
            "median": float(np.median(x)), "min": float(x.min()), "max": float(x.max())}


def unknown_report():
    """batch_unknown.json, in the same structure as the batch reports: the unknown locations are the report's
    own batch, set against the reference batches as segmented by the same v3 teacher (analysis.v3_unknown)."""
    if not UNKNOWN_MEASUREMENTS.is_file():
        print("no v3 measurements for the unknown batch (run python -m analysis.v3_unknown); skipped")
        return
    data = json.loads(UNKNOWN_MEASUREMENTS.read_text(encoding="utf-8"))
    ref, unk = data["reference"], data["unknown"]
    rng = np.random.default_rng(0)
    y = np.array([r["batch"] for r in ref])
    strata = np.array([r["session"] for r in ref])
    comparison = {}
    for mid in SEGMENTATION_METRICS:
        s = compare([r["metrics"].get(mid) for r in ref], y, strata, rng)
        own = own_stats([u["metrics"].get(mid) for u in unk])
        if own:
            s["batch"]["unknown"] = own
            pooled = np.sqrt(np.mean([s["batch"][b]["sd"] ** 2 for b in BATCHES])) or 1.0
            s["unknown_z"] = {b: round((own["mean"] - s["batch"][b]["mean"]) / pooled, 2) for b in BATCHES}
            s["unknown_closest"] = min(BATCHES, key=lambda b: abs(s["unknown_z"][b]))
        comparison[mid] = s
    for mid, q in zip(comparison, bh([s["kruskal_p"] for s in comparison.values()])):
        comparison[mid]["kruskal_q"] = round(q, 4)

    findings = []
    for mid, (name, unit, group, _) in SEGMENTATION_METRICS.items():
        s = comparison[mid]
        if s["kruskal_p"] >= ALPHA or "unknown" not in s["batch"]:
            continue
        robust = s["session_stratified_p"] < ALPHA
        fmt = ((lambda x: f"{x:.1f}%") if unit == "%" else (lambda x: f"{x:.3f}") if unit == "ratio"
               else (lambda x: f"{x:.2f} {unit}"))
        own = s["batch"]["unknown"]
        means = ", ".join(f"{fmt(s['batch'][b]['mean'])} in batch {b[-1]}" for b in BATCHES)
        inside = [b[-1] for b in BATCHES if s["batch"][b]["min"] <= own["mean"] <= s["batch"][b]["max"]]
        text = (f"{name}: the unknown {'location is' if own['n'] == 1 else 'locations average'} {fmt(own['mean'])} "
                f"(vs {means}), closest to batch {s['unknown_closest'][-1]}; "
                + (f"inside the range of batch {', '.join(inside)}." if inside else "outside every batch's range."))
        if not robust:
            text += (" The reference batches differ on this metric only across imaging sessions, so it may "
                     "partly reflect how the images were taken.")
        findings.append({"metric": mid, "closest": s["unknown_closest"], "robust": robust, "text": text,
                         "kruskal_p": round(s["kruskal_p"], 4), "session_stratified_p": round(s["session_stratified_p"], 4)})
    findings.sort(key=lambda f: (not f["robust"], f["kruskal_p"]))

    models = sorted({u["model_label"] for u in unk})
    single = {u["model"]: u["model_validation"] for u in unk if u.get("model_validation")}
    edges = np.round(np.geomspace(0.3, 12, 13), 3)
    locations = [{"sample_id": u["sample_id"], "batch": "unknown", "session": u["session"],
                  "metrics": u["metrics"], "standard_error_pp": {}, "stability_sd_pp": {},
                  "siox_particle_count": len(u["siox_diameters_um"]), "decision": None,
                  "model_label": u["model_label"], "segmented_from": u["segmented_from"],
                  "overlay": f"/batches/unknown/v3-report/overlays/{u['sample_id']}"} for u in unk]
    report = {
        "report_type": "v3_batch_report",
        "generated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "batch_id": "unknown",
        "own_key": "unknown",
        "source": data["model"],
        "metrics": [{"id": mid, "name": n, "unit": u_, "group": g, "description": d}
                    for mid, (n, u_, g, d) in SEGMENTATION_METRICS.items()],
        "general": {
            "n_locations": len(unk),
            "sessions": sorted({u["session"] for u in unk}),
            "comparison": comparison,
            "findings": findings,
            "image_kpi_summary": None,
            "decision_summary": None,
            "skipped": data["skipped"],
            "reference_basis": "the 31 reference locations as segmented by the same v3 teacher",
            "quality": {
                "annotator_agreement_4_phase": 0.817, "annotator_agreement_4_phase_ci95": [0.763, 0.861],
                "annotator_agreement_3_phase": 0.871,
                "per_phase_precision": {"SiOx": 0.96, "graphite": 0.83, "pore": 0.69, "CBD": 0.52},
                "models_used": models,
                "single_detector_validation": single,
                "note": "Annotator agreement is v3's, measured on its U-Net. These locations are segmented by v3's "
                        "LightGBM teacher (the U-Net weights are not in this repository) or, with a single usable "
                        "image, by a one-detector model distilled from it; its agreement with the teacher on held-out "
                        "reference locations is listed.",
            },
            "caveats": [
                f"{len(unk)} unknown location{'s' if len(unk) != 1 else ''}"
                + (": a single location gives no spread, so every comparison rests on one measurement." if len(unk) == 1 else "."),
                "Compared with the references as segmented by the same v3 teacher, not with the U-Net numbers of the "
                "reference reports (the two differ by up to about 5 percentage points of pore).",
                "A location with only one image is segmented by a one-detector model; check its agreement with the "
                "teacher below before relying on small differences.",
                "This describes the material; the batch calls and their track records are in the Classification tab.",
            ],
        },
        "detailed": {
            "locations": locations,
            "reference_means": {mid: {k: v["mean"] for k, v in comparison[mid]["batch"].items()} for mid in SEGMENTATION_METRICS},
            "siox_size_histogram": {"edges_um": edges.tolist(),
                                    "batches": {**{b: size_histogram([r for r in ref if r["batch"] == b], edges)
                                                   for b in BATCHES},
                                                "unknown": size_histogram(unk, edges)}},
            "image_kpis": [],
            "image_kpi_values": {},
        },
    }
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "batch_unknown.json").write_text(json.dumps(report, indent=1), encoding="utf-8")
    print(f"wrote {OUT / 'batch_unknown.json'} ({len(unk)} locations, {len(data['skipped'])} not segmented)")


def main():
    ap = argparse.ArgumentParser(description="General and detailed reports from lucas-sem-analysis v3")
    ap.add_argument("--unknown-only", action="store_true", help="rebuild only the unknown batch's report")
    if ap.parse_args().unknown_only:
        unknown_report()
        return
    rng = np.random.default_rng(0)
    rows = location_metrics()
    y = np.array([r["batch"] for r in rows])
    strata = np.array([r["session"] for r in rows])
    seg_stats = {mid: compare([r["metrics"].get(mid) for r in rows], y, strata, rng) for mid in SEGMENTATION_METRICS}
    for mid, q in zip(seg_stats, bh([s["kruskal_p"] for s in seg_stats.values()])):
        seg_stats[mid]["kruskal_q"] = round(q, 4)

    kv = {r["sample_id"]: r for r in read_csv("kpi_values.csv")}
    ks = {r["kpi"]: r for r in read_csv("kpi_stats.csv")}
    image_kpis = []
    for kid, (name, unit) in IMAGE_KPI_NAMES.items():
        if kid not in ks:
            continue  # v3 reports no statistics for it (bright_cv_25um is undefined on sparse fields)
        st = ks[kid]
        image_kpis.append({
            "id": kid, "name": name, "unit": unit,
            "batch_mean": {b: num(st.get(f"B{b[-1]}_mean")) for b in BATCHES},
            "kruskal_p": num(st.get("kruskal_p")), "kruskal_q": num(st.get("kruskal_q_bh")),
            "session_stratified_p": num(st.get("session_stratified_p")),
            "b3_vs_rest_cliffs_delta": num(st.get("B3_vs_rest_cliffs_delta")),
            "most_correlated_session_probe": st.get("most_correlated_probe"),
            "session_probe_rho": num(st.get("max_abs_rho_session_probe")),
            "flag": (st.get("flag") or "").strip() or None,
        })
    image_kpis.sort(key=lambda k: k["kruskal_p"] if k["kruskal_p"] is not None else 1)

    validation = json.loads((METRICS / "validation_summary.json").read_text(encoding="utf-8"))
    decision_eval = json.loads((METRICS / "decision_eval.json").read_text(encoding="utf-8"))
    ai = validation.get("ai_points_uniform", {})
    quality = {
        "annotator_agreement_4_phase": ai.get("accuracy"),
        "annotator_agreement_4_phase_ci95": ai.get("accuracy_ci95"),
        "annotator_agreement_3_phase": 0.871,
        "per_phase_precision": {"SiOx": 0.96, "graphite": 0.83, "pore": 0.69, "CBD": 0.52},
        "stability_sd_pp": validation.get("stability_sd_pp"),
        "student_vs_teacher_agreement": validation.get("student_vs_teacher", {}).get("agreement_confident_px"),
        "note": "Agreement with an independent, blind annotator on uniformly random points (v3 report §5). "
                "Binder (CBD) precision is about 0.5, so composition is reported as three phases first.",
    }
    hist_edges = np.round(np.geomspace(0.3, 12, 13), 3)
    particle_rows = read_csv("particle_sizes.csv")

    OUT.mkdir(parents=True, exist_ok=True)
    for batch in BATCHES:
        mine = [r for r in rows if r["batch"] == batch]
        findings = []
        for mid, (name, unit, group, _) in SEGMENTATION_METRICS.items():
            s = seg_stats[mid]
            if s["kruskal_p"] < ALPHA:
                findings.append(describe(batch, mid, name, unit, s, robust=s["session_stratified_p"] < ALPHA))
        findings.sort(key=lambda f: (not f["robust"], f["kruskal_p"]))
        decided = [r["decision"] for r in mine if r["decision"]]
        answered = [d for d in decided if d["answer_type"] != "unsure"]
        right = sum(1 for d in answered if (d["answer_type"] == "pair" and batch in (d["answer"] or "")) or d["answer"] == batch)
        sizes = {b: np.array([float(p["eq_diam_um"]) for p in particle_rows if p["batch"] == b]) for b in BATCHES}
        areas = {b: np.array([float(p["area_um2"]) for p in particle_rows if p["batch"] == b]) for b in BATCHES}
        histogram = {b: {"count_share": (np.histogram(sizes[b], hist_edges)[0] / max(len(sizes[b]), 1)).round(4).tolist(),
                         "area_share": (np.histogram(sizes[b], hist_edges, weights=areas[b])[0]
                                        / max(areas[b].sum(), 1e-9)).round(4).tolist(),
                         "n_particles": int(len(sizes[b]))} for b in BATCHES}
        metric_defs = [{"id": mid, "name": n, "unit": u, "group": g, "description": d}
                       for mid, (n, u, g, d) in SEGMENTATION_METRICS.items()]
        report = {
            "report_type": "v3_batch_report",
            "generated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "batch_id": batch[-1],
            "source": "lucas-sem-analysis-v3 committed outputs (U-Net four-phase segmentation)",
            "metrics": metric_defs,
            "general": {
                "n_locations": len(mine),
                "sessions": sorted({r["session"] for r in mine}),
                "composition_3": {k: seg_stats[k]["batch"][batch] for k in ("pore_pct", "carbon_pct", "SiOx_pct")},
                "composition_4": {k: seg_stats[k]["batch"][batch] for k in ("pore_pct", "graphite_pct", "SiOx_pct", "CBD_pct")},
                "comparison": {mid: seg_stats[mid] for mid in SEGMENTATION_METRICS},
                "findings": findings,
                "image_kpi_summary": {
                    "n": len(image_kpis),
                    "nominal_p_below_0_05": sum(1 for k in image_kpis if (k["kruskal_p"] or 1) < ALPHA),
                    "surviving_fdr": sum(1 for k in image_kpis if (k["kruskal_q"] or 1) < ALPHA),
                    "session_robust": sum(1 for k in image_kpis if (k["session_stratified_p"] or 1) < ALPHA),
                },
                "decision_summary": {"locations": len(mine), "answered": len(answered), "right": right,
                                     "all_batches": decision_eval.get("LOO", {}).get("accuracy_when_answering"),
                                     "coverage_all_batches": decision_eval.get("LOO", {}).get("coverage")},
                "quality": quality,
                "caveats": [
                    "31 reference locations (7 / 7 / 17): every batch difference rests on few locations.",
                    "Batch 1 and Batch 2 are hard to tell apart on material alone in every v3 analysis.",
                    "Imaging sessions differ between batches; a difference that does not survive the "
                    "session-stratified test may reflect acquisition rather than material.",
                    "The binder (CBD) fraction is an indication only (precision ~0.5).",
                ],
            },
            "detailed": {
                "locations": mine,
                "reference_means": {mid: {b: seg_stats[mid]["batch"][b]["mean"] for b in BATCHES} for mid in SEGMENTATION_METRICS},
                "siox_size_histogram": {"edges_um": hist_edges.tolist(), "batches": histogram},
                "image_kpis": image_kpis,
                "image_kpi_values": {r["sample_id"]: {k["id"]: num(kv[r["sample_id"]].get(k["id"])) for k in image_kpis}
                                     for r in mine if r["sample_id"] in kv},
                "image_kpi_note": "v3 src/kpi.py: plain image processing of the BSE / InLens images (multi-Otsu "
                                  "thresholds, shapes, contrast, orientation, spectra); no trained model and no label "
                                  "map. Supplementary: none survives multiple-testing correction, and several follow "
                                  "the imaging session.",
            },
        }
        path = OUT / f"batch_{batch[-1]}.json"
        path.write_text(json.dumps(report, indent=1), encoding="utf-8")
        print(f"wrote {path} ({len(mine)} locations, {len(findings)} findings)")
    unknown_report()


if __name__ == "__main__":
    main()
