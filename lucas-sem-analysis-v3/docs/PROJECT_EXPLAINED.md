# The whole project, explained (Polaron track: which battery batch is this SEM image from?)

> **Update (current method, used by the website's Demo and Pipeline pages).** After organiser feedback, the batch
> **decision now comes from Guanyi's KPI model** (ETD-dark solid: area dark in ETD but solid in BSE, i.e. sub-surface
> pores; diagonal LDA fitted on the 31 reference locations). Our v3 material model (U-Net segmentation + DINOv2) is the
> **check and the explanation**, and contributes **10 % of the final probability** (90 % KPI model + 10 % v3 material
> model; 10 % is the largest share that changes none of the 9 unknown answers). If the v3 material model alone picks
> another batch, the confidence is Low. Two confidence levels only: **High** when the KPI model is at least 50 % sure
> and the v3 material model agrees, otherwise **Low**. The facts file sent to the agents includes the KPI model's full evidence
> (all 32 KPIs, nearest reference locations, its own reference validation). The
> **imaging fingerprint and the tile texture model are no longer used** (they read imaging conditions, not material).
> Composition is shown with GET4 95 % sampling intervals. Unknown batch: 3e122cbj → Batch 2 (Low, material model
> disagrees), fn0mhxef → Batch 1, xrv9xvzb → Batch 3, matching the organisers' feedback. Six further unknown
> locations: 0eryguqq → Batch 3, 4hq27w4c → Batch 1, fhwrjtet → Batch 3, fspqbkxl → Batch 2 (Low),
> soo2ax3r → Batch 2 (Low), y59rxmxl → Batch 1 (Low, material model says Batch 2). The track-record statistics
> below and on page 1 of the website were computed for the earlier method and have **not** been recomputed.

This is the explainer for the pitch. Part A says what we built and why. Part B goes through every step, with its
settings and its results. Part C is a bank of judge questions with suggested answers.

All batch-identification numbers are **leave-one-location-out**: each location is predicted by models that never
saw it. More on that in B5.8.

---

# Part A: the 60-second version

**Task.** We have 31 SEM cross-sections of a graphite + SiOx lithium-ion anode from three production batches
(7 / 7 / 17 locations). An unknown set has to be assigned to batch 1, 2 or 3, with evidence and an honest
uncertainty.

**What we built, in four layers:**
1. **Label-free segmentation.** Every pixel becomes pore, graphite, SiOx or binder, without anyone labelling
   anything by hand. Rules label the easy pixels and Claude labels the hard regions. A LightGBM "teacher" learns
   from those labels and a fast U-Net "student" learns from the teacher. It agrees 87 % with an independent
   annotator on pore / carbon / SiOx.
2. **Two independent batch detectors that must agree:**
   - an **imaging fingerprint**, which reads how the image was acquired: noise, scan banding, grey levels;
   - a **material model**, which reads what the material looks like: segmentation measurements plus DINOv2, a
     self-supervised vision model.
3. **A decision layer that is allowed to say "unsure".**
   - It answers 84 % of locations and is right 85 % of the time when it answers.
   - High-confidence answers are right 10 / 12.
   - An always-answer mode reaches 0.80 balanced accuracy (permutation p = 0.001).
4. **Text-only explanations.** Every prediction writes a `facts.json`, including the maps described in words.
   Three Claude agents (analyst, materials expert, skeptic) turn it into a report and may only quote numbers that
   are in the file. A code check verifies that.

**The honest headline finding:** Batch 1 and Batch 2 differ only subtly (Batch 2 is more porous, with more open and hidden
pores; their ranges overlap), so the
system says "Batch 1 or Batch 2" when the evidence splits. Batch 1 is less porous (14.4 % vs 17.8 % and 18.2 %),
and that difference survives a within-session test.

---

# Part B: every process in detail

## B1. The data

- **31 locations.** Batch 1 has 7, Batch 2 has 7, Batch 3 has 17.
- **Three detectors per location**, all imaging the same spot and lined up to within 0.4 px:

  | Detector | What it shows |
  |---|---|
  | **BSE** (backscattered electrons) | Brightness follows atomic number (Z). SiOx (Si, O) is brighter than carbon, so BSE is the composition view. It is also the grainiest view |
  | **Inlens** (in-lens secondary electrons) | Fine surface detail, edges and particle rims. Its brightness is affected by charging and channelling |
  | **ETD or SE** (Everhart-Thornley secondary electrons) | Topography and shading. Pores stay black. 27 locations have ETD, 4 have SE |

