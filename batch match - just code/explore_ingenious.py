"""
Scratch: two ways to get more certainty out of the same models, tested on held-out data.

A. CONFORMAL PREDICTION SETS. Instead of "Batch_x or unsure", the smallest set of batches that
   contains the true one with >= 90% probability. The set threshold is calibrated on held-out
   predictions of the OTHER locations (nested, like evaluate), so the guarantee is honest.
B. DECIDE PER LOT. Several locations of one lot are pooled (product of their probabilities).
     pooled held-out : every location's probability comes from a model that never saw it, but
                       that model did see the other locations of the pool (slightly optimistic)
     strict          : the whole pool is left out of training (slightly pessimistic: fewer
                       locations of that batch remain to learn from)
"""

import itertools
import warnings

import numpy as np

import batch_classifier as B

warnings.filterwarnings("ignore")
ALPHA = 0.10
rng = np.random.default_rng(0)


def conformal_q(scores, alpha=ALPHA):
    n = len(scores)
    k = int(np.ceil((n + 1) * (1 - alpha)))
    return 1.0 if k > n else float(np.sort(scores)[k - 1])


rows = B.index(B.ROOT)
D = B.Data(rows, B.build_features(rows), *B.build_texture(rows), B.build_materials(rows))
locs = sorted(set(D.loc))
bi = {b: i for i, b in enumerate(D.batches)}
img_p, loc_p, img_set, loc_set, cals = {}, {}, {}, {}, []
for n, l in enumerate(locs):
    train = D.loc != l
    others = [m for m in locs if m != l]
    inner = B.held_out_scores(D, train, others)
    cal = B.calibrate(D, inner)
    cals.append(cal)
    idx = sorted(inner)
    p_in = np.array([B.combine(*inner[i], cal) for i in idx])
    y_in = np.array([bi[D.batch[i]] for i in idx])
    q_img = conformal_q(1 - p_in[np.arange(len(idx)), y_in])
    loc_in = np.array([D.loc[i] for i in idx])
    q_loc = conformal_q(np.array([1 - B.location_proba(p_in[loc_in == m])[bi[D.batch_of[m]]] for m in others]))
    models = B.fit_models(D, train)
    ps = []
    for i in np.nonzero(D.loc == l)[0]:
        p = B.combine(*B.raw_scores(D, models, i), cal)
        img_p[i] = p
        ps.append(p)
        img_set[i] = [b for b in D.batches if 1 - p[bi[b]] <= q_img]
    loc_p[l] = B.location_proba(np.array(ps))
    loc_set[l] = [b for b in D.batches if 1 - loc_p[l][bi[b]] <= q_loc]
    print(f"  {n + 1}/{len(locs)} {l}", flush=True)


def describe_sets(sets, truth, title):
    covered = [t in s for s, t in zip(sets, truth)]
    print(f"\n{title}: true batch inside the set {sum(covered)}/{len(sets)} ({100 * np.mean(covered):.0f}%; "
          f"guarantee >= {100 * (1 - ALPHA):.0f}%), average set size {np.mean([len(s) for s in sets]):.2f}")
    for b in D.batches:
        kinds = {}
        for s, t in zip(sets, truth):
            if t != b:
                continue
            key = " or ".join(x[-1] for x in s) if s else "empty"
            kinds[key] = kinds.get(key, 0) + 1
        print(f"  true {b}: " + ", ".join(f"{{{k}}} x{v}" for k, v in sorted(kinds.items(), key=lambda kv: -kv[1])))


describe_sets([img_set[i] for i in sorted(img_set)], [D.batch[i] for i in sorted(img_set)], "A. SETS, single images")
describe_sets([loc_set[l] for l in locs], [D.batch_of[l] for l in locs], "A. SETS, locations")

print("\nB. DECIDE PER LOT (k locations of the same lot pooled), % of lots identified correctly")
print(f"  {'k':>2s}  " + "  ".join(f"{b:>9s}" for b in D.batches) + "   (pooled held-out)")
for k in (1, 2, 3, 4, 5):
    accs = []
    for b in D.batches:
        members = [l for l in locs if D.batch_of[l] == b]
        combos = list(itertools.combinations(members, k))
        if len(combos) > 600:
            combos = [combos[j] for j in rng.choice(len(combos), 600, replace=False)]
        right = [D.batches[B.location_proba(np.array([loc_p[m] for m in c])).argmax()] == b for c in combos]
        accs.append(100 * np.mean(right))
    print(f"  {k:2d}  " + "  ".join(f"{a:8.0f}%" for a in accs))

fixed = {"T_fingerprint": float(np.median([c["T_fingerprint"] for c in cals])),
         "T_texture": float(np.median([c["T_texture"] for c in cals]))}
print(f"  strict: the whole pool left out of training (calibration fixed at the median temperatures)")
for k in (2, 3):
    accs = []
    for b in D.batches:
        members = [l for l in locs if D.batch_of[l] == b]
        combos = list(itertools.combinations(members, k))
        combos = [combos[j] for j in rng.choice(len(combos), min(40, len(combos)), replace=False)]
        right = []
        for c in combos:
            models = B.fit_models(D, ~np.isin(D.loc, c))
            pl = []
            for m in c:
                pl.append(B.location_proba(np.array([B.combine(*B.raw_scores(D, models, i), fixed)
                                                     for i in np.nonzero(D.loc == m)[0]])))
            right.append(D.batches[B.location_proba(np.array(pl)).argmax()] == b)
        accs.append(100 * np.mean(right))
    print(f"  {k:2d}  " + "  ".join(f"{a:8.0f}%" for a in accs) + "   (strict)")
