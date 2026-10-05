# Frontend

React 19 + Vite single-page app for the EM batch-QC workspace. It has three pages, switched by the URL hash:

- **Batches** (default): pick reference batch 1–3 to browse its images, the General and Detailed reports (SEM pipeline v3
  four-phase segmentation) and the GET4 uncertainty results; pick **Unknown** to see each unknown location's batch call
  with its evidence.
- **Demo** (`#demo`): upload the BSE + InLens (+ ETD) images of one location and run the SEM pipeline (v3) on them.
- **Pipeline** (`#pipeline/<run>`): every step's output for one run, plus the multi-agent report.

All data comes from the FastAPI backend in `../backend`; see the repository-root README for backend setup and the data
it needs.

## Scripts

Run from this folder after `npm install`:

| Command                | What it does                                          |
| ---------------------- | ----------------------------------------------------- |
| `npm run dev`          | Start the Vite dev server (http://localhost:5173).    |
| `npm run build`        | Production build into `dist/`.                        |
| `npm run preview`      | Serve the production build locally.                   |
| `npm run lint`         | Lint with Oxlint (`.oxlintrc.json`).                  |
| `npm run format`       | Format every file with Prettier (`.prettierrc.json`). |
| `npm run format:check` | Check formatting without writing (for CI).            |

## Configuration

| Variable       | Default                 | Purpose              |
| -------------- | ----------------------- | -------------------- |
| `VITE_API_URL` | `http://localhost:8000` | Base URL of the API. |

Set it in `frontend/.env` (ignored by Git), e.g. `VITE_API_URL=http://127.0.0.1:8002`, which is what
`scripts/start_website.bat` writes. Vite reads it at start-up, so restart `npm run dev` after changing it.

## Folder structure

```text
src/
├── main.jsx                 # entry point: global styles and the React root
├── App.jsx                  # hash routing and the Batches page
├── components/              # shared UI: TopBar, Tabs, PointNetwork (animated background)
├── hooks/                   # useJson (fetch JSON with loading/error state), useTooltip (chart tooltips)
├── lib/                     # small helpers: api.js, batchLabel.js, tabPanel.js, v3format.js
├── styles/                  # theme.css (design tokens), index.css (globals), App.css (layout),
│                            #   report.css (cards, tiles, tables and charts shared by the reports)
└── features/                # one folder per page section
    ├── reference/           #   BatchPicker, ImageGallery (Images tab)
    ├── v3report/            #   GeneralReport, DetailedReport, SegmentationCharts
    ├── uncertainty/         #   Get4Results (Uncertainty (GET4) tab)
    ├── unknown/             #   UnknownBatch, KpiTrackRecord (unknown batch: Classification tab)
    └── v3live/              #   DemoPage, PipelinePage, V3UnknownCalls, V3Widgets, pipelineSteps
```

Colours live in `src/styles/theme.css`; chart colour ramps are defined next to the charts that use them.