- **Resolution:** 25 nm per pixel, roughly 2,060–2,316 × 7,000 px, so about 175 × 55 µm per image.
- **Imaging sessions.** We have no session metadata, so **image height** stands in for the session: images taken
  together share a height. That gives 13 groups, and the sessions mix batches. This matters a lot (B5.8 and B9).
- **Unknown set:** 3 new locations × 3 detectors. None is a re-shot of a known spot.

## B2. Preprocessing (`src/preprocess.py`)

1. Read the green channel (the TIFFs are RGB with identical channels).
2. Downsample 2 × 2 by block mean, to 50 nm/px. This halves the noise and is still finer than the smallest
   features.
3. **Exclusion mask:**
   - an 8-px border;
   - the copper current collector (saturated BSE ≥ 240 connected to the top or bottom edge);
   - three manually confirmed unpolished strips.

   About 1 % of pixels are excluded (label 255).
4. Normalise each detector to its 0.5–99.5 percentile range of valid pixels, mapped to [0, 1].
5. Apply a 3 × 3 median filter to remove speckle noise.

## B3. Labels without hand-labelling

We needed training labels but did not want to hand-label. The solution has two sources.

### B3a. Rule seeds (`src/seeds.py`): the easy pixels
- **SiOx:** BSE above the upper multi-Otsu threshold (Otsu's method finds the thresholds that best split the
  histogram into 3 classes). Then morphological opening, keeping objects ≥ 2 µm², and an erosion so only
  confident cores remain.
- **Pore:** dark in Inlens and ETD/SE and not SiOx-bright, or BSE-dark and ETD-dark.
- **Graphite:** mid-grey BSE, smooth Inlens texture, and far from any strong edge, i.e. the interiors of large
  flat particles.
- **Binder (CBD):** a rule was written, but **dropped**. When Claude checked these pixels blind, it disagreed
  22 / 41 times, while it agreed with the pore, graphite and SiOx rules.
- Pixels claimed by two rules stay unlabelled. Seeds cover only the confident part of each image.

**Why rules aren't enough:**
- **Open pores.** The sections are not resin-filled, so you can look into a pore and see grey material below the
  polished plane. In BSE it looks grey like graphite.
- **Binder vs particle rims.** No simple brightness rule separates them.

### B3b. AI-labelled superpixels (`src/ai_labels.py`): the hard regions
- **Superpixels.** SLIC groups pixels into small regions of similar intensity, about 300 px each (~0.75 µm²,
  "~1 µm"), computed on all three detectors stacked together (compactness 3).
- **Rendering.** Each chosen superpixel is shown to **Claude Opus 5.5** as three side-by-side crops of the same
  8 × 8 µm area (BSE | Inlens | ETD/SE), with the superpixel outlined in yellow.
- **The prompt** describes what each class looks like in each detector. For example: a pore can have a grey
  floor; binder is lacy and nanoporous at particle necks.
- **The answer** is a strict JSON format: label (pore / graphite / SiOx / CBD / mixed / uncertain), confidence
  (low / medium / high) and a one-line reason.
- **Batch API:** requests went through Anthropic's Message Batches API, which is half price and asynchronous.
- **Filtering:** only medium- and high-confidence labels of the 4 real classes are used.
- **Blind controls:** already-seeded superpixels were mixed in without telling Claude. That's how we measured that
  it agrees with the pore / graphite / SiOx rules and caught the bad binder rule.
- **Round 1:** 1,178 superpixels in ambiguous regions.
- **Round 2 (active learning, v2):** 992 new superpixels chosen where the v1 U-Net was **least confident**, mostly
  pore vs binder, plus a random control set. 803 were used for training and 189 held out. Labelling the model's
  own doubts is the most efficient use of the annotation budget.

## B4. Per-pixel features (`src/features.py`)

There are 27 features per detector. For BSE and Inlens, that's 54 for the teacher:
- at 4 scales (σ = 1, 2, 4, 8 px): Gaussian blur, gradient magnitude, Laplacian of Gaussian, both Hessian
  eigenvalues and local standard deviation (24);
- the denoised value;
- a fine-texture energy, |difference of Gaussians|, which picks up lacy binder;
- a context feature: the value minus its local mean. In BSE this is a depth / shadow cue for pore floors.

These describe each pixel's neighbourhood at several sizes, so the classifier can tell "smooth grey interior" from
"grey but finely textured" from "grey next to a shadow".

## B5. The teacher: LightGBM (`src/teacher.py`)

