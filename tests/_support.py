"""Shared test helpers: deterministic synthetic SEM images and golden-file (characterisation) checks.

Golden files pin the CURRENT numerical behaviour of the analysis code so that refactors can be verified:
a test turns its outputs into JSON-able data (arrays become summaries, see `summarise_array`) and calls
`check_golden(name, data)`, which compares them with tests/golden/<name>.json at a relative tolerance of
1e-9 and an absolute tolerance of 1e-12 (override with GOLDEN_RTOL / GOLDEN_ATOL). Regenerate after an
intended change with

    UPDATE_GOLDEN=1 python -m pytest            # rewrites every golden file that a test touches

and review the diff of tests/golden/ before committing it.

The default tolerance holds on the platform the golden files were generated on (Windows, Python 3.14, the
pinned packages). Other platforms differ by up to ~2e-7 relative (float32 FFTs, BLAS), so CI on Linux runs
with GOLDEN_RTOL=1e-5 GOLDEN_ATOL=5e-7 (.github/workflows/ci.yml).
"""

import json
import math
import os
from pathlib import Path

import numpy as np
import tifffile
from scipy import ndimage

REPO_ROOT = Path(__file__).resolve().parents[1]
GOLDEN_DIR = Path(__file__).resolve().parent / "golden"
RTOL = float(os.environ.get("GOLDEN_RTOL", "1e-9"))
ATOL = float(os.environ.get("GOLDEN_ATOL", "1e-12"))


def update_golden() -> bool:
    """True when the golden files should be (re)written instead of compared."""
    return os.environ.get("UPDATE_GOLDEN", "").strip().lower() in {"1", "true", "yes"}


# ---------------------------------------------------------------- synthetic SEM-like images


def synthetic_phases(seed: int, shape: tuple[int, int] = (384, 384)) -> np.ndarray:
    """Phase map 0 pore / 1 graphite / 2 bright phase: thresholded smooth random fields (blob-like features)."""
    rng = np.random.default_rng(seed)
    f1 = ndimage.gaussian_filter(rng.standard_normal(shape), 5)
    f2 = ndimage.gaussian_filter(rng.standard_normal(shape), 3)
    pore = f1 < np.quantile(f1, 0.22)
    bright = (f2 > np.quantile(f2, 0.90)) & ~pore
    labels = np.ones(shape, np.uint8)
    labels[pore] = 0
    labels[bright] = 2
    return labels


def render(
    labels: np.ndarray,
    seed: int,
    levels: tuple[float, float, float] = (0.12, 0.45, 0.85),
    noise: float = 0.04,
    shading: float = 0.08,
    stripes: float = 0.0,
) -> np.ndarray:
    """Grey image in [0, 1] (float64) of a phase map: phase grey levels, slight blur, smooth shading,
    optional horizontal scan-line stripes and Gaussian pixel noise."""
    rng = np.random.default_rng(seed + 10_000)
    h, w = labels.shape
    img = np.asarray(levels, float)[labels]
    img = ndimage.gaussian_filter(img, 1.0)
    yy, xx = np.mgrid[0:h, 0:w]
    img = img * (1 + shading * (xx / w - 0.5)) + 0.4 * shading * (yy / h - 0.5)
    if stripes:
        img = img + stripes * rng.standard_normal(h)[:, None]
    img = img + rng.normal(0.0, noise, labels.shape)
    return np.clip(img, 0.0, 1.0)


def synthetic_image(
    seed: int = 0,
    shape: tuple[int, int] = (384, 384),
    dtype=np.float32,
    stripes: float = 0.0,
) -> np.ndarray:
    """Deterministic SEM-like BSE image: three intensity phases with blobs, shading and noise.

    Float dtypes are returned in [0, 1]; integer dtypes are scaled to their full range."""
    img = render(synthetic_phases(seed, shape), seed, stripes=stripes)
    dtype = np.dtype(dtype)
    if np.issubdtype(dtype, np.integer):
        return np.round(img * np.iinfo(dtype).max).astype(dtype)
    return img.astype(dtype)


# Grey levels (pore, graphite, bright) and noise of the three detector views of one field. ETD keeps
# pores black; InLens fills pores in; BSE is the noisiest view (analysis.fields tells them apart that way).
DETECTOR_LOOKS = {
    "BSE": {"levels": (0.12, 0.45, 0.85), "noise": 0.06},
    "ETD": {"levels": (0.05, 0.50, 0.70), "noise": 0.015},
    "Inlens": {"levels": (0.40, 0.45, 0.90), "noise": 0.015},
}


def detector_views(
    seed: int, shape: tuple[int, int] = (512, 512), shift: tuple[int, int] = (0, 0)
) -> dict[str, np.ndarray]:
    """uint8 BSE / ETD / Inlens views of the same synthetic field; the SE views are displaced by `shift`."""
    labels = synthetic_phases(seed, shape)
    views = {}
    for i, (det, look) in enumerate(DETECTOR_LOOKS.items()):
        lab = labels if det == "BSE" else np.roll(labels, shift, axis=(0, 1))
        img = render(lab, seed + 100 * i, levels=look["levels"], noise=look["noise"], shading=0.03)
        views[det] = np.round(img * 255).astype(np.uint8)
    return views


