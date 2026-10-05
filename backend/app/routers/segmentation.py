"""SEM pipeline (v3) results: four-phase segmentation and batch decisions (frontend: General and Detailed reports).

The segmentation splits each location into pore, graphite, SiOx and binder (CBD). v3's batch decision combines an
imaging fingerprint model and a material model by agreement and may answer a single batch, "Batch_1 or Batch_2" or
"unsure". All numbers are the committed sem_pipeline results; for the 31 reference locations the decision uses
leave-one-location-out probabilities. Overlays come from sem_pipeline/outputs/segmentation, which
run_cpu_pipeline.py rebuilds from data/raw.
"""

import csv
import json
import logging
from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from ..batches import read_kpi_json
from ..paths import (
    LOCATION_ID_PATTERN,
    SEM_BATCH_ID_FACTS_DIR,
    SEM_METRICS_DIR,
    SEM_SEGMENTATION_DIR,
    UNKNOWN_BATCH,
    V3_REPORT_DIR,
    V3_UNKNOWN_DIR,
)

router = APIRouter()
logger = logging.getLogger(__name__)
SEGMENTATION_PHASES = ["pore", "graphite", "SiOx", "CBD"]
PHASE_COLORS = {"pore": "#1e6eff", "graphite": "#aa6eff", "SiOx": "#ff9600", "CBD": "#28d278"}
REFERENCE_BATCHES = ["Batch_1", "Batch_2", "Batch_3"]
METRICS_DIR = SEM_METRICS_DIR
SEGMENTATION_DIR = SEM_SEGMENTATION_DIR
BATCH_ID_FACTS_DIR = SEM_BATCH_ID_FACTS_DIR


def read_metrics_csv(name: str) -> list[dict[str, str]]:
    """Rows of one sem_pipeline metrics CSV, or HTTP 404 when it has not been generated."""
    path = METRICS_DIR / name
    if not path.is_file():
        raise HTTPException(404, f"SEM pipeline result {name} not found")
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def to_float(value: Any) -> float | None:
    """Parse a CSV cell as a float; blanks and non-numeric cells become None."""
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _sample_record(
    row: dict[str, str],
    batch: str,
    teacher: dict[str, dict[str, str]],
    siox: dict[str, dict[str, str]],
) -> dict[str, Any]:
    """One reference location: phase fractions, SiOx particle statistics and v3's batch decision."""
    sid = row["sample_id"]
    facts_path = BATCH_ID_FACTS_DIR / f"{sid}.json"
    facts = json.loads(facts_path.read_text(encoding="utf-8")) if facts_path.is_file() else {}
    loo = facts.get("loo_prediction", {})
    loo_p = loo.get("p_F") or []
    decision = facts.get("decision") or {}
    answer, answer_type = decision.get("answer"), decision.get("answer_type")
    prediction_set = decision.get("prediction_set") or []
    particles = siox.get(sid, {})
    return {
        "sample_id": sid,
        "session": row["height_group"],
        "phases_pct": {k: to_float(row[f"{k}_pct"]) for k in SEGMENTATION_PHASES},
        "pore_deep_pct": to_float(row["pore_deep_pct"]),
        "pore_open_pct": to_float(row["pore_open_pct"]),
        "excluded_pct": to_float(row["excluded_pct"]),
        "teacher_cpu_phases_pct": {k: to_float(teacher[sid].get(f"{k}_pct")) for k in SEGMENTATION_PHASES}
        if sid in teacher
        else None,
        "siox_particles": {
            "count": to_float(particles.get("n_particles")),
            "per_1000um2": to_float(particles.get("per_1000um2")),
            "median_diameter_um": to_float(particles.get("eq_diam_median_um")),
            "p90_diameter_um": to_float(particles.get("eq_diam_p90_um")),
        },
        # v3's actual answer for this location (leave-one-location-out for the reference set).
        "decision": {
            "answer": answer,
            "answer_type": answer_type,
            "correct": None
            if answer_type == "unsure" or not decision
            else (batch in prediction_set if answer_type == "pair" else answer == batch),
            "confidence": decision.get("confidence"),
            "imaging_side_pick": decision.get("imaging_side_pick"),
            "material_side_pick": decision.get("material_side_pick"),
            "sides_agree": decision.get("sides_agree"),
            "probabilities": decision.get("average_calibrated_probabilities"),
            "reasons": decision.get("reasons", []),
            "forced_answer": (facts.get("forced_mode") or {}).get("answer"),
        }
        if decision
        else None,
        "three_class_pct": (facts.get("phases") or {}).get("three_class_pct"),
        "summary_sentences": facts.get("summary_sentences", []),
        "batch_id": {
            "loo_predicted": loo.get("pred_F"),
            "loo_probabilities": dict(zip(REFERENCE_BATCHES, loo_p, strict=False)) if loo_p else None,
            "correct": loo.get("pred_F") == batch if loo else None,
            "confidence": facts.get("confidence", {}).get("tier"),
            "acquisition_warning": facts.get("acquisition", {}).get("warning"),
        },
        "overlay": (SEGMENTATION_DIR / batch / sid / "overlay.jpg").is_file(),
    }


