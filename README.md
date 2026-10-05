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
   domain with a label-free U-Net; GET4 attaches a 95 % sampling interval to every phase fraction.
3. **Classify.** A KPI model (`analysis/classify.py`) decides the batch; the v3 material model and the batch-match
   classifier (`batch_match/`) act as independent checks.
4. **Explain.** Three Claude agents turn the numeric evidence into a written report.

The full method, with evaluation results and limitations, is in [docs/methods.md](docs/methods.md).

## Quick start (Windows)

Run [scripts/start_website.bat](scripts/start_website.bat) (double-click it, or run it from a terminal). On first run it
creates `.venv`, installs the backend and frontend dependencies, starts the API on port 8002 and the website on port
5173, and opens <http://localhost:5173>. Close the two server windows to stop it.

The website has three pages:

- **Batches** — reports for reference batches 1–3 and the unknown batch, including each unknown location's batch call.
- **Demo** — upload the BSE + InLens (+ ETD) images of one location to get its batch and confidence (about 1.5 min on a
  GPU).
- **Pipeline** — every intermediate output of a run, and **Generate report** for the agent-written explanation.

### Files you must add locally

These are not in Git (see `.gitignore`) and must be put in place once:

| What                                                                                  | Where                                         | Source                                   |
| ------------------------------------------------------------------------------------- | --------------------------------------------- | ---------------------------------------- |
| Raw TIFFs (batches 1–3, unknown)                                                      | `data/raw/batch_1..3/`, `data/raw/unknown/`   | team Google Drive — see [Dataset](#dataset) |
| v3 model weights (`student.pt`, `bid_model.pkl`, `fingerprint_model.pkl`, `v3_model.pkl`, …) | `sem_pipeline/models/`                        | release `lucas-sem-v3.0`, `models_v3.0.zip` |
| v3 known-spot index (`known_spot_index.npz`)                                          | `sem_pipeline/data/processed/`                | same zip                                 |
| Anthropic API key (for **Generate report**)                                           | `sem_pipeline/.env` (see `.env.example`)      | your own key — never commit it           |

The Demo and Pipeline pages need a Python 3.14 with PyTorch (CUDA recommended) and the packages in
`sem_pipeline/requirements.txt` and `requirements-gpu.txt`; the launcher records that interpreter's path the first time
it finds one. The rest of the website runs from `.venv`.

## Dataset

The microscopy dataset is stored outside Git. Download the batch folders from the
[Google Drive dataset](https://drive.google.com/drive/folders/12UnB4HYDElXzoR4I0mG7NZ0buSr4QXF6) (the folder owner must
grant your Google account access) and extract them so the TIFFs sit directly in these folders:

```text
data/
└── raw/
    ├── batch_1/   img_<location>_<detector> (<n>).tif
    ├── batch_2/
    ├── batch_3/
    └── unknown/
```

Keep the supplied filenames: `<detector>` is `BSE`, `ETD`, `Inlens` or `SE`. Files must not be nested in an extra
`Batch_N` folder. Restart the backend after adding or replacing images.

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
├── docs/              # methods.md (scientific method), analysis.md (pipeline and API reference)
├── frontend/          # React + Vite website
├── knowledge/         # verified SEM reference data used by the report agents
├── scripts/           # start_website.bat launcher
├── sem_pipeline/      # SEM segmentation + batch-ID pipeline (v3), its outputs and agent report runs
├── data/              # Git-ignored: raw/ (TIFFs) and processed/ (generated outputs)
└── pyproject.toml     # shared Ruff lint/format configuration
```

Each component has its own README: [frontend](frontend/README.md), [batch_match](batch_match/README.md),
[sem_pipeline](sem_pipeline/README.md), [knowledge](knowledge/README.md).

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
