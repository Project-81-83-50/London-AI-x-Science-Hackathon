"""Guanyi's KPI classifier (analysis.classify) applied to ONE location, for the Demo / Pipeline pages.

Measures the location exactly like analysis.kpis (BSE intensity segmentation at 50 nm/px, location KPIs, and the
cross-detector comparison with its ETD / InLens views), then fits analysis.classify's selected diagonal LDA on the
31 reference locations and classifies this one. Writes JSON to --out with everything the explanation layer needs:
the call, the deciding KPI(s), every KPI with its meaning and the batch means, the nearest reference locations, the
model's own reference validation, and the session hint (not used by the model).

  python -m analysis.kpi_single --bse X_BSE.tif [--inlens X_Inlens.tif] [--etd X_ETD.tif] --out kpi_call.json
"""
import argparse
import json

import numpy as np

from . import kpis as K
from .classify import (BATCHES, FEATURES, VALIDATION_CACHE, SelectedDLDA, anova_rank, batch_dir, image_height,
                       load_locations, matrix)

METHOD = ("Diagonal LDA (shared diagonal variance, equal batch priors) on the standardised KPI(s) that best separate the "
          "reference batches (one-way ANOVA F), chosen from 32 candidates: 25 measured on the BSE image's 3-class intensity "
          "segmentation (pore / graphite / bright phase) and 7 from comparing it pixel by pixel with the same field's ETD "
          "and InLens segmentations. How many KPIs to keep is chosen by an inner leave-one-out test.")


def measure(bse, views):
    img, px = K.read_grey(bse)
    rim, share = K.view_score(img, px)
    b = max(1, round(K.TARGET_NM / px)) if px else 2
    work = K.bin_image(img, b)
    labels, _ = K.segment(work)
    kp, _ = K.measure_location(labels, (px * b if px else K.TARGET_NM) / 1000)
    others = {}
    for det, path in views.items():
        im, p = K.read_grey(path)
        others[det] = K.bin_image(im, max(1, round(K.TARGET_NM / p)) if p else 2)
    if others:
        cross, _ = K.cross_detector(work, labels, others)
        kp.update(cross)
    info = {"pixel_size_nm": px, "analysis_pixel_nm": (px * b) if px else K.TARGET_NM,
            "segmentation": "BSE grey levels split into 3 intensity classes: pore (black), graphite (grey), bright phase",
            "segmentation_confidence": "clean" if K.view_confidence(rim, share) == "clean" else "usable", "views_compared": sorted(others)}
    return kp, info


def show(v, unit, scale):
    return None if v is None or not np.isfinite(v) else round(float(v) * (scale or 1), 3)


