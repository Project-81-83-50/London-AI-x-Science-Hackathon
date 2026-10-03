# HANDOFF: read this first (for the next agent / LLM)

This file is the context you need to continue the work without redoing it. Detailed results are in
`reports/report.md`; how to run things is in `README.md`.

## 1. Project in three lines
- **Data:** 31 SEM cross-sections of a graphite + SiOx Li-ion anode, 3 batches (7 / 7 / 17). Each sample has
  BSE + Inlens + ETD-or-SE images, 25 nm/px.
- **Done:** a label-free 4-phase segmentation (pore, graphite, SiOx, CBD; U-Net, 0.45 s per image on GPU), a
  validation suite, a batch-identification stage (segmentation features + DINOv2), and a non-ML KPI exploration.
- **Next (planned by the team):** a multi-agent / narrator layer that reads the per-sample facts JSON in
  `outputs/batchid/`.

## 2. State of each stage

| Stage | Status | Key output | Key number |
|---|---|---|---|
| Inventory / QC | done | `data/manifest.csv`, `data/qc.csv` | 93 TIFFs; detectors co-registered to < 0.4 px |
| Preprocessing + exclusions | done | `data/processed/<sid>/*.npy`, `data/exclusions.json` | 1.1 % excluded (border, Cu foil in `epqdaau9`, unpolished in `i9jiqjwl` / `5n1q8atc`) |
| Training labels | done (**paid, cached**) | `outputs/metrics/ai_superpixel_labels.csv` | 1,178 superpixels labelled by Claude Opus 5.5 |
| Teacher (LightGBM) | done | `models/teacher.txt` | all per-sample gates pass |
| Student (U-Net) | done | `models/student.pt`, `student.onnx` | 94.5 % agreement with teacher on held-out samples |
| Delivered segmentation | done | `outputs/segmentation/<batch>/<sid>/labels.png` | 82.1 % accuracy vs independent AI points |
| Batch identification | done (scored **once**) | `outputs/metrics/bid_scores.json`, `bid_null.json` | 0.59 balanced accuracy LOO, permutation p = 0.01 |
| Two-version comparison (+ brightness head) | done, exploratory | `outputs/metrics/bid_compare.json` | see report §5 |
| Non-ML KPIs | done, exploratory | `outputs/metrics/kpi_stats.csv` | nothing survives FDR |
| Facts JSON per sample | done | `outputs/batchid/<sid>.json` | input for the narrator layer |

## 3. Decisions already made (don't redo them unless you have a reason)
1. **No hand labels.** Rule seeds cover the easy pixels and AI-annotated superpixels the hard ones. The rule-based CBD
   seeds were **dropped**: the AI annotator contradicted them 22/41 times, but agreed 100 % with the pore / graphite /
   SiOx rules.
2. **The plan's "Inlens-dark = pore" rule is wrong for some samples.** In `kbdh4tri`, polished graphite is the
   darkest Inlens phase. That is why grey-floored pores come from the AI labels.
3. **SiOx physical constraint** (`src/physics.py`): a pixel can only be SiOx if its smoothed BSE is above the image's
   upper multi-Otsu threshold. Without it, rims and halos inflated SiOx by 1.5-4 pp.
4. **SiOx gate compares like with like.** The baseline `thr` drops particles < 2 um^2, so the gate applies the same
   filter (`siox_thrlike_pct`).
5. **Detectors: BSE + Inlens only.** Adding ETD/SE changed fractions by < 0.5 pp, and 4 samples have SE instead of ETD.
6. **Batch-ID discipline (from `docs/route_to_80` synthesis):**
   - two pre-registered configurations, scored once;
   - permutation null with the selection inside;
   - every scored run is logged in `outputs/metrics/look_ledger.csv`.
   **Every extra scored configuration inflates the reported accuracy.** Log anything new as exploratory.
7. **Delivered labels come from the student**, which is at least as accurate as the teacher on the independent points.

