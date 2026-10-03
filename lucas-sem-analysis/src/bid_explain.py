"""Batch-ID stage, step 4: evidence maps, per-sample facts JSON, and end-to-end prediction for new images.

Evidence (exact, not attention): every DINO head is StandardScaler -> PCA -> logistic regression on a weighted
mean of patch tokens, so it folds into logits = A x + c0, and token i contributes A t_i w_i / sum(w). The map of
contribution[winner] - contribution[runner-up] (mean over the fixed head grid and, for head R, over region
types) is the evidence map; per-token contributions sum to the head's logits (reconstruction error reported).
The S head's evidence is per feature: LDA coefficient x robust z.

Usage:
  python -m src.bid_explain samples                    # JSON + evidence PNG for the 31 training samples
  python -m src.bid_explain predict --bse X_BSE.tif --inlens X_Inlens.tif --out outputs/batchid/new/X
"""
import argparse
import json
import pickle
import time
from pathlib import Path

import numpy as np
from PIL import Image
from scipy import ndimage as ndi

from . import config as C
from .bid_features import S_FEATURES, features as label_features
from .bid_model import BATCHES, token_phase_weights

OUT = C.ROOT / "outputs" / "batchid"
PATCH = 14


def fold_head(sc, pca, lr):
    """logits = A @ x + c0 for x in raw feature space."""
    W = lr.coef_ @ pca.components_ / sc.scale_            # (3, F)
    c0 = lr.intercept_ - lr.coef_ @ pca.components_ @ (sc.mean_ / sc.scale_ + pca.mean_)
    return W, c0


def dino_evidence(model, tokens, weights):
    """tokens (hp, wp, F); weights (hp, wp, 4) phase fractions. Returns logits (3,), per-token contrib (hp, wp, 3)."""
    hp, wp, nf = tokens.shape
    heads = model["dino_heads"]
    if model["dino_head"] == "R":
        per = len(model["grid"])
        regions = [C.CLASSES.index(r) for r in model["regions"]]
        contrib = np.zeros((hp, wp, 3))
        logits = np.zeros(3)
        for j, k in enumerate(regions):
            w = weights[..., k]
            s = max(w.sum(), 1e-6)
            for sc, pca, lr in heads[j * per:(j + 1) * per]:
                A, c0 = fold_head(sc, pca, lr)
                contrib += (tokens @ A.T) * (w / s)[..., None] / (per * len(regions))
                logits += (A @ ((tokens * w[..., None]).sum((0, 1)) / s) + c0) / (per * len(regions))
        return logits, contrib
    # texton head T: logits = A sqrt(h) + c0 with h_j = n_j / N. Giving each token in texton j the share
    # A[:, j] / (N sqrt(h_j)) makes the per-token contributions sum exactly to A sqrt(h).
    km = model["kmeans"]
    valid = weights.sum(-1) > 0.5
    assign = km.predict(tokens.reshape(-1, nf).astype(km.cluster_centers_.dtype)).reshape(hp, wp)
    n_valid = max(int(valid.sum()), 1)
    h = np.bincount(assign[valid], minlength=km.n_clusters) / n_valid
    contrib = np.zeros((hp, wp, 3))
    logits = np.zeros(3)
    for sc, pca, lr in heads:
        A, c0 = fold_head(sc, pca, lr)
        share = A[:, assign] / (n_valid * np.sqrt(np.maximum(h[assign], 1e-12)))     # (3, hp, wp)
        contrib += np.where(valid[..., None], share.transpose(1, 2, 0), 0) / len(heads)
        logits += (A @ np.sqrt(h) + c0) / len(heads)
    return logits, contrib


def s_evidence(model, f):
    x = np.array([f[k] for k in model["S_features"]])
    z = np.clip((x - model["S_median"]) / model["S_iqr"], -3, 3)
    lda = model["lda"]
    proba = lda.predict_proba(z[None])[0]
    contrib = lda.coef_ * z[None]                         # (3, 5)
    return proba, z, contrib


