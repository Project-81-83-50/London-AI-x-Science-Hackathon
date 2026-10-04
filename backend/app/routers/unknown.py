"""The unknown batch (frontend: Unknown in the batch picker): its classification against batches 1-3,
uploading and deleting images in data/raw/unknown, and re-running the analysis as a background job."""

import hashlib
import os
import re
import shutil
import subprocess
import sys
import threading
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query, Request

from ..batches import read_kpi_json
from ..paths import (BATCH_MATCH_PATH, CLASSIFICATION_PATH, FIELD_DATA_DIR, V3_REPORT_DIR, V3_TEACHER_PATH,
                     V3_UNKNOWN_DIR, IMAGE_NAME_PATTERN, KPI_DATA_DIR, PREVIEW_CACHE_DIR,
                     RAW_DATA_DIR, REPO_ROOT, UNKNOWN_BATCH)

router = APIRouter()

UNKNOWN_DIR = RAW_DATA_DIR / UNKNOWN_BATCH
# Stricter than the listing pattern: one alphanumeric location code, a known filter, .tif only.
UPLOAD_NAME = re.compile(r"^img_[A-Za-z0-9]+_(BSE|ETD|Inlens|SE)\.tif$")
TIFF_MAGIC = (b"II*\x00", b"MM\x00*", b"II+\x00", b"MM\x00+")  # classic and BigTIFF, both byte orders
MAX_UPLOAD_BYTES = 300 * 1024 * 1024
ANALYSIS_LOG = CLASSIFICATION_PATH.parent / "analysis_run.log"

_job_lock = threading.Lock()
_job = {"state": "idle", "started": None, "finished": None, "returncode": None}


def _now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _analysis_running() -> bool:
    return _job["state"] == "running"


def _identical_unknown_image(sha256: str, size: int, exclude) -> str | None:
    """Name of an unknown-batch image with exactly these bytes (only same-size files are hashed).
    Copies of reference images are allowed: the classifier reports them as exact matches."""
    for path in UNKNOWN_DIR.glob("*.tif"):
        if path == exclude or path.stat().st_size != size:
            continue
        if hashlib.sha256(path.read_bytes()).hexdigest() == sha256:
            return path.name
    return None


@router.get("/unknown/classification")
def get_unknown_classification():
    """Batch 1/2/3 classification of the locations in data/raw/unknown (analysis.classify)."""
    return read_kpi_json(CLASSIFICATION_PATH, "No classification of the unknown batch found; run "
                         "python -m analysis.classify")


@router.get("/unknown/batch-match")
def get_unknown_batch_match():
    """The teammate's batch-match classifier on the unknown images (analysis.batch_match predict)."""
    if not BATCH_MATCH_PATH.is_file():
        raise HTTPException(404, "No batch-match result for the unknown batch yet; run "
                                 "python -m analysis.batch_match train once, then re-run the analysis")
    return read_kpi_json(BATCH_MATCH_PATH, "No batch-match result")


@router.get("/unknown/batch-match/evaluation")
def get_batch_match_evaluation():
    """How often batch match is right on held-out reference locations (analysis.batch_match evaluate)."""
    path = BATCH_MATCH_PATH.parent / "evaluation_report.json"
    if not path.is_file():
        raise HTTPException(404, "No batch-match evaluation yet; run python -m analysis.batch_match evaluate")
    return read_kpi_json(path, "No batch-match evaluation")


@router.put("/batches/unknown/images/{image_name}")
async def upload_unknown_image(image_name: str, request: Request, overwrite: bool = Query(default=False)):
    """Save one TIFF (raw request body) into data/raw/unknown.

    The name must be img_<location>_<BSE|ETD|Inlens|SE>.tif; the body must start with a TIFF header and
    stay under the size limit. An existing file is only replaced when overwrite=true. The file is
    written to a temporary name first, so a failed upload never leaves a partial image behind."""
    if not UPLOAD_NAME.fullmatch(image_name):
        raise HTTPException(422, f"{image_name}: name must look like img_<location>_<BSE|ETD|Inlens|SE>.tif")
    if _analysis_running():
        raise HTTPException(409, "The unknown batch is being analysed; upload again when it finishes")
    UNKNOWN_DIR.mkdir(parents=True, exist_ok=True)
    target = UNKNOWN_DIR / image_name
    replaced = target.exists()
    if replaced and not overwrite:
        raise HTTPException(409, f"{image_name} already exists; tick 'replace existing files' to overwrite it")

    temporary = UNKNOWN_DIR / f".{image_name}.uploading"
    size = 0
    header = b""
    digest = hashlib.sha256()
    try:
        with open(temporary, "wb") as out:
            async for chunk in request.stream():
                if len(header) < 4:
                    header += chunk[: 4 - len(header)]
                size += len(chunk)
                if size > MAX_UPLOAD_BYTES:
                    raise HTTPException(413, f"{image_name} is larger than {MAX_UPLOAD_BYTES // 2**20} MB")
                digest.update(chunk)
                out.write(chunk)
        if size == 0:
            raise HTTPException(422, f"{image_name} is empty")
        if header not in TIFF_MAGIC:
            raise HTTPException(415, f"{image_name} is not a TIFF image")
        duplicate = _identical_unknown_image(digest.hexdigest(), size, exclude=target)
        if duplicate:
            raise HTTPException(409, f"{image_name} is identical to {duplicate}, already in the unknown batch")
        os.replace(temporary, target)
    finally:
        temporary.unlink(missing_ok=True)
    return {"filename": image_name, "bytes": size, "replaced": replaced}


