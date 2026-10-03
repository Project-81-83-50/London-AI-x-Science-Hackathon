# London AI × Science Hackathon

An attempt at Track 4

## Track 4: Materials manufacturing by Polaron

Can you detect when a supplier's material has changed before it becomes a manufacturing problem?

Battery manufacturers need incoming electrode material to be consistent batch to batch but subtle shifts in formulation or processing can alter microstructure in ways that only surface as defects much later in production. Using electron microscopy images, teams build a trustworthy, interpretable, uncertainty-aware QC system that compares incoming batches against an approved baseline: detecting whether a batch has meaningfully changed, quantifying what's driving the difference, and explaining the verdict (accept / investigate / reject) to a materials expert, not just a black-box score.

Teams get a baseline batch plus several incoming batches (mixing acceptable and defective variation); a brand-new unseen batch drops ~8 hours into day one to test generalization.

Judged on: quality of extracted material KPIs, accuracy on the new batch, interpretability, honest handling of uncertainty, and real-world usability for a QC decision, not just raw accuracy.

## Run locally

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

The dashboard reads batch summaries from `GET /batches` and full results from `GET /batches/{batch_id}/analysis`. Set `VITE_API_URL` in `frontend/.env` if the API is running somewhere other than `http://localhost:8000`.

## Project map

Source and supported configuration files include concise comments. JSON cannot contain comments, lockfiles are generated, and binary assets cannot hold useful source comments, so those purposes are listed here.

| File or folder                                                | Purpose                                                                                            |
| ------------------------------------------------------------- | -------------------------------------------------------------------------------------------------- |
| `backend/app/main.py`                                         | FastAPI app, CORS setup, mock-data loading, and the batch API routes.                              |
| `backend/app/schemas.py`                                      | Pydantic models that validate summaries, KPIs, drivers, and analyses.                              |
| `backend/app/requirements.txt`                                | Python dependencies used by the backend and Modal image.                                           |
| `backend/app/mock/B-01.json`                                  | Example analysis returned by the API; JSON syntax does not allow comments.                         |
| `backend/modal_app.py`                                        | Modal image and web-function configuration for hosting FastAPI.                                    |
| `frontend/src/App.jsx`                                        | React state, API requests, batch selector, and sections to implement.                              |
| `frontend/src/main.jsx`                                       | React entry point that mounts `App` into the HTML root.                                            |
| `frontend/src/App.css`                                        | Workspace layout, responsive rules, and starter-section styling.                                   |
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
