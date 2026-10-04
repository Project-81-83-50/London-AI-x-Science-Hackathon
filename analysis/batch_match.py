"""
Adapter for the teammate's batch-match classifier ("batch match - just code/batch_classifier.py",
which uses the GET4 version in the same folder). His code is used unchanged; this module only

- points it at this project's data: references in data/raw/batch_N (reported as Batch_N, the names
  his material range rule expects), the unknown set in data/raw/unknown;
- keeps its caches and trained model in data/processed/batch_match/ instead of his out/ folder;
- returns predictions as JSON (his predict prints text), following his predict step by step:
  training-image guard, known-location matcher, imaging fingerprint + texture models, GET4 material
  range rule, "unsure" below the 90%-accuracy threshold; then one answer per location.

    python -m analysis.batch_match train      # one-off: fingerprints, textures, GET4 materials (~40 min)
    python -m analysis.batch_match evaluate   # his leave-one-location-out accuracy, default + forced mode
                                              #   -> data/processed/batch_match/evaluation_report.json
    python -m analysis.batch_match predict    # classify data/raw/unknown -> data/processed/batch_match/unknown.json
"""

import argparse
import importlib
import json
import pickle
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
CODE_DIR = ROOT / "batch match - just code"
RAW = ROOT / "data" / "raw"
OUT = ROOT / "data" / "processed" / "batch_match"
RESULT = OUT / "unknown.json"
REPORT = OUT / "evaluation_report.json"


def classifier():
    """Import his batch_classifier (and its GET4) from his folder, redirected to our output folder."""
    if str(CODE_DIR) not in sys.path:
        sys.path.insert(0, str(CODE_DIR))
    bc = importlib.import_module("batch_classifier")
    bc.ROOT, bc.OUT = RAW, OUT  # OUT is read at call time by train / evaluate / predict
    return bc


def reference_rows(bc):
    rows = []
    for folder in sorted(RAW.glob("batch_[0-9]*")):
        for path in sorted(folder.glob("*.tif")):
            location, view = bc.parse_name(path)
            rows.append({"path": path, "batch": "Batch_" + folder.name.split("_", 1)[1],
                         "location": location, "view": view})
    return rows


def build_data(bc, rows):
    OUT.mkdir(parents=True, exist_ok=True)
    features = bc.build_features(rows, cache=OUT / "fingerprints.json")
    texture = bc.build_texture(rows, cache=OUT / "texture_features.npz")
    materials = bc.build_materials(rows, cache=OUT / "material_percentages.json")
    return bc.Data(rows, features, *texture, materials)


def _probabilities(p, batches):
    return {str(b): round(float(v), 3) for b, v in zip(batches, p)}


