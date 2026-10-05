"""Classify the locations in data/raw/unknown as reference batch 1, 2 or 3.

1. Views are grouped into locations, and each view's detector is checked, by analysis.fields.
   The BSE view of each location is segmented and measured by analysis.kpis (the same code that
   produced the reference KPIs), giving data/processed/batch_kpis/batch_unknown/.
2. Duplicate check: every unknown image is compared with every reference image (file hash and
   phase-correlation of edge maps). A same-field match would identify the batch directly.
3. Classifier: a Gaussian class model with per-feature pooled within-batch variance and equal batch
   priors (diagonal LDA) on standardised KPIs: the BSE segmentation KPIs plus the cross-detector comparisons
   (BSE against the same field's ETD and InLens segmentations; see analysis.kpis.cross_detector). Which KPIs it uses is part of the fitted model,
   not a hand-picked list: the candidate KPIs are ranked by their between-/within-batch variance
   ratio (one-way ANOVA F) on the training locations, and the number kept, k from K_GRID, is the one
   with the best inner leave-one-out balanced accuracy (ties go to the smaller k). Probabilities are
   a softmax of -1/2 the squared standardised distance to each batch mean.
4. Honesty checks on the references, with the whole procedure (ranking, choice of k, fit) repeated
   without the held-out location: nested leave-one-location-out balanced accuracy, per-batch recall,
   confusion matrix, which KPIs each fold chose, and a label-permutation test of the full procedure
   (cached in reference_validation.json; recomputed only when the reference KPIs change).
5. Session hint, kept separate from the material evidence: reference batches imaged at the same
   image height (image height marks the imaging session in this dataset).

Inputs: the KPI reports of analysis.kpis (data/processed/batch_kpis/batch_{1,2,3,unknown}/report.json) and the
raw images (for the duplicate check and session hint).
Output: data/processed/classification/unknown.json, shown in the frontend's Unknown batch section, plus the
validation cache data/processed/classification/reference_validation.json. analysis.kpi_single reuses the same
model for a single uploaded location.

  python -m analysis.classify              # uses cached KPIs for the unknown set if present
  python -m analysis.classify --rebuild    # re-measure the unknown set first
"""

import argparse
import hashlib
import json
import logging
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
from PIL import Image
from scipy import fft

from . import configure_cli_logging, paths
from . import kpis as batch_kpis
from .fields import MATCH_SCORE, batch_dir, edge_map, phase_correlation

logger = logging.getLogger(__name__)

ROOT = paths.REPO_ROOT
KPI_DIR = paths.KPI_DIR
OUT = paths.CLASSIFICATION_DIR / "unknown.json"
BATCHES = ["1", "2", "3"]
VALIDATION_CACHE = OUT.parent / "reference_validation.json"
# Candidate material features: every BSE segmentation KPI and every BSE-vs-ETD/InLens comparison (no acquisition
# properties). The model keeps the number of KPIs from K_GRID that classifies held-out training locations best;
# see SelectedDLDA.
FEATURES = list(batch_kpis.KPI_INDEX)
K_GRID = (1, 2, 3, 4, 6, 8, 12)
# The previous fixed eight-KPI model, kept only to report how much the feature selection changed.
PREVIOUS_FEATURES = [
    "porosity",
    "bright_fraction",
    "bright_area_d50",
    "pore_ecd_area_d50",
    "graphite_chord_x",
    "graphite_orientation",
    "pore_interface_density",
    "crack_share",
]
N_PERMUTATIONS = 200
PROCEDURE = "selected-dlda-v2-cross-detector"  # bump when the procedure changes, to invalidate the validation cache


def load_locations(batch: str, include_all: bool = False) -> tuple[list[dict], dict]:
    """Locations of a batch report. References use only BSE-measured locations; the unknown set keeps every
    location, so an image uploaded without a BSE view of its location still gets a (low-confidence) call."""
    report = json.loads((KPI_DIR / f"batch_{batch}" / "report.json").read_text(encoding="utf-8"))
    return [loc for loc in report["locations"] if include_all or loc["included"]], report


def matrix(locations: list[dict]) -> np.ndarray:
    """KPI matrix; a KPI that could not be measured (None) becomes NaN."""
    return np.array(
        [[np.nan if loc["kpis"].get(f) is None else loc["kpis"][f] for f in FEATURES] for loc in locations], float
    )


