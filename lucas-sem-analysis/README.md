# SEM anode segmentation (Polaron hackathon)

> **Continuing this work (human or LLM)? Start with [HANDOFF.md](HANDOFF.md).**

Label-free 4-phase segmentation of 31 SEM cross-sections of a calendered **graphite + SiOx** Li-ion anode
(3 batches; BSE + Inlens + ETD/SE detectors, 25 nm/px), plus a fast U-Net that segments a new image pair in
under a second on a laptop GPU, and a batch-identification stage built on top.

| value | class | colour in overlays |
|---|---|---|
| 0 | pore (including open, grey-floored pores) | blue |
| 1 | graphite | purple |
| 2 | SiOx | orange |
| 3 | carbon-binder domain (CBD) | green |
| 255 | excluded (8-px border, Cu current collector, unpolished strips) | red |

Results, validation and caveats are in **[reports/report.md](reports/report.md)**. Headline numbers:

| Measure | Result |
|---|---|
| Dataset composition (mean of 31 samples) | pore 14.9 % (deep 9.4 + open 5.5), graphite 62.5 %, SiOx 6.3 %, CBD 16.4 % |
| Independent accuracy (240 random points, AI-annotated, blind) | 82.1 % (95 % CI 76.7-86.4 %); 100 % on high-confidence points |
| Per-class precision | SiOx 0.96, graphite 0.77, pore 0.75, CBD 0.50 |
| Retraining stability | < 0.6 pp |
| Inference per image | 0.45 s GPU (RTX 5070 Ti), 3.4 s CPU (ONNX) |
| Batch identification (leave-one-out, balanced accuracy) | 0.59 fused (segmentation features + DINOv2 texton head), permutation p = 0.01. A classifier on acquisition properties alone reaches 0.68, so batch is confounded with imaging session |

## Repository layout

```
data/
  raw/Batch_{1,2,3}/img_<sid>_<det>.tif   original TIFFs (git-ignored, read-only)
  manifest.csv                            one row per TIFF: size, pixel size, sha256, channel check
  qc.csv                                  per sample: detector registration shifts, image-height (session) group
  exclusions.json                         visually confirmed regions to exclude
  baseline/baseline.csv                   earlier measurements used for validation (thr, vis)
  processed/                              normalised half-res arrays, features, labels (git-ignored)
  nnUNet_raw/Dataset501_SEMAnode/         the segmented dataset in nnU-Net v2 format (git-ignored, release asset)
src/                                      one module per stage (see below)
models/                                   teacher.txt, student.pt / .onnx, bid_model.pkl (git-ignored, release asset)
outputs/
  segmentation/<batch>/<sid>/             labels.png, overlay.jpg, siox_instances.png, bse.png, inlens.png (release asset)
  batchid/<sid>.json, <sid>_evidence.jpg  per-sample facts for the narrator layer + evidence maps
  metrics/                                phase fractions, batch stats, particles, validation, KPIs, look ledger, ...
reports/                                  report.md, report_method.md and figures
prior_analysis/                           the earlier vision-LLM analysis that produced the baseline numbers
docs/                                     plan.md (task specification), devin_prompt.md
```

## Method in one paragraph

No pixel was labelled by hand.
1. **Rule-based seeds** label the unambiguous pixels: bright compact SiOx, deep black voids, flat graphite interiors.
2. **Claude Opus 5.5** labels the hard regions by classifying ~1,200 superpixels from BSE | Inlens | ETD crops. These
   are open pores whose floor shows grey sub-surface material (the sections are not resin-filled), and binder vs
   particle rims.
3. **A LightGBM teacher** trained on these labels labels every pixel. It uses multi-scale BSE + Inlens features and
   two self-training rounds.
4. **A U-Net student** (ResNet-18 encoder, 2-channel input) is distilled from the teacher's confident pixels and
   produces the delivered label maps.

A physical constraint keeps SiOx to BSE-bright pixels. Accuracy is checked against the earlier threshold/visual
baselines, retraining stability, held-out samples, and an independent Claude classification of uniformly random
points. Batch identification (`src/dino.py`, `src/bid_*.py`) and an exploratory set of 35 non-ML image KPIs
(`src/kpi.py`) build on the label maps; see report sections 5-7.

## Setup

```bash
pip install -r requirements.txt
pip install torch==2.11.0 torchvision==0.26.0 --index-url https://download.pytorch.org/whl/cu128
pip install --no-deps -r requirements-gpu.txt
```

Put the raw data in `data/raw/Batch_{1,2,3}/`. Inside the hackathon repo, the shared `../data/raw/batch_{1,2,3}/` is used automatically; set `SEM_RAW_DIR` to point elsewhere. Without a GPU, `python run_cpu_pipeline.py` rebuilds the label maps and overlays from the LightGBM teacher and leaves the committed U-Net metrics untouched. The AI-annotation stages need an Anthropic API key in `.env`
(`ANTHROPIC_API_KEY=...`, git-ignored).

## Running

```bash
python run_pipeline.py                      # all stages except the paid AI annotation
python run_pipeline.py --from student       # resume from a stage
```

Stages, in order:
1. **Segmentation:** `manifest` → `preprocess` → `seeds` → `features` → `superpixels` → `ai_apply` → `teacher` →
   `ablation` → `stability` → `student` → `student_predict` → `export_onnx` → `finalize` → `instances` →
   `metrics` → `validate` → `figures` → `nnunet`
2. **Batch identification:** `dino` → `bid_features` → `bid_cache` → `bid_score` → `bid_null` → `bid_fit` →
   `bid_explain`
3. **Exploratory KPIs:** `kpi`

AI annotation (paid, run once; results are committed in `outputs/metrics/`):

```bash
python -m src.ai_labels prepare && python -m src.ai_labels submit && python -m src.ai_labels collect --wait
python -m src.ai_validate prepare-uniform && python -m src.ai_validate submit uniform && python -m src.ai_validate collect uniform --wait
```

## Segment a new image pair

```bash
python -m src.predict --bse img_X_BSE.tif --inlens img_X_Inlens.tif --out outputs/predict/X          # GPU
python -m src.predict --bse img_X_BSE.tif --inlens img_X_Inlens.tif --out outputs/predict/X --cpu    # ONNX, CPU
```

Whole chain for a new image (segmentation → features → DINO → batch prediction → evidence map + facts JSON):

```bash
python -m src.bid_explain predict --bse img_X_BSE.tif --inlens img_X_Inlens.tif --out outputs/batchid/new/X
```

## Train an nnU-Net on the segmented dataset

`python -m src.export_nnunet` writes `data/nnUNet_raw/Dataset501_SEMAnode`:
- BSE and Inlens are the two input channels;
- label 0 = pore, which is nnU-Net's "background";
- excluded pixels get the ignore label 4.

Then:

```bash
pip install nnunetv2
nnUNetv2_plan_and_preprocess -d 501 --verify_dataset_integrity
nnUNetv2_train 501 2d 0
```

## Large files

Raw data, label maps, the nnU-Net dataset and model weights are git-ignored. They go to the GitHub release
instead (`python -m src.package_release --tag v1.0`, which writes `release/*.zip`).
