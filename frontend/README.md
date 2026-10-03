# React + Vite

## This project

The page in `src/App.jsx` presents the microscopy workflow. Pick a reference batch (1–3) to browse its views in tabs: Images, KPI report, Segmentation and Uncertainty (GET4). Below that, the Unknown batch section shows each unknown location's batch 1, 2 or 3 classification with its evidence. Data comes from the API at `VITE_API_URL` (set in `.env`); TIFF previews and downloads are served from `data/raw/`, which is not tracked in Git. Code layout:

- `src/main.jsx` mounts the app.
- `src/styles/` holds `theme.css` (every colour token), `index.css` (global defaults) and `App.css` (page layout).
- `src/components/` holds shared UI (`TopBar`, `Tabs`, `PointNetwork`).
- `src/hooks/` holds `useJson` and `useTooltip`, and `src/lib/` holds small helpers.
- `src/features/` has one folder per page section: `reference/` (BatchPicker, ImageGallery), `kpi/`, `segmentation/`, `uncertainty/` and `unknown/`.

See the repository-root README for backend setup and the full project map.

The commands for this project's frontend are `npm run dev`, `npm run build`, and `npm run lint`.

## Vite starter reference

This template provides a minimal setup to get React working in Vite with HMR and some Oxlint rules.

Currently, two official plugins are available:

- [@vitejs/plugin-react](https://github.com/vitejs/vite-plugin-react/blob/main/packages/plugin-react) uses [Oxc](https://oxc.rs)
- [@vitejs/plugin-react-swc](https://github.com/vitejs/vite-plugin-react/blob/main/packages/plugin-react-swc) uses [SWC](https://swc.rs/)

## React Compiler

The React Compiler is not enabled on this template because of its impact on dev & build performances. To add it, see [this documentation](https://react.dev/learn/react-compiler/installation).

## Expanding the Oxlint configuration

If you are developing a production application, we recommend using TypeScript with type-aware lint rules enabled. Check out the [TS template](https://github.com/vitejs/vite/tree/main/packages/create-vite/template-react-ts) for information on how to integrate TypeScript and Oxlint's TypeScript related rules in your project.
