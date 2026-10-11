import hashlib
import json
import math
from collections.abc import Iterator
from typing import Any

from .models import Comparison, Document, Fact, Sample

REGISTRY_VERSION = "sem-facts-2026-10-v1"
CONCEPTS = {
    "detector_contrast": "SEM secondary electron backscattered electron contrast graphite silicon oxide electrode topography charging detector geometry",
    "porosity": "graphite silicon oxide anode SEM cross section porosity area fraction stereology sampling uncertainty",
    "particles": "silicon oxide graphite anode particle size distribution equivalent diameter microscopy interpretation",
    "carbon_binder": "graphite silicon oxide anode carbon binder domain SEM segmentation reliability",
    "attribution": "linear classifier signed feature attribution evidence maps limitations causal interpretation",
    "transport": "battery electrode porosity Bruggeman tortuosity assumptions three dimensional microstructure",
    "anisotropy": "battery electrode pore anisotropy chord length two dimensional microscopy",
}
FEATURES = {
    "siox_frac": ("SiOx segmented area", "%", "particles"),
    "siox_ecd_aw": ("SiOx area-weighted equivalent diameter", "µm", "particles"),
    "pore_all_frac": ("Segmented pore area", "%", "porosity"),
    "pore_open_excess": ("All-pore minus deep-pore area", "pp", "porosity"),
    "pore_chord_aniso": ("Horizontal/vertical pore chord ratio", "ratio", "anisotropy"),
}


def numeric(value: Any, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (float, int)) or not math.isfinite(value):
        raise ValueError(f"{field}: expected a finite number")
    return float(value)


def robust_score(value: float, median: float, iqr: float) -> float:
    scale = iqr / 1.349 if iqr else 1.0
    return max(-3.0, min(3.0, (value - median) / scale))


def lda_contributions(z: list[float], winner: list[float], runner: list[float], variance: list[float]) -> list[float]:
    if not (len(z) == len(winner) == len(runner) == len(variance)) or any(v <= 0 for v in variance):
        raise ValueError("Invalid diagonal-LDA parameter dimensions or variances")
    return [0.5 * ((x - r) ** 2 - (x - w) ** 2) / v for x, w, r, v in zip(z, winner, runner, variance, strict=True)]


def leaves(value: Any, path: str = "") -> Iterator[tuple[str, Any]]:
    if isinstance(value, dict):
        for key, child in value.items():
            yield from leaves(child, path + "/" + str(key).replace("~", "~0").replace("/", "~1"))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from leaves(child, path + f"/{index}")
    else:
        yield path, value


