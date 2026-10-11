# SEM Batch Identification — London AI × Science Hackathon (Track 4)

Identify which manufacturing batch an SEM image of a graphite + SiOx battery anode came from, explain the call with
visible material evidence, and state how certain it is.

Three reference batches of SEM images are known; each location of an unknown batch must be assigned to batch 1, 2 or
3, with an explanation and a stated uncertainty (Track 4, *Materials manufacturing*, set by Polaron).

## What it does

- **Segments** every location into pore, graphite, SiOx and binder with a label-free U-Net, and gives every phase
  fraction a 95 % sampling interval (GET4).
- **Classifies** a location: 90 % a KPI model on the raw BSE / ETD / InLens images, 10 % a material model (U-Net
  features + DINOv2); confidence is High only when both agree. Training images are refused and re-shot known spots
  recognised.
- **Explains** each call with a research-grounded report written by a small team of Claude agents with Corrective RAG.

How the parts fit together: [docs/architecture.md](docs/architecture.md).

## Quick start

1. Put the reference TIFFs in `ReferenceBatches/Batch_1..3/` and unpack the trained models from release
   [`models_v3.0.zip`](https://github.com/Project-81-83-50/London-AI-x-Science-Hackathon/releases/tag/tagtag) (which
   file goes where: [docs/getting-started.md](docs/getting-started.md#files-you-must-add-locally)).
2. Start the website: `scripts\start_website.bat` on Windows, `./scripts/start_website.sh` on macOS / Linux. It sets up
   `.venv` and the frontend on first run, then opens <http://localhost:5173>.
3. Once, generate the reference reports: `.venv/bin/python -m analysis.reports` (Windows:
   `.venv\Scripts\python.exe -m analysis.reports`).

The Demo needs PyTorch and the pipeline packages, and **Generate report** needs an Anthropic API key; both are covered
in [docs/getting-started.md](docs/getting-started.md), including a macOS (CPU) setup.

## Data that is not in Git: `ReferenceBatches/` and `data/`

Both folders are listed in `.gitignore`, so `git add .` skips them and they are never pushed to GitHub. Every
teammate creates them locally.

| Folder | What it holds | Why it is not in Git |
| --- | --- | --- |
| `ReferenceBatches/Batch_1..3/` | the original SEM TIFFs of the three reference batches (93 images, about 1.6 GB) | far beyond GitHub's file and repository limits (100 MB per file), and the dataset is shared only with its owner's permission, so it must not be published |
| `data/raw/unknown/` | optional TIFFs of the unknown batch | same reasons as above |
| `data/processed/` | everything generated from the images: KPI data, GET4 reports, General / Detailed reports, previews, research caches | generated output: it can always be rebuilt from the images, and would go stale in Git |

The trained models (`sem_pipeline/models/`) are excluded for the same reason and come from the GitHub release instead
(see Quick start).

### Recreating `ReferenceBatches/`

1. Get access to the original
   [Google Drive dataset](https://drive.google.com/drive/folders/12UnB4HYDElXzoR4I0mG7NZ0buSr4QXF6) from its owner (or
   ask a teammate who has the files).
2. Download the three batch folders and put the TIFFs directly in `ReferenceBatches/Batch_1/`, `Batch_2/` and
   `Batch_3/` at the repository root, keeping the original names (`img_<location>_<detector>.tif`; no extra nested
   folders). `ReferenceBatches/` should hold 21, 21 and 51 TIFFs.
   - Alternatively, once you have access, `python scripts/fetch_missing.py` (run from `batch_match/`) downloads the
     files listed in `batch_match/scripts/drive_files.json` into `batch_match/data/batches/`; move them into
     `ReferenceBatches/Batch_N/` afterwards.
3. On the website's first page, click **Refresh local images**: each batch should show its images.

### Recreating `data/`

With `ReferenceBatches/` in place, run once from the repository root (about 3 minutes):

```bash
.venv/bin/python -m analysis.reports      # Windows: .venv\Scripts\python.exe -m analysis.reports
```

This creates `data/processed/` (KPI data for the Demo's KPI model, GET4 reports, General and Detailed reports).
Image previews and research caches are added by the website as it is used. Rerun the command whenever the reference
images change. `data/raw/unknown/` is only needed if you have unknown-batch images: copy those TIFFs there.

## The website

- **Batches** — the reference batches 1–3 (tabs: **Images**, **General report** with "How sure are these numbers?",
  **Detailed report**) and the unknown batch with each location's batch call.
- **Demo** — upload the BSE + InLens (+ ETD, recommended) images of one location to get its batch and confidence.
- **Pipeline** — every step of a run, and **Generate report** for the agent-written explanation.

## Documentation

| | |
| --- | --- |
| [Getting started](docs/getting-started.md) | install, data and model files, macOS, running the parts by hand |
| [Architecture](docs/architecture.md) | components, how one location is classified, where outputs live |
| [Analysis reference](docs/analysis.md) | every analysis stage with its command, outputs and API routes |
| [Research reports](docs/research-reports.md) | the agent-written reports: configuration, evidence policy, CLI |
| [Development](docs/development.md) | tests, linting, repository layout and conventions |

## Repository at a glance

```text
frontend/      React + Vite website          backend/       FastAPI service
analysis/      KPIs, classifier, GET4        sem_pipeline/  v3 SEM pipeline (U-Net, DINOv2, models)
batch_match/   earlier classifier            knowledge/     reference data for the report agents
docs/          documentation                 tests/         pytest suite
scripts/       website launchers
```

Never commit `.env` files, raw images or model weights.
