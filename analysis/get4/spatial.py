"""Uncertainty of one image's phase fraction: factor 1 (area, two-point covariance) and factor 2 (regularity,
tile overdispersion and the top-to-bottom trend), combined per phase mask by `analyse_phase`."""

import numpy as np
from scipy import fft, stats


def _raw_autocorr(m: np.ndarray, max_lag: int) -> tuple[np.ndarray, np.ndarray]:
    """Zero-padded FFT autocorrelation for |dy|, |dx| <= max_lag, plus pair counts."""
    h, w = m.shape
    shape = (h + max_lag, w + max_lag)
    f = fft.rfft2(m, s=shape, workers=-1)
    corr = fft.irfft2(f * np.conj(f), s=shape, workers=-1)
    corr = np.roll(corr, (max_lag, max_lag), axis=(0, 1))[: 2 * max_lag + 1, : 2 * max_lag + 1]
    lags = np.abs(np.arange(-max_lag, max_lag + 1))
    overlap = np.outer(np.clip(h - lags, 0, None), np.clip(w - lags, 0, None))
    return corr.astype(np.float64), overlap.astype(np.float64)


def normalised_covariance(mask: np.ndarray, max_lag: int, tile: int | None = None) -> tuple[np.ndarray, float]:
    """C(dy, dx). For huge images the pair sums are accumulated over tiles (bounded memory)."""
    m = mask.astype(np.float32)
    phi = float(m.mean())
    h, w = m.shape
    blocks = (
        [m] if tile is None else [m[y : y + tile, x : x + tile] for y in range(0, h, tile) for x in range(0, w, tile)]
    )
    acc = np.zeros((2 * max_lag + 1,) * 2)
    cnt = np.zeros_like(acc)
    for b in blocks:
        if min(b.shape) > max_lag:
            c, o = _raw_autocorr(b, max_lag)
            acc += c
            cnt += o
    if not 0 < phi < 1:
        return np.zeros_like(acc), phi
    s2 = acc / np.maximum(cnt, 1)
    return (s2 - phi**2) / (phi * (1 - phi)), phi


FEATURE_CUTOFF = 5  # in correlation lengths: keeps ~96% of an exponential C(r)


def integral_range(cov: np.ndarray, max_lag: int, corr_len: float | None = None) -> tuple[float, int, bool, np.ndarray]:
    """Sum C(r) out to the first zero of its radial average, or FEATURE_CUTOFF correlation
    lengths if sooner. The cap stops large-scale structure (gradients) from posing as
    "bigger features": anything beyond it must show up in the tile test as irregularity.
    Returns (a, r_cut, truncated, C_trunc)."""
    yy, xx = np.indices(cov.shape) - max_lag
    r = np.rint(np.hypot(yy, xx)).astype(int)
    profile = (np.bincount(r.ravel(), cov.ravel()) / np.bincount(r.ravel()))[: max_lag + 1]
    zeros = np.nonzero(profile <= 0)[0]
    r_cut = max_lag if len(zeros) == 0 else int(zeros[0])
    if corr_len:
        r_cut = min(r_cut, int(np.ceil(FEATURE_CUTOFF * corr_len)))
    truncated = r_cut >= max_lag
    cov_trunc = np.where(r < r_cut, cov, 0.0)
    return float(cov_trunc.sum()), r_cut, truncated, cov_trunc


def correlation_length(cov: np.ndarray, max_lag: int, axis: str) -> int | None:
    """Lag at which C drops below 1/e along x or y: a feature-size proxy."""
    line = cov[max_lag, max_lag:] if axis == "x" else cov[max_lag:, max_lag]
    below = np.nonzero(line < 1 / np.e)[0]
    return int(below[0]) if len(below) else None


def predicted_se(cov_trunc: np.ndarray, max_lag: int, phi: float, height: int, width: int) -> float:
    """Exact finite-window SE of phi_hat for a height x width window."""
    ky, kx = min(height - 1, max_lag), min(width - 1, max_lag)
    sub = cov_trunc[max_lag - ky : max_lag + ky + 1, max_lag - kx : max_lag + kx + 1]
    wy = 1 - np.abs(np.arange(-ky, ky + 1)) / height
    wx = 1 - np.abs(np.arange(-kx, kx + 1)) / width
    var = phi * (1 - phi) * (wy[:, None] * wx[None, :] * sub).sum() / (height * width)
    return float(np.sqrt(max(var, 0.0)))


def info_bits(se: float) -> float:
    """Bits gained about phi relative to a flat prior on [0, 1]."""
    return float(-0.5 * np.log2(2 * np.pi * np.e * se**2)) if se > 0 else float("inf")


