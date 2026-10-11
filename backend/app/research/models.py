from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class Settings(Contract):
    writer_model: str = "claude-sonnet-5-5"
    reviewer_model: str = "claude-sonnet-5-5"
    effort: str = "low"
    online: bool = True
    max_calls: int = Field(default=14, ge=4, le=24)
    max_questions: int = Field(default=2, ge=0, le=4)
    retrieval_rounds: int = Field(default=2, ge=0, le=3)
    max_documents: int = Field(default=6, ge=0, le=12)
    max_web_requests: int = Field(default=24, ge=0, le=60)
    draft_attempts: int = Field(default=3, ge=1, le=3)
    max_output_tokens: int = Field(default=6000, ge=1000, le=16000)
    total_output_tokens: int = Field(default=36000, ge=4000, le=64000)
    timeout: float = Field(default=45, gt=0, le=120)
    deadline: float = Field(default=240, ge=10, le=600)
    cache_ttl: int = Field(default=86400, ge=0, le=86400)
    source_max_age: int = Field(default=30 * 86400, ge=3600, le=90 * 86400)


class Fact(Contract):
    id: str
    sample_id: str
    pointer: str
    label: str
    value: float | str | bool
    raw_value: Any
    display: str
    unit: str = ""
    role: Literal["observation", "baseline", "attribution", "calculation", "diagnostic", "quality"]
    method: str = ""
    description: str = ""
    denominator: str = ""
    uncertainty: str = ""
    used_by_model: bool = False
    formula: str | None = None
    inputs: list[str] = Field(default_factory=list)
    contrast: list[str] = Field(default_factory=list)


class Comparison(Contract):
    metric: str
    value_id: str
    reference_ids: dict[str, str]
    relation: Literal["mean", "median"] = "mean"
    used_by_model: bool = False


class Sample(Contract):
    sample_id: str
    answer: str
    answer_type: str = "specific"
    confidence: str | None = None
    schema_version: str
    facts: list[Fact]
    comparisons: list[Comparison] = Field(default_factory=list)
    attribution_pair: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    concepts: list[str] = Field(default_factory=list)


class Document(Contract):
    input_hash: str
    registry_version: str
    samples: list[Sample]
    inventory: dict[str, str]


class Source(Contract):
    id: str
    document_id: str
    title: str
    text: str
    url: str = ""
    doi: str | None = None
    authors: list[str] = Field(default_factory=list)
    year: int | None = None
    location: str
    content_hash: str
    access: Literal["full_text", "technical", "abstract", "seed"]
    status: Literal["approved", "candidate", "excluded"] = "candidate"
    license: str | None = None
    updates: Literal["none_found", "notice", "unknown"] = "unknown"
    checked_at: float
    caveats: list[str] = Field(default_factory=list)


class Question(Contract):
    concept: str
    sample_ids: list[str] = Field(min_length=1)
    focus: Literal["meaning", "limitations", "counter_evidence"] = "meaning"


class ToolRequest(Contract):
    name: Literal["facts", "comparisons", "definitions"]
    sample_id: str
    fact_ids: list[str] = Field(default_factory=list, max_length=30)


class Analysis(Contract):
    done: bool
    tools: list[ToolRequest] = Field(default_factory=list, max_length=3)
    selected_facts: list[str] = Field(default_factory=list)
    questions: list[Question] = Field(default_factory=list, max_length=4)
    reason: str = Field(max_length=1200)


class SearchPlan(Contract):
    focus: Literal["meaning", "limitations", "counter_evidence"]
    reason: str = Field(max_length=600)


class Grade(Contract):
    source_id: str
    verdict: Literal["supported", "ambiguous", "unsupported"]
    relevant: bool
    applicable: bool
    answers_question: bool = False
    statement: str
    quote: str
    limitations: list[str] = Field(default_factory=list)
    conflict: bool = False
    reason: str = Field(max_length=1200)


class Grades(Contract):
    items: list[Grade]


class Citation(Contract):
    source_id: str
    quote: str = Field(min_length=25, max_length=2400)


class Claim(Contract):
    id: str = Field(min_length=1, max_length=100)
    sample_id: str
    kind: Literal["decision", "opposing", "interpretation", "limitation"]
    text: str = Field(min_length=1, max_length=4000)
    citations: list[Citation] = Field(default_factory=list, max_length=3)


class Explanation(Contract):
    sample_id: str
    answer: str
    claims: list[Claim] = Field(min_length=1, max_length=5)


class Draft(Contract):
    explanations: list[Explanation] = Field(min_length=1)


class Finding(Contract):
    claim_id: str
    category: Literal["unsupported", "contradiction", "causal", "inapplicable", "style"]
    reason: str = Field(max_length=1000)
    evidence_ids: list[str] = Field(default_factory=list)
    action: Literal["rewrite", "retrieve", "remove"]


class Review(Contract):
    findings: list[Finding] = Field(max_length=5)


class Report(Contract):
    version: str = "crag-v1"
    status: Literal["done"] = "done"
    research_status: Literal["supported", "incomplete", "not_needed"]
    explanations: dict[str, str]
    claims: list[dict[str, Any]]
    facts: dict[str, Fact]
    sources: dict[str, Source]
    markdown: str
    audit: dict[str, Any]
