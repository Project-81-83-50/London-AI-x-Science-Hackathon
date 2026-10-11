# SEM Batch Identification — London AI × Science Hackathon (Track 4)

Identify which manufacturing batch an SEM image of a graphite + SiOx battery anode came from, explain the call with
visible material evidence, and state how certain it is.

## The challenge

Track 4 (*Materials manufacturing*, set by Polaron): three reference batches of SEM images are known. Images within a
batch show the same electrode at different locations and with different detectors (BSE, InLens, ETD/SE), so views of
one location are compared as a group rather than treated as different materials. Each location of an unknown batch must
be assigned to batch 1, 2 or 3, with an explanation and a stated uncertainty.

## How it works

1. **Group and verify views.** `analysis/fields.py` registers images against each other to recover which views show the
   same location and identifies each view's real detector from its pixels.
2. **Segment.** The SEM pipeline (`sem_pipeline/`) segments each location into pore, graphite, SiOx and carbon-binder
   domain with a label-free U-Net; GET4 attaches a 95 % sampling interval to every phase fraction, and the General
   report pools these per batch (how precisely each batch is known, and whether one location can be told apart).
3. **Classify.** A KPI model (`analysis/classify.py`, `analysis/kpi_single.py` for one location) gives 90 % of the
   probability; the v3 material model (U-Net features + DINOv2) gives 10 % and is the agreement check: confidence is
   High only when the KPI model is at least 50 % sure and both pick the same batch. The KPI model decides only on KPIs
   measured for that location (its strongest one needs an ETD image). A training-image guard and a known-location
   matcher can override the answer: a training image is refused, and a re-shot of a known spot gets that spot's
   batch. The earlier batch-match classifier (`batch_match/`) is kept for comparison; its matcher and GET4 range rule
   were built into v3.
4. **Explain.** A decision analyst/coordinator, research librarian, materials writer and independent grounding reviewer
   produce a research-grounded report. Corrective RAG investigates insufficient retrieval; typed Python checks gate
   numerical evidence and citations before publication.

Every analysis stage, with its commands, outputs and API routes, is in [docs/analysis.md](docs/analysis.md); the SEM
pipeline's decisions and open issues are in [sem_pipeline/HANDOFF.md](sem_pipeline/HANDOFF.md) and its evaluation
results in [sem_pipeline/reports/report.md](sem_pipeline/reports/report.md).

## Quick start

On Windows run [scripts/start_website.bat](scripts/start_website.bat) (double-click it, or run it from a terminal); on
macOS / Linux run `./scripts/start_website.sh` from the repository root. On first run the launcher creates `.venv`,
installs the backend and frontend dependencies, starts the API on port 8002 and the website on port 5173, and opens
<http://localhost:5173>. Close the two server windows (Windows) or press Ctrl+C (macOS / Linux) to stop it.

The website has three pages:

- **Batches** — the reference batches 1–3 (tabs: **Images**; **General report**, the batch at a glance with GET4's
  "How sure are these numbers?"; **Detailed report**, every location and statistic) and the unknown batch, including
  each unknown location's batch call.
- **Demo** — upload the BSE + InLens (+ ETD, recommended) images of one location to get its batch and confidence
  (about 1 min; about 45 s on an M2 Pro CPU).
- **Pipeline** — every intermediate output of a run, and **Generate report** for the agent-written explanation.

### Files you must add locally

These are not in Git (see `.gitignore`) and must be put in place once:

| What                                                                                  | Where                                         | Source                                   |
| ------------------------------------------------------------------------------------- | --------------------------------------------- | ---------------------------------------- |
| Raw TIFFs (batches 1–3, unknown)                                                      | `ReferenceBatches/Batch_1..3/`, `data/raw/unknown/` | your local dataset — see [Dataset](#dataset) |
| v3 model weights (`student.pt`, `bid_model.pkl`, `fingerprint_model.pkl`, `v3_model.pkl`, …) | `sem_pipeline/models/`                        | release [lucas-sem-analysis v3](https://github.com/Project-81-83-50/London-AI-x-Science-Hackathon/releases/tag/tagtag), `models_v3.0.zip` |
| v3 known-spot index (`known_spot_index.npz`)                                          | `sem_pipeline/data/processed/`                | same zip                                 |
| Anthropic API key (for **Generate report**)                                           | `sem_pipeline/.env` (see `.env.example`)      | your own key — never commit it           |

Then generate the reference reports once (about 3 minutes; the launchers do not do this):

```bash
.venv/bin/python -m analysis.reports      # Windows: .venv\Scripts\python.exe -m analysis.reports
```

It writes the KPI reference data the Demo's KPI model needs, the GET4 reports and image checks, and the General and
Detailed reports, all under the Git-ignored `data/processed/`. After that, only the **Images** tab needs the reference
TIFFs; rerun it whenever the reference images change.

The Demo and Pipeline pages need a Python 3.14 with PyTorch (CUDA recommended) and the packages in
`sem_pipeline/requirements.txt` and `requirements-gpu.txt`. The launcher records the first interpreter it finds with
them (the website's `.venv` first); if none is recorded, the API uses its own Python when that has PyTorch. The rest of
the website runs from `.venv`.

### Demo and Pipeline on macOS (Apple Silicon, CPU)

Without CUDA the models run on the CPU (about 45 s per location on an M2 Pro). Install the sem_pipeline packages into
the website's own `.venv`; the API then uses that interpreter for runs, so no `v3_python.txt` is needed:

```bash
# model weights + known-spot index from models_v3.0.zip (see the table above)
unzip models_v3.0.zip -d /tmp/models_v3
cp /tmp/models_v3/{student.pt,student.onnx,teacher.txt,bid_model.pkl,fingerprint_model.pkl,v3_model.pkl} sem_pipeline/models/
mkdir -p sem_pipeline/data/processed && cp /tmp/models_v3/known_spot_index.npz sem_pipeline/data/processed/
# PyTorch (macOS wheels from PyPI) and the other sem_pipeline packages
.venv/bin/python -m pip install torch==2.11.0 torchvision==0.26.0 lightgbm==4.7.0 onnxruntime==1.30.0
.venv/bin/python -m pip install --no-deps segmentation-models-pytorch==0.5.0 timm==1.0.30
.venv/bin/python -m pip install huggingface-hub safetensors tqdm pyyaml
# reference reports, including the KPI model's reference data (about 3 minutes)
.venv/bin/python -m analysis.reports
```

DINOv2 weights are downloaded from Hugging Face by `timm` on the first run.

Optional: the Detailed report shows segmentation overlays once the U-Net has been run on each reference location
(from `sem_pipeline/`, once per location), followed by `python -m analysis.v3_report` from the repository root:

```bash
../.venv/bin/python -m src.predict --cpu --bse <BSE.tif> --inlens <Inlens.tif> \
  --out outputs/segmentation/Batch_N/<location>
```

## Research-grounded reports

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

### Evidence and retrieval policy

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

### Offline verification

```bash
.venv/bin/python -m pip install -r requirements-dev.txt
GOLDEN_RTOL=1e-5 GOLDEN_ATOL=5e-7 .venv/bin/python -m pytest -m 'not realdata'
.venv/bin/python -m ruff check .
.venv/bin/python -m ruff format --check .
```

These use the existing CI golden-file tolerances for cross-platform FFT differences. Research tests mock Claude and
scholarly providers, including the full report API-to-engine flow; they do not spend API credits. They cover source
admission, corrective retrieval, citation/ownership checks, cancellation, stale generations and input immutability.
From `frontend/`, run `npm run lint`, `npm run format:check` and `npm run build`.

## Dataset

Reference batches are the local images you supply, not image sets invented or classified by the website. Put the
original TIFFs directly in these Git-ignored folders:

```text
ReferenceBatches/
├── Batch_1/   img_<location>_<detector>.tif   (a " (<n>)" copy number before .tif is also accepted)
├── Batch_2/
└── Batch_3/
data/raw/unknown/   # optional unknown images, kept separate from the reference library
```

The original [Google Drive dataset](https://drive.google.com/drive/folders/12UnB4HYDElXzoR4I0mG7NZ0buSr4QXF6)
remains an optional source (access requires permission from its owner). Legacy `data/raw/batch_1..3/` folders are still
supported. A present `ReferenceBatches/Batch_N` folder takes precedence, even when empty; the API never silently mixes
both sources for one batch. `analysis.fields.batch_dir` uses the same preference when its default input root is used;
an explicit module-level `RAW` override continues to take precedence.

Keep the supplied filenames: `<detector>` is `BSE`, `ETD`, `Inlens` or `SE`. Avoid adding an extra nested batch folder.
Use **Refresh local images** on the first page after adding or replacing files. The API scans the actual directories
at request time, and `GET /batches/inventory` reports the source, image/group counts, detector labels and cover preview.
The gallery supports filename/location search, detector filtering, enlarged previews and original-TIFF downloads.
These operations do not move or alter TIFFs, run AI reports, retrain the classifier or regenerate saved analysis outputs.
Existing analysis/report tabs and the Demo/Pipeline workflows remain separate.

Filenames are checked against the pixels: an earlier copy of the dataset had shuffled location codes and wrong detector
suffixes, so `analysis/fields.py` recovers location groups by image registration and each view's detector from its
contrast (BSE is grainy backscatter, ETD keeps pores black, InLens fills pores and lights up particle rims). Where a
filename disagrees with its image, the gallery shows the corrected `<location>_<detector>` label and marks it.

## Running the components manually

```powershell
# Backend (from the repository root)
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend\app\requirements.txt -r analysis\requirements.txt
.\.venv\Scripts\python.exe -m uvicorn app.main:app --app-dir backend --reload --port 8002

# Frontend (second terminal)
cd frontend
copy .env.example .env
npm install
npm run dev
```

The API's interactive docs are at <http://localhost:8002/docs>, and `GET /health` reports whether it is up.

Analysis outputs are generated by Python modules run from the repository root, for example:

```powershell
.\.venv\Scripts\python.exe -m analysis.reports           # all reference-batch reports
.\.venv\Scripts\python.exe -m analysis.classify --rebuild # classify the unknown batch
```

Every stage — reference reports, GET4 uncertainty, SEM pipeline v3 reports, in-house KPIs, batch match and the
unknown-batch classification — is documented with its commands, outputs and API routes in
[docs/analysis.md](docs/analysis.md).

## Repository layout

```text
.
├── analysis/          # Python package: field grouping, KPIs, classification, GET4, report builders
├── backend/           # FastAPI service (backend/app) and Modal deployment (modal_app.py)
├── batch_match/       # batch-match classifier, a GET4 shim, research experiments
├── docs/              # analysis.md (pipeline and API reference)
├── frontend/          # React + Vite website
├── knowledge/         # verified SEM reference data used by the report agents
├── scripts/           # website launchers: start_website.bat (Windows), start_website.sh (macOS / Linux)
├── sem_pipeline/      # SEM segmentation + batch-ID pipeline (v3), its outputs and agent report runs
├── ReferenceBatches/  # Git-ignored: your reference TIFFs, Batch_1..3
├── data/              # Git-ignored: raw/ (unknown / legacy TIFFs) and processed/ (generated outputs)
└── pyproject.toml     # shared Ruff lint/format configuration
```

Components with their own README: [frontend](frontend/README.md), [batch_match](batch_match/README.md),
[knowledge](knowledge/README.md); `sem_pipeline/` is described by [HANDOFF.md](sem_pipeline/HANDOFF.md).

## Development

```powershell
# Python: lint and format (configuration in pyproject.toml)
.\.venv\Scripts\python.exe -m pip install ruff
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m ruff format .

# Frontend: lint, format and build
cd frontend
npm run lint
npm run format
npm run build
```

Editor settings (indentation, line endings) are in `.editorconfig`. Never commit `.env` files, raw data or model
weights.