@router.delete("/batches/unknown/images/{image_name}")
def delete_unknown_image(image_name: str):
    """Delete one image from data/raw/unknown, with its cached preview.

    When the last image goes, the unknown batch's generated results (location manifest, KPI report,
    classification) are removed too, so no stale classification is shown. Otherwise re-run the analysis
    (POST /unknown/analysis) to update them; the frontend does this automatically."""
    if not IMAGE_NAME_PATTERN.fullmatch(image_name) or Path(image_name).name != image_name:
        raise HTTPException(422, f"{image_name} is not an image name")
    if _analysis_running():
        raise HTTPException(409, "The unknown batch is being analysed; delete again when it finishes")
    target = UNKNOWN_DIR / image_name
    if not target.is_file():
        raise HTTPException(404, f"{image_name} is not in the unknown batch")
    target.unlink()
    for preview in (PREVIEW_CACHE_DIR / f"batch_{UNKNOWN_BATCH}").glob(f"{target.stem}_*.jpg"):
        preview.unlink(missing_ok=True)
    remaining = sorted(p.name for p in UNKNOWN_DIR.glob("*.tif") if IMAGE_NAME_PATTERN.fullmatch(p.name))
    if not remaining:
        CLASSIFICATION_PATH.unlink(missing_ok=True)
        BATCH_MATCH_PATH.unlink(missing_ok=True)
        (V3_REPORT_DIR / f"batch_{UNKNOWN_BATCH}.json").unlink(missing_ok=True)
        shutil.rmtree(V3_UNKNOWN_DIR, ignore_errors=True)
        (FIELD_DATA_DIR / f"batch_{UNKNOWN_BATCH}.json").unlink(missing_ok=True)
        shutil.rmtree(KPI_DATA_DIR / f"batch_{UNKNOWN_BATCH}", ignore_errors=True)
    return {"deleted": image_name, "remaining": len(remaining)}


BATCH_MATCH_MODEL = BATCH_MATCH_PATH.parent / "batch_model.pkl"


def _run_analysis():
    """KPI classification first; then, when their models exist, the teammate's batch-match classifier
    (python -m analysis.batch_match train) and v3's segmentation of the unknown images with the General and
    Detailed reports (lucas-sem-analysis-v3/run_cpu_pipeline.py). A failure in those optional steps is logged
    but does not fail the job."""
    ANALYSIS_LOG.parent.mkdir(parents=True, exist_ok=True)
    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    try:
        with open(ANALYSIS_LOG, "w", encoding="utf-8") as log:
            code = subprocess.run([sys.executable, "-m", "analysis.classify", "--rebuild"],
                                  cwd=REPO_ROOT, stdout=log, stderr=subprocess.STDOUT, env=env).returncode
            if code == 0 and BATCH_MATCH_MODEL.is_file():
                log.write("batch match: classifying the unknown images with the teammate's classifier\n")
                log.flush()
                matched = subprocess.run([sys.executable, "-m", "analysis.batch_match", "predict"],
                                         cwd=REPO_ROOT, stdout=log, stderr=subprocess.STDOUT, env=env).returncode
                if matched != 0:
                    log.write(f"batch match failed (exit {matched}); the KPI classification is still valid\n")
            elif code == 0:
                log.write("batch match skipped: run python -m analysis.batch_match train once to enable it\n")
            if code == 0 and V3_TEACHER_PATH.is_file():
                log.write("v3: segmenting the unknown images with lucas-sem-analysis v3's teacher\n")
                log.flush()
                for step in (["analysis.v3_unknown"], ["analysis.v3_report", "--unknown-only"]):
                    done = subprocess.run([sys.executable, "-m", *step], cwd=REPO_ROOT, stdout=log,
                                          stderr=subprocess.STDOUT, env=env).returncode
                    if done != 0:
                        log.write(f"v3 step {step[0]} failed (exit {done}); the KPI classification is still valid\n")
                        break
            elif code == 0:
                log.write("v3 reports skipped: run python run_cpu_pipeline.py in lucas-sem-analysis-v3 once\n")
    except OSError as error:
        ANALYSIS_LOG.write_text(f"could not start the analysis: {error}\n", encoding="utf-8")
        code = -1
    with _job_lock:
        _job.update(state="done" if code == 0 else "failed", finished=_now(), returncode=code)


@router.post("/unknown/analysis")
def start_unknown_analysis():
    """Re-measure and re-classify the unknown batch (python -m analysis.classify --rebuild) in the background."""
    images = [p for p in UNKNOWN_DIR.glob("*.tif") if IMAGE_NAME_PATTERN.fullmatch(p.name)] if UNKNOWN_DIR.is_dir() else []
    if not images:
        raise HTTPException(422, "data/raw/unknown has no images to analyse; upload some first")
    with _job_lock:
        if _analysis_running():
            raise HTTPException(409, "An analysis of the unknown batch is already running")
        _job.update(state="running", started=_now(), finished=None, returncode=None)
    threading.Thread(target=_run_analysis, daemon=True).start()
    return get_unknown_analysis()


@router.get("/unknown/analysis")
def get_unknown_analysis():
    """State of the latest unknown-batch analysis job, with the last lines of its log as progress."""
    lines = []
    if ANALYSIS_LOG.is_file():
        lines = [l for l in ANALYSIS_LOG.read_text(encoding="utf-8", errors="replace").splitlines() if l.strip()]
    images = sorted(p.name for p in UNKNOWN_DIR.glob("*.tif")) if UNKNOWN_DIR.is_dir() else []
    return {**_job, "log_tail": lines[-8:], "images": len(images)}
