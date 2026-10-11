# Getting started

How to install and run the website, which files you must add, and where the data goes. For what the system
does, see [architecture.md](architecture.md).

## Quick start

On Windows run [scripts/start_website.bat](../scripts/start_website.bat) (double-click it, or run it from a terminal); on
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

## Files you must add locally

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

## Demo and Pipeline on macOS (Apple Silicon, CPU)

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
[docs/analysis.md](analysis.md).
