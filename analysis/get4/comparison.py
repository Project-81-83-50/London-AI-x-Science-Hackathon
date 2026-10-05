"""Lot A versus lot B: how sure we are that each phase fraction changed, and by more than a tolerance."""

import json
from pathlib import Path

import numpy as np
from scipy import stats

from .constants import Z95


def parse_tolerances(text: str | None) -> dict[str, float]:
    """'pore=0.02,bright phase=0.01' -> {'pore': 0.02, 'bright phase': 0.01} (absolute phase fraction)."""
    tol = {}
    for part in filter(None, (s.strip() for s in (text or "").split(","))):
        name, value = part.split("=")
        tol[name.strip()] = float(value)
    return tol


def _lot_variance(phase: dict, other: dict) -> tuple[float, bool, bool]:
    """Variance of a lot's mean phi. A lot whose field-to-field variation could not be
    estimated (one image) borrows the other lot's, if that one has it."""
    var = phase["se_ci"] ** 2
    unknown = "NOT ESTIMABLE" in phase["tau2_source"]
    if unknown and "NOT ESTIMABLE" not in other["tau2_source"]:
        return var + other["tau2"], False, True
    return var, unknown, False


def _cdf(x, nu: float):
    """Student-t CDF with nu degrees of freedom (normal CDF for infinite nu)."""
    return stats.t.cdf(x, nu) if np.isfinite(nu) else stats.norm.cdf(x)


def _prob_range(prob, d: float, sys_h: float, n: int = 41) -> list[float]:
    """Lowest / highest prob(centre) as the segmentation bias runs over +-sys_h. A bias
    bound is not a distribution, so it gives a probability RANGE, not one number."""
    vals = [prob(d + bias) for bias in np.linspace(-sys_h, sys_h, n)]
    return [float(min(vals)), float(max(vals))]


def how_sure(p: list[float]) -> str:
    """Plain words for a probability range [lo, hi]."""
    lo, hi = p
    if lo >= 0.95:
        return "very likely"
    if lo >= 0.80:
        return "likely"
    if hi <= 0.05:
        return "very unlikely"
    if hi <= 0.20:
        return "unlikely"
    return "uncertain"


