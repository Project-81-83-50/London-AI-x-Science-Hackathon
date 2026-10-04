"""Every file-system location and name pattern the API reads, in one place."""

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
MOCK_DIR = Path(__file__).parent / "mock"
RAW_DATA_DIR = REPO_ROOT / "data" / "raw"
PROCESSED_DIR = REPO_ROOT / "data" / "processed"
GET4_DATA_DIR = PROCESSED_DIR / "get4"
KPI_DATA_DIR = PROCESSED_DIR / "batch_kpis"
FIELD_DATA_DIR = PROCESSED_DIR / "fields"
PREVIEW_CACHE_DIR = PROCESSED_DIR / "previews"
CLASSIFICATION_PATH = PROCESSED_DIR / "classification" / "unknown.json"
# Further analysis: the newest lucas-sem-analysis version (v1 and v2 stay alongside it, unused by the API).
LUCAS_DIR = REPO_ROOT / "lucas-sem-analysis-v3"
BATCH_MATCH_PATH = PROCESSED_DIR / "batch_match" / "unknown.json"
# General and detailed batch reports built on v3 (analysis.v3_report).
V3_REPORT_DIR = PROCESSED_DIR / "v3_report"
# The unknown batch segmented by v3's CPU-trained teacher (analysis.v3_unknown).
V3_UNKNOWN_DIR = PROCESSED_DIR / "v3_unknown"
V3_TEACHER_PATH = LUCAS_DIR / "models" / "teacher_cpu.txt"

UNKNOWN_BATCH = "unknown"  # data/raw/unknown: images of unknown origin, classified against batches 1-3
LOCATION_ID_PATTERN = re.compile(r"^[A-Za-z0-9]+$")
IMAGE_NAME_PATTERN = re.compile(
    r"^img_(?P<specimen>.+?)_(?P<filter>BSE|ETD|Inlens|SE)(?:\s+\(\d+\))?\.tif$",
    re.IGNORECASE,
)
