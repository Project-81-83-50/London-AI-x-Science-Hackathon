"""Batch 1/2/3 classification of the unknown set from analysis.classify (frontend: Unknown batch)."""

from fastapi import APIRouter

from ..batches import read_kpi_json
from ..paths import CLASSIFICATION_PATH

router = APIRouter()


@router.get("/unknown/classification")
def get_unknown_classification():
    """Batch 1/2/3 classification of the locations in data/raw/unknown (analysis.classify)."""
    return read_kpi_json(CLASSIFICATION_PATH, "No classification of the unknown batch found; run "
                         "python -m analysis.classify")
