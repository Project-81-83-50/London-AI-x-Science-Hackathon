"""
Scratch: the two-step model (Batch_3?  -> material range rule -> Batch_1 vs Batch_2 specialist)
with an "unsure" option, nested leave-one-location-out exactly like batch_classifier.evaluate.

Answer: Batch_3 if P(Batch_3) >= 0.5; otherwise the range rule if it fires, else the specialist.
Confidence: P(Batch_3), or (1 - P(Batch_3)) * P(specialist's choice). Both steps are temperature
calibrated and the answer threshold chosen on held-out predictions of the OTHER locations.
"""

import warnings

import numpy as np

import batch_classifier as B

warnings.filterwarnings("ignore")
rows = B.index(B.ROOT)
D = B.Data(rows, B.build_features(rows), *B.build_texture(rows), B.build_materials(rows))
locs = sorted(set(D.loc))
IS3 = np.where(D.batch == "Batch_3", "B3", "B12").astype(object)
C1, C2 = np.array(["B12", "B3"], dtype=object), np.array(["Batch_1", "Batch_2"], dtype=object)


def fit_two_step(train):
    m = {}
    for v in B.VIEWS:
        tr = train & (D.view == v)
        t12 = tr & (D.batch != "Batch_3")
        m[v] = (B.fit_view(D.Xf[tr], IS3[tr]), B.fit_view(D.Xf[t12], D.batch[t12]))
    return m


def scores(models, i):
    (s1, mu1), (s2, mu2) = models[D.view[i]]
    return B.log_proba(s1, mu1, D.Xf[i:i + 1], C1)[0], B.log_proba(s2, mu2, D.Xf[i:i + 1], C2)[0]


def three_class(l1, l2, T1, T2):
    p3 = B.softmax(l1 / T1)[1]
    q = B.softmax(l2 / T2)
    return np.array([(1 - p3) * q[0], (1 - p3) * q[1], p3])


def answer(p, vote):
    if p[2] >= 0.5:
        return "Batch_3", p[2], "model"
    if vote:
        return vote, 1.0, "material"
    k = int(np.argmax(p[:2]))
    return C2[k], p[k], "model"


def calibrate(inner):
    """inner: {image index: (l1, l2)} held-out. Returns temperatures + thresholds (image, location)."""
    idx = np.array(sorted(inner))
    y3 = (D.batch[idx] == "Batch_3").astype(int)
    T1 = B.fit_temperature(np.array([inner[i][0] for i in idx]), y3)
    i12 = idx[D.batch[idx] != "Batch_3"]
    T2 = B.fit_temperature(np.array([inner[i][1] for i in i12]), (D.batch[i12] == "Batch_2").astype(int))
    loc_idx = {}
    for i in idx:
        loc_idx.setdefault(D.loc[i], []).append(i)
    L1 = {l: sum(inner[i][0] for i in ii) for l, ii in loc_idx.items()}
    L2 = {l: sum(inner[i][1] for i in ii) for l, ii in loc_idx.items()}
    ll = sorted(loc_idx)
    TL1 = B.fit_temperature(np.array([L1[l] for l in ll]), np.array([D.batch_of[l] == "Batch_3" for l in ll], int))
    l12 = [l for l in ll if D.batch_of[l] != "Batch_3"]
    TL2 = B.fit_temperature(np.array([L2[l] for l in l12]), np.array([D.batch_of[l] == "Batch_2" for l in l12], int))
    ci, ri = [], []
    for i in idx:
        a, c, _ = answer(three_class(*inner[i], T1, T2), None)
        ci.append(c), ri.append(a == D.batch[i])
    cl, rl = [], []
    for l in ll:
        a, c, _ = answer(three_class(L1[l], L2[l], TL1, TL2), None)
        cl.append(c), rl.append(a == D.batch_of[l])
    return {"T": (T1, T2), "TL": (TL1, TL2),
            "t_img": B.choose_threshold(np.array(ci), np.array(ri), 5),
            "t_loc": B.choose_threshold(np.array(cl), np.array(rl), 3)}


img, loc = [], []
for n, l in enumerate(locs):
    train = D.loc != l
    others = [m for m in locs if m != l]
    inner = {}
    for m in others:
        mm = fit_two_step(train & (D.loc != m))
        for i in np.nonzero(D.loc == m)[0]:
            inner[i] = scores(mm, i)
    cal = calibrate(inner)
    models = fit_two_step(train)
    ranges = B.material_ranges(D.materials, D.batch_of, [m for m in others if D.batch_of[m] in B.RANGE_BATCHES])
    vote = B.range_vote(D.materials[l], ranges)
    s = {i: scores(models, i) for i in np.nonzero(D.loc == l)[0]}
    for i, (l1, l2) in s.items():
        a, c, how = answer(three_class(l1, l2, *cal["T"]), vote if D.view[i] == "BSE" else None)
        img.append((D.batch[i], a, c >= cal["t_img"] or how == "material"))
    a, c, how = answer(three_class(sum(x[0] for x in s.values()), sum(x[1] for x in s.values()), *cal["TL"]), vote)
    loc.append((D.batch_of[l], a, c >= cal["t_loc"] or how == "material"))

for title, rec in (("SINGLE IMAGES", img), ("LOCATIONS", loc)):
    t = np.array([r[0] for r in rec], dtype=object)
    a = np.array([r[1] for r in rec], dtype=object)
    ok = np.array([r[2] for r in rec])
    print(f"{title}: forced {100 * np.mean(a == t):.0f}% ({np.sum(a == t)}/{len(t)});  with unsure: answered {ok.sum()}/{len(t)}, "
          f"right {np.sum(ok & (a == t))}/{ok.sum()} ({100 * np.sum(ok & (a == t)) / max(ok.sum(), 1):.0f}%)")
    for b in D.batches:
        m = t == b
        print(f"  {b}: forced {np.sum((a == t) & m)}/{m.sum()};  with unsure {np.sum(ok & (a == t) & m)} right, "
              f"{np.sum(ok & (a != t) & m)} wrong, {np.sum(~ok & m)} unsure")