def explain(model, sid, lab, tokens, f, extra):
    weights = token_phase_weights(lab, *tokens.shape[:2])
    logits_d, contrib = dino_evidence(model, tokens, weights)
    e = np.exp(logits_d - logits_d.max())
    p_d = e / e.sum()
    p_s, z, s_contrib = s_evidence(model, f)
    p_f = (p_s + p_d) / 2
    order = np.argsort(p_f)[::-1]
    win, run = int(order[0]), int(order[1])
    ev = contrib[..., win] - contrib[..., run]
    recon = float(np.abs(contrib.sum((0, 1)) - (logits_d - _c0_mean(model))).max())
    # top evidence regions
    valid_tok = weights.sum(-1) > 0.5
    thr = np.percentile(ev[valid_tok], 90)
    top = (ev >= thr) & valid_tok
    cc, n = ndi.label(top)
    regions = []
    for i in np.argsort([-ev[cc == j].sum() for j in range(1, n + 1)])[:3]:
        ys, xs = np.nonzero(cc == i + 1)
        y0, y1, x0, x1 = ys.min() * PATCH, (ys.max() + 1) * PATCH, xs.min() * PATCH, (xs.max() + 1) * PATCH
        sub = lab[y0:y1, x0:x1]
        v = sub != C.EXCLUDED
        regions.append({"bbox_um": [round(v_ * C.NM_PER_PX / 1000, 2) for v_ in (x0, y0, x1, y1)],
                        "evidence_share": round(float(ev[cc == i + 1].sum() / max(ev[ev > 0].sum(), 1e-9)), 3),
                        "local_phase_pct": {c: round(100 * float((sub[v] == k).mean()), 1) for k, c in enumerate(C.CLASSES)} if v.any() else {}})
    top_w = weights[top].sum(0)
    all_w = weights[valid_tok].sum(0)
    excluded_share = float((1 - weights.sum(-1))[ev > thr].mean()) if (ev > thr).any() else 0.0
    return {
        "sample_id": sid,
        "predicted_batch": BATCHES[win], "runner_up": BATCHES[run],
        "probabilities": {"fused_F": dict(zip(BATCHES, np.round(p_f, 3).tolist())),
                          "S_head": dict(zip(BATCHES, np.round(p_s, 3).tolist())),
                          "dino_head": dict(zip(BATCHES, np.round(p_d, 3).tolist()))},
        "features_S": {k: {"value": round(float(f[k]), 4), "robust_z": round(float(zz), 2),
                           "push_toward_winner_vs_runner_up": round(float(s_contrib[win, i] - s_contrib[run, i]), 3)}
                       for i, (k, zz) in enumerate(zip(model["S_features"], z))},
        "evidence": {"phase_share_in_top10pct_evidence_pct": {c: round(100 * float(top_w[k] / max(top_w.sum(), 1e-9)), 1) for k, c in enumerate(C.CLASSES)},
                     "phase_share_whole_image_pct": {c: round(100 * float(all_w[k] / max(all_w.sum(), 1e-9)), 1) for k, c in enumerate(C.CLASSES)},
                     "top_regions": regions, "reconstruction_error": recon,
                     "shortcut_alarm": excluded_share > 0.3},
        **extra,
    }, ev


def _c0_mean(model):
    return np.mean([fold_head(*h)[1] for h in model["dino_heads"]], 0)


PROBE_SKIP = ("batch", "sample_id")


