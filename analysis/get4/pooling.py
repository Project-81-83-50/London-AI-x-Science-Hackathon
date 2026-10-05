"""Factor 3 (difference between images): random-effects pooling of a batch and next-measurement advice."""

import numpy as np
from scipy import stats

from .constants import PHASES, Z95
from .spatial import info_bits


def random_effects(phis, var_area, var_irreg, tau2_prior: float | None = None) -> dict:
    """DerSimonian-Laird random-effects pooling with Hartung-Knapp CI and an exact variance budget."""
    phis, var_area, var_irreg = map(np.asarray, (phis, var_area, var_irreg))
    v = var_area + var_irreg
    k = len(phis)
    w = 1 / v
    mu_fe = (w * phis).sum() / w.sum()
    q = float((w * (phis - mu_fe) ** 2).sum())
    if k > 1:
        c = w.sum() - (w**2).sum() / w.sum()
        tau2, tau2_source = max(0.0, (q - (k - 1)) / c), "estimated"
        if tau2_prior is not None and k < 3 and tau2_prior >= tau2:
            # too few images to trust the estimate; borrow the baseline's unless these images disagree more
            tau2, tau2_source = tau2_prior, "from baseline (too few images to estimate)"
    elif tau2_prior is not None:
        tau2, tau2_source = tau2_prior, "from baseline (single image)"
    else:
        tau2, tau2_source = 0.0, "NOT ESTIMABLE from one image"

    ws = 1 / (v + tau2)
    mu = float((ws * phis).sum() / ws.sum())
    se = float(np.sqrt(1 / ws.sum()))
    if k > 1:
        hk = (ws * (phis - mu) ** 2).sum() / (k - 1) / ws.sum()
        se_ci, tcrit = max(se, float(np.sqrt(hk))), float(stats.t.ppf(0.975, k - 1))
    else:
        se_ci, tcrit = se, Z95
    pred = None
    if k >= 3:
        half = float(stats.t.ppf(0.975, k - 2) * np.sqrt(tau2 + se_ci**2))
        pred = [max(0.0, mu - half), min(1.0, mu + half)]

    norm = ws.sum() ** 2
    budget = {
        "area": float((ws**2 * var_area).sum() / norm),
        "regularity": float((ws**2 * var_irreg).sum() / norm),
        "between images": float(tau2 * (ws**2).sum() / norm),
    }
    return {
        "phi": mu,
        "se": se,
        "se_ci": se_ci,
        "ci95": [max(0.0, mu - tcrit * se_ci), min(1.0, mu + tcrit * se_ci)],
        "prediction_interval_new_field": pred,
        "tau": float(np.sqrt(tau2)),
        "tau2": float(tau2),
        "tau2_source": tau2_source,
        "I2": float(max(0.0, (q - (k - 1)) / q)) if k > 1 and q > 0 else 0.0,
        "n_images": k,
        "budget": budget,
        "bits": info_bits(se_ci),
    }


def next_measurement(var_area, var_irreg, tau2: float) -> dict[str, float]:
    """Same extra imaging area spent two ways: double every field, or add as many new fields.

    Only tau2 separates them: within-image variance falls with area either way, but
    field-to-field variance only averages down with more locations."""
    v = np.asarray(var_area) + np.asarray(var_irreg)

    def se(variances):
        return np.sqrt(1 / (1 / (variances + tau2)).sum())

    now = se(v)
    return {
        "bits_bigger_fields": float(np.log2(now / se(v / 2))),
        "bits_more_fields": float(np.log2(now / se(np.concatenate([v, v])))),
    }


def analyse_batch(results: list[dict], tau2_prior: dict | None = None, class_names: dict = PHASES) -> dict:
    """Pool every class over the images (random effects), with the systematic ranges and next-step advice."""
    batch = {}
    for name in class_names.values():
        ph = [r["phases"][name] for r in results]
        prior = None if tau2_prior is None else tau2_prior.get(name)
        pooled = random_effects(
            [p["phi"] for p in ph], [p["var_area"] for p in ph], [p["var_irregularity"] for p in ph], prior
        )
        pooled["next"] = next_measurement(
            [p["var_area"] for p in ph], [p["var_irregularity"] for p in ph], pooled["tau2"]
        )
        pooled["threshold_range"] = [
            min(p["threshold_range"][0] for p in ph),
            max(p["threshold_range"][1] for p in ph),
        ]
        pooled["shading_shift_mean"] = float(np.mean([p["shading_shift"] for p in ph]))
        pooled["systematic_range"] = [
            min(p["systematic_range"][0] for p in ph),
            max(p["systematic_range"][1] for p in ph),
        ]
        pooled["systematic_halfwidth"] = float(
            np.mean([(p["systematic_range"][1] - p["systematic_range"][0]) / 2 for p in ph])
        )
        pooled["variant_shifts"] = np.mean([p["variant_shifts"] for p in ph], axis=0).tolist()
        pooled["images"] = [
            {"image": r["image"], "phi": p["phi"], "se": p["se_image"]} for r, p in zip(results, ph, strict=True)
        ]
        batch[name] = pooled
    return batch
