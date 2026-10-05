## Answer
Batch_3, Medium confidence, final probability 0.9475 (90 % KPI model + 10 % v3 material model).

## What the image shows
- Composition (U-Net segmentation, 95 % sampling intervals from GET4): pore 14.8 % [12.9 to 16.7], carbon 80.7 % [78.2 to 83.2], SiOx 4.5 % [2.7 to 6.3]. The binder value is experimental (precision ~50 %).
- SiOx is roughly random (Clark-Evans 1.02, 72 particles). It is slightly enriched in the top third (6 %) versus the bottom third (4 %). The largest SiOx particle is 6.2 µm across.
- Pores are enriched in the bottom-centre (22 % vs 15 % overall). The largest pore is 74.7 µm², 31.9 × 10.4 µm, horizontal.
- The GET4 range check fits all three batches, so it gives no answer.

## Why this batch
- **KPI model (Guanyi, diagonal LDA, 90 % weight):** it used one KPI, ETD-dark solid (area dark in ETD but solid in BSE: sub-surface pores, shadowed edges or binder). The image value is 5.7 %. Batch means are 2.5 % (Batch_1), 3.0 % (Batch_2) and 4.6 % (Batch_3). The KPI probability for Batch_3 is 0.9656.
- Two other KPIs also lean Batch_3: BSE minus ETD porosity (-5.293 pp vs means -1.845 / -2.134 / -3.972) and bright phase lit in InLens (14.8 % vs 71.2 / 79.1 / 40.8). Pore–solid interface density (0.439) is closest to Batch_2, so the KPIs do not all agree.
- The three nearest reference locations are all Batch_3 (distances 0.03, 0.07, 0.43).
- **KPI model's own reference validation (KPI model alone):** leave-one-out balanced accuracy 0.683 against chance 0.333, permutation p = 0.005.
- **v3 material model (10 % weight):** it agrees, picking Batch_3 (calibrated 0.785, fused 0.645). The DINOv2 head gives 0.948 for Batch_3, with its evidence concentrated on SiOx (2.2× its share of the image). The segmentation S-head favours Batch_1 (0.434 vs 0.342 for Batch_3), so material-side support is mixed.

## Caveats
- Batch_1 and Batch_2 are statistically indistinguishable in this dataset; any call between them is low-certainty.
- The image height (1612 px) matches Batch_3 references, and the nearest training acquisition is also Batch_3. Acquisition properties alone give 0.68 balanced accuracy, so the match may partly reflect imaging session rather than material. No model uses this hint.
- ETD-dark solid is a proxy, not a porosity value. Its interpretation (sub-surface voids, contacts or binder) is unverified.
- The location is new (best edge-map match 11 SD; a match needs 15).
- Track-record statistics for the combined method have not been recomputed.

## Verification notes
- Removed expert claims about the "illustrative 25–40 % porosity example", swelling room, electrolyte access, EIS/FIB-SEM, pulverisation and the D1/D2/C1/C3/A1/A2 references. None of these appear in facts.json.
- Removed the expert's statement that ETD shadowing exaggerates dark area, as an unsupported mechanism. It is kept only as the facts.json description of the KPI.
- Removed the analyst's validation figures (LOO_F 0.608, LOGO_F 0.56). They are valid in facts.json but describe the material model's own validation and were omitted for brevity.
- All other numbers were checked against facts.json.