- **What LightGBM is:** a gradient-boosted decision-tree classifier. It is fast, strong on tabular features, and
  runs on CPU.
- **Training:** all seed and AI-label pixels (training split), multiclass, learning rate 0.12, 300 trees, 63
  leaves, at least 200 samples per leaf.
- **Self-training (2 rounds):** after each fit, pixels predicted with probability ≥ 0.9 that also agree with
  their 5 × 5 neighbourhood majority are added as new labels, and the model is refit. This spreads the labels
  from the confident cores into similar-looking pixels.
- **Physics constraint** (`src/physics.py`), applied to every model: a pixel can only be SiOx if its smoothed BSE
  is above the SiOx/carbon Otsu threshold. SiOx must be Z-bright, whatever its texture. This removes bright rims
  and halos that inflated SiOx by 1.5–4 percentage points (pp). Small dark specks inside SiOx particles are filled
  back in.
- **Detector ablation:** adding ETD/SE as a third input changed the phase fractions by less than 0.5 pp, and 4
  locations have SE instead of ETD. So segmentation uses **BSE + Inlens only**.
- **Stability:** refitting on 3 random subsets × 2 seeds moves the phase fractions by less than 0.8 pp.

## B6. The student: U-Net, distilled from the teacher (`src/student.py`)

- **What a U-Net is:** a convolutional network shaped like a "U":
  - an **encoder** shrinks the image step by step and learns what is there;
  - a **decoder** grows it back to full size and learns where it is;
  - **skip connections** pass fine detail from the encoder to the decoder.

  It outputs a class for every pixel. It's the standard architecture for microscopy segmentation.
- **Our U-Net:**
  - built with `segmentation_models_pytorch`;
  - **ResNet-18 encoder** pretrained on ImageNet;
  - 2 input channels (BSE, Inlens), 4 output classes;
  - **12.5 M parameters**.
- **Knowledge distillation:** a small, fast "student" model learns to imitate a "teacher". Here:
  - the student's targets are the **teacher's labels**;
  - pixels where the teacher's probability is below 0.7 are **ignored**, as are excluded pixels;
  - so it learns only from confident labels and fills in the rest from image context.
- **Why distil instead of just using the teacher?**
  - **Speed:** 0.31 s per image on GPU and 1.5 s on CPU (ONNX), against minutes for 54-feature extraction plus
    LightGBM.
  - **Spatial coherence:** a CNN sees shapes and context, not just per-pixel features.
  - **Accuracy:** the student is at least as good as the teacher on independent points (81.7 % vs 80.8 %).
  - **Deployability:** one weights file, exportable to ONNX.
- **Training settings:**
  - 25 locations for training, **6 held out** (2 per batch);
  - random 512 × 512 crops, 3,000 per epoch, batch size 12, **18 epochs**;
  - optimiser AdamW (learning rate 1e-3, weight decay 1e-4) with a one-cycle schedule;
  - loss = **cross-entropy + Dice**. Dice counters class imbalance, because SiOx is only about 6 % of pixels.
  - **Augmentation:** horizontal flips, intensity changes, noise, synthetic Inlens banding (imitates charging
    stripes) and small elastic deformations. These make it robust to imaging variation.
- **Inference:** tiled into 512-px tiles with 64-px overlap and soft blending at the seams, then the physics
  constraint and clean-up. The model is exported to ONNX and GPU and CPU outputs agree on 99.99 % of pixels.
- **Student vs teacher on the 6 held-out locations:** 96.1 % agreement on confident pixels, 91.0 % on all pixels.

## B7. How good is the segmentation? (`src/ai_validate.py`, `src/validate.py`)

There is no human ground truth, so we built an independent check:
- **240 uniformly random points.** Claude labelled them **without seeing any model output**.
  - 4 classes: **81.7 %** (95 % CI 76.3–86.1).
  - 3 classes (pore / carbon / SiOx): **87.1 %** (82.2–90.7).
  - On the 113 points Claude was sure about: **100 %**.
- **Class-stratified points**, measuring precision: SiOx 0.96, graphite 0.83, pore 0.69, **binder 0.52**. So
  composition is reported mainly as **pore / carbon / SiOx**, and binder is marked experimental.
- **Held-out superpixels in the hardest regions:** 70 % (64 % in v1, before active learning).
- **Against the earlier threshold baseline:** SiOx agrees within 0.13 pp, and pore is at or above the threshold
  lower bound in all 31 locations.

**Dataset composition** (mean of locations):

