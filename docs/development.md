# Development

Tests, linting, formatting and the conventions the repository follows. CI (`.github/workflows/ci.yml`) runs
the same checks on every push and pull request.

## Offline verification

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

## Lint, format and build


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

## Repository layout

```text
.
├── README.md            # what the project is, quick start, where to read next
├── docs/                # getting started, architecture, analysis reference, research reports, development
├── frontend/            # React + Vite website (its own package.json, lint and format config)
├── backend/             # FastAPI service (backend/app) and the Modal deployment (modal_app.py)
├── analysis/            # Python package: view grouping, KPIs, classification, GET4, report builders
├── sem_pipeline/        # the v3 SEM segmentation + batch-ID pipeline, its committed results and example runs
├── batch_match/         # the earlier batch-match classifier and its research experiments
├── knowledge/           # verified SEM reference data used by the report agents
├── scripts/             # website launchers: start_website.bat (Windows), start_website.sh (macOS / Linux)
├── tests/               # pytest suite for every Python component; golden files in tests/golden/
├── .github/workflows/   # CI: Ruff, pytest, frontend lint / format / build
├── pyproject.toml       # shared Ruff and pytest configuration
├── requirements-dev.txt # Ruff and pytest (runtime packages are pinned per component)
├── ReferenceBatches/    # Git-ignored: your reference TIFFs, Batch_1..3
└── data/                # Git-ignored: raw/ (unknown / legacy TIFFs) and processed/ (generated outputs)
```

## Where things go

- **Code** belongs to one component. Add new folders to that component's paths module (`backend/app/paths.py`,
  `analysis/paths.py`, `sem_pipeline/src/config.py`) rather than hard-coding them in the module that uses them.
- **Dependencies** are pinned per component: `backend/app/requirements.txt`, `analysis/requirements.txt`,
  `sem_pipeline/requirements.txt` (+ `requirements-gpu.txt`), `frontend/package.json`; tools in `requirements-dev.txt`.
- **Generated files** go under the Git-ignored `data/processed/` (or `sem_pipeline/outputs/segmentation/`), never
  next to the code. Rebuild them with `python -m analysis.reports`.
- **Data and weights** (TIFFs, `.pt` / `.pkl` / `.onnx`, `.env`) are never committed; see
  [getting-started.md](getting-started.md) for where they come from.
- **Tests** go in `tests/`. Numerical outputs are compared with golden files; regenerate them deliberately with
  `UPDATE_GOLDEN=1` and review the diff. Tests that need the raw images are marked `realdata`.
- **Docs**: user-facing pages in `docs/`, short component notes in each component's README. Superseded material goes in
  an `archive/` folder (e.g. `sem_pipeline/docs/archive/`) rather than next to current docs.