def write_tiff(path: Path, arr: np.ndarray, pixel_nm: float | None = None) -> Path:
    """Write a TIFF; with `pixel_nm`, the resolution tags give that pixel size (pixels per centimetre)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    if pixel_nm:
        per_cm = 1e7 / pixel_nm
        tifffile.imwrite(path, arr, resolution=(per_cm, per_cm), resolutionunit="CENTIMETER")
    else:
        tifffile.imwrite(path, arr)
    return path


# ---------------------------------------------------------------- golden files


def summarise_array(a, n_sample: int = 48) -> dict:
    """Order-sensitive numerical fingerprint of an array (shape, dtype, moments, an index-weighted sum and an
    evenly spaced sample), so a golden file pins an image or label map without storing it."""
    a = np.asarray(a)
    flat = a.ravel()
    out = {"shape": list(a.shape), "dtype": str(a.dtype)}
    if flat.size == 0:
        return out
    if a.dtype == bool:
        flat = flat.astype(np.int64)
    f = flat.astype(np.float64)
    finite = np.isfinite(f)
    ff = f[finite]
    out.update(
        n_nonfinite=int((~finite).sum()),
        sum=float(ff.sum()),
        sum_sq=float((ff**2).sum()),
        min=float(ff.min()) if ff.size else None,
        max=float(ff.max()) if ff.size else None,
        index_weighted_sum=float((np.where(finite, f, 0.0) * np.linspace(0.0, 1.0, f.size)).sum()),
        sample=f[np.linspace(0, f.size - 1, min(n_sample, f.size)).astype(int)].tolist(),
    )
    if np.issubdtype(a.dtype, np.integer) or a.dtype == bool:
        lo = int(flat.min())
        if lo >= 0 and int(flat.max()) < 256:
            out["bincount"] = np.bincount(flat.astype(np.int64)).tolist()
    return out


def jsonable(x):
    """Plain JSON data from numpy scalars / arrays, tuples, Paths and dicts with non-string keys.
    Arrays with more than 64 elements are summarised (summarise_array), smaller ones kept as lists."""
    if isinstance(x, dict):
        return {str(k): jsonable(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [jsonable(v) for v in x]
    if isinstance(x, np.ndarray):
        return summarise_array(x) if x.size > 64 else jsonable(x.tolist())
    if isinstance(x, np.bool_):
        return bool(x)
    if isinstance(x, np.integer):
        return int(x)
    if isinstance(x, np.floating):
        return float(x)
    if isinstance(x, Path):
        return x.as_posix()
    return x


def drop_keys(x, keys: set[str]):
    """Copy of nested data without the given dict keys (timestamps, absolute paths)."""
    if isinstance(x, dict):
        return {k: drop_keys(v, keys) for k, v in x.items() if k not in keys}
    if isinstance(x, list):
        return [drop_keys(v, keys) for v in x]
    return x


def _close(a: float, b: float, rtol: float, atol: float) -> bool:
    if math.isnan(a) or math.isnan(b):
        return math.isnan(a) and math.isnan(b)
    if math.isinf(a) or math.isinf(b):
        return a == b
    return math.isclose(a, b, rel_tol=rtol, abs_tol=atol)


def compare(expected, actual, rtol: float = RTOL, atol: float = ATOL, path: str = "$") -> list[str]:
    """Differences between two JSON-like structures (numbers within tolerance; bools and ints exact)."""
    diffs = []
    if isinstance(expected, dict) and isinstance(actual, dict):
        for k in sorted(set(expected) | set(actual)):
            if k not in actual:
                diffs.append(f"{path}.{k}: missing in actual")
            elif k not in expected:
                diffs.append(f"{path}.{k}: unexpected key in actual")
            else:
                diffs += compare(expected[k], actual[k], rtol, atol, f"{path}.{k}")
    elif isinstance(expected, list) and isinstance(actual, list):
        if len(expected) != len(actual):
            diffs.append(f"{path}: length {len(actual)} != expected {len(expected)}")
        else:
            for i, (e, a) in enumerate(zip(expected, actual, strict=True)):
                diffs += compare(e, a, rtol, atol, f"{path}[{i}]")
    elif isinstance(expected, bool) or isinstance(actual, bool):
        if expected is not actual:
            diffs.append(f"{path}: {actual!r} != expected {expected!r}")
    elif isinstance(expected, (int, float)) and isinstance(actual, (int, float)):
        if not _close(float(expected), float(actual), rtol, atol):
            diffs.append(f"{path}: {actual!r} != expected {expected!r}")
    elif expected != actual:
        diffs.append(f"{path}: {actual!r} != expected {expected!r}")
    return diffs


def load_golden(name: str) -> object | None:
    """Stored golden data, or None if there is no golden file of that name."""
    path = GOLDEN_DIR / f"{name}.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else None


def check_golden(name: str, data, rtol: float = RTOL, atol: float = ATOL, missing: str = "fail") -> None:
    """Compare `data` with tests/golden/<name>.json, or write it when UPDATE_GOLDEN=1.

    `missing` is what happens when the golden file does not exist: "fail" (default) or "skip"
    (used by the realdata tests, whose golden files depend on locally available images)."""
    import pytest

    data = json.loads(json.dumps(jsonable(data)))  # exactly what would be stored (tuples -> lists etc.)
    path = GOLDEN_DIR / f"{name}.json"
    if update_golden():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, indent=1, sort_keys=True) + "\n", encoding="utf-8")
        return
    expected = load_golden(name)
    if expected is None:
        message = f"no golden file {path.relative_to(REPO_ROOT).as_posix()}; run with UPDATE_GOLDEN=1 to create it"
        if missing == "skip":
            pytest.skip(message)
        pytest.fail(message)
    diffs = compare(expected, data, rtol, atol)
    if diffs:
        shown = "\n  ".join(diffs[:25])
        more = f"\n  ... and {len(diffs) - 25} more" if len(diffs) > 25 else ""
        pytest.fail(f"{len(diffs)} difference(s) from golden {name} (rtol={rtol}):\n  {shown}{more}")
