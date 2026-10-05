# Analysis pipeline reference

How each analysis stage is run, what it writes and which API route serves it. Run every command from the repository
root with the project virtual environment. All outputs go to the Git-ignored `data/processed/`.

## Generate reference reports

After copying images directly into `data/raw/batch_N/`, generate the reference-batch reports from the repository root with one command:

```powershell
.\.venv\Scripts\python.exe -m analysis.reports
```

The command detects populated `batch_N` folders and runs the KPI, fast GET4, and General/Detailed report generators in sequence. It stops and reports an error if any generator fails. Use `--full-resolution` to run GET4 at full resolution and create its per-image diagnostic plots:

```powershell
.\.venv\Scripts\python.exe -m analysis.reports --full-resolution
```

Reports are written under `data/processed/`. The General/Detailed report builder summarizes the v3 results already included in the repository; it does not retrain or re-segment the v3 model. Run this command again after changing the reference images. The running backend reads the generated files when requests are made; refresh the frontend to load the updated reports.

## GET4 batch uncertainty analysis

GET4 can run a separate uncertainty analysis for every `data/raw/batch_N` folder. Install its Python packages from the repository root, then optionally check which images it will use:

```powershell
.\.venv\Scripts\python.exe -m pip install -r analysis\requirements.txt
.\.venv\Scripts\python.exe -m analysis.get4 --project --list-only
```

For the full-resolution analysis and per-image diagnostic plots, run:

```powershell
.\.venv\Scripts\python.exe -m analysis.get4 --project --out data\processed\get4
```

To create reports faster, use:

```powershell
.\.venv\Scripts\python.exe -m analysis.get4 --project --fast --out data\processed\get4
```

Fast mode uses 2x coarser sampling by default when image calibration is available and no `--bin`, `--target-px`, or baseline is supplied; without calibration it keeps GET4's existing 2x binning fallback. It skips per-image diagnostic plots but still runs segmentation and uncertainty calculations, writes website-ready `analysis_report.json` and uncertainty JSON, and retains batch plots. The report records fast mode and its sampling scale in `analysis_settings`; the website does not flag it. Run without `--fast` for full-resolution analysis and per-image plots. Use `--project --list-only` to check which files and location codes will be included.

Project mode reads the filename location code (`img_<location>_<detector> (N).tif`) and analyses every recognized detector separately within each batch. For example, `img_4ih2ggld_BSE (6).tif` is location `4ih2ggld` imaged with BSE. Results are written under `data/processed/get4/batch_N/<DETECTOR>/`; `location_manifest.json` links all detector views that share a location code.

When a reference batch is selected in the frontend, its website-ready report is requested from `GET /batches/{batch_id}/analysis-report?detector=BSE` (replace `BSE` with the selected filter). The generated `analysis_report.json` contains provisional image-derived KPI candidates for BSE, detector-intensity metrics for other filters, per-location evidence, confidence intervals, quality flags, and a machine-readable decision status. Generate the GET4 reports locally before expecting results to appear.

The unknown batch has the same **Uncertainty (GET4)** tab, served by `GET /batches/unknown/analysis-report?detector=BSE`. You don't generate it by hand: the unknown-batch analysis job runs `python -m analysis.get4 --project --fast --batch unknown` after the KPI classification (about 30 s for three locations) and writes to `data/processed/get4/unknown/`. `--batch` limits project mode to the named `data/raw` folders; without it, project mode analyses every `batch_N` folder as before.

Each batch is a separate battery, so reports do not compare one batch against another or use a cross-batch baseline. No accept/watch/reject verdict is assigned unless approved KPI limits are defined. Different detector views of one location are linked as related observations, not pooled as independent locations. BSE uses GET4's provisional pore/graphite/bright intensity segmentation; ETD, InLens, and other recognized detectors report low/mid/high intensity classes only, because the BSE material-phase labels are not validated for those filters. Inspect each segmentation plot before interpreting any fractions as material properties. The reports estimate segmentation/sampling uncertainty within each detector group; they do not prove a change in battery properties or match images to source batches.

