# London AI × Science Hackathon

An attempt at Track 4

## Track 4: Materials manufacturing by Polaron

Can you identify which known battery batch each microscopy image came from?

The first three batches are known reference sets. Images within a batch show the same battery from different angles and with different imaging filters, so those views need to be compared as a group rather than treated as different materials. Later batches 4 and 5 contain a mixture of images from the first three. The task is to organise those images by source batch and explain each match using visible evidence, while being clear about uncertainty.

The frontend presents this reference-to-incoming workflow. It does not claim to classify images until microscopy files and image-level analysis are connected.

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

## Project map

Source and supported configuration files include concise comments. JSON cannot contain comments, lockfiles are generated, and binary assets cannot hold useful source comments, so those purposes are listed here.

| File or folder                                                | Purpose                                                                                            |
| ------------------------------------------------------------- | -------------------------------------------------------------------------------------------------- |
| `backend/app/main.py`                                         | FastAPI app, CORS setup, mock-data loading, and local microscopy image routes.                    |
| `backend/app/schemas.py`                                      | Pydantic models that validate summaries, KPIs, drivers, and analyses.                              |
| `backend/app/requirements.txt`                                | Python dependencies used by the backend and Modal image, including TIFF preview support.           |
| `backend/app/mock/B-01.json`                                  | Example analysis returned by the API; JSON syntax does not allow comments.                         |
| `backend/modal_app.py`                                        | Modal image and web-function configuration for hosting FastAPI.                                    |
| `data/raw/batch_1/`–`batch_3/`                                | Locally downloaded reference microscopy TIFFs; raw data is Git-ignored.                             |
| `frontend/src/App.jsx`                                        | Reference-batch workflow, selectable image galleries, and API data-readiness status.                |
| `frontend/src/main.jsx`                                       | React entry point that mounts `App` into the HTML root.                                            |
| `frontend/src/App.css`                                         | Workflow layout, responsive rules, and batch-card styling.                                        |
| `frontend/src/index.css`                                      | Global defaults and root element styling.                                                          |
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
