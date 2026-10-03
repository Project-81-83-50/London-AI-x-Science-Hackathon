# SEM anode segmentation and batch identification: report

*31 samples (Batch_1: 7, Batch_2: 7, Batch_3: 17), 2026-10-03. Implements `docs/plan.md`; the batch-identification
part follows the "Route to 80 %" synthesis, trimmed. No pixel was labelled by hand.*

## 1. Summary

**Segmentation (deliverable).**
- 4-class label maps for all 31 samples at 50 nm/px: 0 pore, 1 graphite, 2 SiOx, 3 CBD, 255 excluded.
- They come from a 12.5 M-parameter U-Net that segments a new BSE + Inlens pair in **0.45 s on the RTX 5070 Ti** and
  **3.4 s on CPU (ONNX)**.
- Dataset composition (mean of samples): **pore 14.9 %** (deep 9.4 % + open/grey-floored 5.5 %), **graphite 62.5 %**,
  **SiOx 6.3 %**, **CBD 16.4 %**.

**Accuracy.**
- **Independent check, 82.1 %** pixel accuracy (95 % CI 76.7-86.4 %). Claude Opus 5.5 classified 240 uniformly random
  points without seeing any model output; the model agrees with **100 %** of the 113 points Claude marked
  high-confidence.
- **Per-class precision:** SiOx 96 %, graphite 77 %, pore 75 %, **CBD 50 %**. The pore/CBD boundary is the
  main uncertainty.
- **SiOx vs the threshold baseline:** within 0.13 pp on average (Spearman 0.96).
- **Pore:** above the threshold lower bound in every sample.
- **Stability:** phase fractions move < 0.6 pp when the teacher is retrained on other sample subsets and seeds.

**Batch differences.**
- **Batch 1 is less porous** (12.2 ± 1.6 % vs 15.5 ± 3.4 % and 15.7 ± 1.8 %; Kruskal-Wallis p = 0.004; B1 vs B3
  Holm p = 0.001). It weakens when only samples from the same imaging session are compared (p = 0.07).
- **SiOx and CBD fractions do not differ between batches.**
- The earlier vision-LLM claim that open-pore excess marks Batch 3 does **not** replicate in measured pixels.

**Batch identification** (one pre-registered scoring run, leave-one-sample-out):
- Segmentation features alone: balanced accuracy **0.42**.
- Fused with a DINOv2 texton head: **0.59** (Batch 1 5/7, Batch 2 2/7, Batch 3 13/17); permutation **p = 0.01**;
  leave-session-out **0.47**.
- **A classifier that sees only acquisition properties** (image size, grey levels, noise, banding) **reaches 0.68**,
  better than the material does. Batch membership is confounded with imaging session, and an honest batch claim
  needs that confound resolved first (§6).

## 2. What was delivered

| Path | Content |
|---|---|
| `outputs/segmentation/<batch>/<sid>/` | `labels.png` (uint8), `overlay.jpg`, `siox_instances.png` (uint16), `bse.png`, `inlens.png` |
| `outputs/metrics/phase_fractions.csv` | per sample: 4 classes, deep / open pore, SiOx after the baseline's size filter, excluded %, valid px |
| `outputs/metrics/batch_stats.csv` | per batch x class: mean, SD, range; Kruskal-Wallis; Holm-corrected Mann-Whitney; session-stratified permutation p |
| `outputs/metrics/particle_sizes.csv`, `siox_summary.csv` | 4,653 SiOx particles: area, equivalent diameter, aspect ratio, centroid |
| `outputs/metrics/validation.csv`, `validation_summary.json` | all validation numbers below |
| `outputs/metrics/kpi_values.csv`, `kpi_stats.csv` | 35 non-ML image KPIs and their batch statistics (§7) |
| `outputs/batchid/<sid>.json`, `<sid>_evidence.jpg` | per-sample facts JSON (predictions, features, evidence regions, QC) and evidence map |
| `models/student.pt`, `student.onnx`, `teacher.txt`, `bid_model.pkl` | deployable models (release asset) |
| `data/nnUNet_raw/Dataset501_SEMAnode/` | the segmented dataset in nnU-Net v2 format (release asset) |
| `reports/figures/` | contact sheet, hard-case panels, seed overlays, AI-label examples |

`python -m src.predict` segments a new image pair. `python -m src.bid_explain predict` runs the whole chain:
segmentation, features, DINO, batch prediction and evidence. On this laptop that takes 14 s, about 8 s once the
models are loaded.

## 3. Method