## 4. The most important open issue: session confound
- **The acquisition-only probes predict batch with 0.68 balanced accuracy, better than any material model.** These
  are image height, grey levels, noise and banding (`outputs/metrics/bid_session_probes.csv`).
- **Image height marks an imaging session, and sessions mix batches.** For example, `ffwubibz` B1, `r17byphk` B2 and
  `cfe5vt7s` B3 were all imaged at 2080 px.
- **Within a session, B1 and B2 look identical in brightness.** The pore black level differs strongly between
  sessions (~34 in the 2060-px B3 session vs ~7-20 elsewhere), which points to a detector offset/brightness setting.
- **Ask the organisers:**
  - Were kV, beam current, working distance and detector brightness/contrast the same for all batches?
  - Which images were taken in the same session?
  - Does the blind set reuse training images, and is matching allowed?
- **Do not add raw brightness features** to the headline model unless the organisers confirm identical settings. See
  the two-version comparison in report §5.

## 5. Known weaknesses of the segmentation
- **pore ↔ CBD confusion.** CBD precision is 0.50 and pore precision 0.75.
- **Open pore interiors sometimes read as graphite.** Porosity 14.9 % vs 19.6 % [15.1, 25.1] from independent points.
- **CBD amount is partly a session readout.** The SE-detector session and the 1904-px session read 20-24 %.
- **Student vs teacher phase fractions differ by up to 3.9 pp** on held-out samples (plan target was 1 pp).

## 5b. Best exploratory batch-ID design (report §5.2)
- **Two-step classifier:** "Batch 3?" (original model), then "Batch 1 or 2?" (dedicated classifier).
- **Results:** leave-one-out 0.64 and leave-session-out 0.56, vs 0.59 / 0.47 for the original. The B1-vs-B2 step is
  not yet significant (p = 0.16).
- **Only B1-vs-B2 lead:** ETD graphite-surface roughness (B1 rougher). It is moderate in raw units (δ = 0.63,
  p = 0.05) and perfect only on normalised images.
- **Before any new/blind data is opened,** pre-register step 2 = ETD graphite roughness + total porosity and test it
  exactly once. Step 2 needs the ETD image.

## 6. Suggested next steps
1. **Narrator / multi-agent layer.**
   - It reads `outputs/batchid/<sid>.json` and must quote only numbers that exist in that file.
   - The `loo_prediction` field is the honest prediction for training samples; the top-level probabilities come from
     a model that saw the sample.
2. **Get session metadata from the organisers**, then re-run `src/metrics.py` and `src/bid_model.py score` with
   session as a blocking factor.
3. **If settings were identical,** test the SiOx/graphite BSE contrast ratio as a declared new configuration (it is
   the only B1 vs B2 lead). EDS on a few particles per batch would confirm SiOx stoichiometry.
4. **To improve pore/CBD:** label more ambiguous superpixels (costs API money), or train the nnU-Net on
   `data/nnUNet_raw/Dataset501_SEMAnode`.

## 7. Practicalities
- **Python 3.14, Windows.** GPU needs torch 2.11.0+cu128. Install torch **before** `segmentation-models-pytorch` with
  `--no-deps`, or pip replaces it with a CPU build.
- **Windows multiprocessing:** inline `python -` scripts cannot use `ProcessPoolExecutor`; put the code in a module.
- **Write text files with `encoding="utf-8"`.** The default cp1252 corrupts files containing →, µ, ±.
- **Paid stages** (`src/ai_labels.py`, `src/ai_validate.py`) call the Anthropic API. Their results are already
  committed, so do not re-run them unless you mean to (≈ $37 spent in this stage).
- **The API key lives in `.env` (git-ignored). Never commit it.**
- **Large files** (raw data, label maps, models, nnU-Net dataset) are in the GitHub release `v1.0` zips. Rebuild them
  with `python -m src.package_release --tag v1.0`.
- **To restore the raw data:** put `Batch_1/2/3` under `data/raw/`, then run `python run_pipeline.py`. All stages are
  deterministic except GPU training.