| Phase | % |
|---|---|
| Pore | 17.3 (deep 9.5 + open 7.7) |
| Graphite | 61.0 |
| SiOx | 6.3 |
| Binder | 15.4 |

The independent estimate of porosity is 19.6 % [15.1, 25.1].

**Batch differences:**
- **Batch 1 is less porous:** 14.4 % vs 17.8 % and 18.2 %. Kruskal-Wallis p = 0.004, and **p = 0.031 when
  labels are shuffled only within imaging sessions**, so it is not just a session effect.
- SiOx and binder do not differ between batches.

## B8. Batch identification: the models

### B8a. Material side, part 1: segmentation features (the "S head")

Five physical measurements from the label map:
- SiOx area %;
- area-weighted SiOx particle diameter;
- open-pore excess;
- total pore %;
- pore chord anisotropy (are pores elongated in one direction?).

Each is converted to a **robust z-score** (median and IQR, clipped at ±3) and fed to a **shrinkage LDA**.

**LDA** (linear discriminant analysis) fits one Gaussian per batch with a shared covariance and draws linear
boundaries between them. **Shrinkage** pulls the covariance estimate toward a simpler one, which is essential
with 31 samples. On its own the S head scores 0.48.

### B8b. Material side, part 2: DINOv2 (the "D head")

- **What DINOv2 is:**
  - a **Vision Transformer** (ViT) from Meta, trained **self-supervised** (no labels) on about 142 million images;
  - it learns general-purpose visual features: textures, shapes, parts;
  - "ViT-S/14" is the small model (about 21 M parameters), working on **14 × 14-pixel patches**;
  - "with registers" adds a few extra tokens that absorb global information. That gives cleaner patch features.
- **How we use it:**
  - **frozen**, i.e. no fine-tuning, which would overfit with 31 samples;
  - we tile each normalised BSE and Inlens image into 518 × 518 crops and keep the **patch tokens**;
  - each token is a 384-number description of a 0.7 µm patch (14 px at 50 nm/px).

  So every location becomes a grid of "visual words".
- **Texton histogram:**
  - **k-means** groups all patch tokens into **K = 24** recurring "textons" (visual words), fitted only on the
    training locations of each fold;
  - each location becomes a 24-bin histogram: how often each texton appears;
  - square root → standardise → PCA (4 or 8 components) → balanced logistic regression, averaged over 6 settings.
- **Explainability:** the head is linear, so its score splits **exactly** into a contribution per patch (summing
  back to within ~1e-13). That gives a true evidence map, red = toward the batch and blue = against, not a
  heuristic saliency map.
- **Material model F** = the average of S and D. Leave-one-out balanced accuracy **0.61** (permutation p = 0.005).

### B8c. Imaging side: the acquisition fingerprint (teammate's design, replicated exactly, 23 / 31)

Seventeen measurements per detector view (BSE, Inlens, ETD/SE):

| Group | Measurements |
|---|---|
| Noise | level and spikiness (kurtosis) of the residual after a 3 × 3 median filter |
| Scan direction | correlation of the noise along and across the scan lines |
| Banding | dominant horizontal banding period and how dominant it is; line-to-line brightness jitter |
| Stripes | vertical stripe (column pattern) strength |
| Frequency | high-frequency power in x and y |
| Grey levels | 1st / 50th / 99th percentile, number of grey levels used, clipping at black and white |
| File | **LZW compressibility** (bytes per pixel) |

Each measurement → robust z → shrinkage LDA per view, and the views are combined. Leave-one-out balanced accuracy
**0.70** (p = 0.002).

**What it really measures:** how each batch was imaged, more than what the material is. We say this openly (B9).

### B8d. Tile texture model (teammate's design, rebuilt; information only)
- The image is cut into 12.8 µm tiles (512 px at 25 nm/px).
- Each tile is described by:
  - local binary patterns: tiny pixel-neighbourhood patterns, counted;
  - grey-level co-occurrence texture: contrast, homogeneity, energy, correlation;
  - power-spectrum bands.
- Logistic regression per view; the tile probabilities are averaged.
- Leave-one-out 0.58 (0.68 on BSE alone). **It does not vote**: letting it vote lowered accuracy from 85 % to
  80 %. It is reported for information.

### B8e. Training-image guard and known-spot matcher (teammate's design)
- **Guard:** an input whose pixels are identical to a training image is refused. Testing on training data would
  be meaningless.
