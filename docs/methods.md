# Methods: SEM batch identification for a graphite + SiOx anode

**Task.** Assign each SEM cross-section location of a lithium-ion anode to one of three production batches, explain
the call with material evidence, and state how certain it is.

**Data.**
- 31 reference locations (Batch 1: 7, Batch 2: 7, Batch 3: 17) and 9 unknown locations.
- Each location is imaged with three co-registered detectors:
  - **BSE**: atomic-number contrast, so SiOx is bright;
  - **Inlens**: surface detail and edges;
  - **ETD/SE**: topography; pores stay black.
- Resolution: 25 nm per pixel, about 175 × 55 µm per image.

---

## 1. Pipeline at a glance

```
3 detector images (BSE, Inlens, ETD)
  │
  ├─ 1. Training-image guard + known-location matcher ──────► refuse / known spot (stop)
  ├─ 2. Preprocessing (50 nm/px, normalise, exclusion mask)
  ├─ 3. U-Net segmentation: pore / graphite / SiOx / binder
  ├─ 4. Composition + GET4 95 % sampling intervals
  ├─ 5. v3 material model: segmentation features + DINOv2 evidence ──► 10 % of the probability, agreement check
  ├─ 6. KPI model (ETD-dark solid) ──────────────────────────────────► 90 % of the probability
  ├─ 7. Decision: batch + High / Low confidence
  └─ 8. facts.json (text only) → three-agent Claude explanation + number check
```

---

## 2. Preprocessing
- Use the green channel (the RGB channels are identical) and downsample 2 × 2 to **50 nm/px**.
- **Exclusion mask:**
  - an 8-px border;
  - the Cu current collector (saturated BSE touching the top or bottom edge);
  - three manually confirmed unpolished strips.
  
  About 1 % of pixels are excluded.
- Normalise each detector to its 0.5–99.5 percentile range, then apply a 3 × 3 median filter.

## 3. Label-free four-phase segmentation
No pixel was labelled by hand.

1. **Rule seeds** cover the easy pixels:
   - SiOx = BSE above the upper multi-Otsu threshold;
   - pore = dark in Inlens and ETD;
   - graphite = smooth, mid-grey interiors.
   
   A rule for binder was dropped after an AI check contradicted it 22 times in 41.
2. **AI-labelled superpixels** cover the hard regions: grey-floored open pores, and binder vs particle rims.
   - SLIC superpixels of about 1 µm.
   - Claude Opus labelled each one from side-by-side BSE | Inlens | ETD crops, via the Batch API.
   - Round 1: 1,178 superpixels. Round 2 (active learning, where the model was least sure): 992 more.
   - Only medium- and high-confidence labels are used. Blind seeded controls measured the annotator's agreement.
3. **Teacher:** a LightGBM classifier.
   - Features: 54 multi-scale per-pixel features from BSE + Inlens (Gaussian, gradient, Laplacian, Hessian,
     local SD, texture energy, context), at σ = 1–8 px.
   - 300 trees, learning rate 0.12, and 2 self-training rounds that add pixels with probability ≥ 0.9 that also
     agree with their neighbourhood.
4. **Physics constraint:** a pixel can only be SiOx if it is BSE-bright (Z-contrast). This removes false SiOx at
   particle rims.
5. **Student (delivered model):** a U-Net, distilled from the teacher.
   - ResNet-18 encoder, 2 input channels (BSE, Inlens), 4 classes, 12.5 M parameters.
   - Trained only on pixels where the teacher's probability is at least 0.7.
   - Loss: cross-entropy + Dice. AdamW, 18 epochs, 512-px crops, augmentation (intensity, noise, banding,
     elastic).
   - Runtime: 0.31 s per image on GPU, 1.5 s on CPU (ONNX).
6. **Validation** (no human ground truth; a blind AI annotator on 240 random points):

   | Measure | Result |
   |---|---|
   | 4-class accuracy | 81.7 % |
   | 3-class accuracy (pore / carbon / SiOx) | 87.1 % |
   | Points the annotator marked high-confidence | 100 % |
   | Precision: SiOx / graphite / pore / binder | 0.96 / 0.83 / 0.69 / 0.52 |
   | Retraining stability | < 0.8 pp |

   Composition is therefore reported as **pore / carbon / SiOx**, with binder marked experimental.