def load_references() -> tuple[list[dict], np.ndarray, np.ndarray]:
    """Reference locations (tagged with their batch), their batch labels and their KPI matrix.

    A reference location missing a view has no comparison with it; that KPI takes the other references' mean.
    """
    ref_locs, y = [], []
    for b in BATCHES:
        locs, _ = load_locations(b)
        ref_locs += [{**loc, "batch": b} for loc in locs]
        y += [b] * len(locs)
    X = matrix(ref_locs)
    X = np.where(np.isnan(X), np.nanmean(X, 0), X)
    return ref_locs, np.array(y), X


class DiagonalLDA:
    """Standardise, then a Gaussian per batch with a shared diagonal covariance and equal priors."""

    def fit(self, X: np.ndarray, y: np.ndarray) -> "DiagonalLDA":
        self.mu, self.sd = X.mean(0), X.std(0, ddof=1) + 1e-12
        Z = (X - self.mu) / self.sd
        self.classes = sorted(set(y))
        self.means = np.array([Z[y == c].mean(0) for c in self.classes])
        resid = np.concatenate([Z[y == c] - Z[y == c].mean(0) for c in self.classes])
        self.var = resid.var(0, ddof=len(self.classes)) + 0.05  # small ridge for stability
        return self

    def z(self, X: np.ndarray) -> np.ndarray:
        """Standardise with the training mean and SD."""
        return (np.atleast_2d(X) - self.mu) / self.sd

    def scores(self, X: np.ndarray) -> np.ndarray:
        """Log-likelihood (up to a constant) of each row under each batch."""
        Z = self.z(X)
        return np.array([-0.5 * (((Z - m) ** 2) / self.var).sum(1) for m in self.means]).T

    def proba(self, X: np.ndarray) -> np.ndarray:
        """Batch probabilities per row (softmax of the scores; equal priors)."""
        s = self.scores(X)
        e = np.exp(s - s.max(1, keepdims=True))
        return e / e.sum(1, keepdims=True)


def balanced_accuracy(y: np.ndarray, pred: np.ndarray) -> float:
    """Mean per-class recall."""
    return float(np.mean([np.mean(pred[y == c] == c) for c in sorted(set(y))]))


def anova_rank(X: np.ndarray, y: np.ndarray) -> np.ndarray:
    """Feature indices, most batch-separating first (one-way ANOVA F; scale-free)."""
    classes = sorted(set(y))
    grand = X.mean(0)
    between = sum(np.sum(y == c) * (X[y == c].mean(0) - grand) ** 2 for c in classes) / (len(classes) - 1)
    within = sum(((X[y == c] - X[y == c].mean(0)) ** 2).sum(0) for c in classes) / (len(y) - len(classes))
    return np.argsort(-(between / (within + 1e-12)), kind="stable")


def _predict(X_train: np.ndarray, y_train: np.ndarray, X_test: np.ndarray) -> np.ndarray:
    """Fit a DiagonalLDA and return its most likely batch for each test row."""
    m = DiagonalLDA().fit(X_train, y_train)
    return np.array(m.classes)[np.argmax(m.proba(X_test), 1)]


class SelectedDLDA:
    """Diagonal LDA on the k most batch-separating KPIs, with k chosen by inner leave-one-out."""

    def fit(self, X: np.ndarray, y: np.ndarray) -> "SelectedDLDA":
        n = len(y)
        inner = {k: np.empty_like(y) for k in K_GRID}
        for j in range(n):
            keep = np.arange(n) != j
            order = anova_rank(X[keep], y[keep])
            for k in K_GRID:
                cols = order[:k]
                inner[k][j] = _predict(X[keep][:, cols], y[keep], X[j : j + 1, cols])[0]
        self.inner_scores = {k: balanced_accuracy(y, inner[k]) for k in K_GRID}
        self.k = max(K_GRID, key=lambda k: (self.inner_scores[k], -k))
        self.cols = anova_rank(X, y)[: self.k]
        self.model = DiagonalLDA().fit(X[:, self.cols], y)
        self.classes = self.model.classes
        return self

    def proba(self, X: np.ndarray) -> np.ndarray:
        """Batch probabilities per row, using only the selected KPI columns of X."""
        return self.model.proba(np.atleast_2d(X)[:, self.cols])


def leave_one_out(X: np.ndarray, y: np.ndarray) -> tuple[np.ndarray, list[tuple[str, ...]]]:
    """Held-out prediction for every location, refitting the whole procedure without it."""
    pred, chosen = np.empty_like(y), []
    for i in range(len(y)):
        keep = np.arange(len(y)) != i
        m = SelectedDLDA().fit(X[keep], y[keep])
        pred[i] = m.classes[int(np.argmax(m.proba(X[i])))]
        chosen.append(tuple(FEATURES[c] for c in m.cols))
    return pred, chosen