def compare_phase(name: str, a: dict, b: dict, tol: float, imaging_flagged: bool, scale_mismatch: bool) -> dict:
    """How sure are we that lot B differs from lot A for one phase, and by how much?

    delta = phi_B - phi_A. Its interval = t * sampling SE (random: area, regularity,
    field-to-field) + systematic half-width (segmentation, added linearly as a bias bound).
    Segmentation bias is mostly common-mode: nudging the thresholds moves both lots the
    same way. So delta is recomputed under every segmentation variant (threshold nudges,
    local thresholds) and only the change in DELTA counts. If imaging differs between
    lots that cancellation can't be trusted, and both lots' full ranges are combined.

    Two probabilities, each a range over the segmentation bias (flat prior on delta, so
    they are the confidence intervals read as probabilities):
      p_direction  the true change has the sign we observed (a real change, of any size)
      p_beyond     the true change is larger than +-tol (a change that matters)
    No decision is made here: the numbers say how sure we are, not what to do."""
    d = b["phi"] - a["phi"]
    va, unknown_a, borrowed_a = _lot_variance(a, b)
    vb, unknown_b, borrowed_b = _lot_variance(b, a)
    se = float(np.sqrt(va + vb))

    def dof(k):
        return k - 1 if k > 1 else np.inf

    denom = va**2 / dof(a["n_images"]) + vb**2 / dof(b["n_images"])
    nu = (va + vb) ** 2 / denom if denom > 0 else np.inf  # Welch-Satterthwaite
    t95 = float(stats.t.ppf(0.975, nu)) if np.isfinite(nu) else Z95
    t90 = float(stats.t.ppf(0.95, nu)) if np.isfinite(nu) else 1.644854

    if a.get("variant_shifts") and b.get("variant_shifts") and not imaging_flagged:
        sys_h = float(np.max(np.abs(np.subtract(b["variant_shifts"], a["variant_shifts"]))))
        sys_kind = "common-mode cancelled"
    else:
        ha = a.get("systematic_halfwidth", (a["systematic_range"][1] - a["systematic_range"][0]) / 2)
        hb = b.get("systematic_halfwidth", (b["systematic_range"][1] - b["systematic_range"][0]) / 2)
        sys_h, sys_kind = float(np.hypot(ha, hb)), "independent (imaging differs or old JSON)"
    h95, h90 = t95 * se + sys_h, t90 * se + sys_h

    sign = 1.0 if d >= 0 else -1.0
    p_direction = _prob_range(lambda c: _cdf(sign * c / se, nu), d, sys_h)
    p_beyond = _prob_range(lambda c: 1 - (_cdf((tol - c) / se, nu) - _cdf((-tol - c) / se, nu)), d, sys_h)
    # what the width of the delta interval is made of (95% half-widths)
    width = {
        "lot A sampling": float(t95 * np.sqrt(va)),
        "lot B sampling": float(t95 * np.sqrt(vb)),
        "segmentation": sys_h,
    }

    caveats = []
    if borrowed_a or borrowed_b:
        caveats.append("one lot has a single field: borrowed the other lot's field-to-field variation")
    if unknown_a or unknown_b:
        caveats.append(
            "field-to-field variation unknown (1 field per lot): probabilities are OVERSTATED, "
            "a lot difference cannot be told apart from a location difference"
        )
    if imaging_flagged:
        caveats.append("imaging conditions flagged in at least one image: part of delta may be imaging, not material")
    if scale_mismatch:
        caveats.append("lots analysed at different pixel sizes: these probabilities are not meaningful")

    settle = None
    if how_sure(p_beyond) not in ("very likely", "very unlikely") and not scale_mismatch:
        # sampling SE falls as 1/sqrt(imaging); how much imaging would push the interval to one side of tol?
        if abs(d) < tol:
            room, goal, t_used = tol - abs(d) - sys_h, "95% sure the change is within tolerance", t90
        else:
            room, goal, t_used = abs(d) - tol - sys_h, "95% sure the change exceeds tolerance", t95
        if room > 0:
            settle = (
                f"~{max((t_used * se / room) ** 2, 1.0):.1f}x more imaging per lot (area or locations) "
                f"would make us {goal}, if the difference stays this size"
            )
            if unknown_a or unknown_b:
                settle = "image >= 3 LOCATIONS per lot (more area alone cannot reveal location variation); " + settle
        else:
            settle = (
                "more imaging cannot make us sure: difference +- segmentation error straddles the tolerance; "
                "only better segmentation can"
            )

    return {
        "phase": name,
        "phi_a": a["phi"],
        "phi_b": b["phi"],
        "delta": float(d),
        "delta_rel": float(d / a["phi"]) if a["phi"] > 0 else None,
        "tolerance": float(tol),
        "se_sampling": se,
        "dof": float(nu),
        "systematic_halfwidth": sys_h,
        "systematic_kind": sys_kind,
        "interval95": [float(d - h95), float(d + h95)],
        "interval90": [float(d - h90), float(d + h90)],
        "p_direction": p_direction,
        "p_beyond_tolerance": p_beyond,
        "how_sure_real_change": how_sure(p_direction),
        "how_sure_beyond_tolerance": how_sure(p_beyond),
        "interval_width": width,
        "caveats": caveats,
        "to_settle": settle,
        "n_images": [a["n_images"], b["n_images"]],
    }


def compare_lots(path_a: str | Path, path_b: str | Path, tol_abs: dict[str, float], tol_rel: float) -> dict:
    """Compare two batch_uncertainty.json files phase by phase (lot A is the baseline)."""
    lots = []
    for path in (path_a, path_b):
        data = json.loads(Path(path).read_text())
        lots.append(data if "phases" in data or "intensity_classes" in data else {"phases": data})
    a, b = lots
    detector_a, detector_b = a.get("detector", "BSE"), b.get("detector", "BSE")
    if detector_a != "BSE" or detector_b != "BSE":
        raise ValueError(
            "lot comparison supports BSE phase estimates only; detector intensity classes are not comparable phases"
        )
    scale_a, scale_b = a.get("target_pixel_nm"), b.get("target_pixel_nm")
    scale_mismatch = bool(scale_a and scale_b and abs(scale_a / scale_b - 1) > 0.01) or (bool(scale_a) != bool(scale_b))
    flagged = [im["image"] for lot in lots for im in lot.get("images", []) if im.get("imaging_flags")]
    rows = []
    for name, pa in a["phases"].items():
        if name not in b["phases"]:
            continue
        tol = tol_abs.get(name, tol_rel * pa["phi"])
        rows.append(compare_phase(name, pa, b["phases"][name], tol, bool(flagged), scale_mismatch))
    strongest = max(rows, key=lambda r: (r["p_beyond_tolerance"][0], r["p_direction"][0]))
    return {
        "lot_a": str(path_a),
        "lot_b": str(path_b),
        "scale_nm": [scale_a, scale_b],
        "scale_mismatch": scale_mismatch,
        "flagged_images": flagged,
        "strongest_evidence": strongest["phase"],
        "phases": rows,
    }