See [report_method.md](report_method.md) for the full description. In short:
- **Labels (no hand annotation):** rule seeds for the unambiguous pixels; Claude Opus 5.5 labelled 1,178 superpixels
  in the ambiguous regions; the rule-based CBD seeds were dropped because the annotator contradicted them 22/41
  times.
- **Teacher:** LightGBM on 54 multi-scale BSE + Inlens features, with two self-training rounds and a physical SiOx
  constraint (SiOx must be BSE-bright).
- **Student:** a U-Net distilled from the teacher's confident pixels.
- **Validation:** against the two earlier baselines; stability; held-out samples; independent AI point checks.

Two deviations from the plan, both forced by the data:
1. **Pore seeds.** The plan's "Inlens-dark = pore" rule fails where polished graphite is the darkest Inlens phase
   (e.g. `kbdh4tri`). Grey-floored pores therefore come from the AI superpixels, not from an intensity rule.
2. **SiOx gate.** The plan's gate compared SiOx with `thr` directly. But `thr` discards particles < 2 um^2 and thin
   edges, so the gate compares like with like: our SiOx after the same filter. Unfiltered, SiOx is ~0.5-1.5 pp
   higher because it includes small particles.

## 4. Segmentation results

### 4.1 Phase fractions by batch (% of valid area, mean ± SD)

| Phase | Batch_1 (7) | Batch_2 (7) | Batch_3 (17) | Kruskal-Wallis p | Session-stratified p | Holm MW 1v2 / 1v3 / 2v3 |
|---|---|---|---|---|---|---|
| pore (all) | 12.2 ± 1.6 | 15.5 ± 3.4 | 15.7 ± 1.8 | **0.004** | 0.073 | 0.052 / **0.001** / 0.53 |
| — deep (BSE-dark) | 7.9 ± 1.5 | 9.2 ± 1.5 | 10.0 ± 1.8 | 0.050 | 0.064 | 0.42 / 0.039 / 0.46 |
| — open (grey-floored) | 4.3 ± 1.2 | 6.2 ± 2.2 | 5.7 ± 1.0 | 0.026 | 0.32 | 0.11 / 0.020 / 0.80 |
| graphite | 64.9 ± 4.7 | 62.9 ± 3.1 | 61.3 ± 5.2 | 0.32 | 0.016 | n.s. |
| SiOx | 7.9 ± 3.5 | 5.7 ± 1.3 | 5.9 ± 0.9 | 0.22 | 0.56 | n.s. |
| CBD | 15.0 ± 3.6 | 16.0 ± 3.7 | 17.1 ± 5.0 | 0.70 | 0.31 | n.s. |

**How to read this table:**
- **SiOx:** Batch 1's higher mean comes from two samples imaged in one session (`4ih2ggld` 10.7 %, `5n1q8atc`
  14.6 %, the only 2316-px images). The rest of Batch 1 is 4.7-7.4 %.
- **CBD:** the amount clusters by imaging session. All four SE-detector samples (one session) and two of three
  1904-px samples read 20-24 %, against 11-17 % elsewhere, so treat CBD amount as partly a session readout.
- **SiOx particles:** median equivalent diameter 1.2-1.3 um; p90 3.4-4.2 um; 14-19 particles per 1000 um^2.

Figures: `reports/figures/contact_sheet.jpg` (all 31 overlays) and `hard_*.jpg` for the plan's hard cases:
- `kbdh4tri`: grey-floored pores captured;
- `epqdaau9`: Cu foil excluded;
- `r17byphk`: Inlens channelling contrast not turned into another class;
- `5n1q8atc`, `i9jiqjwl`: unpolished regions excluded.

### 4.2 Validation

| Check | Result | Target |
|---|---|---|
| SiOx vs `thr` (same size filter), mean abs. diff | **0.13 pp**, Spearman 0.96 | within 1.5 pp per sample: **met in all 31** |
| Pore >= `thr` (BSE lower bound) | **31 / 31** | every sample |
| Pore between `thr` and `vis` | 20 / 31 | "most" |
| Expected rankings | 3 / 4. `f1vzngrs` ranks 4th least porous (12.2 %), not top 3; the gap to 3rd is < 1 pp | all |
| Stability (teacher refit, 3 subsets x 2 seeds), SD of fractions | mean 0.01-0.14 pp, max 0.56 pp | < 1 pp: **met** |
| Student vs teacher, 6 held-out samples | 94.6 % of confident px (91.5 % all px) | >= 90 %: **met** |
| Student vs teacher fractions, held-out samples | max diff 3.9 pp (pore, `epqdaau9`: pore ↔ CBD swaps) | within 1 pp: **not met** |
| AI point check, uniform (n = 240) | **82.1 %** [76.7, 86.4]; 100 % on the 113 high-confidence points | — |
| AI point check, per predicted class (n = 30 each) | precision SiOx 0.96, graphite 0.77, pore 0.75, CBD 0.50 | — |
| Held-out AI superpixels (n = 141) | 83.7 % agreement [76.7, 88.9] | — |
| Detector ablation (SiOx MAD vs `thr`) | BSE 0.71, BSE + Inlens 0.78, + ETD/SE 0.82 pp; fractions change < 0.5 pp | third detector kept only if clearly better: **not kept** |
| Inference time per image | **0.45 s** GPU, **3.4 s** CPU (ONNX); GPU/CPU label agreement 99.99 % | <= 3 s GPU, <= 20 s CPU: **met** |