def classify(kp, bse):
    ref, y = [], []
    for b in BATCHES:
        locs, _ = load_locations(b)
        ref += [{**loc, "batch": b} for loc in locs]
        y += [b] * len(locs)
    y = np.array(y)
    X = matrix(ref)
    X = np.where(np.isnan(X), np.nanmean(X, 0), X)
    u = np.array([np.nan if kp.get(f) is None else kp[f] for f in FEATURES], float)
    missing = [f for f, v in zip(FEATURES, u) if np.isnan(v)]
    u = np.where(np.isnan(u), X.mean(0), u)
    sel = SelectedDLDA().fit(X, y)
    p = sel.proba(u)[0]
    order = np.argsort(-p)
    top, margin = float(p[order[0]]), float(p[order[0]] - p[order[1]])
    tier = "medium" if top >= 0.5 else "low"  # the model scores < 0.7 on held-out references, so never "high"
    m, cols = sel.model, sel.cols
    zu = m.z(u[cols][None])[0]
    mp, mr = m.means[order[0]], m.means[order[1]]
    contrib = 0.5 * ((zu - mr) ** 2 - (zu - mp) ** 2) / m.var
    drivers = []
    for k in np.argsort(-np.abs(contrib)):
        f = FEATURES[cols[k]]
        group, name, unit, scale = K.KPI_INDEX[f][:4]
        drivers.append({"feature": f, "name": name, "unit": unit, "scale": scale, "value": float(u[cols[k]]),
                        "description": K.KPI_INDEX[f][4] if len(K.KPI_INDEX[f]) > 4 else "",
                        "batch_means": {f"Batch_{c}": float(X[y == c, cols[k]].mean()) for c in BATCHES},
                        "support_for_answer": round(float(contrib[k]), 3)})
    # every KPI, in the order of how well it separates the reference batches
    rank = {FEATURES[c]: i + 1 for i, c in enumerate(anova_rank(X, y))}
    all_kpis = []
    for j, f in enumerate(FEATURES):
        group, name, unit, scale = K.KPI_INDEX[f][:4]
        means = {f"Batch_{c}": show(X[y == c, j].mean(), unit, scale) for c in BATCHES}
        val = show(kp.get(f) if kp.get(f) is not None else np.nan, unit, scale)
        all_kpis.append({"id": f, "name": name, "group": group, "unit": unit,
                         "description": K.KPI_INDEX[f][4] if len(K.KPI_INDEX[f]) > 4 else "",
                         "value": val, "batch_means": means, "separation_rank": rank[f], "used_by_model": f in [FEATURES[c] for c in cols],
                         "closest_batch_mean": None if val is None else min(means, key=lambda b: abs(means[b] - val))})
    all_kpis.sort(key=lambda r: r["separation_rank"])
    Zr, Zu = m.z(X[:, cols]), m.z(u[cols][None])[0]
    dist = np.sqrt((((Zr - Zu) ** 2) / m.var).sum(1))
    nearest = [{"batch": f"Batch_{ref[j]['batch']}", "location_id": ref[j]["location_id"], "distance": round(float(dist[j]), 2)}
               for j in np.argsort(dist)[:3]]
    validation = {}
    if VALIDATION_CACHE.is_file():
        v = json.loads(VALIDATION_CACHE.read_text(encoding="utf-8"))
        validation = {"protocol": "each of the 31 reference locations hidden in turn; KPI choice and fit re-run without it",
                      "loo_balanced_accuracy": round(v.get("loo_balanced_accuracy", 0), 3), "permutation_p": v.get("permutation_p"),
                      "chance": 0.333, "features_chosen_per_fold": v.get("features_chosen_per_fold")}
    heights = {}
    for loc in ref:
        try:
            heights.setdefault(image_height(batch_dir(loc["batch"]) / loc["analysed_image"]), []).append(
                f"Batch_{loc['batch']}: {loc['location_id']}")
        except (OSError, KeyError):
            pass
    h = image_height(bse)
    same = heights.get(h, [])
    session = {"image_height_px": h, "reference_locations_same_height": same,
               "batches": sorted({s.split(":")[0] for s in same}),
               "note": "image height marks the imaging session; shown for context only, NOT used by the model"}
    return {"model": "KPI classifier (Guanyi, analysis.classify)", "method": METHOD,
            "predicted_batch": f"Batch_{m.classes[order[0]]}", "runner_up": f"Batch_{m.classes[order[1]]}",
            "probabilities": {f"Batch_{c}": round(float(v), 4) for c, v in zip(m.classes, p)},
            "confidence": tier, "margin": round(margin, 3), "kpis_used": [FEATURES[c] for c in cols],
            "inner_scores_by_k": {str(k): round(v, 3) for k, v in sel.inner_scores.items()},
            "drivers": drivers, "nearest_reference_locations": nearest, "all_kpis": all_kpis,
            "unmeasured_kpis": missing, "reference_validation": validation, "session_hint": session,
            "n_reference_locations": int(len(y))}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bse", required=True)
    ap.add_argument("--inlens")
    ap.add_argument("--etd")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    views = {k: v for k, v in (("ETD", a.etd), ("InLens", a.inlens)) if v}
    kp, info = measure(a.bse, views)
    out = {**classify(kp, a.bse), "measurement": info,
           "kpi_values_raw": {k: (None if v is None else float(v)) for k, v in kp.items()}}
    with open(a.out, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=1)
    print(json.dumps({k: out[k] for k in ("predicted_batch", "probabilities", "confidence", "kpis_used")}))


if __name__ == "__main__":
    main()