def _pairs(pairs: list[tuple[str, Any]]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _records(data: Any) -> list[dict]:
    if isinstance(data, dict) and "sample_id" in data:
        return [data]
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        containers = [key for key in ("samples", "results", "images") if key in data]
        if len(containers) == 1 and isinstance(data[containers[0]], list):
            return data[containers[0]]
        if not containers and data and all(isinstance(v, dict) and "sample_id" in v for v in data.values()):
            return list(data.values())
    raise ValueError("Expected one sample or an unambiguous collection of sample records")


def role_for(path: str) -> str:
    if any(key in path for key in ("summary_sentences", "/sentences/", "/field_guide")):
        return "generated_summary_not_evidence"
    if path.startswith("/decision/"):
        return "authoritative_decision"
    if any(key in path for key in ("/acquisition/", "/session_hint/", "/qc/", "/novelty/", "/known_location_check/")):
        return "quality_or_route"
    if any(key in path for key in ("/timings_s/", "validation", "inner_scores", "separation_rank")):
        return "diagnostic"
    if "map_text" in path or "/evidence/" in path:
        return "attribution_or_spatial_description"
    if path.startswith(
        (
            "/kpi_model/",
            "/material_model/",
            "/features_S/",
            "/phases/",
            "/phase_fractions_pct/",
            "/material_range_rule/",
            "/batch_1_vs_batch_2/",
        )
    ):
        return "measurement_or_reference_statistic"
    return "provenance_or_unknown_not_a_reason"


class Builder:
    def __init__(self, sample_id: str, index: int):
        self.sample_id = sample_id
        self.index = index
        self.facts: list[Fact] = []
        self.warnings: list[str] = []
        self.concepts: set[str] = set()
        self.comparisons: list[Comparison] = []

    def add(
        self, pointer: str, label: str, value: Any, unit: str = "", role: str = "observation", **metadata: Any
    ) -> str:
        raw = metadata.pop("raw_value", value)
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            value = numeric(value, pointer)
            display = f"{value:.4g}" + ("%" if unit == "%" else f" {unit}" if unit and unit != "ratio" else "")
        else:
            display = str(value)
        fid = f"F{self.index}_{len(self.facts)}"
        self.facts.append(
            Fact(
                id=fid,
                sample_id=self.sample_id,
                pointer=pointer,
                label=label,
                value=value,
                raw_value=raw,
                display=display,
                unit=unit,
                role=role,
                **metadata,
            )
        )
        return fid


def _kpis(record: dict, b: Builder) -> None:
    model = record.get("kpi_model", {})
    drivers = model.get("drivers", [])
    selected = model.get("kpis_used", [d["feature"] for d in drivers])
    if not isinstance(selected, list) or any(not isinstance(k, str) for k in selected):
        raise ValueError("Invalid kpis_used")
    keys = [d["feature"] for d in drivers]
    if len(set(keys)) != len(keys) or set(selected) - set(keys):
        raise ValueError("Selected KPI driver records are missing or duplicated")
    rows = {row["id"]: row for row in model.get("all_kpis", [])}
    if len(rows) != len(model.get("all_kpis", [])):
        raise ValueError("duplicate KPI IDs")
    missing = set(model.get("unmeasured_kpis", []))
    for i, driver in enumerate(drivers):
        key = driver["feature"]
        if key not in selected:
            continue
        row = rows.get(key)
        if row is not None and row.get("used_by_model") is False:
            raise ValueError(f"Selected KPI {key} is marked unused")
        if key in missing or row is not None and row.get("value") is None:
            b.warnings.append(f"KPI {key} is unmeasured/imputed, not an observed sample property.")
            continue
        scale = numeric(driver.get("scale", 1), "KPI scale")
        if scale <= 0:
            raise ValueError("KPI scale must be positive")
        value = numeric(driver["value"], key) * scale
        if row and abs(numeric(row["value"], key) - value) > 0.0011:
            raise ValueError(f"KPI {key}: raw and display-unit scale disagree")
        unit = driver.get("unit", "")
        path = f"/kpi_model/drivers/{i}"
        method = model.get("measurement", {}).get("segmentation", "KPI intensity segmentation")
        quality = any(
            term in key.lower()
            for term in ("noise", "sharpness", "banding", "height", "brightness", "session", "file_size")
        )
        if quality:
            b.warnings.append(
                f"Selected predictor {key} is an acquisition proxy, not an intrinsic material characteristic."
            )
        fid = b.add(
            path + "/value",
            driver.get("name", key),
            value,
            unit,
            raw_value=driver["value"],
            description=driver.get("description", ""),
            role="quality" if quality else "observation",
            method=method,
            used_by_model=True,
            denominator="valid image area" if unit == "%" else "",
        )
        references = {}
        for batch, mean in driver.get("batch_means", {}).items():
            mean_value = numeric(mean, key) * scale
            mid = b.add(
                path + "/batch_means/" + batch,
                f"{key}: {batch} mean",
                mean_value,
                unit,
                role="baseline",
                raw_value=mean,
                method=method,
                used_by_model=True,
            )
            references[batch] = mid
            b.add(
                f"/derived/{key}/distance/{batch}",
                f"Absolute distance of {key} to {batch} mean",
                abs(value - mean_value),
                "pp" if unit == "%" else unit,
                role="calculation",
                method=method,
                formula="abs(sample - reference_mean)",
                inputs=[fid, mid],
            )
        if len(references) >= 2:
            b.comparisons.append(Comparison(metric=key, value_id=fid, reference_ids=references, used_by_model=True))
        if "support_for_answer" in driver:
            b.add(
                path + "/support_for_answer",
                f"{key}: reported KPI log-score margin contribution",
                driver["support_for_answer"],
                "score",
                role="calculation",
                used_by_model=True,
                method="reported diagonal-LDA contribution; not independently recomputed without fitted parameters",
                formula="0.5 * ((z - runner_mean)^2 - (z - winner_mean)^2) / shared_variance",
                contrast=[model.get("predicted_batch", ""), model.get("runner_up", "")],
                inputs=[fid],
            )
        b.concepts.add(
            "detector_contrast"
            if "etd" in key or "inlens" in key
            else "porosity"
            if "pore" in key or "porosity" in key
            else "particles"
        )


def _material(record: dict, b: Builder) -> list[str]:
    material = record.get("material_model", record)
    prefix = "/material_model" if "material_model" in record else ""
    pair = [material.get("predicted_batch"), material.get("runner_up")]
    pair = pair if all(isinstance(x, str) and x for x in pair) and pair[0] != pair[1] else []
    for key, item in material.get("features_S", {}).items():
        if key not in FEATURES or item.get("value") is None:
            continue
        label, unit, concept = FEATURES[key]
        base = prefix + "/features_S/" + key
        value_id = b.add(
            base + "/value", label, item["value"], unit, method="material segmentation", used_by_model=True
        )
        b.concepts.add(concept)
        if "robust_z" in item:
            b.add(
                base + "/robust_z",
                label + ": pooled-training relative score",
                item["robust_z"],
                "score",
                role="calculation",
                inputs=[value_id],
                method="material feature normalization, not per-batch SD",
                formula="clip((x - training_median)/(training_IQR/1.349), -3, 3); zero scale becomes 1",
            )
        if "push_toward_winner_vs_runner_up" in item:
            b.add(
                base + "/push_toward_winner_vs_runner_up",
                label + ": reported material-model score contrast",
                item["push_toward_winner_vs_runner_up"],
                "score",
                role="calculation",
                contrast=pair,
                inputs=[value_id],
                formula="winning S coefficient times z minus runner-up coefficient times z",
            )
    evidence = material.get("map_text", {}).get("evidence_by_phase", {})
    if evidence and not pair:
        b.warnings.append(
            "Material attribution has no identifiable winner/runner-up pair; it cannot justify a class contrast."
        )
    if evidence and pair:
        b.concepts.add("attribution")
        root = prefix + "/map_text/evidence_by_phase/"
        for sign in ("positive", "negative"):
            for phase, item in evidence.get(sign, {}).items():
                for metric in ("share_pct", "enrichment_vs_area"):
                    if item.get(metric) is None:
                        continue
                    value = numeric(item[metric], "DINO attribution")
                    if value < 0 or metric == "share_pct" and value > 100:
                        raise ValueError("Invalid DINO attribution range")
                    b.add(
                        root + f"{sign}/{phase}/{metric}",
                        f"{phase}: {sign} {metric}",
                        value,
                        "%" if metric == "share_pct" else "ratio",
                        role="attribution",
                        contrast=pair,
                        denominator=f"{sign} attribution magnitude"
                        if metric == "share_pct"
                        else f"{sign} attribution share / phase area share",
                        method="DINO signed contribution map, not chemical identity or classification probability",
                    )
        for phase, value in evidence.get("area_pct", {}).items():
            b.add(
                root + "area_pct/" + phase,
                phase + ": token-weighted area",
                value,
                "%",
                denominator="valid token-weighted area",
                method="map phase weighting",
            )
        if evidence.get("positive_share_of_total_evidence_pct") is not None:
            value = numeric(evidence["positive_share_of_total_evidence_pct"], "total signed evidence")
            if not 0 <= value <= 100:
                raise ValueError("Invalid total signed evidence percentage")
            fid = b.add(
                root + "positive_share_of_total_evidence_pct",
                "Positive share of total signed evidence",
                value,
                "%",
                role="attribution",
                contrast=pair,
                denominator="positive plus negative attribution magnitude",
                formula="100 * positive_magnitude / (positive_magnitude + negative_magnitude)",
            )
            b.add(
                "/derived/negative_evidence_pct",
                "Negative share of total signed evidence",
                100 - value,
                "%",
                role="attribution",
                contrast=pair,
                denominator="positive plus negative attribution magnitude",
                formula="100 - positive share",
                inputs=[fid],
            )
    for section in ("spatial", "objects", "evidence_regions"):
        for pointer, value in leaves(material.get("map_text", {}).get(section, {})):
            if not isinstance(value, (int, float)) or isinstance(value, bool):
                continue
            unit = "µm²" if "_um2" in pointer else "µm" if "_um" in pointer else "%" if "_pct" in pointer else ""
            b.add(
                prefix + "/map_text/" + section + pointer,
                f"{section}: {pointer}",
                value,
                unit,
                role="attribution" if section == "evidence_regions" else "observation",
                contrast=pair,
                method="reported map descriptor, not direct visual inspection",
            )
    return pair


def _composition(record: dict, b: Builder) -> None:
    phases = record.get("phases", {})
    composition_path = "/phases/three_class_pct/" if "three_class_pct" in phases else "/phase_fractions_pct/"
    for phase, value in phases.get("three_class_pct", record.get("phase_fractions_pct", {})).items():
        b.add(
            composition_path + phase,
            phase + ": segmented area",
            value,
            "%",
            denominator="valid 2-D image area",
            method="material segmentation",
        )
    if phases.get("reliability"):
        b.warnings.append(phases["reliability"])
    for phase, interval in phases.get("sampling_uncertainty_95", {}).items():
        if len(interval) != 2 or interval[0] > interval[1]:
            raise ValueError("Invalid sampling interval")
        for j, value in enumerate(interval):
            b.add(
                f"/phases/sampling_uncertainty_95/{phase}/{j}",
                f"{phase}: sampling interval endpoint",
                value,
                "%",
                uncertainty="sample sampling interval, not segmentation accuracy or classifier confidence",
            )
    for i, row in enumerate(record.get("material_range_rule", {}).get("phases", [])):
        for batch, interval in row.get("ranges", {}).items():
            for j, value in enumerate(interval):
                b.add(
                    f"/material_range_rule/phases/{i}/ranges/{batch}/{j}",
                    f"{row['phase']}: {batch} range endpoint",
                    value,
                    "%",
                    role="baseline",
                    method="material range rule",
                )
        if len(row.get("fits_ranges_of", [])) > 1:
            b.warnings.append(
                f"The {row['phase']} sampling interval overlaps multiple batch ranges; overlap is not batch equivalence."
            )
    for i, row in enumerate(record.get("batch_1_vs_batch_2", {}).get("differences", [])):
        role = "quality" if row.get("may_reflect_imaging") else "baseline"
        reference_ids = {}
        for key in ("Batch_1_mean", "Batch_2_mean", "Batch_2_minus_Batch_1", "this_location"):
            if row.get(key) is not None:
                unit = "pp" if key == "Batch_2_minus_Batch_1" and row.get("unit") == "%" else row.get("unit", "")
                fid = b.add(
                    f"/batch_1_vs_batch_2/differences/{i}/{key}",
                    f"{row['measure']}: {key}",
                    row[key],
                    unit,
                    role=role,
                    method=row.get("source", ""),
                )
                if key in {"Batch_1_mean", "Batch_2_mean"}:
                    reference_ids[key.removesuffix("_mean")] = fid
        phase = {"total porosity (U-Net segmentation)": "pore", "SiOx area": "SiOx"}.get(row["measure"])
        measured = next(
            (fact for fact in b.facts if phase and fact.pointer == "/phases/three_class_pct/" + phase), None
        )
        if role != "quality" and measured and len(reference_ids) == 2:
            b.comparisons.append(Comparison(metric=row["measure"], value_id=measured.id, reference_ids=reference_ids))
        for j, value in enumerate(row.get("ci95", [])):
            b.add(
                f"/batch_1_vs_batch_2/differences/{i}/ci95/{j}",
                row["measure"] + ": mean-difference interval endpoint",
                value,
                "pp" if row.get("unit") == "%" else row.get("unit", ""),
                role=role,
                method=row.get("source", ""),
                uncertainty="interval for B2-minus-B1 mean DIFFERENCE, not a sample interval",
            )


def decode(document: str | dict | list) -> Document:
    text = document if isinstance(document, str) else json.dumps(document, ensure_ascii=False, allow_nan=False)
    data = json.loads(text, object_pairs_hook=_pairs)
    json.dumps(data, allow_nan=False)
    records, seen, samples, inventory = _records(data), set(), [], {}
    if not records:
        raise ValueError("No sample records")
    for index, record in enumerate(records):
        sid = record.get("sample_id") if isinstance(record, dict) else None
        if (
            not isinstance(sid, str)
            or not sid.strip()
            or sid != sid.strip()
            or len(sid) > 200
            or any(ord(c) < 32 for c in sid)
        ):
            raise ValueError("Invalid sample_id")
        if sid in seen:
            raise ValueError("duplicate sample_id")
        seen.add(sid)
        decision = record.get("decision")
        if decision is not None and not isinstance(decision, dict):
            raise ValueError("decision must be an object")
        decision = decision or {}
        answer = decision.get("answer", record.get("predicted_batch"))
        if not isinstance(answer, str) or not answer.strip():
            raise ValueError(f"{sid}: missing authoritative decision")
        confidence = decision.get("confidence", record.get("confidence"))
        confidence = confidence.get("tier") if isinstance(confidence, dict) else confidence
        inventory.update({sid + ":" + pointer: role_for(pointer) for pointer, _ in leaves(record)})
        b = Builder(sid, index)
        _kpis(record, b)
        pair = _material(record, b)
        _composition(record, b)
        b.warnings.extend(
            str(x) for x in decision.get("reasons", []) if decision.get("answer_type") in {"refused", "known_location"}
        )
        if decision.get("statistics_note"):
            b.warnings.append(decision["statistics_note"])
        if record.get("acquisition", {}).get("warning"):
            b.warnings.append(record["acquisition"]["warning"])
        weights, kpi, material = (
            decision.get("weights", {}),
            decision.get("kpi_probabilities"),
            decision.get("material_model_calibrated"),
        )
        if weights and isinstance(kpi, dict) and isinstance(material, dict):
            for batch, actual in decision.get("probabilities", {}).items():
                if batch in kpi and batch in material:
                    expected = (
                        weights.get("kpi_model", 0) * kpi[batch] + weights.get("v3_material_model", 0) * material[batch]
                    )
                    if abs(expected - actual) > 0.001:
                        b.warnings.append(f"Reported fusion for {batch} does not match its supplied component values.")
                    b.add(
                        "/derived/fusion/" + batch,
                        "Reconstructed reported fusion: " + batch,
                        expected,
                        "probability",
                        role="diagnostic",
                        formula="kpi_weight * kpi_probability + material_weight * calibrated_material_probability",
                    )
        elif "kpi_model" in record and not material:
            b.warnings.append(
                "Calibrated material probabilities are absent; do not assume the stated weighted fusion was applied."
            )
        samples.append(
            Sample(
                sample_id=sid,
                answer=answer,
                answer_type=decision.get("answer_type", "specific"),
                confidence=confidence,
                schema_version="kpi_material_v1"
                if "kpi_model" in record
                else "material_v3"
                if "material_model" in record
                else "legacy",
                facts=b.facts,
                comparisons=b.comparisons,
                warnings=list(dict.fromkeys(b.warnings)),
                concepts=sorted(b.concepts),
                attribution_pair=pair,
            )
        )
    return Document(
        input_hash=hashlib.sha256(text.encode()).hexdigest(),
        registry_version=REGISTRY_VERSION,
        samples=samples,
        inventory=inventory,
    )