**Which model delivers the labels.** The student does. On the independent points it is at least as good as the
teacher: 82.1 % vs 80.8 % uniform, equal on the held-out samples and on the stratified points.

**Independent dataset composition.** From the uniform points (Claude's labels, 95 % CI):
- pore 19.6 % [15.1, 25.1];
- graphite 58.8 % [52.4, 64.8];
- SiOx 7.9 % [5.1, 12.0];
- CBD 13.8 % [10.0, 18.7].

The model's fractions (14.9 / 62.5 / 6.3 / 16.4) fall inside these intervals for SiOx and CBD. They are just
outside for pore (lower) and graphite (higher).

Confusion on the uniform points (rows = Claude, columns = model; pore, graphite, SiOx, CBD):

```
pore      31   8   0   8
graphite   3 135   0   3
SiOx       1   1  12   5
CBD        4  10   0  19
```

**Known weaknesses:**
1. **pore ↔ CBD.** Lacy binder is itself nanoporous, and pore walls look textured. It is the hardest call for the
   annotator too.
2. **Some open pores read as graphite.** Sub-surface flakes seen through a pore look like graphite. The model catches
   the cavity rims but labels part of the interior graphite, e.g. the large top-centre cavity in
   `hard_kbdh4tri.jpg`. Porosity is therefore still somewhat under-called: 14.9 % vs 19.6 % [15.1, 25.1] from the
   independent points.
3. **CBD along particle edges.** Some edge pixels are called CBD, so the CBD fraction may be over-called by a few pp.

## 5. Batch identification

One pre-registered procedure, scored once (look ledger: `outputs/metrics/look_ledger.csv`):
- **S:** five features from the label maps (SiOx %, area-weighted SiOx diameter, open-pore excess, total pore %,
  pore chord anisotropy) → robust z, clipped → shrinkage LDA.
- **F:** S averaged with a DINOv2-S/14-reg head. The segment-level head (tokens pooled over SiOx / pore / CBD) had to
  beat the whole-image head by >= 2 correct samples. It did not (20 vs 21), so the pre-registered fallback, a
  texton histogram (k-means K = 24, fitted in-fold), was used.

| | Balanced accuracy | Batch_1 | Batch_2 | Batch_3 |
|---|---|---|---|---|
| S, leave-one-sample-out | 0.42 | 4/7 | 1/7 | 9/17 |
| **F, leave-one-sample-out** | **0.59** | 5/7 | 2/7 | 13/17 |
| S, leave-one-session-out | 0.39 | 4/7 | 0/7 | 10/17 |
| F, leave-one-session-out | 0.47 | 4/7 | 0/7 | 14/17 |
| **Acquisition probes only (nuisance classifier)** | **0.68** | 4/7 | 4/7 | 15/17 |
| Permutation null for F (200 shuffles, falsifier choice inside each) | mean 0.33, 95th pct 0.48, 99th pct 0.55 → **F p = 0.01**; S p = 0.20 | | | |

- **The 2080-px triplet** (one sample per batch, imaged together), leave-session-out: 1/3 correct.
- **Evidence maps are exact.** Per-token contributions sum to the head's logits; reconstruction error 2e-13.
- **Each sample has a facts file**, `outputs/batchid/<sid>.json`, ready for the narrator layer. It contains:
  - the leave-one-out prediction and the final-model probabilities;
  - feature values with robust z-scores, each feature's push toward the winning batch, and half-split SDs;
  - the top-3 evidence regions with local phase fractions;
  - the phase share inside the top-10 % evidence;
  - a shortcut alarm.

**Interpretation.**
- **The fused result is a real signal.** It is above the 99th percentile of the label-shuffled null (p = 0.01) with
  the whole procedure inside each shuffle; the segmentation features alone are not (p = 0.20).
- **Batch 3 is partly recognisable** (13-14/17).
- **Batch 1 vs Batch 2 is not** (2/7 for Batch 2).
- **The acquisition-only classifier beats every material classifier.** This fails the plan's red-team check (it
  required <= 0.45). It means grey levels, noise, banding and image size differ systematically between batches.
