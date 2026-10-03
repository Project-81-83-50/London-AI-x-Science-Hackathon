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