@router.get("/batches/{batch_id}/segmentation-report")
def get_segmentation_report(batch_id: str) -> dict[str, Any]:
    """Four-phase segmentation and batch identification of one reference batch.

    Phase fractions, particle statistics and batch-ID facts are the committed sem_pipeline results (U-Net student
    labels); overlays come from outputs/segmentation, which run_cpu_pipeline.py rebuilds from data/raw."""
    if not batch_id.isdigit():
        raise HTTPException(404, f"Unknown image batch {batch_id}")
    batch = f"Batch_{batch_id}"
    phases = [r for r in read_metrics_csv("phase_fractions.csv") if r["batch"] == batch]
    if not phases:
        raise HTTPException(404, f"No SEM pipeline results for batch {batch_id}")
    stats = [r for r in read_metrics_csv("batch_stats.csv") if r["batch"] == batch]
    siox = {r["sample_id"]: r for r in read_metrics_csv("siox_summary.csv") if r["batch"] == batch}
    try:
        teacher = {r["sample_id"]: r for r in read_metrics_csv("teacher_cpu_fractions.csv")}
    except HTTPException:
        logger.debug("teacher_cpu_fractions.csv not generated; reporting without teacher phase fractions")
        teacher = {}
    seg_info = {}
    if (SEGMENTATION_DIR / "README.json").is_file():
        seg_info = json.loads((SEGMENTATION_DIR / "README.json").read_text(encoding="utf-8"))

    samples = [_sample_record(row, batch, teacher, siox) for row in phases]
    reference = next(
        (
            json.loads(p.read_text(encoding="utf-8")).get("validation_reference")
            for p in sorted(BATCH_ID_FACTS_DIR.glob("*.json"))
        ),
        None,
    )
    decision_eval_path = METRICS_DIR / "decision_eval.json"
    decision_eval = json.loads(decision_eval_path.read_text(encoding="utf-8")) if decision_eval_path.is_file() else {}
    loo_eval = decision_eval.get("LOO", {})
    return {
        "batch_id": batch_id,
        "source": "sem_pipeline",
        "version": 3,
        "decision_track_record": {
            "coverage": loo_eval.get("coverage"),
            "accuracy_when_answering": loo_eval.get("accuracy_when_answering"),
            "confidence_tiers": loo_eval.get("confidence_tiers"),
            "session_held_out": decision_eval.get("LOGO_session", {}).get("accuracy_when_answering"),
        }
        if loo_eval
        else None,
        "classes": SEGMENTATION_PHASES,
        "class_colors": PHASE_COLORS,
        "overlay_source": seg_info.get("source_model"),
        "batch_stats": [
            {
                "class": r["class"],
                "n": int(r["n"]),
                "mean_pct": to_float(r["mean_pct"]),
                "sd_pct": to_float(r["sd_pct"]),
                "min_pct": to_float(r["min_pct"]),
                "max_pct": to_float(r["max_pct"]),
                "kruskal_p": to_float(r["kruskal_p"]),
                "session_stratified_p": to_float(r["session_stratified_perm_p"]),
            }
            for r in stats
        ],
        "samples": samples,
        "batch_id_reference": reference,
    }


@router.get("/batches/{batch_id}/v3-report")
def get_v3_report(batch_id: str) -> dict:
    """General and detailed report built on v3's segmentation (analysis.v3_report): a reference batch, or the
    unknown batch as segmented by v3's CPU-trained teacher (analysis.v3_unknown)."""
    path = V3_REPORT_DIR / f"batch_{batch_id}.json"
    if not (batch_id.isdigit() or batch_id == UNKNOWN_BATCH) or not path.is_file():
        hint = (
            "run python -m analysis.v3_unknown, then python -m analysis.v3_report --unknown-only"
            if batch_id == UNKNOWN_BATCH
            else "run python -m analysis.v3_report"
        )
        raise HTTPException(404, f"No v3 report for batch {batch_id}; {hint}")
    return read_kpi_json(path, "No v3 report")


@router.get("/batches/unknown/v3-report/overlays/{location_id}")
def get_v3_unknown_overlay(location_id: str) -> FileResponse:
    """v3 four-phase overlay of one unknown location (blue pore, purple graphite, orange SiOx, green CBD)."""
    path = V3_UNKNOWN_DIR / "overlays" / f"{location_id}.jpg"
    if not LOCATION_ID_PATTERN.fullmatch(location_id) or not path.is_file():
        raise HTTPException(404, f"No v3 overlay for unknown location {location_id}")
    return FileResponse(path, media_type="image/jpeg", headers={"Cache-Control": "no-cache"})


@router.get("/batches/{batch_id}/segmentation-report/overlays/{sample_id}")
# Former path, still written into the overlay URLs of v3 reports generated before the rename; hidden from the docs.
@router.get("/batches/{batch_id}/lucas-report/overlays/{sample_id}", include_in_schema=False)
def get_segmentation_overlay(batch_id: str, sample_id: str) -> FileResponse:
    """Four-phase segmentation overlay (blue pore, purple graphite, orange SiOx, green CBD, red excluded)."""
    if not batch_id.isdigit() or not LOCATION_ID_PATTERN.fullmatch(sample_id):
        raise HTTPException(404, "Unknown overlay")
    path = SEGMENTATION_DIR / f"Batch_{batch_id}" / sample_id / "overlay.jpg"
    if not path.is_file():
        raise HTTPException(404, f"No overlay for {sample_id}; run sem_pipeline/run_cpu_pipeline.py")
    return FileResponse(path, media_type="image/jpeg", headers={"Cache-Control": "no-cache"})