## General and detailed reports (SEM pipeline v3)

For batches 1–3, the frontend's **General report** and **Detailed report** tabs are built on the SEM pipeline's (v3) machine-learning four-phase segmentation, not on the intensity classes of `analysis/kpis/`. `analysis/v3_report.py` reads the committed outputs in `sem_pipeline/outputs/`, so it needs neither the v3 model weights nor a GPU, and writes one file per batch to `data/processed/v3_report/batch_N.json` (about 30 seconds):

```powershell
.\.venv\Scripts\python.exe -m analysis.v3_report
```

- **General report:** the batch at a glance.
  - Composition as three phases: pore / carbon / SiOx. This split agrees with an independent annotator 87% of the time; binder precision is only about 0.5.
  - A chart placing the batch against the other two on seven segmentation metrics.
  - Plain-language key findings, each marked *holds within sessions* or *may be session*.
  - Segmentation accuracy, v3's batch-decision record for the batch, and caveats.
- **Detailed report:**
  - **Every location:** three-phase fractions with v3's standard errors, four phases, deep/open pores, SiOx density, size and spacing, segmentation stability and v3's decision.
  - **Every metric:** batch means ± SD, Kruskal-Wallis p with Benjamini-Hochberg q, a within-session permutation p, Holm-corrected pairwise p and Cliff's delta.
  - **SiOx size distribution:** from v3's 4,587 measured particles.
  - **Batch-decision table**, and v3's 35 threshold-based image KPIs as a supplement, with the pipeline's session-sensitivity flags.

A difference "holds within sessions" when it survives a test that shuffles batch labels only inside imaging sessions (image-height groups). On the current data only the pore fraction does: batch 1 has 14.3% pores, against 17.8% for batch 2 and 18.2% for batch 3. The route is `GET /batches/{batch_id}/v3-report`.

### The unknown batch

The unknown batch gets the same two reports, laid out like a reference batch's. Its locations are the report's own batch ("U" in the charts), shown against batches 1–3. A report is produced even when only one image has been uploaded. v3's delivered U-Net weights are a release asset that isn't in this repository, so `analysis/v3_unknown.py` segments the unknown images with v3's LightGBM **teacher** instead. `sem_pipeline/run_cpu_pipeline.py` rebuilds the teacher from the committed labels, with no API calls. Train it once, which takes about an hour on an 8-core laptop:

```powershell
cd sem_pipeline
$env:SEM_WORKERS = 4
..\.venv\Scripts\python.exe run_cpu_pipeline.py      # writes models/teacher_cpu.txt and the reference overlays
cd ..
.\.venv\Scripts\python.exe -m analysis.v3_unknown                  # segment + measure -> data/processed/v3_unknown/
.\.venv\Scripts\python.exe -m analysis.v3_report --unknown-only    # -> data/processed/v3_report/batch_unknown.json
```

`analysis/v3_unknown.py` runs v3's own steps on each unknown BSE + InLens pair:

1. normalisation, border and Cu-foil exclusion;
2. 27 features per detector;
3. the teacher;
4. the SiOx physics constraint and clean-up;
5. SiOx particle instances.

The detectors come from the pixels, via `analysis/fields.py`. A location with only one usable image (BSE, InLens or ETD/SE) is segmented by a **one-detector model** distilled from the teacher:

- It is trained on the teacher's confident pixels of the reference locations, with that detector's features only.
- It is first fitted on v3's student training split and scored against the teacher on the 6 held-out locations (pixel agreement and phase-fraction differences), then refitted on all 31.
- The three models are trained once, on the first run (a few minutes), into `data/processed/v3_unknown/models/`.
- Their held-out scores are shown in both reports.

Without BSE, the deep/open pore split, which is defined on BSE, is not measured.

The teacher's fractions differ from the U-Net's by up to about 5 percentage points of pore. So for a like-for-like comparison, the 31 reference locations are re-measured from the **same teacher's** label maps, not taken from the U-Net numbers in the reference reports. Each unknown location is then placed against those reference batches, metric by metric: the closest batch mean, the distance to each batch in pooled SDs, and which batch ranges it falls inside. The reports describe the material; the batch calls stay in the Classification tab.