def tile_scaling(mask: np.ndarray, sizes, min_tiles: int = 8) -> list[dict]:
    """Observed std of phi across non-overlapping L x L tiles."""
    m = mask.astype(np.float32)
    rows = []
    for s in sizes:
        ny, nx = m.shape[0] // s, m.shape[1] // s
        n = ny * nx
        if n < min_tiles:
            continue
        tiles = m[: ny * s, : nx * s].reshape(ny, s, nx, s).mean(axis=(1, 3))
        sd = float(tiles.std(ddof=1))
        rows.append(
            {"side": int(s), "n_tiles": int(n), "observed_se": sd, "observed_se_err": sd / np.sqrt(2 * (n - 1))}
        )
    return rows


def dispersion(tiles: list[dict], min_tiles: int = 16) -> dict | None:
    """Overdispersion D at the largest tile size with enough tiles, with a 90% interval."""
    ok = [t for t in tiles if t["n_tiles"] >= min_tiles and t["predicted_se"] > 0]
    if not ok:
        return None
    t = ok[-1]
    d = (t["observed_se"] / t["predicted_se"]) ** 2
    dof = t["n_tiles"] - 1
    return {
        "D": d,
        "D_90": [d * dof / stats.chi2.ppf(0.95, dof), d * dof / stats.chi2.ppf(0.05, dof)],
        "tile_side": t["side"],
        "n_tiles": t["n_tiles"],
    }


def depth_trend(mask: np.ndarray, cov_trunc: np.ndarray, max_lag: int, phi: float, n_bands: int = 8) -> dict | None:
    """Change in phi from top to bottom of the image (assumes y = through-thickness)."""
    h, w = mask.shape
    bh = h // n_bands
    if bh < 2:
        return None
    y = (np.arange(n_bands) + 0.5) / n_bands
    f = np.array([mask[i * bh : (i + 1) * bh].mean() for i in range(n_bands)])
    slope = np.polyfit(y, f, 1)[0]
    se_band = predicted_se(cov_trunc, max_lag, phi, bh, w)
    slope_se = se_band / np.sqrt(((y - y.mean()) ** 2).sum())
    return {"change_top_to_bottom": float(slope), "se": float(slope_se), "band_phi": f.tolist()}


def analyse_phase(mask: np.ndarray, max_lag: int, tile: int | None, sizes, unit_len: float) -> dict:
    """Area and regularity factors of one phase mask: phi, its variance terms, N_eff and the tile checks."""
    h, w = mask.shape
    area = h * w
    cov, phi = normalised_covariance(mask, max_lag, tile)
    lx, ly = correlation_length(cov, max_lag, "x"), correlation_length(cov, max_lag, "y")
    corr_len = np.sqrt(lx * ly) if lx and ly else None
    a, r_cut, truncated, cov_trunc = integral_range(cov, max_lag, corr_len)

    var_floor = 0.25 / area  # keeps absent / saturated phases from getting zero variance
    var_area = max(predicted_se(cov_trunc, max_lag, phi, h, w) ** 2, var_floor)

    tiles = tile_scaling(mask, sizes)
    for row in tiles:
        s = row["side"]
        row["predicted_se"] = predicted_se(cov_trunc, max_lag, phi, s, s)
        row["naive_se"] = float(np.sqrt(phi * (1 - phi)) / s)
    disp = dispersion(tiles)
    d_used = max(disp["D"], 1.0) if disp else 1.0
    var_irreg = var_area * (d_used - 1.0)
    var_image = var_area + var_irreg

    start = tiles[-1]["side"] if tiles else 4
    extrapolated = [
        {"side": float(s), "predicted_se": predicted_se(cov_trunc, max_lag, phi, int(s), int(s))}
        for s in np.geomspace(start, np.sqrt(area), 8)
    ]

    return {
        "phi": phi,
        "var_area": var_area,
        "var_irregularity": var_irreg,
        "var_image": var_image,
        "se_image": float(np.sqrt(var_image)),
        "se_naive_pixels": float(np.sqrt(phi * (1 - phi) / area)),
        "dispersion": disp,
        "integral_range": a * unit_len**2,
        "integral_range_truncated": truncated,
        "corr_length_x": None if lx is None else lx * unit_len,
        "corr_length_y": None if ly is None else ly * unit_len,
        "resolution_limited": bool(lx and ly and min(lx, ly) < 5),
        "n_eff": float(area / a) if a > 0 else float(area),
        "bits": info_bits(np.sqrt(var_image)),
        "depth_trend": depth_trend(mask, cov_trunc, max_lag, phi),
        "tiles": tiles,
        "extrapolated": extrapolated,
    }
