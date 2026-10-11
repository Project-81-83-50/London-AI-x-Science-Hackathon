# Architecture

What the system does, how its parts fit together, and where every output lives. For installation see
[getting-started.md](getting-started.md); for every command and API route see [analysis.md](analysis.md).

## The problem

Track 4 (*Materials manufacturing*, set by Polaron): three reference batches of SEM images of a graphite + SiOx
battery anode are known. Images within a batch show the same electrode at different locations and with different
detectors (BSE, InLens, ETD/SE), so views of one location are compared as a group rather than treated as different
materials. Each location of an unknown batch must be assigned to batch 1, 2 or 3, with an explanation and a stated
uncertainty.

## Components

| Folder | What it is | Entry points |
| --- | --- | --- |
| [`frontend/`](../frontend/README.md) | React + Vite website: the Batches, Demo and Pipeline pages | `npm run dev` |
| [`backend/`](../backend/README.md) | FastAPI service: images, reports, Demo runs, research-grounded reports | `uvicorn app.main:app --app-dir backend` |
| [`analysis/`](../analysis/README.md) | Python package: view grouping, KPIs and the KPI classifier, GET4, report builders | `python -m analysis.<module>` |
| [`sem_pipeline/`](../sem_pipeline/README.md) | The v3 SEM pipeline: U-Net segmentation, DINOv2, material model, known-spot matcher | `python -m src.<stage>` (from `sem_pipeline/`) |
| [`batch_match/`](../batch_match/README.md) | The earlier batch-match classifier, kept for comparison | `analysis.batch_match` |
| [`knowledge/`](../knowledge/README.md) | Verified SEM reference data used by the report agents | read by `backend/app/research` |

The website only talks to the API; the API reads generated files and starts the Python tools as subprocesses. Each
component reads its folders from one module: `backend/app/paths.py`, `analysis/paths.py` and `sem_pipeline/src/config.py`.

## How it works

1. **Group and verify views.** `analysis/fields.py` registers images against each other to recover which views show the
   same location and identifies each view's real detector from its pixels.
2. **Segment.** The SEM pipeline segments each location into pore, graphite, SiOx and carbon-binder domain with a
   label-free U-Net (trained without hand labels: rule seeds plus Claude-labelled superpixels, a LightGBM teacher, a
   U-Net student). GET4 attaches a 95 % sampling interval to every phase fraction; the General report pools these per
   batch (how precisely each batch is known, and whether one location can be told apart).
3. **Classify.** A KPI model (`analysis/classify.py`, `analysis/kpi_single.py` for one location) gives 90 % of the
   probability; the v3 material model (U-Net features + DINOv2) gives 10 % and is the agreement check. Confidence is
   High only when the KPI model is at least 50 % sure and both pick the same batch.
4. **Explain.** A decision analyst/coordinator, research librarian, materials writer and independent grounding reviewer
   produce a research-grounded report with Corrective RAG; typed Python checks gate numbers and citations
   ([research-reports.md](research-reports.md)).

## Classifying one location (Demo and Pipeline pages)

`POST /v3/jobs` creates a run folder in `sem_pipeline/website/runs/<job>/`; the uploaded TIFFs go to `input/`. The run
then executes, in order (the Pipeline page shows each step):

| # | Step | Code | Used in the answer? |
| --- | --- | --- | --- |
| 1 | Read BSE + InLens, 50 nm/px, normalise, mask border and Cu foil | `src.predict.prepare` | input to 2–7 |
| 2 | U-Net segmentation (+ SiOx physics constraint) | `src.student`, `src.physics` | via 5 |
| 3 | Five material features from the label map | `src.bid_features.features` | via 5 |
| 4 | DINOv2 patch features (frozen ViT-S/14) | `src.dino` | via 5 |
| 5 | Material model: features + DINOv2 textons, calibrated, with an evidence map | `src.bid_model`, `src.bid_explain`, `src.v3` | 10 % + agreement check |
| 6 | Training-image guard and known-location matcher | `src.known_spot` | can override: refuse / known spot |
| 7 | GET4 sampling intervals and range rule | `src.v3.material_se`, `range_rule` | context only |
| 8 | KPI model on the raw BSE / ETD / InLens images, using only the KPIs measured here | `analysis.kpi_single` | 90 % |
| 9 | Decision: 90 % KPI + 10 % material, High / Low confidence | `backend/app/routers/v3.py` `current_method` | the answer |
| 10 | Agent report, on request | `backend/app/research` | explanation only |

Steps 1–7 run as `python -m src.bid_explain predict` inside `sem_pipeline/` (the earlier imaging-fingerprint and
tile-texture models are also computed there but do not affect the answer). Step 8 runs `python -m analysis.kpi_single`
from the repository root. Everything ends in the run's `output/facts.json`, the text-only record the agents read.

## Where data and outputs live

| Path | Contents | In Git? |
| --- | --- | --- |
| `ReferenceBatches/Batch_1..3/` | your reference TIFFs | no |
| `data/raw/unknown/` | optional unknown TIFFs (legacy reference folders: `data/raw/batch_N/`) | no |
| `data/processed/` | everything `python -m analysis.reports` and the API generate: KPI data, GET4, v3 reports, previews, research caches | no |
| `sem_pipeline/models/`, `sem_pipeline/data/processed/` | trained weights and the known-spot index (release `models_v3.0.zip`) | no |
| `sem_pipeline/outputs/metrics/`, `outputs/batchid/` | the pipeline's committed results for the 31 reference locations | yes |
| `sem_pipeline/outputs/segmentation/` | label maps and overlays of the reference locations | no |
| `sem_pipeline/website/runs/unknown_*/` | the nine unknown-batch runs, committed as examples | yes |
| `sem_pipeline/website/runs/demo_*/` | your Demo uploads and their results | no |
