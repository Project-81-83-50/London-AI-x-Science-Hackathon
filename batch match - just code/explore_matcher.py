"""
Scratch: can an image (or a crop of it, in ANY view) be matched back to its known location?

Every known image is reduced to a structure map (4x binned, shading removed, normalised).
A query is located by FFT cross-correlation against every known image; the peak is scored
in standard deviations of the correlation surface. Test: random crops of each BSE / SE /
InLens image, matched against the OTHER two views only (so it must work across detectors).
"""

import numpy as np
import tifffile
from scipy import fft, ndimage

from batch_classifier import ROOT, index

S = 4


def structure(path_or_array):
    a = tifffile.imread(path_or_array) if not isinstance(path_or_array, np.ndarray) else path_or_array
    g = (a[..., 0] if a.ndim == 3 else a).astype(np.float32)
    h, w = g.shape[0] // S * S, g.shape[1] // S * S
    g = g[:h, :w].reshape(h // S, S, w // S, S).mean(axis=(1, 3))
    g = ndimage.gaussian_gradient_magnitude(g, 1.0)  # edges: shared by all detectors
    g -= ndimage.gaussian_filter(g, 10)
    return (g - g.mean()) / (g.std() + 1e-6)


def match_score(query, ref):
    H, W = ref.shape[0] + query.shape[0], ref.shape[1] + query.shape[1]
    fr = fft.rfft2(ref, s=(H, W), workers=-1)
    fq = fft.rfft2(query, s=(H, W), workers=-1)
    x = fr * np.conj(fq)
    c = fft.irfft2(x / (np.abs(x) + 1e-6 * np.abs(x).mean()), s=(H, W), workers=-1)
    return float((c.max() - c.mean()) / c.std())


def main():
    rows = index(ROOT)
    refs = [structure(r["path"]) for r in rows]
    rng = np.random.default_rng(0)
    results = []
    for qi, r in enumerate(rows):
        a = tifffile.imread(r["path"])
        g = a[..., 0] if a.ndim == 3 else a
        ch, cw = rng.integers(600, 1200), rng.integers(800, 2400)  # crop 15-30 um x 20-60 um
        y, x = rng.integers(0, g.shape[0] - ch), rng.integers(0, g.shape[1] - cw)
        q = structure(g[y: y + ch, x: x + cw])
        scores = [(match_score(q, refs[j]), j) for j, rr in enumerate(rows)
                  if not (rr["location"] == r["location"] and rr["view"] == r["view"])]  # exclude the source image itself
        scores.sort(reverse=True)
        s1, j1 = scores[0]
        s2 = next(s for s, j in scores if rows[j]["location"] != rows[j1]["location"])
        ok = rows[j1]["location"] == r["location"]
        results.append((ok, s1, s2))
        print(f"  {r['batch']}/{r['path'].name:26s} crop {ch}x{cw}: best {rows[j1]['view']:6s} {rows[j1]['location']} "
              f"score {s1:6.1f} (best other location {s2:5.1f})  {'OK' if ok else 'WRONG'}", flush=True)
    ok = np.array([r[0] for r in results]); s1 = np.array([r[1] for r in results]); s2 = np.array([r[2] for r in results])
    print(f"\nmatched to the right location: {ok.sum()}/{len(ok)}   true-match score min {s1[ok].min():.1f}, "
          f"best wrong-location score max {s2.max():.1f}")


if __name__ == "__main__":
    main()
