"""
Scratch: identify the batch of a LOT (k locations of one sample), strictly held out.

For every simulated lot, all k locations are removed from training first.
  material   - lot-average pore and bright-phase fraction (GET4) vs each batch's average,
               with a shared between-location covariance (from training locations only):
               Gaussian likelihood of the lot mean, N(mu_b, S/k + S/n_b + measurement/k)
  fingerprint- texture + fingerprint models refitted without the lot, location probabilities
               multiplied over the lot (calibration fixed at typical temperatures)
  combined   - both log-likelihoods added
Equal prior for each batch (a lot can come from any batch).
"""

import itertools
import sys
import warnings
from pathlib import Path

import numpy as np

PROJECT_DIR = Path(__file__).resolve().parents[1]  # batch_match/
sys.path.insert(0, str(PROJECT_DIR))  # so batch_classifier / get4 import when run from anywhere

import batch_classifier as B  # noqa: E402

warnings.filterwarnings("ignore")
rng = np.random.default_rng(1)
OUT = PROJECT_DIR / "out" / "classifier"
rows = B.index(B.ROOT)
D = B.Data(rows, B.build_features(rows), *B.build_texture(rows), B.build_materials(rows))
locs = sorted(set(D.loc))
PH = ["pore", "bright phase"]  # graphite = 1 - pore - bright, so it adds nothing
M = {l: np.array([D.materials[l][p][0] for p in PH]) for l in locs}
SE = {l: np.array([D.materials[l][p][1] for p in PH]) for l in locs}


def location_lp(train, l):
    """Fingerprint log-probabilities of location l (its views summed), models fitted on `train`."""
    total = np.zeros(len(D.batches))
    for v in B.VIEWS:
        tr, te = train & (D.view == v), (D.loc == l) & (D.view == v)
        if te.any():
            model, means = B.fit_view(D.Xf[tr], D.batch[tr])
            total += B.log_proba(model, means, D.Xf[te], D.batches).sum(0)
    return total


def material_loglik(lot, train_locs):
    k = len(lot)
    xbar = np.mean([M[l] for l in lot], axis=0)
    meas = np.diag(np.mean([SE[l] ** 2 for l in lot], axis=0)) / k
    resid, mus, ns = [], {}, {}
    for b in D.batches:
        tl = [l for l in train_locs if D.batch_of[l] == b]
        X = np.array([M[l] for l in tl])
        mus[b], ns[b] = X.mean(0), len(tl)
        resid.append(X - X.mean(0))
    R = np.vstack(resid)
    S = R.T @ R / (len(R) - len(D.batches))  # shared between-location covariance
    out = []
    for b in D.batches:
        C = S / k + S / ns[b] + meas
        d = xbar - mus[b]
        out.append(-0.5 * (d @ np.linalg.solve(C, d) + np.log(np.linalg.det(C))))
    out = np.array(out)
    return out - np.log(np.exp(out - out.max()).sum()) - out.max()


def fingerprint_loglik(lot):
    """Imaging-fingerprint evidence for the lot; its temperature is fitted on the OTHER locations only."""
    train = ~np.isin(D.loc, lot)
    others = [l for l in locs if l not in lot]
    inner = np.array([location_lp(train & (D.loc != m), m) for m in others])
    T = B.fit_temperature(inner, np.searchsorted(D.batches, np.array([D.batch_of[m] for m in others], dtype=object)))
    total = sum(np.log(B.softmax(location_lp(train, l) / T)) for l in lot)
    return total - np.log(np.exp(total - total.max()).sum()) - total.max()


print(f"{'k':>2s} {'method':12s} " + " ".join(f"{b:>9s}" for b in D.batches) + "   average")
for k in (1, 2, 3, 4, 5):
    res = {"material": [], "fingerprint": [], "combined": []}
    for b in D.batches:
        members = [l for l in locs if D.batch_of[l] == b]
        combos = list(itertools.combinations(members, k))
        combos = [combos[j] for j in rng.choice(len(combos), min(30, len(combos)), replace=False)]
        hits = {m: [] for m in res}
        for lot in combos:
            train_locs = [l for l in locs if l not in lot]
            lm = material_loglik(lot, train_locs)
            lf = fingerprint_loglik(lot)
            for name, ll in (("material", lm), ("fingerprint", lf), ("combined", lm + lf)):
                hits[name].append(D.batches[int(np.argmax(ll))] == b)
        for name in res:
            res[name].append(100 * np.mean(hits[name]))
    for name, accs in res.items():
        print(f"{k:2d} {name:12s} " + " ".join(f"{a:8.0f}%" for a in accs) + f"   {np.mean(accs):6.0f}%", flush=True)