def qc_and_confidence(facts, lab, probes, cu_foil, manual_exclusion, self_id=None):
    """QC flags, acquisition (session) check, novelty flags and a confidence tier, added to `facts` in place."""
    train = C.read_csv(C.OUT_MET / "bid_session_probes.csv")
    keys = [k for k in train[0] if k not in PROBE_SKIP]
    T = np.array([[float(r[k]) for k in keys] for r in train])
    mu, sd = T.mean(0), T.std(0) + 1e-9
    Z = (T - mu) / sd
    z = (np.array([float(probes[k]) for k in keys]) - mu) / sd
    ids = [r["sample_id"] for r in train]
    dist = np.sqrt(((Z - z) ** 2).sum(1))
    if self_id in ids:
        dist[ids.index(self_id)] = np.inf
    nn = int(np.argmin(dist))
    D = np.sqrt(((Z[:, None] - Z[None]) ** 2).sum(-1))
    np.fill_diagonal(D, np.inf)
    nn_max = float(D.min(1).max())
    qc_groups = {r["sample_id"]: r["height_group"] for r in C.read_csv(C.QC)}
    acq_novel = bool(dist[nn] > nn_max)
    feat_novel = [k for k, v in facts["features_S"].items() if abs(v["robust_z"]) >= 3]
    valid = lab != C.EXCLUDED
    facts["qc"] = {"excluded_pct": round(100 * float((~valid).mean()), 2), "cu_foil_detected": bool(cu_foil),
                   "manual_exclusion": bool(manual_exclusion), "detectors_used": ["BSE", "Inlens"]}
    facts["acquisition"] = {
        "probes": {k: round(float(probes[k]), 3) for k in keys},
        "nearest_training_acquisition": {"sample_id": ids[nn], "batch": train[nn]["batch"],
                                         "height_group": qc_groups.get(ids[nn]), "distance_z": round(float(dist[nn]), 2)},
        "novel_acquisition": acq_novel,
        "warning": "acquisition properties alone predict batch at 0.68 balanced accuracy in training; "
                   "a prediction that matches the nearest-acquisition batch may reflect imaging session, not material"}
    facts["novelty"] = {"unusual_features_abs_robust_z_ge_3": feat_novel, "novel_acquisition": acq_novel}
    p = sorted(facts["probabilities"]["fused_F"].values(), reverse=True)
    top, margin = p[0], p[0] - p[1]
    reasons = []
    if facts["evidence"]["shortcut_alarm"]:
        reasons.append("evidence sits on excluded / junk regions")
    if acq_novel:
        reasons.append("acquisition settings unlike any training image")
    if feat_novel:
        reasons.append(f"unusual feature values (|robust z| >= 3): {', '.join(feat_novel)}")
    if reasons or top < 0.5:
        tier = "Low"
        if top < 0.5:
            reasons.append(f"top probability {top:.2f} < 0.5")
    elif top >= 0.7 and margin >= 0.3:
        tier = "High"
    else:
        tier = "Medium"
        reasons.append(f"top probability {top:.2f}, margin {margin:.2f}")
    pair = {facts["predicted_batch"], facts["runner_up"]}
    if pair == {"Batch_1", "Batch_2"} and tier == "High":
        tier = "Medium"
        reasons.append("Batch_1 vs Batch_2 is not reliably separable (leave-one-out recall Batch_2 2/7)")
    facts["confidence"] = {"tier": tier, "reasons": reasons or ["top probability >= 0.7 and margin >= 0.3, no alarms"]}
    return facts


def evidence_png(bse, ev, path):
    h, w = bse.shape
    up = np.kron(ev, np.ones((PATCH, PATCH)))[:h, :w]
    up = np.pad(up, ((0, h - up.shape[0]), (0, w - up.shape[1])))
    m = np.abs(up).max() or 1
    g = np.repeat((bse * 255)[..., None], 3, -1).astype(np.float32) * 0.6
    pos, neg = np.clip(up / m, 0, 1), np.clip(-up / m, 0, 1)
    g[..., 0] += 255 * 0.4 * pos
    g[..., 2] += 255 * 0.4 * neg
    Image.fromarray(g.clip(0, 255).astype(np.uint8)).save(path, quality=88)


def cmd_samples(args):
    model = pickle.load(open(C.MODELS / "bid_model.pkl", "rb"))
    scores = json.load(open(C.OUT_MET / "bid_scores.json"))
    null = json.load(open(C.OUT_MET / "bid_null.json")) if (C.OUT_MET / "bid_null.json").exists() else {}
    feats = {r["sample_id"]: r for r in C.read_csv(C.OUT_MET / "bid_features.csv")}
    probes = {r["sample_id"]: r for r in C.read_csv(C.OUT_MET / "bid_session_probes.csv")}
    ref = {"LOO_F": scores["LOO_F"]["balanced_accuracy"], "LOO_S": scores["LOO_S"]["balanced_accuracy"],
           "LOGO_F": scores["LOGO_F"]["balanced_accuracy"], "nuisance_only_LOO": scores["nuisance_only_LOO"]["balanced_accuracy"],
           "permutation": null}
    OUT.mkdir(parents=True, exist_ok=True)
    for batch, sid in C.sample_ids():
        lab = np.load(C.proc_dir(sid) / "final_labels.npy")
        tokens = np.concatenate([np.load(C.proc_dir(sid) / f"dino_{d}_50nm.npy").astype(np.float32) for d in ("BSE", "Inlens")], -1)
        f = {k: float(feats[sid][k]) for k in S_FEATURES}
        loo = scores["per_sample_LOO"][sid]
        facts, ev = explain(model, sid, lab, tokens, f, {
            "true_batch": batch, "note": "training sample: the probabilities above come from a model that saw it; "
                                         "the honest prediction is loo_prediction",
            "loo_prediction": loo, "validation_reference": ref,
            "features_half_split_sd": {k: float(feats[sid][f"{k}_half_sd"]) for k in S_FEATURES}})
        meta = json.load(open(C.proc_dir(sid) / "meta.json"))
        excl = json.load(open(C.ROOT / "data" / "exclusions.json"))
        qc_and_confidence(facts, lab, probes[sid], meta["cu_foil_px"] > 0, sid in excl, self_id=sid)
        C.write_json(OUT / f"{sid}.json", facts)
        evidence_png(C.load_channels(sid, ["BSE"])["BSE"], ev, OUT / f"{sid}_evidence.jpg")
    print(f"facts JSON + evidence maps for {len(C.sample_ids())} samples -> {OUT}")


