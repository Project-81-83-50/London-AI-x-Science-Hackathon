"""
Scratch: Batch_1 vs Batch_2 from the percentage of each material, using only the value
ranges where the two batches do NOT overlap.

Phase fractions and their sampling SE come from GET4 (one BSE image per location). For each
held-out location the ranges are built from the OTHER locations only. A phase votes for a
batch when the location's value (+- z * SE) lies inside only that batch's range; outside
both ranges it votes for the nearer one. Votes agree -> answer; conflict / no vote -> unsure.
"""

import json
import warnings
from pathlib import Path

import numpy as np

import batch_classifier as B

warnings.filterwarnings("ignore")
HERE = Path(__file__).parent
PHASES = ["pore", "graphite", "bright phase"]


def load():
    table = []
    for p in sorted((HERE / "out" / "get4").glob("Batch_*/*_uncertainty.json")):
        if p.name.startswith("batch"):
            continue
        r = json.loads(p.read_text())
        loc, _ = B.parse_name(r["image"])
        table.append({"batch": p.parent.name, "location": loc,
                      **{f"phi_{k}": r["phases"][k]["phi"] for k in PHASES},
                      **{f"se_{k}": r["phases"][k]["se_image"] for k in PHASES}})
    return table


def vote(v, se, z, r1, r2):
    lo, hi = v - z * se, v + z * se
    in1 = hi >= r1[0] and lo <= r1[1]
    in2 = hi >= r2[0] and lo <= r2[1]
    if in1 and not in2:
        return "Batch_1"
    if in2 and not in1:
        return "Batch_2"
    if not in1 and not in2:
        d1 = min(abs(v - r1[0]), abs(v - r1[1]))
        d2 = min(abs(v - r2[0]), abs(v - r2[1]))
        return "Batch_1" if d1 < d2 else "Batch_2"
    return None


def range_rule(table, i, z, phases, train):
    r = {b: {k: (min(t[f"phi_{k}"] for t in train if t["batch"] == b), max(t[f"phi_{k}"] for t in train if t["batch"] == b))
             for k in phases} for b in ("Batch_1", "Batch_2")}
    t = table[i]
    votes = {k: vote(t[f"phi_{k}"], t[f"se_{k}"], z, r["Batch_1"][k], r["Batch_2"][k]) for k in phases}
    cast = {v for v in votes.values() if v}
    return (cast.pop() if len(cast) == 1 else None), votes


def main():
    table = load()
    print(f"{len(table)} locations measured by GET4")
    b12 = [i for i, t in enumerate(table) if t["batch"] in ("Batch_1", "Batch_2")]
    print("\nper location (% +- 2 SE):")
    for i in b12:
        t = table[i]
        print(f"  {t['batch']} {t['location']}  " + "  ".join(
            f"{k[:6]} {100 * t[f'phi_{k}']:5.1f}+-{200 * t[f'se_{k}']:.1f}" for k in PHASES))

    print("\nBatch_1 vs Batch_2 range rule, each location held out (ranges from the other 13):")
    for phases in (PHASES, ["pore", "bright phase"]):
        for z in (0, 1, 2):
            answered, right, detail = 0, 0, []
            for i in b12:
                train = [table[j] for j in b12 if j != i]
                pred, _ = range_rule(table, i, z, phases, train)
                if pred:
                    answered += 1
                    right += pred == table[i]["batch"]
                    detail.append(f"{table[i]['location'][:4]}{'' if pred == table[i]['batch'] else '(WRONG)'}")
            tag = "+".join(p.split()[0] for p in phases)
            print(f"  {tag:22s} margin {z} SE: answers {answered:2d}/14, correct {right}/{answered} "
                  f"({100 * right / max(answered, 1):.0f}%)   answered: {' '.join(detail)}")
    (HERE / "out" / "classifier" / "get4_phases.json").write_text(json.dumps(table, indent=1))


if __name__ == "__main__":
    main()
