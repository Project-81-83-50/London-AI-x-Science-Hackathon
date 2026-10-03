"""Sample analysis records from the mock folder (used by the frontend's data-readiness line)."""

import json

from fastapi import APIRouter, HTTPException

from ..paths import MOCK_DIR
from ..schemas import Analysis, BatchSummary

router = APIRouter()


def load_mock(batch_id: str) -> dict:
    """Load one batch's sample analysis JSON, or return HTTP 404 if it is unknown."""
    path = MOCK_DIR / f"{batch_id}.json"
    if not path.exists():
        raise HTTPException(404, f"Unknown batch {batch_id}")
    return json.loads(path.read_text(encoding="utf-8"))


@router.get("/batches", response_model=list[BatchSummary])
def list_batches():
    """Return one compact summary for every JSON batch in the mock-data folder."""
    return [load_mock(p.stem) for p in sorted(MOCK_DIR.glob("*.json"))]


@router.get("/batches/{batch_id}/analysis", response_model=Analysis)
def get_analysis(batch_id: str):
    """Return the full analysis record for the requested batch ID."""
    return load_mock(batch_id)
