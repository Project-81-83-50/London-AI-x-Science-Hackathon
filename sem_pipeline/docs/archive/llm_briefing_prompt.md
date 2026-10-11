You are joining a hackathon project (London AI x Science Hackathon, Polaron challenge) at the point where everything up to the multi-agent LLM layer is finished. Treat the following as verified ground truth. Do not re-derive or re-run it unless asked. Code lives in github.com/Project-83-85-50/London-AI-x-Science-Hackathon, folder `sem_pipeline/` (only v3 is in the repository; v1 and v2 were earlier stages of the same pipeline).

# 1. Task and data
- Task: identify which of 3 production batches an SEM cross-section of a graphite + SiOx Li-ion anode comes from, quantify its microstructure, and explain the result. The organisers will supply a blind set that is a mixture of the three batches.
- Data: 31 imaged locations: Batch_1 7, Batch_2 7, Batch_3 17.
  - Each location has three co-registered detector images (misregistration < 0.4 px): BSE, Inlens, and ETD (27 locations) or SE (4).
  - 25 nm/px, about 2060-2316 x 7000 px, RGB TIFF with identical channels (the green channel is used).
- Processing resolution: 50 nm/px (2x2 block mean), per-image normalisation.
- Exclusion mask: 8-px border; Cu current collector (BSE >= 240 connected to the top or bottom edge); manually confirmed unpolished strips (3 locations). About 1 % of pixels are excluded.
- Imaging-session proxy: image height (13 groups). Sessions mix batches.
- Environment: Windows, Python 3.14, torch 2.11.0+cu128, RTX 5070 Ti laptop GPU.

# 2. Label-free 4-phase segmentation
Classes: 0 pore, 1 graphite, 2 SiOx, 3 carbon-binder domain (CBD, "binder"), 255 excluded. No pixel was labelled by hand.
1. **Rule seeds** for unambiguous pixels: bright compact SiOx, deep BSE-black voids, flat graphite interiors. The rule-based CBD seeds were dropped (the AI annotator contradicted them 22/41 times).
2. **AI superpixel labels.** SLIC superpixels (compactness 3) in ambiguous regions were labelled by Claude Opus 5.5 (max effort, Batch API) from BSE | Inlens | ETD crops.
   - Round 1: 1,178 superpixels.
   - Round 2 (active learning): 992 superpixels, where the v1 U-Net was least confident (pore vs CBD and other regions) plus a random pore/CBD control set; 803 train, 189 held out.
3. **Teacher:** LightGBM (lr 0.12, 300 trees) on 54 multi-scale BSE + Inlens features, with stride-2 self-training rounds.
   - Physics constraint: SiOx only where smoothed BSE exceeds the image's upper multi-Otsu threshold; SiOx holes are filled.
4. **Student (delivered labels):** U-Net (segmentation_models_pytorch, ResNet-18 encoder, 2-channel BSE + Inlens input, 12.5 M parameters).
   - 18 epochs, distilled from the teacher's confident pixels; 6 locations held out.
   - Exported to ONNX. Inference 0.31 s/image on GPU, 1.5 s on CPU (ONNX).
5. **Independent validation** (Claude classified points blind to any model output):
   - 240 uniform random points: 81.7 % [76.3, 86.1] for 4 classes; 87.1 % [82.2, 90.7] for 3 classes (pore / carbon = graphite + CBD / SiOx). 100 % on the 113 high-confidence points.
   - Per-class precision: SiOx 0.96, graphite 0.83, pore 0.69, CBD 0.52. The graphite-vs-binder split is experimental, so composition is reported primarily as 3 classes.
   - Held-out round-2 superpixels in previously uncertain regions: 70.1 %.
   - SiOx vs the threshold baseline: mean absolute difference 0.13 pp.
   - Retraining stability: < 0.8 pp.
6. **Dataset composition** (mean of locations): pore 17.3 % (deep 9.5 + open/grey-floored 7.7), graphite 61.0 %, SiOx 6.3 %, CBD 15.4 %.
7. **Batch differences:**
   - Batch_1 is less porous: 14.4 % vs 17.8 % and 18.2 %; Kruskal-Wallis p = 0.004, session-stratified p = 0.031.
   - SiOx and CBD do not differ between batches.
   - **Batch_1 and Batch_2 are statistically indistinguishable:**
     - 3 of 77 features differ at p < 0.05 (3.9 expected by chance);
     - energy-distance permutation p = 0.19;
     - a blinded odd-one-out test by Claude scored 27 % (chance 33 %).
8. **nnU-Net v2 export:** Dataset501_SEMAnode (BSE and Inlens channels; ignore label 4).

# 3. Batch-identification models
All scores are leave-one-location-out (LOO): each location is predicted by models trained on the other 30. Balanced accuracy is the mean per-batch recall.