- **Matcher:**
  - the image is reduced to an **edge map** (particle and pore outlines at about 200 nm/px), which looks similar
    whatever the detector;
  - it is compared with all 93 reference images by **phase correlation**, an FFT method that finds the best
    alignment even when the image is shifted;
  - a **known spot** needs a peak of ≥ 15 standard deviations **and** at least 2 × the next-best location. We
    added the margin because crops produced false matches without it.
- **Results:**
  - **0 / 93 false matches**, for full images and for 50 % crops;
  - all 93 full images matched through another detector's view;
  - 50 % crops matched 71–86 of 93.
- The three unknown locations score 9–10 SD, so they are new spots.

### B8f. GET4 material-range rule (teammate's GET4 error bars)
- **GET4** estimates how precisely one image determines a phase fraction:
  - the **two-point covariance** gives the typical feature size, i.e. how many independent samples the image is
    worth;
  - a **tile overdispersion** factor adds large-scale irregularity.

  The result is a 95 % error bar on pore %, carbon % and SiOx %.
- **The rule:** if a phase's error bar overlaps only one batch's training range, that phase votes for that batch.
  The rule can turn "Batch 1 or Batch 2" into a single answer.
- **In practice:** it fired for 1 / 31 locations (correctly). The composition ranges overlap too much with 7
  locations per batch.

## B9. The session confound (why we are careful)
- A classifier that sees **only acquisition properties** (image size, grey levels, noise) predicts batch at
  **0.68**. So the batches were partly imaged under different conditions.
- That is why we:
  - **require two different kinds of evidence to agree** (imaging and material);
  - test **within-session** effects;
  - report session-held-out results in the report.
- **The unknowns sit in known sessions:** their image heights match sessions that contain only one reference
  batch each. That makes the leave-one-location-out numbers the right guide for them.

## B10. Calibration and the decision layer (`src/v3.py`, `src/decision.py`)

- **Calibration (temperature scaling):** a model saying "90 %" should be right about 90 % of the time. We divide
  each model's log-probabilities by a temperature *T*, fitted on held-out predictions, to fix over- or
  under-confidence. Final values: fingerprint *T* = 3.85, which means it was very over-confident; material
  *T* = 0.64.
- **The agreement rule.** The imaging side (calibrated fingerprint) and the material side (calibrated F) each pick
  a batch:
  - **both pick the same batch** → that batch;
  - **they disagree, but both pick Batch 1 or Batch 2** → "**Batch 1 or Batch 2**"; the GET4 rule may settle it;
  - **otherwise** → "**unsure (leaning X)**", where X is the batch with the highest average probability.
- **Confidence tier:**
  - **High:** both sides agree, the average calibrated probability is above the level at which held-out answers
    were **≥ 90 % right** (chosen inside each fold; the final threshold is 0.62), the fingerprint's detector
    views agree, and there are no novelty or shortcut flags;
  - **Medium:** other agreeing answers, and "Batch 1 or Batch 2";
  - **Low:** unsure.
- **Prediction set:** every batch whose average probability is at least 20 %.
- **Forced mode** (always answers), the teammate's two-step design:
  1. the fingerprint decides "Batch 3 or not";
  2. otherwise the GET4 rule decides, or else a Batch 1-vs-Batch 2 fingerprint specialist.
- **The order for any new image:** guard → matcher → the two sides → agreement rule → GET4 rule → tier.

## B11. How we tested (honesty machinery)
- **Leave-one-location-out (LOO):** hide one location, train on the other 30, predict the hidden one. Repeat 31
  times.
- **Nested:** everything chosen from data is also chosen without the hidden location: calibration temperatures,
  the High threshold, GET4 ranges and the DINOv2 vocabulary.
- **Leave-one-session-out:** a stricter variant that hides a whole imaging session at once. It is in the report.
- **Permutation test:** shuffle the batch labels 200–1000 times and rerun the whole procedure. The p-value is how
  often shuffled labels score as well as the real ones.
- **Balanced accuracy:** the average of per-batch recall. Batch 3 has 17 of 31 locations, so plain accuracy would
  reward always guessing Batch 3.
- **Wilson 95 % intervals** for every success rate.
- **Look ledger** (`outputs/metrics/look_ledger.csv`): every configuration we ever scored is logged. This guards
  against trying many things and only reporting the best.

## B12. Results (leave-one-location-out)