def predict_unknown(forced=False):
    """His predict() for every image in data/raw/unknown, collected as JSON."""
    bc = classifier()
    with open(OUT / "batch_model.pkl", "rb") as fh:
        bundle = pickle.load(fh)
    bc.FEATURES = bundle["features"]
    batches = np.array(bundle["batches"], dtype=object)
    cal, ranges, training = bundle["calibration"], bundle["ranges"], bundle["training_images"]
    refs = [dict(r, edges=r["edges"].astype(np.float32)) for r in bundle["references"]]

    images, groups = [], {}
    for path in sorted((RAW / "unknown").glob("*.tif")):
        name = path.name
        location, view = bc.parse_name(path)
        record = {"image": name, "location_id": location, "view": view}
        refuse = "part of the training data" if name in training else None
        score = 0.0
        if not refuse:
            u8 = bc.load_u8(path)
            score, mbatch, mloc = bc.find_known_location(u8, refs)
            if score >= bc.SELF_MATCH:
                refuse = f"identical to a training image of location {mloc}"
        if refuse:
            images.append({**record, "answer": None, "how": "refused",
                           "detail": f"{refuse} - not predicted; testing a model on its own training images "
                                     "gives a meaningless result"})
            continue
        g = groups.setdefault(location, {"ps": [], "l1": 0.0, "l2": 0.0, "vote": None, "known": None,
                                         "m": None, "n": 0, "views": []})
        g["n"] += 1
        g["views"].append(name)
        if score >= bc.MATCH_THRESHOLD:
            g["known"] = mbatch
            images.append({**record, "answer": mbatch, "how": "known location",
                           "detail": f"known location {mloc} (match {score:.0f} SD), certain"})
            continue
        x = bc.vector(bc.fingerprint(u8))
        vote, m = None, None
        if view == "BSE":
            m = bc.material_percentages(path)
            vote = bc.range_vote(m, ranges)
            g["vote"], g["m"] = vote, m
        if forced:
            l1, l2 = bc.two_step_scores(bundle["two_step"], view, x)
            g["l1"], g["l2"] = g["l1"] + l1, g["l2"] + l2
            ans, how = bc.forced_answer(l1, l2, vote)
            images.append({**record, "answer": ans, "how": f"forced ({how})", "detail": f"forced answer ({how})"})
            continue
        (fp, means), tx = bundle["models"][view]
        p = bc.combine(bc.log_proba(fp, means, x[None], batches)[0],
                       bc.tile_log_proba(tx, bc.texture_tiles(u8), batches), cal)
        ans, how = bc.decide(p, cal["threshold_image"], vote, batches)
        images.append({**record, "answer": ans, "how": how, "probabilities": _probabilities(p, batches),
                       "material_percentages": {k: [round(100 * v[0], 2), round(100 * v[1], 2)] for k, v in m.items()}
                       if m else None,
                       "detail": bc.describe(name, view, ans, how, p, batches, cal["threshold_image"], m, ranges)
                       .split(": ", 1)[-1]})
        g["ps"].append(p)

    locations = []
    for location, g in groups.items():
        entry = {"location_id": location, "views": g["views"]}
        if g["known"]:
            entry.update(answer=g["known"], how="known location", detail="known location, certain")
        elif forced:
            ans, how = bc.forced_answer(g["l1"], g["l2"], g["vote"])
            entry.update(answer=ans, how=f"forced ({how})", detail=f"forced answer ({how})")
        elif g["ps"]:
            p = bc.location_proba(np.array(g["ps"]))
            threshold = cal["threshold_location"] if g["n"] > 1 else cal["threshold_image"]
            ans, how = bc.decide(p, threshold, g["vote"], batches)
            entry.update(answer=ans, how=how, probabilities=_probabilities(p, batches),
                         detail=bc.describe(f"location {location}", f"{len(g['ps'])} views", ans, how, p, batches,
                                            threshold, g["m"], ranges).split(": ", 1)[-1])
        locations.append(entry)
    for image in images:  # locations whose only images were refused still appear, with no answer
        if image["how"] == "refused" and image["location_id"] not in groups:
            locations.append({"location_id": image["location_id"], "views": [image["image"]], "answer": None,
                              "how": "refused", "detail": image["detail"]})
            groups[image["location_id"]] = None

    result = {
        "generated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "method": "Teammate's batch-match classifier (batch match - just code/batch_classifier.py): known-location "
                  "matcher, imaging fingerprint + texture models, GET4 material range rule; answers 'unsure' below "
                  "the confidence at which held-out answers were 90% right.",
        "mode": "forced" if forced else "default",
        "thresholds": {"image": float(cal["threshold_image"]), "location": float(cal["threshold_location"])},
        "locations": sorted(locations, key=lambda l: l["location_id"]),
        "images": images,
    }
    OUT.mkdir(parents=True, exist_ok=True)
    RESULT.write_text(json.dumps(result, indent=1), encoding="utf-8")
    return result


def _wilson(k, n, z=1.96):
    """95% Wilson interval for k right out of n."""
    if n == 0:
        return None
    p = k / n
    centre = (p + z * z / (2 * n)) / (1 + z * z / n)
    half = z * np.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return [round(float(centre - half), 3), round(float(centre + half), 3)]


