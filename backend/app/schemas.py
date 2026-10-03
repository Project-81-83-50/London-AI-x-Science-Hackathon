from pydantic import BaseModel
from typing import Literal

class KPI(BaseModel):
    name: str
    unit: str | None = None
    baseline_mean: float
    batch_mean: float
    ci_low: float
    ci_high: float
    flag: Literal["ok", "watch", "shifted"]
    note: str

class Driver(BaseModel):
    kpi: str
    contribution: float
    explanation: str

class Analysis(BaseModel):
    batch_id: str
    verdict: Literal["accept", "investigate", "reject"]
    confidence: float
    summary: str
    kpis: list[KPI]
    drivers: list[Driver]
    overlay_urls: list[str] = []
    atypical_patch_urls: list[str] = []

class BatchSummary(BaseModel):
    batch_id: str
    verdict: Literal["accept", "investigate", "reject"]
    confidence: float