| | Result |
|---|---|
| **Answers given** | **26 / 31 (84 %)** |
| **Right when answering** | **22 / 26 (85 %)**, 95 % CI 66–94 % |
| Specific-batch answers right | 19 / 23 |
| "Batch 1 or Batch 2" answers right | 3 / 3 |
| High tier right | **10 / 12** |
| Medium tier right | 12 / 14 |
| Unsure | 5 (Batch 2 × 3, Batch 3 × 2) |
| **Forced mode** | **0.80 balanced accuracy, 25 / 31 right**, permutation p = 0.001; per batch 6 / 7, 5 / 7, 14 / 17 |
| Single models (balanced accuracy) | fingerprint 0.70 · material 0.61 · tile texture 0.58 · segmentation features alone 0.48 |

**Comparison with the team's other classifiers:**
- Teammate's batch classifier (his own nested test): answers 58 %, right 94 %; forced 24 / 31.
- KPI classifier: 0.68 balanced.

## B13. Are Batch 1 and Batch 2 the same?
- Of 77 measured features, **3** differ at p < 0.05. Chance alone predicts 3.9.
- A multivariate test of the whole distribution: p = 0.19.
- **A blinded "odd one out" test.** Claude saw three crops, two from one batch, and had to pick the odd one. For
  B1 vs B2 it scored **27 %**, below the 33 % you'd get by chance.
- **Possible small differences:**
  - Batch 2 is about 3.5 pp more porous (CI 0.9–6.3);
  - Batch 1 has stronger vertical stripes in ETD, likely from ion-milling curtaining.
- **Conclusion:** they are the same material, or differ by less than 14 locations can resolve. Hence the
  "Batch 1 or Batch 2" answer.

## B14. Explanations: `facts.json` and the agents
- **`facts.json`, one per image, all text and numbers:**
  - the decision first, then composition;
  - the known-spot and GET4 checks;
  - fingerprint cues with plain meanings;
  - texture cues;
  - the material model's features;
  - **`map_text`**: the segmentation and evidence maps **described in words**: evidence by phase and by region, a
    3 × 3 composition grid, the largest pores and particles with positions, and particle clustering
    (Clark-Evans);
  - quality-check and novelty flags;
  - summary sentences generated only from these numbers.
- **Why text only:** the LLM can't misread a picture, and everything it says is traceable to a number.
- **Three agents** (Claude Sonnet 5.5, medium effort):
  1. **Evidence analyst:** lists the findings, quoting numbers exactly.
  2. **Materials expert:** interprets the microstructure using the team's literature knowledge base (25 Si/C SEM
     features with references), citing items by id and never as measurements.
  3. **Skeptic / writer:** checks every claim against `facts.json`, deletes anything unsupported (and lists what
     it deleted), and writes the final report.
- **Code check:** every number in the report must occur in `facts.json`. Anything else is flagged on screen.

## B15. The website (one click: `START_WEBSITE.bat`)

It starts the API on port 8002 and the website on port 5173. There are three pages:
1. **Batches.** The batch 1–3 reports (composition, statistics, overlays, uncertainty) and the unknown batch. Under
   Unknown → Classification, v3's call per location comes first, with the KPI classifier as a second opinion.
2. **Demo.** Upload BSE + Inlens (+ ETD) of one location. The models are trained on batches 1–3, and the result
   comes back in about 65 s on the laptop GPU: batch, confidence tier and calibrated %.
3. **Pipeline.** A step diagram and every step's output: inputs and quality check, segmentation overlay and
   composition, material features, DINOv2 evidence map, fingerprint, known-spot check, texture, GET4 range,
   calibration and decision. **Generate report** runs the three agents.

## B16. The unknown batch (v3 answers)

| Location | v3 answer | Imaging / material side | KPI classifier (2nd opinion) | Imaging session holds references from |
|---|---|---|---|---|
| 3e122cbj | **Batch 1**, Medium (84 %) | B1 / B1 | Batch 2 (low) — disagrees | Batch 1 only |
| fn0mhxef | **Batch 1**, Medium (63 %) | B1 / B1 | Batch 1 | Batch 2 only |
| xrv9xvzb | **Batch 3**, High (82 %) | B3 / B3 | Batch 3 | Batch 3 only |

`fn0mhxef` is the interesting one. Its session contains only Batch 2 references, yet both of our sides say
Batch 1. So our answer is not simply copying the session.

## B17. Limitations (say these before the judges do)
- 31 locations: the confidence intervals are wide, and one Batch 1 location is worth about 5 points of balanced
  accuracy.
- There is no human ground truth. Accuracy is measured against a blind AI annotator, which is very good on clear
  cases and weak on pore vs binder.
- 2-D area fractions are not 3-D volume fractions.
- The fingerprint partly reads imaging conditions. A blind set imaged in new sessions may score lower.
- The decision rule and forced mode were designed after looking at these 31 locations. Everything is logged and
  nested, but the blind set is the real test.