- Until it is known whether the batches were imaged under different conditions, no batch-identification number,
  including ours, can be attributed to the material.

### 5.1 Exploratory: adding the visible brightness difference

By eye, Batch 2 looks like it has a darker background and lighter SiOx "dots" than Batch 1. We tested this as a
third, equal-weight head on raw BSE grey levels: graphite background, SiOx dots, and the contrast ratio
(SiOx − graphite) / (graphite − pore black level). It was added after looking at the data, so it is logged as
exploratory. Both versions were evaluated identically (`src/bid_compare.py`, `outputs/metrics/bid_compare.json`):

| | **A: original** (pre-registered) | B: A + brightness head | brightness head alone |
|---|---|---|---|
| Leave-one-sample-out balanced accuracy | **0.59** (5/7, 2/7, 13/17) | 0.54 (4/7, 2/7, 13/17) | 0.65 (5/7, 5/7, 9/17) |
| Leave-one-session-out | 0.47 (4/7, 0/7, 14/17) | 0.54 (3/7, 3/7, 13/17) | **0.47** (3/7, 4/7, 7/17) |
| Permutation p (200 shuffles, selection inside) | **0.01** | 0.035 | — |

**Raw grey levels per batch.**
- Background: B1 57.3, B2 54.3, B3 57.8.
- Dots: B1 108.3, B2 113.0, B3 112.5. Batch 1's darker dots come entirely from the two 2316-px images, which were
  taken in one session. The other five Batch 1 samples sit at 112-119, like Batch 2.

**Same-session pairs look the same.**
- 2156 px: `fzrt2k6r` B1 has background 62 / dots 114; `b3esycq1` B2 has 62 / 115.
- 2080 px: the contrast ratio is B1 1.09, B2 1.12, B3 1.24.
- 2148 px: the difference reverses (B1 1.59, B2 1.36).

**Conclusion.**
- **Brightness is the best Batch 1 vs 2 separator under leave-one-sample-out, but it collapses when whole sessions
  are held out (0.65 → 0.47).** That is the signature of a session shortcut.
- **Adding it to the fused model does not improve leave-one-sample-out accuracy.**
- **Version A stays the headline.**

### 5.2 Exploratory: ETD/SE topography and a two-step classifier

**Screen.** 77 KPIs were screened for Batch_1 vs Batch_2 (`src/kpi_topo.py`, `src/b12.py`,
`outputs/metrics/b12_screen.csv`). They cover:
- 26 new ETD topography and grain-contrast measures: gradient energy, shading, curtaining, graphite roughness, pore
  relief, edge brightening, flake-to-flake contrast;
- the 35 non-ML KPIs;
- the segmentation features.

**The lead: ETD graphite-surface roughness.** This is the local SD of the ETD signal inside polished graphite.
- **On normalised images it separates the batches perfectly:** Cliff's δ = 1.00, p = 0.0006, BH q = 0.045. It also
  holds without the SE-detector sample and in all 3 same-session B1/B2 pairs.
- **Not detector noise:** the raw ETD noise is identical in B1 and B2 (σ = 7.04).
- **Not the normalisation range:** it does not differ between batches.
- **In raw grey units the effect is moderate** (`src/roughness_check.py`): B1 2.74 vs B2 2.08 vs B3 1.96, δ = 0.63,
  p = 0.053, 2/3 same-session pairs. So part of the perfect separation comes from per-image normalisation and from
  picking the best of 77 measures.
- **Interpretation:** Batch 1 graphite surfaces show ~30 % more ETD texture at the 0.1-0.2 um scale. That suggests a
  sample-preparation or graphite-grade difference, to be confirmed with the organisers.

**Two-step classifier.**
- Step 1, "Batch 3?": the original fused model's honest leave-one-out / leave-session-out probabilities.
- Step 2, "Batch 1 or 2?": trained only on B1/B2 samples; the 3 KPIs with the largest effect are selected inside each
  fold.

| | Leave-one-sample-out | Leave-one-session-out | Step 2 alone (B1 vs B2, n = 14) |
|---|---|---|---|
| Original F (reference) | 0.59 (5/7, 2/7, 13/17) | 0.47 (4/7, 0/7, 14/17) | — |
| Two-step, all 77 KPIs | **0.64** (4/7, 4/7, 13/17) | **0.56** (3/7, 3/7, 14/17) | 10/14; permutation p = 0.16 (null 95th pct 11/14) |
| Two-step, session-insensitive KPIs only | 0.59 (4/7, 3/7, 13/17) | 0.51 | 9/14; p = 0.27 |