**A. Imaging fingerprint** (batch_match design, replicated exactly, 23/31). Measures how each detector image was acquired, 17 measurements per view (BSE, Inlens, ETD/SE):
- noise SD and kurtosis of the residual after a 3x3 median filter;
- lag-1 noise autocorrelation along and across scan lines;
- dominant horizontal banding period and its power share, and row-to-row brightness jitter;
- column (vertical-stripe) pattern strength;
- high-frequency power in x and in y;
- grey-level p1 / p50 / p99, number of distinct levels, and clipping at 0 and 255;
- LZW bytes per pixel (compressibility).

Each measurement is converted to a robust z-score (median / IQR, clipped at ±3) and fed to a shrinkage LDA per view (lsqr solver, automatic shrinkage, equal priors). The views are combined by geometric mean. LOO balanced accuracy 0.70, permutation p = 0.002.

**B. Material model F = mean(S, D).** LOO 0.61, p = 0.005.
- **S:** 5 label-map features (SiOx %, area-weighted SiOx equivalent diameter, open-pore excess, total pore %, pore chord anisotropy) → robust z → shrinkage LDA. LOO 0.48 alone.
- **D:** DINOv2-S/14-reg patch tokens of BSE and Inlens (2 x 384 = 768-dim) → texton histogram (MiniBatchKMeans, K = 24, fitted in-fold) → sqrt → StandardScaler → PCA (4 or 8 components) → balanced logistic regression (C = 0.03 / 0.1 / 0.3), averaged over the 6 configurations.
- The linear heads are folded into exact per-token contributions, so evidence maps are exact (reconstruction error ~1e-13).

**C. Tile texture model** (batch_match design, rebuilt from its description):
- 512-px tiles (12.8 um) at 25 nm/px. Tiles more than 20 % excluded are skipped.
- 45 features per tile:
  - uniform LBP histograms, P = 8, R = 1 and 3 (20);
  - GLCM at 32 levels, d = 1 and 4, 0° and 90°: contrast / homogeneity / energy / correlation (16);
  - power spectrum in 8 log-spaced bands, plus high-frequency x/y anisotropy (9).
- Standardised logistic regression (C = 0.05, location- and batch-balanced weights) per view; tile probabilities averaged.
- LOO 0.58 overall, 0.68 on BSE alone. **Excluded from the vote:** letting it vote lowered accuracy when answering from 85 % to 80 %. It is reported for information only.

**D. Training-image guard and known-location matcher** (batch_match design):
- **Guard:** the SHA-256 of the decoded pixel array is compared with the 93 reference images; an identical image is refused.
- **Matcher:**
  - Edge map: 8x block mean (~200 nm/px), Gaussian σ = 1, Sobel gradient magnitude, standardised, Hann-windowed, zero-padded to 200 x 860.
  - Normalised cross-power phase correlation against all 93 references.
  - Peak score z = (max − mean) / SD of the correlation surface.
  - Known location if z >= 15 **and** z >= 2 x the best score from any other location. The margin was added because crops raise the noise floor; without it, crops gave 12/93 false matches.
  - Results: 0/93 false matches for full images and 0/93 for 50 % crops; 93/93 full images found across detectors; crops found 71/93 via another detector and 86/93 within the same image.

