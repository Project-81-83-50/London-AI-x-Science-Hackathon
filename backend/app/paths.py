"""Every file-system location and name pattern the API reads, in one place.

V3_PROJECT_DIR (environment) moves the folder the v3 Demo / Pipeline runs use; everything else is fixed
relative to the repository."""

import os
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
RAW_DATA_DIR = REPO_ROOT / "data" / "raw"
PROCESSED_DIR = REPO_ROOT / "data" / "processed"
GET4_DATA_DIR = PROCESSED_DIR / "get4"
KPI_DATA_DIR = PROCESSED_DIR / "batch_kpis"
FIELD_DATA_DIR = PROCESSED_DIR / "fields"
PREVIEW_CACHE_DIR = PROCESSED_DIR / "previews"
CLASSIFICATION_PATH = PROCESSED_DIR / "classification" / "unknown.json"
BATCH_MATCH_PATH = PROCESSED_DIR / "batch_match" / "unknown.json"
# The SEM pipeline (v3): four-phase segmentation, batch decisions, the Demo / Pipeline runs and their models.
SEM_PIPELINE_DIR = REPO_ROOT / "sem_pipeline"
SEM_METRICS_DIR = SEM_PIPELINE_DIR / "outputs" / "metrics"
SEM_SEGMENTATION_DIR = SEM_PIPELINE_DIR / "outputs" / "segmentation"
SEM_BATCH_ID_FACTS_DIR = SEM_PIPELINE_DIR / "outputs" / "batchid"
# General and detailed batch reports built on v3 (analysis.v3_report).
V3_REPORT_DIR = PROCESSED_DIR / "v3_report"
# The unknown batch segmented by v3's CPU-trained teacher (analysis.v3_unknown).
V3_UNKNOWN_DIR = PROCESSED_DIR / "v3_unknown"
V3_TEACHER_PATH = SEM_PIPELINE_DIR / "models" / "teacher_cpu.txt"
# Where v3's Demo / Pipeline runs execute: V3_PROJECT_DIR, else this repository's sem_pipeline/ (when it has the
# website code), else two folders above the repository.
V3_PROJECT_DIR = Path(
    os.environ.get("V3_PROJECT_DIR")
    or (SEM_PIPELINE_DIR if (SEM_PIPELINE_DIR / "website" / "agents.py").is_file() else REPO_ROOT.parents[1])
)
V3_RUNS_DIR = V3_PROJECT_DIR / "website" / "runs"
# Holds the path of a Python with PyTorch; scripts/start_website.bat and scripts/start_website.sh write it.
V3_PYTHON_FILE = V3_PROJECT_DIR / "website" / "v3_python.txt"

UNKNOWN_BATCH = "unknown"  # data/raw/unknown: images of unknown origin, classified against batches 1-3
UNKNOWN_IMAGE_DIR = RAW_DATA_DIR / UNKNOWN_BATCH
LOCATION_ID_PATTERN = re.compile(r"^[A-Za-z0-9]+$")
IMAGE_NAME_PATTERN = re.compile(
    r"^img_(?P<specimen>.+?)_(?P<filter>BSE|ETD|Inlens|SE)(?:\s+\(\d+\))?\.tif$",
    re.IGNORECASE,
)