def _stats(records, batches):
    """Coverage, accuracy when answering and per-batch / per-rule counts from his held-out records."""
    rows = [{"item": r["item"], "truth": str(r["truth"]), "answer": str(r["answer"]), "how": r["how"],
             "leaning": str(r["leaning"]),
             "confidence": round(float(r["confidence"]), 3) if np.isfinite(r["confidence"]) else None,
             "correct": None if r["answer"] == "unsure" else bool(r["answer"] == r["truth"])}
            for r in records]
    answered = [r for r in rows if r["correct"] is not None]
    right = sum(r["correct"] for r in answered)
    by_how = {}
    for r in answered:
        h = by_how.setdefault(r["how"], {"answered": 0, "right": 0})
        h["answered"] += 1
        h["right"] += r["correct"]
    per_batch = {}
    for b in map(str, batches):
        mine = [r for r in rows if r["truth"] == b]
        per_batch[b] = {"n": len(mine), "right": sum(r["correct"] is True for r in mine),
                        "wrong": sum(r["correct"] is False for r in mine),
                        "unsure": sum(r["correct"] is None for r in mine)}
    return {
        "n": len(rows), "answered": len(answered), "right": right,
        "coverage": round(len(answered) / len(rows), 3) if rows else None,
        "accuracy_when_answering": round(right / len(answered), 3) if answered else None,
        "ci95": _wilson(right, len(answered)),
        "accuracy_if_always_answering": round(float(np.mean([r["leaning"] == r["truth"] for r in rows])), 3)
        if rows else None,
        "per_batch": per_batch, "by_rule": by_how, "records": rows,
    }


def evaluate_both(bc, data):
    """Run his evaluate() and evaluate_forced() and keep every held-out record (his summary JSON keeps
    only counts), then write one report with coverage, accuracy and 95% intervals."""
    captured, original = {}, bc.summarise

    def capture(rec, batches, title):
        captured[title] = list(rec)
        return original(rec, batches, title)

    bc.summarise = capture
    try:
        modes = {}
        for mode, run in (("default", bc.evaluate), ("forced", bc.evaluate_forced)):
            captured.clear()
            run(data)
            images, locations = (captured[k] for k in sorted(captured, key=lambda k: not k.startswith("SINGLE")))
            modes[mode] = {"single_images": _stats(images, data.batches), "locations": _stats(locations, data.batches)}
    finally:
        bc.summarise = original
    report = {
        "generated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "protocol": "Leave-one-location-out on the 31 reference locations, nested: for each held-out location the "
                    "models, calibration and answer thresholds are refitted without it. Known-location matches are "
                    "not part of this test (a held-out location is never in the reference set); they are exact "
                    "field matches and are treated as certain.",
        "target_accuracy": float(bc.TARGET_ACCURACY),
        "modes": modes,
    }
    REPORT.write_text(json.dumps(report, indent=1), encoding="utf-8")
    for mode, m in modes.items():
        loc = m["locations"]
        print(f"{mode}: answered {loc['answered']}/{loc['n']} locations, right {loc['right']} "
              f"({loc['accuracy_when_answering']}, 95% CI {loc['ci95']})")
    print(f"wrote {REPORT}")
    return report


def main():
    ap = argparse.ArgumentParser(description="Teammate's batch-match classifier on this project's data.")
    ap.add_argument("command", choices=["train", "evaluate", "predict"])
    ap.add_argument("--forced", action="store_true", help="predict: always answer (his two-step forced mode)")
    args = ap.parse_args()
    if args.command == "predict":
        result = predict_unknown(args.forced)
        for loc in result["locations"]:
            print(f"{loc['location_id']}: {loc['answer'] or '-'}  ({loc['how']}) {loc['detail']}")
        print(f"wrote {RESULT}")
        return
    bc = classifier()
    rows = reference_rows(bc)
    print(f"{len(rows)} reference images, {len({r['location'] for r in rows})} locations", flush=True)
    data = build_data(bc, rows)
    if args.command == "train":
        bc.train(data)
    else:
        evaluate_both(bc, data)


if __name__ == "__main__":
    main()
