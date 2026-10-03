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
LUCAS_DIR = REPO_ROOT / "lucas-sem-analysis"

UNKNOWN_BATCH = "unknown"  # data/raw/unknown: images of unknown origin, classified against batches 1-3
LOCATION_ID_PATTERN = re.compile(r"^[A-Za-z0-9]+$")
IMAGE_NAME_PATTERN = re.compile(
    r"^img_(?P<specimen>.+?)_(?P<filter>BSE|ETD|Inlens|SE)(?:\s+\(\d+\))?\.tif$",
    re.IGNORECASE,
)