## 4. Composition and sampling uncertainty (GET4)
- Phase fractions come from the U-Net label map.
- **GET4** (`sem_pipeline/src/get4.py`) gives each fraction a 95 % sampling interval:
  - it estimates the typical feature size from the two-point covariance, i.e. how many independent samples one
    image is worth;
  - it adds a tile-overdispersion factor for large-scale unevenness.
- **Batch finding:** Batch 1 is the least porous (14.4 % vs 17.8 % and 18.2 %). This difference holds when batch
  labels are shuffled only within imaging sessions (p = 0.031). SiOx and binder do not differ between batches.
- **GET4 range rule:** if a phase's interval overlaps only one batch's training range, it votes for that batch.
  It rarely fires: the batch ranges overlap.

## 5. v3 material model (our model; 10 % of the probability, and the agreement check)
- **Segmentation features (S):** 5 physical measurements from the label map:
  - SiOx area %;
  - area-weighted SiOx particle size;
  - open-pore excess;
  - total porosity;
  - pore anisotropy.
  
  Each becomes a robust z-score, fed to a shrinkage LDA.
- **DINOv2 texture (D):**
  - A frozen, self-supervised vision transformer (ViT-S/14 with registers) produces 384-number descriptors for
    each 0.7 µm patch of the BSE and Inlens images.
  - These patches are grouped into 24 "textons" (k-means), and each location becomes a texton histogram.
  - That histogram goes through PCA into a logistic regression.
- **Fusion:** F = mean(S, D), then temperature-calibrated.
- **Explanation:** the D head is linear, so each patch's contribution adds up exactly to the score. That gives an
  exact **evidence map**, which is summarised in words (`map_text`):
  - evidence by phase and by region;
  - a 3 × 3 composition grid;
  - the largest pores and particles;
  - particle clustering.
- **Held-out performance:** 0.61 balanced accuracy, leave-one-location-out (permutation p = 0.005).

## 6. KPI model (`analysis.classify`; 90 % of the probability)
- The BSE image is segmented into three intensity classes (pore / graphite / bright phase), giving 25 KPIs.
- 7 cross-detector KPIs come from comparing the ETD and Inlens segmentations pixel by pixel with BSE.
- **Classifier:** a diagonal LDA on the most batch-separating KPI(s) (ANOVA F). How many to keep is chosen by an
  inner leave-one-out test.
- **Deciding KPI: ETD-dark solid.** This is area that's dark in ETD but solid in BSE: sub-surface pores, shadowed
  edges or binder. Batch means: 2.5 / 3.0 / 4.6 %.
- **Held-out performance:** 0.68 balanced accuracy, nested leave-one-location-out (permutation p = 0.005).

## 7. Guard and known-location matcher (from `batch_match/`)
- **Guard:** an input pixel-identical to a training image is refused.
- **Matcher:**
  - Edge maps at about 200 nm/px are compared with all 93 reference images by phase correlation.
  - A known spot needs a peak ≥ 15 SD **and** ≥ 2 × the next location.
  - In testing: 0 false matches, for full images and for crops. All 9 unknowns are new locations.

## 8. Decision and confidence
- **Probability:** 90 % KPI model + 10 % calibrated v3 material model. 10 % is the largest share that changes
  none of the 9 unknown answers.
- **Answer:** the batch with the highest combined probability.
- **Confidence:**
  - **High:** the KPI model is ≥ 50 % sure **and** the v3 material model picks the same batch.
  - **Low:** otherwise.
  - A known-location match is High; a training image is refused.
