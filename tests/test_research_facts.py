import copy
import json
from pathlib import Path

import pytest

from app.research.facts import decode, lda_contributions, robust_score

ROOT = Path(__file__).resolve().parents[1]


def sample(sample_id="sample_one"):
    return {
        "sample_id": sample_id,
        "decision": {"answer": "Batch_3", "answer_type": "specific", "confidence": "High"},
        "kpi_model": {
            "predicted_batch": "Batch_3",
            "runner_up": "Batch_2",
            "kpis_used": ["etd_dark_solid"],
            "drivers": [
                {
                    "feature": "etd_dark_solid",
                    "name": "ETD-dark solid",
                    "unit": "%",
                    "scale": 100,
                    "value": 0.057,
                    "batch_means": {"Batch_1": 0.025, "Batch_2": 0.03, "Batch_3": 0.046},
                    "support_for_answer": 3.5,
                }
            ],
            "all_kpis": [{"id": "etd_dark_solid", "value": 5.7, "used_by_model": True}],
        },
        "phases": {
            "three_class_pct": {"pore": 14.8, "SiOx": 4.5},
            "sampling_uncertainty_95": {"SiOx": [2.7, 6.3]},
            "reliability": "The graphite/binder split is experimental.",
        },
        "material_model": {
            "predicted_batch": "Batch_3",
            "runner_up": "Batch_1",
            "map_text": {
                "evidence_by_phase": {
                    "positive": {"SiOx": {"share_pct": 10.2, "enrichment_vs_area": 2.25}},
                    "negative": {"SiOx": {"share_pct": 11.0, "enrichment_vs_area": 2.42}},
                    "area_pct": {"SiOx": 4.5},
                    "positive_share_of_total_evidence_pct": 57.8,
                }
            },
        },
    }


def test_decode_current_runs_preserves_inputs():
    files = sorted((ROOT / "sem_pipeline/website/runs").glob("*/output/facts.json"))
    assert len(files) == 9
    for path in files:
        original = path.read_bytes()
        result = decode(original.decode())
        assert result.samples[0].answer == json.loads(original)["decision"]["answer"]
        assert result.samples[0].schema_version == "kpi_material_v1"
        assert path.read_bytes() == original


@pytest.mark.parametrize("shape", ["single", "list", "samples", "results", "images", "mapping"])
def test_shapes_and_no_mutation(shape):
    records = [sample("one"), sample("two")]
    data = (
        records[0]
        if shape == "single"
        else records
        if shape == "list"
        else {str(i): r for i, r in enumerate(records)}
        if shape == "mapping"
        else {shape: records}
    )
    before = copy.deepcopy(data)
    result = decode(data)
    assert [s.sample_id for s in result.samples] == (["one"] if shape == "single" else ["one", "two"])
    assert data == before


def test_units_and_denominators():
    case = decode(sample()).samples[0]
    facts = {f.pointer: f for f in case.facts}
    measured = facts["/kpi_model/drivers/0/value"]
    assert measured.value == pytest.approx(5.7)
    assert measured.raw_value == 0.057 and measured.unit == "%"
    assert case.attribution_pair == ["Batch_3", "Batch_1"]
    pos = facts["/material_model/map_text/evidence_by_phase/positive/SiOx/share_pct"]
    assert pos.denominator == "positive attribution magnitude"
    total = facts["/material_model/map_text/evidence_by_phase/positive_share_of_total_evidence_pct"]
    assert total.value == 57.8 and total.denominator == "positive plus negative attribution magnitude"


def test_missing_predictor_not_presented_as_observed():
    data = sample()
    data["kpi_model"]["unmeasured_kpis"] = ["etd_dark_solid"]
    result = decode(data).samples[0]
    assert not result.comparisons
    assert any("imputed" in w.lower() for w in result.warnings)


def test_bad_scaling_and_duplicate_ids_rejected():
    data = sample()
    data["kpi_model"]["all_kpis"][0]["value"] = 570
    with pytest.raises(ValueError, match="scale"):
        decode(data)
    with pytest.raises(ValueError, match="duplicate"):
        decode([sample(), sample()])


def test_mathematical_helpers():
    assert robust_score(2, 0, 1.349) == 2
    assert robust_score(100, 0, 1.349) == 3
    assert robust_score(-100, 0, 0) == -3
    assert lda_contributions([2], [2], [0], [1]) == [2]
    with pytest.raises(ValueError):
        lda_contributions([2], [2], [0], [0])


def test_refusal_is_not_reclassified():
    data = sample()
    data["decision"] = {
        "answer": "refused",
        "answer_type": "refused",
        "confidence": "Low",
        "reasons": ["Training image"],
    }
    assert decode(data).samples[0].answer == "refused"
