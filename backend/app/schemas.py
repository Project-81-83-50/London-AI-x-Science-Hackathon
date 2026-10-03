"""Pydantic response models: these define and validate the API's JSON shapes."""

from pydantic import BaseModel
from typing import Literal

class KPI(BaseModel):
    """One measured material property compared with the approved baseline."""
    name: str
    unit: str | None = None
    baseline_mean: float
    batch_mean: float
    # These bounds describe the reported interval; define its statistical meaning in the analysis method.
    ci_low: float
    ci_high: float
    flag: Literal["ok", "watch", "shifted"]
    note: str

class Driver(BaseModel):
    """A KPI identified as contributing to a batch-level change."""
    kpi: str
    # Expected to be a relative contribution from 0 to 1; the scoring method should define it.
    contribution: float
    explanation: str

class Analysis(BaseModel):
    """Full result returned by the batch-analysis endpoint."""
    batch_id: str
    verdict: Literal["accept", "investigate", "reject"]
    confidence: float
    summary: str
    kpis: list[KPI]
    drivers: list[Driver]
    overlay_urls: list[str] = []
    atypical_patch_urls: list[str] = []

class BatchSummary(BaseModel):
    """Small result used to populate the frontend's batch selector."""
    batch_id: str
    verdict: Literal["accept", "investigate", "reject"]
    confidence: float