## B18. Cost and compute
- **API cost:** about $80 of Claude Opus labelling in total (v1 + v2). It's a one-off: no labels are needed at
  inference. Agent reports are a few cents each (Sonnet).
- **Hardware:** one laptop with an RTX 5070 Ti.
- **Runtime:** segmentation 0.31 s / image. Full v3 pipeline about 30–65 s per location.

---

# Part C: question bank with suggested answers

### About the problem and the data
1. **Why is this hard?** All batches are the same anode recipe. Differences, if any, are subtle, and we have only
   31 locations. Imaging conditions also differ between batches, so a model can easily learn the microscope
   session instead of the material.
2. **Why three detectors?** They show different physics:
   - BSE: atomic-number contrast, which separates SiOx from carbon;
   - Inlens: surface detail and edges;
   - ETD/SE: topography (pores stay black).

   No single one resolves everything.
3. **What's the unit of analysis?** A location: one spot imaged by 3 detectors. Views of one location are never
   counted as independent samples.

### Labels and segmentation
4. **You said no hand labels. Where did the training labels come from?**
   - Rules for the obvious pixels.
   - Claude Opus for about 2,200 ambiguous superpixels, shown three detectors side by side.
   - Self-training to spread confident labels.
   - Then distillation into a U-Net.
5. **Isn't using an LLM as a labeller risky?**
   - We measured it: blind seeded controls, and an independent 240-point check that the model never saw.
   - It caught our own bad binder rule (22 / 41 disagreements).
   - We only use medium- and high-confidence labels.
6. **Why a teacher and a student instead of one model?**
   - The teacher (LightGBM on hand-designed features) learns well from sparse, noisy labels.
   - The student (U-Net) is about 1,000 × faster, spatially coherent, and at least as accurate on independent
     points.
   - That's classic knowledge distillation.
7. **Why ignore pixels below 0.7 teacher confidence?** So the student doesn't copy the teacher's mistakes. It
   learns from confident pixels and uses image context for the uncertain ones.
8. **How accurate is the segmentation?** 87 % for pore / carbon / SiOx and 82 % for four classes, against a blind
   annotator, and 100 % on clear points. Binder precision is about 0.5, so we report binder as experimental.
9. **What is the physics constraint?** SiOx must be brighter than carbon in BSE (Z-contrast). Any "SiOx"
   prediction on a dark pixel is overruled. This removed 1.5–4 pp of false SiOx at particle rims.
10. **Why is pore lower on the team's GET4 tab?** That tab uses brightness thresholds, so it counts only black
    pores: about 8–10 %, which matches our deep-pore numbers. It misses grey-floored open pores, which our model
    catches.
11. **Did you try nnU-Net?** We exported the dataset in nnU-Net format (Dataset501). The 12.5 M-parameter U-Net
    already met the speed and accuracy targets, so nnU-Net is a ready next step.

### DINOv2 and the models
12. **What is DINOv2 and why use it?** A self-supervised vision transformer trained on about 142 M images. Its
    patch features describe texture and shape without any labels. Frozen, it gives strong general features that
    31 samples could never train from scratch.
13. **Why not fine-tune DINOv2 or train a CNN classifier?** 31 samples would overfit badly. A frozen backbone plus
    a tiny linear head, tested leave-one-out, is the honest choice.
14. **What's a texton?** A recurring visual pattern: one of 24 clusters of DINOv2 patch features. Each location is
    summarised by how often each pattern appears.
15. **How is the evidence map "exact"?** The classification head is linear, so each patch's contribution adds up
    exactly to the score (error about 1e-13). It isn't a heuristic saliency method like Grad-CAM.
16. **What does the fingerprint measure?** Acquisition: noise, scan banding, stripes, grey levels and
    compressibility. It's the strongest single model (0.70), and we're explicit that it reads imaging conditions,
    not chemistry.
17. **Then why trust it?** We don't trust it alone. An answer needs the imaging side **and** the material side to
    agree. Disagreement becomes "unsure" or "Batch 1 or Batch 2".

### Decisions, uncertainty and statistics
18. **How do you decide when to say "unsure"?** Both sides must pick the same batch. If they split between Batch 1
    and 2, we say "Batch 1 or Batch 2". Otherwise we say "unsure (leaning X)".
19. **What does "High confidence" mean?** Both sides agree and the calibrated probability is above the level where
    held-out answers were at least 90 % right. In testing, High was right 10 / 12.
