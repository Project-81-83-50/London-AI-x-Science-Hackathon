# Research-grounded reports

The **Generate report** button on the Pipeline page: a bounded multi-agent explanation (decision analyst /
coordinator, research librarian, materials writer, independent grounding reviewer) with Corrective RAG. This
page covers configuration, the API, the evidence and retrieval policy, and the command-line tools.

## Setup and configuration


Report generation now runs in the **backend Python environment**, independently of the GPU interpreter. Existing
`facts.json` files can be explained without loading the image models. Install/update the backend dependencies when
upgrading an existing checkout; the launch scripts install dependencies automatically only when creating `.venv`.

```bash
.venv/bin/python -m pip install -r backend/app/requirements.txt -r analysis/requirements.txt
```

On Windows use `.venv\Scripts\python.exe`. Copy `sem_pipeline/.env.example` to `sem_pipeline/.env` and set
`ANTHROPIC_API_KEY`. Never put this key in the frontend. Process environment variables override the local files;
`sem_pipeline/.env` overrides the optional repository-root `.env`. Keys are read when a report starts.

- `RESEARCH_MODEL` defaults to the original project's `claude-sonnet-5-5`.
- `RESEARCH_REVIEWER_MODEL` defaults to `claude-sonnet-5-5` for source evaluation and independent review. Configure model IDs available to your account.
- `OPENALEX_API_KEY` is optional for OpenAlex discovery/access quotas. Crossref is the public metadata fallback.
- `RESEARCH_ONLINE=false` disables online **paper retrieval**, not Claude calls.
- `RESEARCH_DEADLINE_SECONDS` defaults to 240. Missing credentials and failed checks return explicit errors, not a
  replacement template. Source gaps can yield a checked measurement-based report marked `research_status=incomplete`.

The Pipeline page keeps **Generate report**, regeneration and Markdown downloads, and now shows concise per-sample
points, expandable calculations/source passages, retrieval gaps and review provenance. It polls running reports after
page reload and supports cancellation. Previously saved reports are labelled **legacy** until regenerated.
Numerical decision/opposition points have a 35-word limit; linked model scores and calculations remain in the
expandable evidence. When accepted applicable literature exists, the report must connect a scientific principle
with sample evidence in an interpretation point, rather than merely listing citations. Theories and performance
claims are not supplied from model memory when retrieval fails. Online document budgets are shared across questions
and corrective rounds so an early search cannot consume every opportunity to investigate another principle.

The existing API remains:

- `POST /v3/jobs/{job}/report`: start or reuse the active job; `?force=true` bypasses the result cache.
- `GET /v3/jobs/{job}/report`: progress/error status or the complete result, still including `markdown` and `check`.
- `POST /v3/jobs/{job}/report/cancel`: request cancellation. An in-flight request may finish before cancellation is observed.

Completed results additionally include `version`, ordered `explanations`, structured `claims`, typed `facts`, cited
`sources`, `research_status` and `audit`. `check` is retained only for compatibility; new clients should use the typed
validation/review audit rather than the old number-occurrence test. `report.json` is the canonical atomic artifact;
`report.md` and `report_status.json` remain available. Input facts, classifiers and model weights are not rewritten.

## Evidence and retrieval policy

The shared implementation lives in `backend/app/research/`; `sem_pipeline/website/agents.py` is only a compatibility
entry point. The decoder handles current KPI/material records, the bundled legacy material records, and ordered
multi-sample documents. It distinguishes raw driver scaling, model contributions, phase area, sampling intervals,
DINO sign-specific denominators and training-relative scores. The selected KPI's supplied batch means are primary
classification evidence. Descriptive material profiles can also be computed from the bundled 31 reference-location
exports, excluding the query location; these are not reconstructed classifier distances or universal acceptance limits.
Unknown export-version compatibility is retained as a limitation, not treated as proven calibration compatibility.

The local index combines BM25 with TF-IDF/latent-semantic vectors (LSA); it needs neither a GPU nor another embedding
API key. Retrieval similarity is not scientific support: a separate evaluator checks original quotations, relevance,
material/method applicability and conditions. Insufficient/conflicting retrieval triggers bounded neutral or
counter-evidence searches through OpenAlex/Crossref and approved technical resources. HTTPS addresses/redirects are
checked against private networks, downloads are bounded, and PDF extraction runs in a limited subprocess. Private
sample IDs, batch measurements and free-form agent queries are never submitted to the scholarly search providers.
The configured Claude service still receives the scoped facts and passages, as in the original explanation path.

The existing knowledge JSON is imported as **discovery leads**: its title/abstract verification is not full-text
verification. Abstract-only material cannot be promoted to inspected experimental evidence. Sources with unresolved
DOI-update checks or notices cannot support final scientific claims. Missing evidence stays a visible research gap.
Newly retrieved passages remain per-run candidates until a human admits them to the reusable library.

Research storage and versioned caches live under Git-ignored `data/processed/research/`. Generation-cache TTL is one
day, with local revalidation and keys covering facts, reference exports, corpus, implementation and model settings.
Source checks age out after thirty days. Two active report jobs are allowed; each has bounded model calls, output
tokens, document/network requests, retrieval rounds, repair attempts and runtime. This is a bounded workflow, not
unrestricted autonomous browsing. Default settings are in `backend/app/research/models.py`.

From the repository root (PowerShell: set `$env:PYTHONPATH="backend"` before the corresponding Python command):

```bash
PYTHONPATH=backend .venv/bin/python -m app.research.cli prepare
PYTHONPATH=backend .venv/bin/python -m app.research.cli inspect path/to/facts.json
PYTHONPATH=backend .venv/bin/python -m app.research.cli run sem_pipeline/website/runs/unknown_0eryguqq
PYTHONPATH=backend .venv/bin/python -m app.research.cli sources
PYTHONPATH=backend .venv/bin/python -m app.research.cli admit SOURCE_ID
PYTHONPATH=backend .venv/bin/python -m app.research.cli admit SOURCE_ID --exclude
```

Review source metadata, the exact passage, its applicability and publication notices before admitting a candidate.
Admission invalidates corpus-versioned caches; it does not bypass per-question evaluation. Scientific review and
real-account model validation remain necessary before relying on generated explanations for consequential decisions.