Once the teacher exists, the upload / delete analysis job runs both commands automatically after the classification. Routes: `GET /batches/unknown/v3-report` and `GET /batches/unknown/v3-report/overlays/{location_id}`.

## In-house KPIs (analysis.kpis), used by the classifier

`analysis/kpis/` measures every batch independently, without using GET4, by its own intensity-class segmentation. Its KPIs feed the unknown-batch classifier (Classification tab); its report is no longer shown as a tab, but `GET /batches/{batch_id}/kpi-report` still serves it. Install its packages once, then run it from the repository root:

```powershell
.\.venv\Scripts\python.exe -m pip install -r analysis\requirements.txt
.\.venv\Scripts\python.exe -m analysis.kpis
```

`analysis/kpis/` first groups each batch's images into fields with `analysis/fields.py`. It reuses the cached manifest in `data/processed/fields/batch_N.json` unless the raw files have changed; pass `--rebuild-fields` to force re-matching. To rebuild only the field manifests, which takes about 30 seconds, run `.\.venv\Scripts\python.exe -m analysis.fields`.

A full run of batches 1–3 takes about three minutes. Use `--batches 1` to rerun a single batch; the summary file keeps the other batches' results. The outputs are written under `data/processed/batch_kpis/`, which Git ignores:

- `batch_N/report.json` holds the KPI breakdown for one batch.
- `batch_N/overlays/<location>.jpg` is a segmentation preview for each location.
- `summary.json` holds each batch's headline KPIs, used for the reference comparison strips.

The API serves them at `GET /batches/{batch_id}/kpi-report`, `GET /batches/{batch_id}/kpi-report/overlays/{location_id}` and `GET /kpi-reports/summary`. Restart the backend after adding the routes, and rerun the script whenever the raw images change.

How it works:

- **Matching fields.** Each image is reduced to an edge map, which looks similar whatever the detector contrast. Every pair in a batch is then phase-correlated: unrelated pairs score at most 0.03, and views of one field score 0.06–0.5. Pairs are merged strongest first, with at most three views per field. Each batch then splits into as many fields as it has filename codes: 7, 7 and 17. Each matched field is one replicate in the statistics.
- **Choosing a view.** The filename detector labels are not reliable: several files labelled `BSE` show the rim-lit edges of an InLens/SE image, and some `Inlens`/`ETD` files show clean composition contrast. So the script test-segments every view of a field and analyses the one whose bright phase forms compact particles at a plausible loading. If no view qualifies, the field is shown in the report but left out of the batch statistics.
- **KPIs.** Each analysed view is segmented into pore, graphite and bright phase. The KPIs cover phase composition, the pore network, bright-particle size and spread, graphite texture and orientation, interface density, Bruggeman transport estimates, and how evenly pores are spread within each image.
- **Statistics.** Each KPI is reported as the mean, SD, CV, t-based 95% CI and per-location values across the analysed locations.

The phases are intensity classes and have not been validated against labelled or EDS data, and no pass/fail limits are defined.

## SEM pipeline v3 (`sem_pipeline/`)

The General and Detailed reports (above) show the results of `sem_pipeline/`, the third iteration of the SEM segmentation pipeline; its own README and HANDOFF explain the method. The API locates it through `SEM_PIPELINE_DIR` in `backend/app/paths.py`.

v3 segments each location's BSE and InLens images into four phases: pore, graphite, SiOx and carbon-binder domain (CBD). It then decides the batch with two independent models, an imaging fingerprint and a material model. When they agree it gives one batch; when they split between batches 1 and 2 it answers "Batch 1 or Batch 2"; otherwise it answers "unsure". Tested by holding out each of the 31 reference locations in turn, it answered 26 of them and was right on 22 (85%).

v3 reads the shared `data/raw/batch_N` folders. Its committed results were computed on byte-identical files: all 93 SHA-256 hashes match `sem_pipeline/data/manifest.csv`. The frontend shows:

- phase tiles and per-location composition,
- the decision table (answer, confidence, each model's pick, right / wrong / abstained),
- segmentation overlays, when present.

The overlays need label maps, which are not in Git. To rebuild them on a CPU-only machine, install the extra package once and run v3's CPU pipeline:

```powershell
.\.venv\Scripts\python.exe -m pip install lightgbm==4.7.0
cd sem_pipeline
$env:SEM_WORKERS = 3     # fewer parallel processes for machines with < 16 GB RAM
..\.venv\Scripts\python.exe run_cpu_pipeline.py
```

The CPU pipeline makes no API calls, and it writes `outputs/segmentation/`. The paid stages (`src/ai_labels.py`, `src/ai_validate.py`, `src/triangle_test.py`) call the Anthropic API, so don't re-run them unless you mean to. The API routes are `GET /batches/{batch_id}/segmentation-report` and `GET /batches/{batch_id}/segmentation-report/overlays/{sample_id}`.

## Batch match (`batch_match/`)

`batch_match/` holds the batch-match classifier, `batch_classifier.py`, together with `get4.py`, a shim over `analysis.get4` (the single GET4 implementation) that the classifier imports as a library; see `batch_match/README.md`. `analysis/batch_match.py` connects it to this project: it reads the references from `data/raw/batch_N` and the unknown images from `data/raw/unknown`, and keeps its caches and model in `data/processed/batch_match/`.

The classifier decides each unknown image in this order:

1. It refuses an image identical to a training image.
2. It matches a known location.
3. It applies a GET4 material-range rule.
4. It uses fingerprint and texture models.

It answers "unsure" below its 90%-accuracy thresholds. Train it once, which takes roughly 40 minutes because GET4 measures every reference BSE image, then use it:

```powershell
.\.venv\Scripts\python.exe -m analysis.batch_match train      # writes data/processed/batch_match/batch_model.pkl
.\.venv\Scripts\python.exe -m analysis.batch_match evaluate   # track record -> data/processed/batch_match/evaluation_report.json
.\.venv\Scripts\python.exe -m analysis.batch_match predict    # writes data/processed/batch_match/unknown.json
```

Once the model exists, the unknown-batch analysis job runs `predict` automatically after the KPI classification. The frontend shows the result as a **second opinion** under each location in the Unknown → Classification tab, served by `GET /unknown/batch-match`. If batch match fails, the failure is logged and the KPI classification still stands.

`evaluate` runs the classifier's own nested leave-one-location-out tests (about 5 minutes each): each reference location is hidden, the models and answer thresholds are refitted without it, and it is then predicted. The tests run twice, once in the default mode and once in the always-answer mode. Unlike the standalone script, the report keeps every held-out answer with its confidence. It records:

- how often the classifier answers rather than saying "unsure",
- how often its answers are right, with a 95% Wilson interval,
- right, wrong and unsure counts per batch.

The Classification tab shows this track record next to the KPI model's accuracy, in a confidence-against-outcome chart with one dot per held-out location. Each unknown location's answer then shows its confidence and how often held-out locations at that confidence or higher were right. Known-location matches are not part of the test: they are exact field matches, and are treated as certain. The route is `GET /unknown/batch-match/evaluation`.

GET4 has one implementation, the `analysis/get4/` package: it produces the per-batch GET4 tab (see above), and batch match (`batch_match/get4.py`) and the SEM pipeline (`sem_pipeline/src/get4.py`) use it through thin shims.

## Unknown batch classification

In the frontend, **Unknown** sits in the batch picker next to batches 1–3. Its tabs are **Images**, **General report** and **Detailed report** (v3 segmentation, see above) and **Classification** (each location's batch call with evidence). New unknown images are added through the API (there is currently no upload tab in the UI): `PUT` `.tif` files named `img_<location>_<BSE|ETD|Inlens|SE>.tif`. The API checks each file and refuses it with a clear message if any of these fail:

- the name must follow that pattern exactly,
- the file must start with a real TIFF header and be under 300 MB,
- it must not be byte-identical to an image already in the unknown batch,
- a file with the same name is only replaced when the request sets `overwrite=true`.

Accepted files are saved to `data/raw/unknown/`. Start the analysis below with `POST /unknown/analysis` (about 30 s per location). The routes are:

- `PUT /batches/unknown/images/{image_name}` uploads one file as the raw request body.
- `DELETE /batches/unknown/images/{image_name}` deletes one file and its cached preview.
- `POST /unknown/analysis` starts the analysis, and `GET /unknown/analysis` reports its status and recent log lines.

Uploads and deletions are refused while an analysis is running.

If the last image is deleted, the unknown batch's location grouping, KPI report, classification, batch-match result and v3 reports are removed too, so no stale result remains.

Every location is classified, including one uploaded without a BSE image. Such a location is measured from its InLens or ETD image, and its call is marked low confidence because the model was trained on BSE measurements. Any KPI that cannot be measured takes the reference average, which favours no batch.

If an unknown image is an exact copy of a reference image, or shows the same field as one, that decides its batch with high confidence. The material-KPI model's own call is still shown for comparison.

To run the analysis by hand instead, put the files in `data/raw/unknown/` and run:

```powershell
.\.venv\Scripts\python.exe -m analysis.classify --rebuild
```

This takes about a minute for three locations, and writes `data/processed/classification/unknown.json`, which the frontend's Unknown batch section reads through `GET /unknown/classification`. The steps:

1. **Measure:** the unknown images are grouped into locations, and their detectors are checked from the pixels, by `analysis/fields.py`. Each location's BSE image is then measured by the same `analysis/kpis/` code as the references.
2. **Check for duplicates:** every unknown image is compared with every reference image, by file hash and by image content.
3. **Compare the detectors:** the location's ETD and InLens views are segmented like the BSE view, aligned to it, and compared pixel by pixel, giving 7 cross-detector KPIs (`analysis.kpis.cross_detector`). ETD keeps pores black and InLens fills shallow pores in and lights up particle rims, so where they disagree with BSE says something about the pores and surfaces that BSE alone does not. Example: *ETD-dark solid* is the area that is dark in ETD but solid in BSE (sub-surface pores, shadowed edges or carbon-binder). Measuring the ETD and InLens views on their own, as 50 more separate KPIs, lowered the nested accuracy (53%), so only the comparisons are used.
4. **Classify:** each location gets a probability for batch 1, 2 and 3 from a diagonal LDA. The model ranks all 32 candidate KPIs (25 BSE + 7 cross-detector) by how well they separate the reference batches (ANOVA F) and keeps the best *k*. It chooses *k* from 1, 2, 3, 4, 6, 8 or 12 by an inner leave-one-out test, preferring the smaller *k* on ties. On the current references it keeps one KPI, ETD-dark solid, in 30 of 31 folds. Within the imaging sessions shared by several batches it orders batch 1 below batch 2 in all three such sessions and batch 2 below batch 3 in two of three, so it mostly reflects the material, not the imaging. It does depend on detector settings too: a within-session label shuffle raises the null accuracy to about 54% (p = 0.06). The output lists the features driving each call and the most similar reference locations.
5. **Test the model on the references:** each reference location is held out in turn, and the *whole* procedure is re-run without it: the KPI ranking, the choice of *k* and the fit. This nested test is needed because choosing features on all 31 locations and then testing on them would overstate the accuracy. A 200-shuffle permutation test repeats the full procedure too. Together with per-batch recall and the KPIs each fold chose, these results are cached in `data/processed/classification/reference_validation.json`. They are recomputed (about 10 minutes) only when the reference KPIs change, so uploads stay fast. The nested balanced accuracy is 68% (permutation p = 0.005), up from 58% with BSE KPIs only and 48% for the earlier fixed eight-KPI model; wider searches over model types scored lower in the same nested test. Chance is 33%. Per-batch recall is 71% / 57% / 76%.
6. **Show a session hint:** the reference batches imaged at the same image height are listed separately, because image height marks the imaging session. The hint is not used by the model.

Images in the unknown set are also available through the image routes as batch `unknown`, for example `GET /batches/unknown/images` and `GET /batches/unknown/kpi-report`.