- **Unknown batch results:**

  | Answer | Locations | Confidence |
  |---|---|---|
  | Batch 3 | `0eryguqq`, `fhwrjtet`, `xrv9xvzb` | High |
  | Batch 1 | `4hq27w4c`, `fn0mhxef` | High |
  | Batch 1 | `y59rxmxl` | Low (material model disagrees) |
  | Batch 2 | `3e122cbj` | Low (material model disagrees) |
  | Batch 2 | `fspqbkxl`, `soo2ax3r` | Low (KPI model below 50 %) |

## 9. Explanation layer
- **`facts.json`**, one per location, all text and numbers. In order:
  - summary sentences;
  - the decision with both models' probabilities;
  - composition with sampling intervals;
  - the KPI model's full evidence: all 32 KPIs with meanings and batch means, the nearest reference locations, and
    its own validation;
  - the known-spot and range checks;
  - the v3 material model's features and evidence, described in words.
- **Three-agent pipeline:** Claude Sonnet, medium effort. Each agent is a separate call with its own role and
  inputs:
  1. **Evidence analyst:** extracts the findings from `facts.json`.
  2. **Materials expert:** interprets them using the team's literature knowledge base (Si/C SEM features,
     referenced).
  3. **Skeptic / writer:** checks every claim against `facts.json`, removes unsupported ones (and lists them), and
     writes the report.
- **Number check (code):** every number in the report must appear in `facts.json`.
- The agents never see images.

## 10. Tested and not used
| Method | Why it was dropped |
|---|---|
| Imaging fingerprint (noise, scan banding, grey levels) | Strong (0.70), but it recognises the microscope **session**, not the material. Acquisition properties alone predict batch at 0.68 |
| Tile texture model (LBP, co-occurrence, spectrum) | Weaker (0.58), and also reads imaging texture |
| Teammate's batch-match classifier | Fingerprint/texture-based; replaced by the KPI model |
| Agreement rule of the earlier v3 (fingerprint + material) | Fooled by imaging session on `3e122cbj` (its session holds only Batch 1 references) |

## 11. Evaluation protocol
- **Leave-one-location-out:** each reference location is predicted by models trained on the other 30.
- **Nested:** feature choices, calibration and thresholds are made without the held-out location.
- **Permutation tests:** labels are shuffled and the whole procedure re-run, to test against chance.
- **Balanced accuracy:** used because Batch 3 has 17 of 31 locations.
- **Not re-tested:** the combined 90/10 method and its High/Low rule have **not** been held-out tested. The page-1
  track-record statistics on the website are from earlier versions and are marked outdated.

## 12. Limitations
- Only 31 reference locations, so every interval is wide.
- **Batch 1 and Batch 2 differ only subtly, so they are the hardest pair to tell apart:**
  - Batch 2 is more porous: 17.8 % vs 14.4 % (+3.5 pp, 95 % CI 1.0–6.3). It has more open (+2.2 pp) and more hidden
    sub-surface pores (ETD-dark solid 3.0 % vs 2.5 %), and a more open pore network.
  - Batch 1 has slightly more and larger SiOx particles (weaker evidence), a lower SiOx-to-graphite brightness in BSE,
    and a rougher graphite surface in ETD. The last two may partly reflect imaging or preparation.
  - Their location ranges overlap (porosity about 11–17 % vs 14–23 %), so a single location in the overlap is hard
    to call. With 7 locations per batch, only 3 of 77 features reach p < 0.05.
- No human ground truth for segmentation. Binder is the weakest class.
- 2-D area fractions are not 3-D volume fractions.
- The KPI model's deciding feature depends on ETD detector settings. A within-session label-shuffle test gives
  p = 0.06.

## 13. Software and compute
- **Code layout:**
  - Python: PyTorch, segmentation_models_pytorch, LightGBM, scikit-learn, scikit-image;
  - DINOv2 via torch.hub;
  - website: FastAPI + React (Vite);
  - LLM calls: Anthropic SDK.
- **Hardware:** one laptop with an RTX 5070 Ti.
- **Runtime:** about 90 s per new location for the full pipeline.
- **API cost:** about $80 of one-off Claude Opus labelling. Reports cost a few cents each (Sonnet).
- **To run:** double-click `scripts/start_website.bat` (API on port 8002, site on port 5173).
