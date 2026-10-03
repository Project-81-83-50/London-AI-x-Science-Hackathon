# React + Vite

## This project

The page in `src/App.jsx` describes the microscopy workflow: batches 1–3 are known reference sets, and incoming batches 4–5 need to be organised by source image batch with supporting evidence. Selecting a reference batch loads its inventory from `GET /batches/{batch_id}/images`; selecting it again hides the gallery. Batch summaries load from `GET /batches`, using `VITE_API_URL` from `.env`. TIFF previews and downloads are served by the API from the selected `data/raw/batch_{id}` folder; raw datasets are not tracked in Git. Image-to-reference matches are not yet implemented. `src/main.jsx` mounts the page, `src/App.css` styles its sections, and `src/index.css` sets global styles. See the repository-root README for backend setup and the project map.

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