def reference_validation(X: np.ndarray, y: np.ndarray) -> dict:
    """Nested LOO and the permutation test of the full procedure; cached, since a permutation test of a
    nested procedure takes minutes and the references rarely change."""
    key = hashlib.sha256(
        np.ascontiguousarray(X).tobytes() + "".join(y).encode() + PROCEDURE.encode() + str(N_PERMUTATIONS).encode()
    ).hexdigest()
    if VALIDATION_CACHE.is_file():
        cached = json.loads(VALIDATION_CACHE.read_text(encoding="utf-8"))
        if cached.get("key") == key:
            return cached
    loo, chosen = leave_one_out(X, y)
    loo_bacc = balanced_accuracy(y, loo)
    logger.info(
        "nested LOO balanced accuracy %.3f; permutation test of the full procedure (%d label shuffles, a few minutes) ...",
        loo_bacc,
        N_PERMUTATIONS,
    )
    rng = np.random.default_rng(0)
    null = []
    for n, yp in enumerate(rng.permutation(y) for _ in range(N_PERMUTATIONS)):
        null.append(balanced_accuracy(yp, leave_one_out(X, yp)[0]))
        if (n + 1) % 50 == 0:
            logger.info("  %d/%d", n + 1, N_PERMUTATIONS)
    prev = [FEATURES.index(f) for f in PREVIOUS_FEATURES]
    everyone = np.arange(len(y))
    prev_pred = np.array(
        [_predict(X[everyone != i][:, prev], y[everyone != i], X[i : i + 1, prev])[0] for i in everyone]
    )
    stability = {}
    for c in chosen:
        stability[", ".join(c)] = stability.get(", ".join(c), 0) + 1
    result = {
        "key": key,
        "loo": loo.tolist(),
        "loo_balanced_accuracy": loo_bacc,
        "permutation_p": float((1 + np.sum(np.array(null) >= loo_bacc)) / (1 + N_PERMUTATIONS)),
        "null_mean": float(np.mean(null)),
        "features_chosen_per_fold": dict(sorted(stability.items(), key=lambda kv: -kv[1])),
        "previous_model_loo_balanced_accuracy": balanced_accuracy(y, prev_pred),
    }
    VALIDATION_CACHE.parent.mkdir(parents=True, exist_ok=True)
    VALIDATION_CACHE.write_text(json.dumps(result, indent=1), encoding="utf-8")
    return result


