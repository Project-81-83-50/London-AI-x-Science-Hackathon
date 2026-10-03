"""FastAPI routes for listing material batches and retrieving their analysis."""

import json
from pathlib import Path
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from .schemas import Analysis, BatchSummary

app = FastAPI(title="EM QC API")

# Allow the local Vite page and other frontends to call this API during development.
# For a public production deployment, replace "*" with the approved frontend origin.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], 
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

MOCK_DIR = Path(__file__).parent / "mock"

def load_mock(batch_id: str) -> dict:
    """Load one batch's sample analysis JSON, or return HTTP 404 if it is unknown."""
    path = MOCK_DIR / f"{batch_id}.json"
    if not path.exists():
        raise HTTPException(404, f"Unknown batch {batch_id}")
    return json.loads(path.read_text(encoding="utf-8"))

@app.get("/batches", response_model=list[BatchSummary])
def list_batches():
    """Return one compact summary for every JSON batch in the mock-data folder."""
    return [load_mock(p.stem) for p in sorted(MOCK_DIR.glob("*.json"))]

@app.get("/batches/{batch_id}/analysis", response_model=Analysis)
def get_analysis(batch_id: str):
    """Return the full analysis record for the requested batch ID."""
    return load_mock(batch_id)

if __name__ == "__main__":
    import uvicorn
    # Running this module directly starts the local development API on port 8000.
    uvicorn.run(app, host="0.0.0.0", port=8000)