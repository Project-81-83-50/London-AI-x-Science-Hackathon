"""Across-location statistics of a batch: KPI summaries (mean, SD, CV, t-based 95% CI), log-spaced size
histograms and the plain-language findings of the report."""

import numpy as np
from scipy import stats

from .catalogue import KPI_INDEX


def summarise(values, signed: bool = False) -> dict:
    """Mean, SD, CV and t-based 95% CI of one KPI across locations, with a consistency label."""
    v = np.array([x for x in values if x is not None and np.isfinite(x)], float)
    if not len(v):
        return {"n": 0}
    out = {
        "n": int(len(v)),
        "mean": float(v.mean()),
        "min": float(v.min()),
        "max": float(v.max()),
        "sd": None,
        "cv": None,
        "ci95": None,
        "consistency": "single location",
    }
    if len(v) > 1:
        sd = float(v.std(ddof=1))
        half = float(stats.t.ppf(0.975, len(v) - 1) * sd / np.sqrt(len(v)))
        ci = [out["mean"] - half, out["mean"] + half]
        if signed:
            out.update(sd=sd, ci95=ci, consistency="non-zero" if ci[0] > 0 or ci[1] < 0 else "includes zero")
            return out
        cv = sd / abs(out["mean"]) if out["mean"] else None
        out.update(
            sd=sd,
            cv=cv,
            ci95=ci,
            consistency="consistent"
            if cv is not None and cv < 0.10
            else "moderate"
            if cv is not None and cv < 0.25
            else "variable",
        )
    return out


def histogram(values: np.ndarray, lo: float, hi: float, n_bins: int = 24) -> dict:
    """Log-spaced histogram (share of particles per bin) for size distributions."""
    edges = np.geomspace(lo, hi, n_bins + 1)
    v = np.clip(values, lo, hi * 0.9999)
    counts = np.histogram(v, edges)[0]
    return {
        "edges": edges.tolist(),
        "counts": counts.tolist(),
        "shares": (counts / max(counts.sum(), 1)).tolist(),
        "total": int(counts.sum()),
    }


def locations_phrase(n: int) -> str:
    """'1 location' / 'n locations'."""
    return f"{n} location" + ("" if n == 1 else "s")


def findings(groups: list[dict], locations: list[dict]) -> list[str]:
    """Plain-language observations derived only from this batch's numbers."""
    k = {kpi["id"]: kpi for g in groups for kpi in g["kpis"]}
    notes = []

    def pct(x):
        return f"{x * 100:.1f}%"

    if k["porosity"]["n"]:
        notes.append(
            f"Average composition is {pct(k['porosity']['mean'])} pore, "
            f"{pct(k['graphite_fraction']['mean'])} graphite and {pct(k['bright_fraction']['mean'])} "
            f"bright phase across {k['porosity']['n']} locations."
        )
    if k["bright_area_d50"]["n"]:
        notes.append(
            f"Half of the bright-phase area sits in particles larger than "
            f"{k['bright_area_d50']['mean']:.2f} µm; by count the median is "
            f"{k['bright_d50']['mean']:.2f} µm and D90 is {k['bright_d90']['mean']:.2f} µm."
        )
    ori = k["graphite_orientation"]
    if ori["n"]:
        notes.append(
            f"Graphite runs are {ori['mean']:.2f}× longer horizontally than vertically: "
            + (
                "flakes lie strongly along the image width."
                if ori["mean"] > 1.3
                else "flakes are mildly aligned with the image width."
                if ori["mean"] > 1.1
                else "flakes show little preferred orientation."
            )
        )
    variable = [
        kpi["name"]
        for kpi in k.values()
        if kpi.get("consistency") == "variable" and KPI_INDEX[kpi["id"]][0] not in ("homogeneity",)
    ]
    if variable:
        notes.append("Location-to-location spread exceeds 25% CV for: " + ", ".join(variable) + ".")
    g = k["porosity_gradient"]
    if g["n"] > 1 and g["ci95"] and (g["ci95"][0] > 0 or g["ci95"][1] < 0):
        notes.append(
            f"Porosity changes consistently from the top to the bottom of the images "
            f"({g['mean'] * 100:+.1f} percentage points, 95% CI excludes zero)."
        )
    excluded = [l["location_id"] for l in locations if not l["included"]]
    if excluded:
        notes.append(
            f"{locations_phrase(len(excluded))} had no BSE view and "
            f"{'was' if len(excluded) == 1 else 'were'} left out: " + ", ".join(excluded) + "."
        )
    usable = [l["location_id"] for l in locations if l["confidence"] == "usable"]
    if usable:
        notes.append(
            f"{locations_phrase(len(usable))} {'has' if len(usable) == 1 else 'have'} a BSE view whose "
            "bright class may include binder or particle edges (lower confidence): " + ", ".join(usable) + "."
        )
    mixed = sum(len(l["filename_codes"]) > 1 for l in locations)
    assigned = sum(not l["location_recovered"] for l in locations)
    if mixed or assigned:
        notes.append(
            f"Files were regrouped by image matching into {len(locations)} locations; {mixed} of them "
            "combine files with different filename codes. Each location is named with one filename code; "
            f"for {assigned} of them several codes fit equally well, so the name is assigned, not recovered."
        )
    views = [v for l in locations for v in l["views"]]
    # A filename "SE" counts as the chamber secondary-electron detector, i.e. ETD.
    wrong = sum(
        v["detector"].upper() != {"SE": "ETD"}.get(v["filename_detector"], v["filename_detector"]) for v in views
    )
    if wrong:
        notes.append(
            f"Detectors were identified from the images: {wrong} of {len(views)} files carry a different "
            "detector label in their filename."
        )
    if not (mixed or assigned or wrong):
        notes.append(
            f"All {len(views)} filenames agree with the images: each location's files show the same field, "
            "and every filter label matches the detector identified from the image."
        )
    return notes