**E. GET4 material-range rule** (GET4 from batch_match; `src/get4.py` is a shim over the repository's `analysis.get4`):
- Image standard error of each phase fraction (pore / carbon / SiOx) from the two-point-covariance integral range plus a tile-overdispersion factor; 95 % CI = ±1.96 SE.
- Batch range = [min, max] over the training locations. A phase votes for a batch when its CI overlaps only that batch's range.
- The rule answers Batch_1 or Batch_2 when the votes agree and no side points to Batch_3. It fired for 1/31 locations (correct).

**F. Calibration:** temperature scaling per model (T on a log grid 0.05-20, minimising NLL) fitted on nested inner-LOO predictions.

# 4. Decision and uncertainty layer (v3 = v2 agreement rule + batch_match additions)
Order of steps for an image:
1. **Guard** → "refused (training image)".
2. **Matcher** → the known location's batch, "Certain (known location)".
3. **Two sides:**
   - imaging side = calibrated fingerprint;
   - material side = calibrated F.
4. **Answer:**
   - both sides pick the same batch → that batch ("specific");
   - both pick within {Batch_1, Batch_2} but disagree → "Batch_1 or Batch_2" ("pair"); the GET4 rule may resolve it;
   - otherwise → "unsure (leaning X)", where X is the argmax of the average calibrated probability.
5. **Confidence tier:**
   - High = specific, the average calibrated top probability >= a nested threshold (the smallest level at which inner held-out specific answers were >= 90 % right, n >= 5), the fingerprint views agree, and there are no novelty or shortcut flags;
   - Medium = other specific answers, and pair answers;
   - Low = unsure.

   The prediction set is every batch with average probability >= 0.2.
6. **Forced mode** (`--forced`), always answers:
   - the fingerprint model decides Batch_3 or not;
   - otherwise the GET4 rule decides if it fires;
   - otherwise a Batch_1-vs-Batch_2 fingerprint specialist decides (per-view 2-class shrinkage LDA, averaged).
7. **Evaluation protocol:** nested LOO. The outer fold holds out one location. Calibration temperatures, the High threshold and the batch ranges are chosen on an inner LOO over the remaining 30. The DINOv2 texton vocabulary is fitted per outer fold (label-free). Every scored configuration is logged in `outputs/metrics/look_ledger.csv`.

# 5. Results (nested leave-one-location-out)
- **Answers 26/31 (84 %); right when answering 22/26 (85 %, 95 % CI 66-94).**
  - specific answers 19/23 right;
  - "Batch_1 or Batch_2" answers 3/3 right.
- **Tiers:** High 10/12 right (83 %); Medium 12/14; unsure 5 (Batch_2 x3, Batch_3 x2).
- **Per true batch:**
  - Batch_1: 4 right, 2 pair, 1 wrong;
  - Batch_2: 2 right, 1 pair, 1 wrong, 3 unsure;
  - Batch_3: 13 right, 2 wrong, 2 unsure.
- **Forced mode:** balanced accuracy 0.80 (25/31; Batch_1 6/7, Batch_2 5/7, Batch_3 14/17), label-permutation p = 0.001 (1000 shuffles, null 99th percentile 0.60).
- **Single models:** fingerprint 0.70, material 0.61, texture 0.58.
- **Caveats:**
  - n = 31, so the intervals are wide.
  - "Right when answering" is not balanced accuracy.
  - Batch_2 is the weak batch.
  - Acquisition properties alone predict batch at 0.68, so the fingerprint partly reads imaging conditions. Blind images from new imaging sessions may score lower.
  - The decision rule and forced mode were designed after seeing these 31 locations.

# 6. The LLM input: facts.json (text only)
`python -m src.bid_explain predict --bse X_BSE.tif --inlens X_Inlens.tif [--etd X_ETD.tif] --out DIR [--holdout SID] [--forced]` (about 30 s) writes `facts.json`, `labels.png`, `overlay.jpg` and `evidence.jpg`. For the 31 known locations, `outputs/batchid/<sid>.json` holds the same structure, with every probability and decision taken from nested-LOO models that never saw that location.

Field order:
- `summary_sentences`: plain-English sentences generated only from numbers in the file.
- `field_guide`.
- `sample_id`; `true_batch` for the known locations.
- **`decision`:** answer, answer_type (specific / specific_by_material_range / pair / unsure / known_location / refused / forced), confidence, leaning, imaging_side_pick, material_side_pick, sides_agree, prediction_set, average_calibrated_probabilities, high_tier_threshold, reasons, track_record (this tier and this answer type, LOO and session-out), basis.
- `phases`: four_class_pct, three_class_pct, reliability note.
- `known_location_check`: status, per-view best match score, location, note.
- `material_range_rule`: per phase pct, ci95, fits_ranges_of, and the batch ranges.
- `fingerprint_model`: probabilities, per_view, views_agree, top_measurements (measurement, plain meaning, robust_z, direction, push_toward_winner), calibration.
- `texture_model`: used_in_decision = false, calibrated_probabilities, per_view_raw, top_features.
- `material_model`: probabilities (fused_F, S_head, dino_head), features_S, evidence statistics, and **`map_text`**, which describes the maps in words:
  - evidence_by_phase and evidence_by_region, with share and enrichment;
  - spatial: 3x3 grid composition, notable enriched or depleted regions, top/middle/bottom trend;
  - objects: largest pores and SiOx particles with area, length, orientation and position in um; Clark-Evans clustering;
  - sentences.
- `qc`, `acquisition` (probes, nearest training acquisition, warning), `novelty` flags.
- `decision_v2` and `forced_mode`, for comparison.
- `timings_s`.
- At the end: `loo_prediction` / `confidence` / `validation_reference`. These are copies kept for the team frontend and are NOT the answer.

# 7. Rules for anything built on top (including the multi-agent LLM layer)
- Input is text only (`facts.json`). Quote only numbers that exist in it; never invent measurements, mechanisms or certainty.
- Lead with `decision.answer`, `decision.confidence` and `decision.track_record`. Never present one model's pick (fingerprint, texture, material, decision_v2, loo_prediction) as the answer.
- "unsure" and "Batch_1 or Batch_2" are legitimate, honest outcomes. Always state that Batch_1 and Batch_2 are statistically indistinguishable in this data.
- A known-location answer is identification by matching, not classification. Say so.
- Report composition as pore / carbon / SiOx. The binder value is experimental.
- Imaging-fingerprint cues describe acquisition (noise, banding, grey levels), not material. Present them that way.
- Keep the Anthropic API key in `.env` (git-ignored). Never commit it.

Your role: using this as context, [describe the multi-agent LLM task here].
