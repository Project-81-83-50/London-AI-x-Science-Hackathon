# backend

FastAPI service behind the website. It serves the images and generated reports, runs Demo uploads through the SEM
pipeline and the KPI model, and produces the research-grounded reports.

```bash
# from the repository root (the launchers in scripts/ do this for you, on port 8002)
.venv/bin/python -m uvicorn app.main:app --app-dir backend --reload --port 8002
```

Interactive API docs: <http://localhost:8002/docs>. Packages: `app/requirements.txt`.

| Path | Purpose |
| --- | --- |
| `app/main.py` | the FastAPI app: logging, CORS, `GET /health`, and the routers |
| `app/routers/images.py` | batch inventory, image listing, cached JPEG previews, TIFF downloads (Images tab) |
| `app/routers/segmentation.py` | SEM pipeline results, General / Detailed reports and overlays |
| `app/routers/get4.py` | GET4 reports (image checks in the General report; the unknown-batch analysis) |
| `app/routers/kpi.py` | per-batch KPI reports and overlays |
| `app/routers/unknown.py` | the unknown batch: uploads, its classification and analysis job |
| `app/routers/v3.py` | Demo runs (`/v3/jobs`), the Pipeline page, the decision rule and report endpoints |
| `app/research/` | the multi-agent, Corrective RAG report engine ([docs/research-reports.md](../docs/research-reports.md)) |
| `app/paths.py` | every file-system location the API reads |
| `app/settings.py` | settings from the environment: `LOG_LEVEL`, `V3_PYTHON` (also `V3_PROJECT_DIR` in `paths.py`) |
| `app/batches.py` | shared helpers: batch IDs, raw-image folders, reading generated JSON |
| `modal_app.py` | optional Modal deployment of the API as a cloud URL |

Demo runs execute `python -m src.bid_explain predict` in `sem_pipeline/` with a Python that has PyTorch (`V3_PYTHON`,
`sem_pipeline/website/v3_python.txt`, or the API's own interpreter), then `python -m analysis.kpi_single`; see
[docs/architecture.md](../docs/architecture.md).
