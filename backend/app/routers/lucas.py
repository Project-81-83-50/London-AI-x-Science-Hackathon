"""lucas-sem-analysis results: four-phase segmentation and batch identification (frontend: Segmentation tab).

Phase fractions, particle statistics and batch-ID facts are Lucas's committed results; overlays come from
lucas-sem-analysis/outputs/segmentation, which run_cpu_pipeline.py rebuilds from data/raw."""

import csv
import json

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from ..paths import LOCATION_ID_PATTERN, LUCAS_DIR

router = APIRouter()
LUCAS_PHASES = ["pore", "graphite", "SiOx", "CBD"]


def read_lucas_csv(name: str) -> list[dict]:
    path = LUCAS_DIR / "outputs" / "metrics" / name
    if not path.is_file():
        raise HTTPException(404, f"lucas-sem-analysis result {name} not found")
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def lucas_number(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


@router.get("/batches/{batch_id}/lucas-report")
def get_lucas_report(batch_id: str):
    """Results of lucas-sem-analysis (4-phase segmentation and batch identification) for one batch.

    Phase fractions, particle statistics and batch-ID facts are Lucas's committed results (U-Net student
    labels); overlays come from outputs/segmentation, which run_cpu_pipeline.py rebuilds from data/raw."""
    if not batch_id.isdigit():
        raise HTTPException(404, f"Unknown image batch {batch_id}")
    batch = f"Batch_{batch_id}"
    phases = [r for r in read_lucas_csv("phase_fractions.csv") if r["batch"] == batch]
    if not phases:
        raise HTTPException(404, f"No lucas-sem-analysis results for batch {batch_id}")
    stats = [r for r in read_lucas_csv("batch_stats.csv") if r["batch"] == batch]
    siox = {r["sample_id"]: r for r in read_lucas_csv("siox_summary.csv") if r["batch"] == batch}
    try:
        teacher = {r["sample_id"]: r for r in read_lucas_csv("teacher_cpu_fractions.csv")}
    except HTTPException:
        teacher = {}
    seg_dir = LUCAS_DIR / "outputs" / "segmentation"
    seg_info = {}
    if (seg_dir / "README.json").is_file():
        seg_info = json.loads((seg_dir / "README.json").read_text(encoding="utf-8"))

    samples = []
    for row in phases:
        sid = row["sample_id"]
        facts_path = LUCAS_DIR / "outputs" / "batchid" / f"{sid}.json"
        facts = json.loads(facts_path.read_text(encoding="utf-8")) if facts_path.is_file() else {}
        loo = facts.get("loo_prediction", {})
        loo_p = loo.get("p_F") or []
        particles = siox.get(sid, {})
        samples.append({
            "sample_id": sid,
            "session": row["height_group"],
            "phases_pct": {k: lucas_number(row[f"{k}_pct"]) for k in LUCAS_PHASES},
            "pore_deep_pct": lucas_number(row["pore_deep_pct"]),
            "pore_open_pct": lucas_number(row["pore_open_pct"]),
            "excluded_pct": lucas_number(row["excluded_pct"]),
            "teacher_cpu_phases_pct": {k: lucas_number(teacher[sid].get(f"{k}_pct")) for k in LUCAS_PHASES}
            if sid in teacher else None,
            "siox_particles": {
                "count": lucas_number(particles.get("n_particles")),
                "per_1000um2": lucas_number(particles.get("per_1000um2")),
                "median_diameter_um": lucas_number(particles.get("eq_diam_median_um")),
                "p90_diameter_um": lucas_number(particles.get("eq_diam_p90_um")),
            },
            "batch_id": {
                "loo_predicted": loo.get("pred_F"),
                "loo_probabilities": dict(zip(["Batch_1", "Batch_2", "Batch_3"], loo_p)) if loo_p else None,
                "correct": loo.get("pred_F") == batch if loo else None,
                "confidence": facts.get("confidence", {}).get("tier"),
                "acquisition_warning": facts.get("acquisition", {}).get("warning"),
            },
            "overlay": (seg_dir / batch / sid / "overlay.jpg").is_file(),
        })
    reference = next((json.loads(p.read_text(encoding="utf-8")).get("validation_reference")
                      for p in sorted((LUCAS_DIR / "outputs" / "batchid").glob("*.json"))), None)
    return {
        "batch_id": batch_id,
        "source": "lucas-sem-analysis",
        "classes": LUCAS_PHASES,
        "class_colors": {"pore": "#1e6eff", "graphite": "#aa6eff", "SiOx": "#ff9600", "CBD": "#28d278"},
        "overlay_source": seg_info.get("source_model"),
        "batch_stats": [{
            "class": r["class"], "n": int(r["n"]), "mean_pct": lucas_number(r["mean_pct"]),
            "sd_pct": lucas_number(r["sd_pct"]), "min_pct": lucas_number(r["min_pct"]),
            "max_pct": lucas_number(r["max_pct"]), "kruskal_p": lucas_number(r["kruskal_p"]),
            "session_stratified_p": lucas_number(r["session_stratified_perm_p"]),
        } for r in stats],
        "samples": samples,
        "batch_id_reference": reference,
    }


@router.get("/batches/{batch_id}/lucas-report/overlays/{sample_id}")
def get_lucas_overlay(batch_id: str, sample_id: str):
    """4-phase segmentation overlay (blue pore, purple graphite, orange SiOx, green CBD, red excluded)."""
    if not batch_id.isdigit() or not LOCATION_ID_PATTERN.fullmatch(sample_id):
        raise HTTPException(404, "Unknown overlay")
    path = LUCAS_DIR / "outputs" / "segmentation" / f"Batch_{batch_id}" / sample_id / "overlay.jpg"
    if not path.is_file():
        raise HTTPException(404, f"No overlay for {sample_id}; run lucas-sem-analysis/run_cpu_pipeline.py")
    return FileResponse(path, media_type="image/jpeg", headers={"Cache-Control": "no-cache"})
