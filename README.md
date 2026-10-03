# London AI × Science Hackathon

An attempt at Track 4

## Track 4: Materials manufacturing by Polaron

Can you identify which known battery batch each microscopy image came from?

The first three batches are known reference sets. Images within a batch show the same battery from different angles and with different imaging filters, so those views need to be compared as a group rather than treated as different materials. An unknown batch of images then has to be assigned to batch 1, 2 or 3, with each match explained using visible evidence and with its uncertainty stated.

The frontend presents this workflow: the reference batches with their analysis reports, then the unknown batch with a classification for each location (see [Unknown batch classification](#unknown-batch-classification)).

## Batch image dataset

The microscopy dataset is stored outside Git, so every teammate must download it separately after cloning the repository. Download the batch folders from the [Google Drive dataset](https://drive.google.com/drive/folders/12UnB4HYDElXzoR4I0mG7NZ0buSr4QXF6). The folder owner must allow your Google account to view and download the files.

In File Explorer, download and extract each reference batch so that the TIFF files sit directly inside these folders at the repository root:

```text
data/
└── raw/
    ├── batch_1/
    │   └── img_<specimen>_<filter> (<number>).tif
    ├── batch_2/
    │   └── img_<specimen>_<filter> (<number>).tif
    └── batch_3/
        └── img_<specimen>_<filter> (<number>).tif
```

Create the `batch_1`, `batch_2`, and `batch_3` folders if they are missing. Move the image files themselves into the matching folder; avoid leaving them one level deeper inside an extra `Batch_1`, `Batch_2`, or `Batch_3` folder. Keep the supplied filenames unchanged. The image API recognizes `.tif` files named `img_<specimen>_<filter> (N).tif`, where `<filter>` is `BSE`, `ETD`, `Inlens`, or `SE` and `N` is the number already in the supplied filename. It scans the batch folder itself, not nested subfolders.

An earlier copy of the dataset had shuffled filenames: views of one location carried different `<specimen>` codes, and the `<filter>` suffixes were wrong. `analysis/fields.py` therefore checks every name against the pixels. It recovers which images show the same location by registering them against each other, so a mismatch is caught rather than shown silently. With the corrected filenames, every group's files share one code and every label agrees with its image. It also identifies each view's real detector from the image: BSE is the grainy backscatter view, ETD keeps pores black, and InLens fills pores in and lights up particle rims. This ETD/InLens orientation was calibrated on the corrected filenames. Each group is named with one location code, and every image is labelled with its filename when the filename agrees with the image. If a file's code or filter disagrees with its image, the gallery shows the corrected `<location>_<detector>` label and marks it. If the codes are shuffled, so that several codes fit a group equally well, the group is marked "name assigned". The gallery uses these groups and labels once the manifests exist. Without them, it falls back to filename-code groups and shows a warning.

You can confirm the files are in the right place from PowerShell opened at the repository root:

```powershell
Get-ChildItem .\data\raw\batch_1 -File
Get-ChildItem .\data\raw\batch_2 -File
Get-ChildItem .\data\raw\batch_3 -File
```

The image folders are intentionally excluded from Git, so downloading the repository alone will not download these large datasets. Each teammate must download/extract the images locally. The backend reads them from the repository-root `data\raw` folder. Restart the backend after adding or replacing image files so each teammate is testing against the same local dataset.

## Run locally

Install the backend packages once from the repository root. If `.venv` does not exist yet, create it first with `py -m venv .venv`:

```powershell
.\.venv\Scripts\python.exe -m pip install -r backend\app\requirements.txt
```

Start the API from the repository root in one terminal:

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --app-dir backend --reload --port 8000
```

Start the React app from `frontend` in a second terminal:

```powershell
cd frontend
npm install
npm run dev
```

Open the Vite URL printed in the frontend terminal, normally <http://localhost:5173>. The browser page is served by Vite; `http://localhost:8000` is the API, with interactive docs at <http://localhost:8000/docs>.

Before opening the gallery, check that the API sees each local folder by opening <http://localhost:8000/batches/1/images>, <http://localhost:8000/batches/2/images>, and <http://localhost:8000/batches/3/images>. Each URL should return a JSON list of specimen groups and TIFF filenames. An empty list means the corresponding local folder is empty or the TIFFs are nested/misnamed. Select a reference batch to load its image inventory; select it again to hide the gallery. Image previews and original TIFF downloads are fetched only for the selected batch from the local raw-data folder. `GET /batches/{batch_id}/analysis` remains available for analysis records; image-to-reference matches are not implemented. The default API address is `http://localhost:8000`; if you change it, set `VITE_API_URL` in `frontend/.env` and restart Vite.

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

Fast mode uses 2x coarser sampling by default when image calibration is available and no `--bin`, `--target-px`, or baseline is supplied; without calibration it keeps GET4's existing 2x binning fallback. It skips per-image diagnostic plots but still runs segmentation and uncertainty calculations, writes website-ready `analysis_report.json` and uncertainty JSON, and retains batch plots. The report records fast mode and its sampling scale, and the website labels it so reduced-resolution results are not mistaken for a full-resolution run. Run without `--fast` for full-resolution analysis and per-image plots. Use `--project --list-only` to check which files and location codes will be included.

Project mode reads the filename location code (`img_<location>_<detector> (N).tif`) and analyses every recognized detector separately within each batch. For example, `img_4ih2ggld_BSE (6).tif` is location `4ih2ggld` imaged with BSE. Results are written under `data/processed/get4/batch_N/<DETECTOR>/`; `location_manifest.json` links all detector views that share a location code.

When a reference batch is selected in the frontend, its website-ready report is requested from `GET /batches/{batch_id}/analysis-report?detector=BSE` (replace `BSE` with the selected filter). The generated `analysis_report.json` contains provisional image-derived KPI candidates for BSE, detector-intensity metrics for other filters, per-location evidence, confidence intervals, quality flags, and a machine-readable decision status. Generate the GET4 reports locally before expecting results to appear.

Each batch is a separate battery, so reports do not compare one batch against another or use a cross-batch baseline. No accept/watch/reject verdict is assigned unless approved KPI limits are defined. Different detector views of one location are linked as related observations, not pooled as independent locations. BSE uses GET4's provisional pore/graphite/bright intensity segmentation; ETD, InLens, and other recognized detectors report low/mid/high intensity classes only, because the BSE material-phase labels are not validated for those filters. Inspect each segmentation plot before interpreting any fractions as material properties. The reports estimate segmentation/sampling uncertainty within each detector group; they do not prove a change in battery properties or match images to source batches.

## Batch KPI reports

`analysis/kpis.py` analyses each reference batch independently, without using GET4, and writes the report shown in the frontend when a reference batch is selected. Install its packages once, then run it from the repository root:

```powershell
.\.venv\Scripts\python.exe -m pip install -r analysis\requirements.txt
.\.venv\Scripts\python.exe -m analysis.kpis
```

`analysis/kpis.py` first groups each batch's images into fields with `analysis/fields.py`. It reuses the cached manifest in `data/processed/fields/batch_N.json` unless the raw files have changed; pass `--rebuild-fields` to force re-matching. To rebuild only the field manifests, which takes about 30 seconds, run `.\.venv\Scripts\python.exe -m analysis.fields`.

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

## lucas-sem-analysis four-phase segmentation

`lucas-sem-analysis/` segments each sample into pore, graphite, SiOx and carbon-binder domain (CBD) and attempts batch identification; its own README and HANDOFF explain the method. It reads the shared `data/raw/batch_N` folders directly (override with `SEM_RAW_DIR`). Its committed results were computed on files byte-identical to the current `data/raw`: all 93 SHA-256 hashes match `lucas-sem-analysis/data/manifest.csv`. The frontend shows them under each selected reference batch, as phase tiles, per-sample composition, leave-one-out batch identification and segmentation overlays.

The overlays need label maps, which are not in Git. The delivered U-Net needs a GPU and model weights that were never published, so on a CPU-only machine rebuild them with the LightGBM teacher. Install its extra package once, then run the CPU pipeline:

```powershell
.\.venv\Scripts\python.exe -m pip install lightgbm==4.7.0
cd lucas-sem-analysis
$env:SEM_WORKERS = 3     # fewer parallel processes for machines with < 16 GB RAM
..\.venv\Scripts\python.exe run_cpu_pipeline.py
```

The run uses the committed AI labels, so it makes no API calls, and it takes roughly an hour on an 8-core laptop. It writes `outputs/segmentation/` and `outputs/metrics/teacher_cpu_fractions.csv`. The committed U-Net results (`phase_fractions.csv`, `batch_stats.csv`, `siox_summary.csv`, `batchid/*.json`) are left unchanged, and the frontend shows those numbers. Each overlay card also lists the teacher's fractions, so you can see how closely the overlay model agrees. The API routes are `GET /batches/{batch_id}/lucas-report` and `GET /batches/{batch_id}/lucas-report/overlays/{sample_id}`.

## Unknown batch classification

Put the unknown images in `data/raw/unknown/`, named `img_<location>_<filter>.tif` like the reference files, then run from the repository root:

```powershell
.\.venv\Scripts\python.exe -m analysis.classify --rebuild
```

This takes about a minute for three locations, and writes `data/processed/classification/unknown.json`, which the frontend's Unknown batch section reads through `GET /unknown/classification`. The steps:

1. **Measure:** the unknown images are grouped into locations, and their detectors are checked from the pixels, by `analysis/fields.py`. Each location's BSE image is then measured by the same `analysis/kpis.py` code as the references.
2. **Check for duplicates:** every unknown image is compared with every reference image, by file hash and by image content.
3. **Classify:** each location gets a probability for batch 1, 2 and 3 from one pre-declared model, a diagonal LDA on eight standardised BSE KPIs. The output lists the features driving each call and the most similar reference locations.
4. **Test the model on the references:** each reference location is held out in turn and predicted. The balanced accuracy, per-batch recall and a 500-permutation test are reported alongside the predictions, so every call can be read against how often the model is right.
5. **Show a session hint:** the reference batches imaged at the same image height are listed separately, because image height marks the imaging session. The hint is not used by the model.

Images in the unknown set are also available through the image routes as batch `unknown`, for example `GET /batches/unknown/images` and `GET /batches/unknown/kpi-report`.

## Project map

Run every analysis module from the repository root as `python -m analysis.<module>`. The backend and frontend read only the files those modules write under `data/processed/`. Source files carry concise comments; the table below covers files that cannot (JSON, lockfiles, binary assets) and explains how the folders are organised.

```text
.
├── analysis/                  # in-house image analysis (one Python package)
│   ├── fields.py              #   group views into locations, identify each view's detector
│   ├── kpis.py                #   per-location KPIs and batch reports
│   ├── classify.py            #   classify the unknown batch as batch 1, 2 or 3
│   ├── get4.py                #   GET4 segmentation-uncertainty analysis
│   └── requirements.txt
├── backend/
│   ├── app/
│   │   ├── main.py            #   FastAPI app, CORS, router registration
│   │   ├── paths.py           #   every data folder and filename pattern the API reads
│   │   ├── batches.py         #   batch IDs, raw-image folders, reading generated JSON
│   │   ├── routers/           #   one module per frontend feature
│   │   │   ├── images.py      #     image groups, cached previews, TIFF downloads
│   │   │   ├── kpi.py         #     KPI reports, overlays, summary
│   │   │   ├── lucas.py       #     lucas-sem-analysis segmentation results
│   │   │   ├── get4.py        #     GET4 uncertainty reports
│   │   │   ├── unknown.py     #     unknown-batch classification
│   │   │   └── mock.py        #     sample analysis records (data-readiness line)
│   │   ├── schemas.py  mock/  requirements.txt
│   └── modal_app.py           #   Modal deployment
├── frontend/src/
│   ├── main.jsx  App.jsx
│   ├── styles/                #   theme.css (all colours), index.css, App.css
│   ├── components/            #   shared UI: TopBar, Tabs, PointNetwork
│   ├── hooks/                 #   useJson, useTooltip
│   ├── lib/                   #   tabPanel (ARIA helper for Tabs)
│   └── features/              #   one folder per page section
│       ├── reference/         #     BatchPicker, ImageGallery
│       ├── kpi/               #     KpiReport
│       ├── segmentation/      #     LucasReport
│       ├── uncertainty/       #     Get4Results
│       └── unknown/           #     UnknownBatch
├── lucas-sem-analysis/        # four-phase segmentation project (own README); reads data/raw
└── data/                      # Git-ignored: raw/ (TIFFs) and processed/ (generated outputs)
```

| File or folder                                                | Purpose                                                                                            |
| ------------------------------------------------------------- | -------------------------------------------------------------------------------------------------- |
| `backend/app/mock/B-01.json`                                  | Example analysis returned by the API; JSON syntax does not allow comments.                         |
| `backend/app/requirements.txt`                                | Python dependencies used by the backend and Modal image, including TIFF preview support.           |
| `analysis/requirements.txt`                                   | Python packages for the analysis package.                                                          |
| `data/raw/batch_1/`–`batch_3/`, `data/raw/unknown/`           | Locally downloaded microscopy TIFFs; raw data is Git-ignored.                                      |
| `frontend/index.html`                                         | Browser document, metadata, fonts, and React mount point.                                          |
| `frontend/vite.config.js`                                     | Vite setup and React plugin.                                                                       |
| `frontend/package.json`                                       | Frontend dependencies and npm scripts; JSON does not allow comments.                               |
| `frontend/package-lock.json`                                  | Generated dependency tree for repeatable installs; do not edit manually.                           |
| `frontend/.oxlintrc.json`                                     | Oxlint rules; JSON does not allow comments.                                                        |
| `frontend/.env`                                               | Local Vite API URL; excluded from Git.                                                             |
| `.env.example`                                                | Example environment-variable template; never put real credentials here.                            |
| `.gitignore` and `frontend/.gitignore`                        | Files and local data Git should not track.                                                         |
| `frontend/README.md`                                          | Frontend setup and file-purpose notes.                                                             |
| `frontend/public/favicon.svg` and `frontend/public/icons.svg` | Browser favicon and SVG icon sprite.                                                               |
| `frontend/src/assets/`                                        | Image and logo assets retained from the Vite starter; binary files cannot contain source comments. |
