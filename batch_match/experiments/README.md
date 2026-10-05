# experiments

Exploratory research scripts behind the design of `../batch_classifier.py`. They are kept for
provenance and are not part of the production path: most are top-level scripts that compute and
print as they run, some depend on caches written by others (in `../out/classifier/`), and
`explore_deep.py` needs `onnx` / `onnxruntime` and a ResNet-50 ONNX model in `../out/models/`.
Each script adds `batch_match/` to `sys.path`, so it can be run from anywhere, e.g.
`python experiments/explore_compare.py` from `batch_match/`.

| Script | What it explores |
| --- | --- |
| `calibration_check.py` | Are get4's per-image error bars the right size? Cuts one image into crops and compares predicted vs observed scatter. |
| `explore_b12.py` | Which method best separates Batch_1 from Batch_2 (binary specialists, leave-one-location-out). |
| `explore_compare.py` | Every method under the same leave-one-location-out test, by view and by batch, plus an equal-weight ensemble. |
| `explore_confidence.py` | Whether "trust the most confident method" is a good way to combine methods (uses `explore_compare.py` output). |
| `explore_deep.py` | Pretrained ResNet-50 (ImageNet) features for every 224 x 224 tile as a generic texture representation. |
| `explore_deep_eval.py` | Leave-one-location-out accuracy of the ResNet-50 tile features. |
| `explore_descriptors.py` | Physically meaningful per-location descriptors from the segmented, pixel-registered views. |
| `explore_fingerprint.py` | Acquisition / sample-preparation fingerprint per image at full resolution (origin of the imaging fingerprint). |
| `explore_harmonized.py` | Material features measured after harmonising every image to the same imaging conditions. |
| `explore_harmonized_eval.py` | Leave-one-location-out evaluation of the harmonised material features. |
| `explore_ingenious.py` | Conformal prediction sets and per-lot decisions as ways to get more certainty from the same models. |
| `explore_lot.py` | Identifying the batch of a lot (k locations of one sample), strictly held out. |
| `explore_matcher.py` | Matching an image or crop, in any view, back to its known location (origin of the known-location matcher). |
| `explore_material2.py` | Production-step markers per location from all three registered, harmonised views. |
| `explore_material2_eval.py` | Screens the production-step markers and classifies locations with them. |
| `explore_nested.py` | Nested leave-one-location-out, so that choosing the feature set / model is part of what is tested. |
| `explore_noise_acf.py` | Noise autocorrelation fingerprint (detector / scan-speed impulse response). |
| `explore_ranges.py` | Batch_1 vs Batch_2 from material percentages, using only non-overlapping value ranges (origin of the range rule). |
| `explore_ranges_pipeline.py` | The range rule inside the full three-batch pipeline, leave-one-location-out. |
| `explore_texture.py` | The tile texture features (spectrum, edges, LBP, co-occurrence, phase fractions), recomputed for the comparison. |
| `explore_twostep_unsure.py` | The two-step model with an "unsure" option, nested leave-one-location-out. |
| `get4_verdict_version.py` | Variant of `../get4.py` whose lot comparison issues ACCEPT / INVESTIGATE / REJECT verdicts (`../get4.py` reports probabilities only). |
