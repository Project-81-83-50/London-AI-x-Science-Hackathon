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

![The General report of reference batch 1: composition with 95 % intervals and the comparison with batches 2 and 3](docs/images/general-report.jpg)

### How a location's batch is decided

1. **KPI model (90 % of the probability).** The raw BSE image is split into three brightness classes and compared
   pixel by pixel with the ETD and InLens views, giving 32 KPIs. A diagonal LDA, fitted on the 31 reference locations,
   uses the most batch-separating KPIs that were measured for this location (usually *ETD-dark solid*: area dark in
   ETD but solid in BSE, which needs an ETD image).
2. **Material model (10 %, and the check).** Five measurements from the U-Net segmentation plus DINOv2 texture
   features, calibrated on the references.
3. **Answer and confidence.** The batch with the highest combined probability. Confidence is **High** when the KPI
   model is at least 50 % sure *and* the material model picks the same batch, otherwise **Low**.
4. **Overrides.** An image identical to a training image is refused; a re-shot of a known reference location gets that
   location's batch.

## Requirements

- Python 3.14 (tested) and Node.js 22 (as in CI).
- For the Demo: PyTorch and the SEM-pipeline packages. A CUDA GPU is fastest; a recent laptop CPU (tested on an
  Apple M2 Pro) takes about 45 s per location.
- The reference TIFFs (about 1.6 GB) and the trained models from the GitHub release; neither is in Git.
- For **Generate report** only: an Anthropic API key.

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

## Results

All accuracies are leave-one-location-out on the 31 reference locations (7 / 7 / 17): each location is predicted by
models that never saw it. Balanced accuracy is used because Batch 3 dominates; chance is 33 %.

| What | Result |
| --- | --- |
| Segmentation vs. a blind independent annotator | 87 % (pore / carbon / SiOx), 82 % with binder separate; binder precision only ~0.5 |
| KPI model (90 % of the decision) | 68 % balanced accuracy, nested test, permutation p = 0.005; recall 71 / 57 / 76 % for batches 1 / 2 / 3 |
| Material model (10 %) | 61 % balanced accuracy, permutation p = 0.005 |

Calls for the nine unknown locations:

| Answer | Locations | Confidence |
| --- | --- | --- |
| Batch 3 | `0eryguqq`, `fhwrjtet`, `xrv9xvzb` | High |
| Batch 1 | `4hq27w4c`, `fn0mhxef` | High |
| Batch 1 | `y59rxmxl` | Low (material model says Batch 2) |
| Batch 2 | `3e122cbj` | Low (material model disagrees) |
| Batch 2 | `fspqbkxl`, `soo2ax3r` | Low (KPI model below 50 %) |

Details: [sem_pipeline/reports/report.md](sem_pipeline/reports/report.md) and [docs/analysis.md](docs/analysis.md).

## Troubleshooting

| Symptom | Cause and fix |
| --- | --- |
| "API unreachable" at the bottom of the Batches page | The API is not running: start it with the launcher (or see [running the parts by hand](docs/getting-started.md#running-the-components-manually)) and check that `frontend/.env` points to its port. |
| A batch card says *Folder not found* or shows 0 images | `ReferenceBatches/Batch_N/` is missing or has a nested folder; see [Recreating `ReferenceBatches/`](#recreating-referencebatches), then click **Refresh local images**. |
| General or Detailed report: "No v3 report …" | Reports were never generated: run `python -m analysis.reports`. |
| Demo fails at "U-Net segmentation" or straight away | The model files or PyTorch are missing: unpack `models_v3.0.zip` and install the pipeline packages ([getting started](docs/getting-started.md)). |
| Demo answer is refused | The upload is pixel-identical to a reference image; this is by design. |
| **Generate report** fails with a credentials error | Set `ANTHROPIC_API_KEY` in `sem_pipeline/.env` (copy `.env.example`), then try again. |

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
