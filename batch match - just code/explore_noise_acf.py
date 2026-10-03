"""
Scratch: noise autocorrelation fingerprint (detector / scan-speed impulse response).

Noise residual = image minus a 9x9 local mean, kept only in flat areas (lowest 30% of
smoothed gradient). Its normalised 2-D autocorrelation at lags -4..4 is computed for
each quarter of every image (4 samples per image), for every view.
"""

import json
from pathlib import Path

import numpy as np
import tifffile
from scipy import fft, ndimage

from batch_classifier import ROOT, index

OUT = Path(__file__).parent / "out" / "classifier"
L = 4


def acf_fingerprint(g):
    g = g.astype(np.float32)
    hp = g - ndimage.uniform_filter(g, 9)
    grad = ndimage.gaussian_gradient_magnitude(g, 2.0)
    flat = grad <= np.percentile(grad, 30)
    flat &= (g > np.percentile(g, 2)) & (g < np.percentile(g, 98))  # avoid clipped pixels
    x = np.where(flat, hp, 0.0)
    m = flat.astype(np.float32)
    shape = (g.shape[0] + L, g.shape[1] + L)
    fx, fm = fft.rfft2(x, s=shape, workers=-1), fft.rfft2(m, s=shape, workers=-1)
    num = fft.irfft2(fx * np.conj(fx), s=shape, workers=-1)
    den = fft.irfft2(fm * np.conj(fm), s=shape, workers=-1)
    num, den = (np.roll(a, (L, L), axis=(0, 1))[: 2 * L + 1, : 2 * L + 1] for a in (num, den))
    acf = num / np.maximum(den, 1)
    acf /= acf[L, L]
    half = acf[L:, :].ravel()[L + 1:]  # unique half-plane (acf is symmetric), lag 0 dropped
    return half


def main():
    rows = index(ROOT)
    out = []
    for r in rows:
        a = tifffile.imread(r["path"])
        g = (a[..., 0] if a.ndim == 3 else a)[:, 8:-8]
        q = g.shape[1] // 4
        for k in range(4):
            out.append({"batch": r["batch"], "location": r["location"], "view": r["view"], "part": k,
                        "acf": acf_fingerprint(g[:, k * q: (k + 1) * q]).tolist()})
        print(f"  {r['batch']}/{r['path'].name}", flush=True)
    (OUT / "noise_acf.json").write_text(json.dumps(out))


if __name__ == "__main__":
    main()