20. **What is calibration?** Making "80 %" mean right about 80 % of the time, by temperature scaling on held-out
    predictions. The fingerprint was very over-confident (T = 3.85).
21. **How did you avoid overfitting with 31 samples?**
    - Leave-one-location-out, **nested**, so thresholds and calibration never see the test location.
    - Permutation tests.
    - Balanced accuracy.
    - A look ledger of every configuration tried.
    - Tiny linear models with shrinkage.
22. **What's your accuracy?** It answers 84 % of locations and is right 85 % of the time when it answers. Forced
    to always answer, it reaches 0.80 balanced accuracy, versus 0.33 for chance (p = 0.001).
23. **Isn't "right when answering" inflated?** Partly: it isn't balanced, and "Batch 1 or Batch 2" is an easier
    answer. That's why we also show specific answers (19 / 23), per-batch outcomes and the balanced forced mode.
24. **What is a permutation test?** Shuffle the batch labels and rerun the whole pipeline. If shuffled labels
    rarely score as well as the real ones (1 in 1,000 here), the signal is real.
25. **What is the session confound and how did you handle it?** The batches were partly imaged under different
    conditions: acquisition alone predicts batch at 0.68. We:
    - require material evidence to agree;
    - run within-session tests (porosity survives, p = 0.031);
    - run leave-one-session-out tests;
    - state it openly.
26. **Are Batch 1 and 2 actually different?** Yes, but subtly. Batch 2 is more porous (17.8 % vs 14.4 %), with more open
    and hidden sub-surface pores; Batch 1 has slightly more and larger SiOx. Their ranges overlap, which is why it is tricky:
    - 3 / 77 features differ (3.9 expected by chance);
    - a blinded odd-one-out test scored 27 % (chance 33 %).

    The honest output is "Batch 1 or Batch 2" when the evidence splits.
27. **Your answer for `3e122cbj` disagrees with the team's KPI classifier. Who is right?** Both of our independent
    sides say Batch 1, and its imaging session contains only Batch 1 references. The KPI classifier calls it
    Batch 2 with low confidence. We show both openly.

### Explainability and the LLM
28. **Why does the LLM only get text?**
    - It can't hallucinate from pixels.
    - Every number is traceable.
    - The maps are described numerically in words (`map_text`).
29. **How do you stop the LLM making things up?**
    - Strict rules.
    - A skeptic agent that removes unsupported claims and lists them.
    - A code check that every number in the report exists in `facts.json`.
30. **Why three agents and not one?** Separation of roles:
    - the analyst extracts the facts;
    - the expert adds domain meaning from a curated knowledge base;
    - the skeptic audits both.

    In our test, the skeptic removed the expert's unverifiable literature claims.
31. **Which model, and what does it cost?** Claude Sonnet at medium effort, a few cents per report. Opus was used
    only for the one-off labelling.

### Engineering and the demo
32. **How long does a prediction take?** About 65 s per location on a laptop GPU for the full pipeline.
    Segmentation alone takes 0.31 s.
33. **What if someone uploads a training image?** It's refused, because that would be a meaningless test. A crop
    or another detector's view of a known spot is recognised (0 false matches in testing) and returns that spot's
    batch.
34. **Can it run without a GPU?** Segmentation runs on CPU via ONNX in 1.5 s. The full pipeline is slower on CPU
    but works.
35. **How do you know the demo isn't just memorising?** Hold-out demo mode refits every model, calibration and
    threshold without the location being shown. All reported accuracies come from such held-out tests.

### Impact and next steps
36. **Why does this matter for battery manufacturing?** Traceability and quality control. It answers "which batch
    is this sample from, and how different are the batches?", and quantifies porosity and SiOx, which drive
    capacity, swelling and rate performance.
37. **What would you do with more time or data?**
    - Session and imaging metadata.
    - More locations per batch.
    - EDS on SiOx particles to test stoichiometry.
    - nnU-Net.
    - Testing on a blind set imaged in new sessions.
38. **What would change your conclusions?** A blind set from new sessions where the fingerprint fails, or evidence
    that Batch 1 and 2 differ by design. That's why our questions to the organisers are in the report (§10).
39. **What's the single biggest risk in your result?** That part of the batch signal is imaging session, not
    material. We designed the agreement rule and the uncertainty layer around exactly that risk.
40. **What are you most proud of?** Honesty under small data:
    - every number is held-out and nested;
    - the system says "unsure" when it should;
    - every explanation is traceable to a measurement.