def cmd_predict(args):
    import torch
    from .dino import load_model as load_dino, token_map
    from .physics import constrain_siox
    from .predict import prepare
    from .student import CKPT, build_model, segment, torch_runner
    from .teacher import clean
    from skimage.filters import threshold_multiotsu
    t0 = time.time()
    timings = {}
    x, exclude = prepare(args.bse, args.inlens)
    timings["read_preprocess_s"] = time.time() - t0
    dev = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    seg = build_model(pretrained=False).to(dev)
    seg.load_state_dict(torch.load(CKPT, map_location=dev))
    seg.eval()
    t = time.time()
    probs = constrain_siox(segment(x, torch_runner(seg, dev)), x[0], exclude, class_axis=0)
    lab = clean(probs.argmax(0), exclude)
    timings["segmentation_s"] = time.time() - t
    t = time.time()
    t_low = float(threshold_multiotsu(x[0][~exclude], classes=3)[0])
    f = label_features(lab, x[0], t_low)
    timings["features_s"] = time.time() - t
    t = time.time()
    dmodel = load_dino(dev)
    img = [np.where(exclude, np.median(x[i][~exclude]), x[i]) for i in range(2)]
    tokens = np.concatenate([token_map(dmodel, a, dev) for a in img], -1)
    timings["dino_s"] = time.time() - t
    model = pickle.load(open(C.MODELS / "bid_model.pkl", "rb"))
    t = time.time()
    scores = json.load(open(C.OUT_MET / "bid_scores.json"))
    stem = Path(args.bse).stem
    sample_id = stem[:-4] if stem.upper().endswith("_BSE") else stem           # img_X_BSE -> img_X
    facts, ev = explain(model, sample_id, lab, tokens, f, {
        "inputs": {"BSE": str(args.bse), "Inlens": str(args.inlens), "detectors_used": ["BSE", "Inlens"]},
        "validation_reference": {"LOO_F": scores["LOO_F"]["balanced_accuracy"], "LOGO_F": scores["LOGO_F"]["balanced_accuracy"]},
        "phase_fractions_pct": {c: round(100 * float((lab[lab != C.EXCLUDED] == k).mean()), 2) for k, c in enumerate(C.CLASSES)}})
    from .bid_features import session_probes
    from .preprocess import cu_foil, read_half
    probes = session_probes(sample_id, {"BSE": args.bse, "Inlens": args.inlens}, lab)
    qc_and_confidence(facts, lab, probes, cu_foil(read_half(args.bse)).any(), False)
    timings["classify_explain_s"] = time.time() - t
    timings["total_s"] = time.time() - t0
    facts["timings_s"] = {k: round(v, 2) for k, v in timings.items()}
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    C.write_json(out / "facts.json", facts)
    Image.fromarray(lab).save(out / "labels.png")
    Image.fromarray(C.overlay_rgb(x[0], lab, alpha=0.45)).save(out / "overlay.jpg", quality=88)
    evidence_png(x[0], ev, out / "evidence.jpg")
    print(json.dumps({k: facts[k] for k in ("predicted_batch", "probabilities", "confidence", "novelty", "timings_s")}, indent=1))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["samples", "predict"])
    ap.add_argument("--bse")
    ap.add_argument("--inlens")
    ap.add_argument("--out")
    args = ap.parse_args()
    {"samples": cmd_samples, "predict": cmd_predict}[args.cmd](args)


if __name__ == "__main__":
    main()