**Conclusion.**
- **The two-step design is more accurate and more robust to session hold-out.** Its B1-vs-B2 step cannot be shown to
  beat chance with 7 + 7 samples, because selecting 3 of 77 features with 13 training samples often looks good by
  luck. ETD roughness was selected in every fold.
- **Recommended next step:** pre-register step 2 as **ETD graphite roughness + total porosity**, fixed now, and test
  it once on the blind / new data. It needs the ETD image, so SE-detector images cannot use step 2.

## 6. The session confound

- **Image heights identify imaging sessions,** and those sessions mix batches. For example, 2080 px:
  `ffwubibz` B1, `r17byphk` B2, `cfe5vt7s` B3. 2068 px with the SE detector: `rxax5ozo` B2 plus three B3.
- **Several batch effects weaken when only same-session samples are compared** (pore p 0.004 → 0.07), and CBD
  amount clusters by session.
- **Recommended question to the organisers:** were kV, beam current, working distance, detector settings and
  stage/session the same for all batches? If not, which samples share a session?
- **With that metadata,** the batch analysis can be re-run with session as a blocking factor.

## 7. Non-ML image KPIs (exploratory)

35 KPIs computed with plain image processing, without the trained models:
- **thresholds:** multi-Otsu dark/bright fractions;
- **pore and SiOx shapes:** size, aspect ratio, solidity, circularity, orientation order, Clark-Evans clustering,
  boundary fractal dimension, chords;
- **contrast:** SiOx/graphite BSE contrast ratio, grey-level skew/kurtosis/entropy, edge density;
- **flake alignment:** structure tensor;
- **power-spectrum** slope and anisotropy;
- **heterogeneity:** window CVs, top/bottom ratio, lacunarity.

Each KPI was tested for batch differences with false-discovery control (BH across the 35 KPIs), a session-stratified
permutation test, and its correlation with acquisition probes.

| KPI | B1 | B2 | B3 | KW p | BH q | Session-stratified p | Cliff's δ B1 vs B2 | Note |
|---|---|---|---|---|---|---|---|---|
| SiOx / graphite BSE contrast ratio | 1.20 | 1.53 | 1.67 | 0.002 | 0.08 | 0.23 | **−0.76** | tracks Inlens grey level (ρ = 0.59) |
| pore-boundary fractal dimension | 1.18 | 1.20 | 1.21 | 0.013 | 0.21 | 0.06 | −0.47 | tracks file size (ρ = 0.63) |
| pore patchiness (CV over 10 um windows) | 0.57 | 0.53 | 0.49 | 0.018 | 0.21 | 0.26 | 0.39 | |
| BSE grey skew (graphite / CBD) | 0.21 | 0.57 | 0.76 | 0.031 | 0.27 | 0.67 | −0.59 | session-sensitive |
| threshold dark (pore) fraction | 8.8 | 10.0 | 10.8 | 0.054 | 0.27 | 0.08 | −0.43 | |

- **No KPI survives the false-discovery correction.** An exploratory classifier (the top-5 KPIs chosen inside each
  leave-one-out fold → shrinkage LDA) scores **0.49**, against a null 95th percentile of 0.58 (p = 0.14), i.e.
  not better than chance.
- **The one lead worth following is the SiOx/graphite BSE contrast ratio.** It is the only measure with a large
  Batch 1 vs Batch 2 effect. BSE contrast depends on mean atomic number, so a real difference would mean a
  different SiOx stoichiometry (the x in SiOx). It also tracks acquisition settings, though. If the organisers
  confirm identical imaging conditions, it becomes the best Batch 1 vs 2 candidate; EDS on a few particles per
  batch would settle it.

## 8. Limitations

- **There is no ground truth.** Accuracy is estimated against an AI annotator, which is good on clear cases (100 % on
  high-confidence points) and unreliable on the pore/CBD boundary.
- **2D area fractions are not volume fractions.** Open-pore detection depends on seeing sub-surface material.
- **One field (~175 x 50 um) per sample;** field-to-field variation within an electrode is unknown.
- **31 samples.** One Batch_1 sample is worth 4.8 balanced-accuracy points.

## 9. API cost

Claude Opus 5.5 at max effort, via the Batch API where possible:

| Item | Cost |
|---|---|
| Superpixel labels | $29.30 |
| Uniform point check | $4.92 |
| Stratified point check | $2.72 |
| Pilot | $0.39 |
| **This stage, total** | **≈ $37** |
| Earlier per-sample analysis (separate) | $33.45 |