def image_height(path: str | Path) -> int:
    """Image height in pixels (it marks the imaging session in this dataset)."""
    with Image.open(path) as im:
        return im.size[1]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--rebuild", action="store_true", help="re-measure the unknown set even if cached")
    args = ap.parse_args()
    configure_cli_logging()

    if args.rebuild or not (KPI_DIR / "batch_unknown" / "report.json").is_file():
        logger.info("measuring the unknown set with batch_kpis ...")
        batch_kpis.analyse_batch("unknown", rebuild_fields=args.rebuild)

    ref_locs, y, X = load_references()
    unk_locs, unk_report = load_locations("unknown", include_all=True)
    U = matrix(unk_locs)

    # Honesty checks on the references (nested: the feature choice is refitted in every fold).
    validation = reference_validation(X, y)
    loo = np.array(validation["loo"])
    loo_bacc, p_value = validation["loo_balanced_accuracy"], validation["permutation_p"]
    confusion = [[int(np.sum((y == t) & (loo == p))) for p in BATCHES] for t in BATCHES]
    print(
        f"reference nested LOO balanced accuracy {loo_bacc:.2f} (chance 0.33, permutation p = {p_value:.3f}; "
        f"previous fixed eight-KPI model {validation['previous_model_loo_balanced_accuracy']:.2f})"
    )

    selected = SelectedDLDA().fit(X, y)
    cols = selected.cols
    used = [FEATURES[c] for c in cols]
    model = selected.model
    # Unmeasurable KPIs take the reference mean: neutral evidence that favours no batch.
    missing = [[FEATURES[c] for c in cols if np.isnan(row[c])] for row in U]
    U = np.where(np.isnan(U), X.mean(0), U)
    probs = selected.proba(U)
    Xs, Us = X[:, cols], U[:, cols]
    Zr, Zu = model.z(Xs), model.z(Us)

    # Duplicate check and session hint.
    ref_files = sorted(p for b in BATCHES for p in batch_dir(b).glob("*.tif"))
    ref_hash = {hashlib.sha256(p.read_bytes()).hexdigest(): p for p in ref_files}
    ref_bse = [(p, fft.fft2(edge_map(p))) for p in ref_files if "_BSE" in p.name]
    ref_height = {}
    for loc in ref_locs:
        ref_height.setdefault(image_height(batch_dir(loc["batch"]) / loc["analysed_image"]), []).append(
            (loc["batch"], loc["location_id"])
        )

    results = []
    for i, loc in enumerate(unk_locs):
        p = probs[i]
        order = np.argsort(-p)
        pred, runner = model.classes[order[0]], model.classes[order[1]]
        margin = float(p[order[0]] - p[order[1]])
        tier = "high" if p[order[0]] >= 0.75 and margin >= 0.4 else "medium" if p[order[0]] >= 0.5 else "low"
        if loo_bacc < 0.7 and tier == "high":
            tier = "medium"  # the model itself is not reliable enough on the references for "high"
        if not loc["included"]:
            tier = "low"  # no BSE image: measured from a detector the model was not trained on
        # Per-KPI log-likelihood ratio of the predicted batch over the runner-up: positive supports the call.
        mean_top, mean_runner = model.means[order[0]], model.means[order[1]]
        contrib = 0.5 * ((Zu[i] - mean_runner) ** 2 - (Zu[i] - mean_top) ** 2) / model.var
        drivers = [
            {
                "feature": used[k],
                "name": batch_kpis.KPI_INDEX[used[k]][1],
                "unit": batch_kpis.KPI_INDEX[used[k]][2],
                "scale": batch_kpis.KPI_INDEX[used[k]][3],
                "value": float(Us[i, k]),
                "batch_means": {c: float(Xs[y == c, k].mean()) for c in BATCHES},
                "support": float(contrib[k]),
            }
            for k in np.argsort(-np.abs(contrib))[:4]
        ]
        dist = np.sqrt((((Zr - Zu[i]) ** 2) / model.var).sum(1))
        nearest = [
            {
                "batch": ref_locs[j]["batch"],
                "location_id": ref_locs[j]["location_id"],
                "distance": round(float(dist[j]), 2),
            }
            for j in np.argsort(dist)[:3]
        ]

        views = [v["filename"] for v in loc["views"]]
        exact = [
            ref_hash[h].relative_to(ROOT).as_posix()
            for v in views
            if (h := hashlib.sha256((batch_dir("unknown") / v).read_bytes()).hexdigest()) in ref_hash
        ]
        fu = fft.fft2(edge_map(batch_dir("unknown") / loc["analysed_image"]))
        best = max(((phase_correlation(fu, f)[0], r) for r, f in ref_bse), key=lambda s: s[0])
        same_field = best[0] >= MATCH_SCORE
        # A copy of, or the same field as, a reference image decides the batch outright; the material
        # model's own call is kept alongside for comparison.
        matched = ROOT / exact[0] if exact else (best[1] if same_field else None)
        if matched is not None:
            decided = matched.parent.name.split("_", 1)[1]
            source = "exact copy of a reference image" if exact else "same field as a reference image"
        else:
            decided, source = pred, "material KPIs"
        height = image_height(batch_dir("unknown") / loc["analysed_image"])
        session = sorted(ref_height.get(height, []))
        session_batches = sorted({b for b, _ in session})

        cautions = []
        if matched is not None and decided != pred:
            cautions.append(
                f"This location is the {source.split(' a ')[0]} {matched.relative_to(ROOT).as_posix()}, so it is "
                f"assigned to batch {decided}; the material-KPI model alone would have said batch "
                f"{pred}, another sign that the model is weak on its own."
            )
        if not loc["included"] and matched is None:
            cautions.append(
                f"No BSE image of this location: it was measured from its {loc['analysed_detector']} "
                "image, but the model was trained on BSE measurements, so this call is only a rough lead. "
                "Upload the location's BSE image for a reliable classification."
            )
        elif not loc["included"]:
            cautions.append(
                f"No BSE image of this location, so the material model's call comes from its "
                f"{loc['analysed_detector']} image; the reference match decides the batch regardless."
            )
        if missing[i]:
            names = ", ".join(batch_kpis.KPI_INDEX[f][1].lower() for f in missing[i])
            cautions.append(f"Could not measure {names}; the reference average was used, which favours no batch.")
        elif loc["confidence"] == "usable":
            cautions.append(
                "This location's BSE segmentation is flagged: binder or particle edges may add to "
                "the bright phase, inflating bright-phase features"
                + (" — the main driver of this prediction." if drivers[0]["feature"].startswith("bright") else ".")
            )
        if p[order[0]] > 0.95 and matched is None:
            cautions.append(
                f"A probability of {p[order[0]]:.2f} overstates certainty: the model is right on "
                f"{loo_bacc:.0%} of reference locations (balanced) when they are held out."
            )
        results.append(
            {
                "location_id": loc["location_id"],
                "cautions": cautions,
                "views": views,
                "analysed_image": loc["analysed_image"],
                "segmentation_confidence": loc["confidence"],
                "measured_from": loc["analysed_detector"],
                "predicted_batch": decided,
                "prediction_source": source,
                "model_prediction": pred,
                "runner_up": runner,
                "probabilities": {c: round(float(p[k]), 3) for k, c in enumerate(model.classes)},
                "confidence": "high" if matched is not None else tier,
                "drivers": drivers,
                "nearest_reference_locations": nearest,
                "duplicate_check": {
                    "exact_copies": exact,
                    "best_same_field_score": round(float(best[0]), 3),
                    "best_same_field_reference": best[1].relative_to(ROOT).as_posix(),
                    "same_field_as_reference": bool(same_field),
                },
                "session_hint": {
                    "image_height_px": height,
                    "reference_locations_same_height": [f"batch {b}: {l}" for b, l in session],
                    "batches": session_batches,
                    "agrees_with_prediction": session_batches == [decided] if session_batches else None,
                },
                "kpis": {f: float(Us[i, k]) for k, f in enumerate(used)},
                "unmeasured_kpis": missing[i],
            }
        )
        print(
            f"{loc['location_id']}: batch {decided} ({source}; model batch {pred}, p={p[order[0]]:.2f}, {tier}); "
            f"session hint {session_batches or 'none'}"
        )

    out = {
        "generated": datetime.now(UTC).isoformat(timespec="seconds"),
        "source_folder": "data/raw/unknown",
        "method": {
            "features": [{"id": f, "name": batch_kpis.KPI_INDEX[f][1]} for f in used],
            "n_candidate_features": len(FEATURES),
            "k_grid": list(K_GRID),
            "inner_scores": {str(k): round(v, 3) for k, v in selected.inner_scores.items()},
            "model": f"Diagonal LDA (shared diagonal variance, equal batch priors) on the {selected.k} of "
            f"{len(FEATURES)} standardised KPIs (BSE segmentation and BSE-vs-ETD/InLens comparisons) that best separate the reference batches (ANOVA F); "
            "the number kept is chosen by inner leave-one-out, and the whole procedure is "
            "re-run inside every validation fold.",
            "decision_rule": "An exact copy of, or the same field as, a reference image decides the batch "
            "(confidence high); otherwise the material-KPI model's top batch is used.",
            "confidence_rule": "high: top probability ≥ 0.75 and margin ≥ 0.40 (only if reference "
            "LOO balanced accuracy ≥ 0.70); medium: top probability ≥ 0.50; "
            "low otherwise.",
            "session_hint": "Reference locations imaged at the same image height, which marks the "
            "imaging session. It is not material evidence and is not used by the model.",
        },
        "reference_validation": {
            "n_locations": {c: int(np.sum(y == c)) for c in BATCHES},
            "loo_balanced_accuracy": round(loo_bacc, 3),
            "chance": round(1 / len(BATCHES), 3),
            "per_batch_recall": {c: round(float(np.mean(loo[y == c] == c)), 3) for c in BATCHES},
            "confusion_rows_true_cols_predicted": confusion,
            "permutation_p": round(p_value, 4),
            "n_permutations": N_PERMUTATIONS,
            "permutation_null_mean": round(validation["null_mean"], 3),
            "validation": "nested leave-one-location-out (feature ranking, choice of k and fit redone per fold)",
            "features_chosen_per_fold": validation["features_chosen_per_fold"],
            "previous_model": {
                "features": PREVIOUS_FEATURES,
                "loo_balanced_accuracy": round(validation["previous_model_loo_balanced_accuracy"], 3),
            },
        },
        "locations": results,
        "caveats": [
            "The references are 31 locations (7 / 7 / 17). Leave-one-out accuracy on them is the best "
            "available estimate of how often this classifier is right on a new location.",
            "Batch 1 and Batch 2 are hard to tell apart in every analysis so far; a prediction between "
            "those two deserves the least trust.",
            "Imaging sessions differ between batches. Material KPIs can partly reflect imaging settings, "
            "which is why the session hint is shown separately rather than used.",
        ],
        "unknown_kpi_findings": unk_report.get("findings", []),
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, indent=1), encoding="utf-8")
    logger.info("wrote %s", OUT)


if __name__ == "__main__":
    main()
