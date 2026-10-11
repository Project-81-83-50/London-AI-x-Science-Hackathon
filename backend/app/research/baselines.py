import hashlib
import json
import statistics
from collections import defaultdict
from pathlib import Path

from .facts import FEATURES, Builder
from .models import Comparison, Document


def reference_records(directory: Path) -> tuple[list[dict], str]:
    records, digest = [], hashlib.sha256()
    for path in sorted(directory.glob("*.json")):
        raw = path.read_bytes()
        digest.update(path.name.encode())
        digest.update(raw)
        record = json.loads(raw)
        if record.get("true_batch") in {"Batch_1", "Batch_2", "Batch_3"}:
            records.append(record)
    return records, digest.hexdigest()


def attach_profiles(document: Document, records: list[dict]) -> None:
    for index, sample in enumerate(document.samples):
        builder = Builder(sample.sample_id, index)
        builder.facts = sample.facts
        groups = defaultdict(dict)
        for record in records:
            sid = str(record.get("sample_id", "")).removeprefix("img_")
            if not sid or sid == sample.sample_id.removeprefix("img_"):
                continue
            material = record.get("material_model", {})
            for feature in FEATURES:
                value = material.get("features_S", {}).get(feature, {}).get("value")
                if isinstance(value, (int, float)) and not isinstance(value, bool):
                    groups[feature, record["true_batch"]][sid] = float(value)
        for feature, (label, unit, _) in FEATURES.items():
            measured = next((f for f in sample.facts if f.pointer.endswith("/features_S/" + feature + "/value")), None)
            if measured is None:
                continue
            medians = {}
            for batch in ("Batch_1", "Batch_2", "Batch_3"):
                values = list(groups[feature, batch].values())
                if len(values) < 2:
                    continue
                quartiles = statistics.quantiles(values, n=4, method="inclusive")
                stats = {
                    "median": statistics.median(values),
                    "q1": quartiles[0],
                    "q3": quartiles[2],
                    "min": min(values),
                    "max": max(values),
                    "locations": len(values),
                }
                for name, value in stats.items():
                    fid = builder.add(
                        f"/reference_profiles/{feature}/{batch}/{name}",
                        f"{label}: {batch} reference {name}",
                        value,
                        "locations" if name == "locations" else unit,
                        role="baseline",
                        method="same named material-segmentation feature in the bundled reference exports; query location excluded",
                        formula="inclusive sample quartiles" if name in {"q1", "q3"} else name,
                    )
                    if name == "median":
                        medians[batch] = fid
            if len(medians) >= 2:
                sample.comparisons.append(
                    Comparison(metric=feature, value_id=measured.id, reference_ids=medians, relation="median")
                )
        if any(c.relation == "median" for c in sample.comparisons):
            sample.warnings.append(
                "Reference profiles are descriptive, not classifier distances or universal batch limits. Exported model/segmentation version compatibility is not independently established; do not use these profiles as decision proof."
            )
