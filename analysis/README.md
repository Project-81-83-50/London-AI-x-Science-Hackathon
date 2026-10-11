# analysis

Python package for the in-house image analysis: grouping views into locations, per-location KPIs, the KPI
classifier, GET4 uncertainty and the report builders the website reads. Run every module from the repository root
with the project's `.venv`; the full reference is [docs/analysis.md](../docs/analysis.md).

| Module | Purpose |
| --- | --- |
| `reports` | run every reference-batch report generator in one command (`python -m analysis.reports`) |
| `fields` | group each batch's images into fields of view and identify every view's detector from its pixels |
| `kpis/` | per-location segmentation KPIs and the detailed KPI report of each batch |
| `classify` | classify the unknown locations as batch 1, 2 or 3 from their KPIs (diagonal LDA) |
| `kpi_single` | the same classifier for one uploaded location (the Demo's KPI model) |
| `get4/` | GET4 uncertainty of phase fractions (area, regularity and between-image factors) |
| `v3_report` | General and Detailed reports built on the SEM pipeline's results, including the GET4 batch uncertainty |
| `v3_unknown` | segment the unknown images with the SEM pipeline |
| `batch_match` | adapter running the earlier batch-match classifier in `batch_match/` |
| `paths` | every folder the modules read from and write to (`python -m analysis.paths` prints them) |

Inputs are the reference TIFFs in `ReferenceBatches/Batch_N/` (else `data/raw/batch_N/`) and `data/raw/unknown/`;
outputs go to the Git-ignored `data/processed/`. Packages: `analysis/requirements.txt`.
