# sem_pipeline

The v3 SEM pipeline: label-free four-phase segmentation (U-Net), DINOv2 texture features, the material model, the
training-image guard and known-location matcher, and GET4 error bars. The website runs it for Demo uploads; how it
fits into the system is in [docs/architecture.md](../docs/architecture.md). Its decisions, state and open issues are in
[HANDOFF.md](HANDOFF.md), its evaluation results in [reports/report.md](reports/report.md).

Run everything from this folder; the stages are modules of the `src` package:

```bash
python -m src.bid_explain predict --bse X_BSE.tif --inlens X_Inlens.tif [--etd X_ETD.tif] --out out_dir  # one location
python -m src.predict --bse X_BSE.tif --inlens X_Inlens.tif --out out_dir [--cpu]                       # segmentation only
python run_pipeline.py [--from STAGE | --only STAGE ...]   # rebuild everything (GPU); run_cpu_pipeline.py on CPU
```

| Path | Contents | In Git? |
| --- | --- | --- |
| `src/` | one module per stage; `config.py` holds every path and constant | yes |
| `run_pipeline.py`, `run_cpu_pipeline.py` | run the stages in order | yes |
| `models/` | trained weights, from release `models_v3.0.zip` (`student_split.json` is committed) | no |
| `data/` | `manifest.csv`, `qc.csv`, `exclusions.json`, `baseline/`; `processed/` (known-spot index, caches) | partly |
| `outputs/metrics/`, `outputs/batchid/` | results for the 31 reference locations, read by the website's reports | yes |
| `outputs/segmentation/` | label maps and overlays of the reference locations | no |
| `website/` | `runs/` (Demo and unknown-batch runs) and `agents.py`, an entry point to the backend's report engine | partly |
| `reports/` | the results report and its figures | yes |
| `docs/` | `PROJECT_EXPLAINED.md` (pitch explainer), `facts_json_explained.md`; `archive/` holds the original task plan and agent prompts | yes |
| `prior_analysis/` | the earlier vision-LLM analysis; its saved results feed `data/baseline/` via `src.manifest` | yes |

Packages: `requirements.txt` (CPU parts) and `requirements-gpu.txt` (PyTorch stack). The macOS (CPU) setup is in
[docs/getting-started.md](../docs/getting-started.md).
